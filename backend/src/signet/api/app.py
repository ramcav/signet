"""FastAPI composition root."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

import yaml
from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
for _candidate in (_BACKEND_ROOT / ".env", _BACKEND_ROOT.parent / ".env", _BACKEND_ROOT.parent.parent / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate)
        break
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..adapters.agent import OpenAIAgentAdapter
from ..adapters.prices import price_table
from ..adapters.xrpl_adapter import XRPLAdapter, load_wallets
from ..application import (
    ApproveEscalationUseCase,
    EscalationRegistry,
    Event,
    EventBus,
    SubmitIntentUseCase,
)
from ..domain import PolicyConfig, PolicyEngine
from ..domain.policy import InMemoryKYT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("signet").setLevel(logging.INFO)
log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "policy.yaml"


class IntentRequest(BaseModel):
    user_message: str
    attempt_single_sig_on_refuse: bool = True


def build_app() -> FastAPI:
    app = FastAPI(title="Signet demo")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── wiring ──────────────────────────────────────────────────────────────
    cfg_dict = yaml.safe_load(CONFIG_PATH.read_text())
    prices = price_table()
    cfg_dict["xrp_usd_price"] = prices["XRP"]
    log.info("live XRP/USD price: $%.4f", prices["XRP"])

    policy_config = PolicyConfig.from_dict(cfg_dict)

    wallets = load_wallets()
    # Add treasury address (which is the agent's wallet in this demo setup —
    # in prod, a separate treasury. Use agent's address as "allowed destination".
    policy_config = PolicyConfig(
        allowlist_destinations=frozenset({wallets.agent.classic_address}),
        allowlist_assets=policy_config.allowlist_assets,
        per_tx_cap_usd=policy_config.per_tx_cap_usd,
        daily_cap_usd=policy_config.daily_cap_usd,
        escalation_tier_threshold_usd=policy_config.escalation_tier_threshold_usd,
        price_table=policy_config.price_table,
    )

    engine = PolicyEngine(config=policy_config, kyt=InMemoryKYT())
    xrpl = XRPLAdapter(wallets=wallets)
    agent = OpenAIAgentAdapter(
        master_address=wallets.master.classic_address,
        treasury_address=wallets.agent.classic_address,
        rlusd_issuer_address=wallets.agent.classic_address,
    )
    bus = EventBus()
    escalations = EscalationRegistry()

    submit_uc = SubmitIntentUseCase(
        agent=agent, policy=engine, xrpl=xrpl, bus=bus, escalations=escalations
    )
    approve_uc = ApproveEscalationUseCase(
        policy=engine, xrpl=xrpl, bus=bus, escalations=escalations
    )

    # ── routes ──────────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        master_balance = xrpl.get_balance_xrp(wallets.master.classic_address)
        return {
            "ok": True,
            "master": wallets.master.classic_address,
            "agent": wallets.agent.classic_address,
            "policy": wallets.policy.classic_address,
            "allowlist": list(policy_config.allowlist_destinations),
            "xrp_usd": policy_config.price_table["XRP"],
            "master_balance_xrp": master_balance,
        }

    @app.post("/intents", status_code=202)
    async def submit_intent(req: IntentRequest):
        """Kick off a run. Returns run_id immediately; progress streams via /events."""
        run_id = uuid4().hex[:12]
        log.info("POST /intents accepted run_id=%s", run_id)

        async def _run():
            try:
                await submit_uc.run(
                    req.user_message,
                    attempt_single_sig_on_refuse=req.attempt_single_sig_on_refuse,
                    run_id=run_id,
                )
            except Exception as exc:
                log.exception("run[%s] failed", run_id)
                await bus.publish(
                    Event(type="run.error", run_id=run_id, data={"message": str(exc)[:200]})
                )

        asyncio.create_task(_run())
        return {"run_id": run_id, "status": "accepted"}

    @app.post("/escalations/{esc_id}/approve")
    async def approve(esc_id: str):
        try:
            result = await approve_uc.approve(esc_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown escalation")
        return {
            "run_id": result.run_id,
            "decision": result.decision.value,
            "tx": {
                "tx_hash": result.tx.tx_hash,
                "explorer_url": result.tx.explorer_url,
                "engine_result": result.tx.engine_result,
                "validated": result.tx.validated,
                "memo_hex": result.tx.memo_hex,
            }
            if result.tx
            else None,
        }

    @app.post("/escalations/{esc_id}/reject")
    async def reject(esc_id: str):
        try:
            result = await approve_uc.reject(esc_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown escalation")
        return {"run_id": result.run_id, "decision": result.decision.value}

    @app.get("/events")
    async def events():
        async def gen():
            async for event in bus.stream():
                yield {"event": event.type, "data": event.to_json()}

        return EventSourceResponse(gen())

    return app


app = build_app()
