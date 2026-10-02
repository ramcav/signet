"""Dependency-injected FastAPI composition root for the local testnet demo."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable
from uuid import uuid4

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..adapters.agent import AGENT_CONFIGURATION_MESSAGE, OpenAIAgentAdapter
from ..adapters.audit_store import AuditStore
from ..adapters.prices import PriceService, PriceUnavailable
from ..adapters.xrpl_adapter import WalletProtectionError, XRPLAdapter, load_wallets
from ..application import ApproveEscalationUseCase, EscalationRegistry, Event, EventBus, SubmitIntentUseCase
from ..application.use_cases import EscalationBusy, _tx_dict
from ..domain import PolicyConfig, PolicyEngine
from ..domain.policy import InMemoryKYT

log = logging.getLogger(__name__)
BACKEND_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = BACKEND_ROOT / "config" / "policy.yaml"


@dataclass
class Services:
    submit: SubmitIntentUseCase
    approve: ApproveEscalationUseCase
    bus: EventBus
    store: AuditStore
    health: Callable[[], dict]
    configuration_error: Callable[[], str | None] = lambda: None


class IntentRequest(BaseModel):
    user_message: str = Field(min_length=1, max_length=8000)
    attempt_single_sig_on_refuse: bool = False
    run_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")


def compose_services() -> Services:
    for candidate in (BACKEND_ROOT / ".env", BACKEND_ROOT.parent / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            break
    config = PolicyConfig.from_dict(yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")))
    wallets = load_wallets(include_master_seed=False)
    config = replace(config, allowlist_destinations=frozenset({wallets.agent.classic_address}))
    xrpl = XRPLAdapter(wallets)
    # Read-only startup audit. Account changes require the explicit setup script.
    try:
        xrpl.assert_protected()
    except WalletProtectionError as exc:
        raise WalletProtectionError(
            f"Treasury protection audit failed: {exc}. "
            "To configure or resume the saved testnet wallets, run "
            "`uv run python ../scripts/fund_wallets.py --secure-existing` from backend/, "
            "then restart the server. Keep the existing wallets.json and its saved keys."
        ) from exc
    demo_price = os.environ.get("SIGNET_DEMO_XRP_USD")
    quotes = PriceService(demo_price=float(demo_price) if demo_price is not None else None)
    engine = PolicyEngine(config, InMemoryKYT())
    agent = OpenAIAgentAdapter(wallets.master.classic_address, wallets.agent.classic_address, wallets.agent.classic_address)
    store = AuditStore(os.environ.get("SIGNET_STATE_DB", str(BACKEND_ROOT / "data" / "signet.sqlite3")))
    bus, escalations = EventBus(), EscalationRegistry()
    common = dict(policy=engine, xrpl=xrpl, bus=bus, escalations=escalations, store=store, quotes=quotes)
    submit = SubmitIntentUseCase(agent=agent, **common)
    approve = ApproveEscalationUseCase(**common)

    def configuration_error():
        return None if agent.is_configured else AGENT_CONFIGURATION_MESSAGE

    def health():
        result = {"ok": True, "master": wallets.master.classic_address,
                  "agent": wallets.agent.classic_address, "policy": wallets.policy.classic_address,
                  "allowlist": sorted(config.allowlist_destinations), "wallet_protected": True,
                  "master_balance_xrp": xrpl.get_balance_xrp(wallets.master.classic_address),
                  "xrp_usd": None, "quote": None,
                  "agent_configured": agent.is_configured,
                  "configuration_error": configuration_error()}
        try:
            quote = quotes.get_quote()
            result.update(xrp_usd=quote.price_usd, quote=quote.to_dict())
        except PriceUnavailable as exc:
            result["quote_error"] = str(exc)
        return result

    return Services(submit, approve, bus, store, health, configuration_error)


def build_app(services: Services | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.services = services or await asyncio.to_thread(compose_services)
        app.state.services.store.recover_interrupted_runs()
        yield
        tasks = list(app.state.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if services is None:
            app.state.services.store.close()

    app = FastAPI(title="Signet demo", lifespan=lifespan)
    app.state.tasks = set()
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Last-Event-ID"])

    def current() -> Services:
        return app.state.services

    async def run_error(run_id: str, exc: BaseException) -> None:
        svc = current()
        reservation = svc.store.get_reservation(run_id)
        unknown = bool(reservation and reservation["status"] in {"reserved", "unknown"})
        svc.store.finish_run(run_id, "unknown" if unknown else "error")
        log.error("run[%s] failed: %s", run_id, type(exc).__name__)
        message = ("The payment outcome is unknown. Check the ledger before submitting again."
                   if unknown else "The run failed before a confirmed payment. Check the service configuration and try again.")
        await svc.bus.publish(Event(type="run.error", run_id=run_id,
                                    data={"message": message, "outcome_unknown": unknown}))

    @app.get("/health")
    def health():
        return current().health()

    @app.post("/intents", status_code=202)
    async def submit_intent(req: IntentRequest):
        svc = current()
        if error := svc.configuration_error():
            raise HTTPException(status_code=503, detail=error)
        run_id = req.run_id or uuid4().hex
        try:
            accepted = svc.store.accept_run(run_id, req.model_dump(exclude={"run_id"}))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if accepted:
            async def execute():
                try:
                    await svc.submit.run(req.user_message, attempt_single_sig_on_refuse=req.attempt_single_sig_on_refuse, run_id=run_id)
                except asyncio.CancelledError as exc:
                    await run_error(run_id, exc)
                    raise
                except Exception as exc:
                    await run_error(run_id, exc)
            task = asyncio.create_task(execute())
            app.state.tasks.add(task)
            task.add_done_callback(app.state.tasks.discard)
        return {"run_id": run_id, "status": "accepted"}

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str):
        run = current().store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run")
        run["receipt"] = current().store.get_receipt(run_id)
        registry = getattr(current().approve, "escalations", None)
        run["escalation_id"] = next((key for key, pending in registry.pending.items()
                                     if pending.run_id == run_id), None) if registry else None
        return run

    @app.get("/runs/{run_id}/receipt")
    def receipt(run_id: str):
        document = current().store.get_receipt(run_id)
        if document is None:
            raise HTTPException(status_code=404, detail="receipt not available")
        # Never interpolate the request path into a response header.
        return JSONResponse(document, headers={"Content-Disposition": 'attachment; filename="signet-receipt.json"'})

    @app.post("/escalations/{esc_id}/approve")
    async def approve(esc_id: str):
        svc = current()
        pending = getattr(svc.approve, "escalations", None)
        run_id = pending.pending[esc_id].run_id if pending and esc_id in pending.pending else None
        try:
            result = await svc.approve.approve(esc_id)
        except asyncio.CancelledError as exc:
            if run_id and esc_id not in svc.approve.escalations.pending:
                await run_error(run_id, exc)
            raise
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown or already resolved escalation") from exc
        except EscalationBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PriceUnavailable as exc:
            raise HTTPException(status_code=503, detail="A fresh price is unavailable; approval remains pending.") from exc
        except Exception as exc:
            if run_id and esc_id not in svc.approve.escalations.pending:
                await run_error(run_id, exc)
            raise HTTPException(status_code=502, detail="Approval could not complete. Check the run status before retrying.") from exc
        return {"run_id": result.run_id, "decision": result.decision.value,
                "tx": _tx_dict(result.tx) if result.tx else None}

    @app.post("/escalations/{esc_id}/reject")
    async def reject(esc_id: str):
        try:
            result = await current().approve.reject(esc_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown or already resolved escalation") from exc
        except EscalationBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"run_id": result.run_id, "decision": result.decision.value}

    @app.get("/events")
    async def events(request: Request, last_event_id: int | None = None):
        raw = request.headers.get("last-event-id")
        try:
            cursor = int(raw) if raw else last_event_id
            if cursor is not None and cursor < 0:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid Last-Event-ID") from exc

        async def gen():
            async for event in current().bus.stream(last_event_id=cursor):
                yield {"id": str(event.id), "event": event.type, "data": event.to_json()}
        return EventSourceResponse(gen())

    return app
