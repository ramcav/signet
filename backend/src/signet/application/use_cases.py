"""Payment orchestration with durable reservations and explicit outcomes."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from uuid import uuid4

from ..adapters.agent import OpenAIAgentAdapter
from ..adapters.audit_store import AuditStore
from ..adapters.prices import PriceQuote, PriceService
from ..adapters.xrpl_adapter import TxResult, XRPLAdapter
from ..domain import Decision, EvaluationResult, Intent, PolicyConfig, PolicyEngine, ReasoningTrace, RuleCheck, RuleStatus
from ..domain.receipt import build_receipt
from .events import Event, EventBus

RULE_STREAM_DELAY_S = 0.05


@dataclass
class ScenarioResult:
    run_id: str
    decision: Decision
    intent: Intent | None
    evaluation: EvaluationResult | None
    tx: TxResult | None = None
    escalation_id: str | None = None
    raw_agent_output: str = ""


@dataclass
class _PendingEscalation:
    run_id: str
    intent: Intent
    trace: ReasoningTrace
    evaluation: EvaluationResult
    config: PolicyConfig
    quote: PriceQuote


class EscalationBusy(ValueError):
    pass


@dataclass
class EscalationRegistry:
    pending: dict[str, _PendingEscalation] = field(default_factory=dict)
    busy: set[str] = field(default_factory=set)

    def put(self, esc_id: str, pending: _PendingEscalation) -> None:
        self.pending[esc_id] = pending

    def claim(self, esc_id: str) -> _PendingEscalation:
        if esc_id in self.busy:
            raise EscalationBusy("escalation is already being resolved")
        pending = self.pending[esc_id]
        self.busy.add(esc_id)
        return pending

    def pop(self, esc_id: str) -> _PendingEscalation:
        return self.pending.pop(esc_id)


@dataclass
class _Workflow:
    policy: PolicyEngine
    xrpl: XRPLAdapter
    bus: EventBus
    escalations: EscalationRegistry
    store: AuditStore
    quotes: PriceService

    async def _emit(self, run_id: str, typ: str, data: dict) -> None:
        await self.bus.publish(Event(type=typ, run_id=run_id, data=data))

    async def _evaluate(self, intent: Intent):
        quote = await asyncio.to_thread(self.quotes.get_quote)
        config = replace(self.policy.config, price_table={"XRP": quote.price_usd})
        engine = PolicyEngine(config, self.policy.kyt, float(self.store.used(intent.from_account)))
        return engine.evaluate(intent), config, quote

    async def _commit(self, run_id, intent, evaluation, config, quote, trace, approval=None):
        receipt = build_receipt(intent, evaluation, config, quote.to_dict(), trace, approval)
        self.store.save_receipt(run_id, receipt.to_dict())
        await self._emit(run_id, "reasoning.commit", {
            "merkle_root": receipt.root, "step_count": len(trace.steps),
            "receipt_url": f"/runs/{run_id}/receipt",
        })
        return receipt.root

    async def _complete(self, result: ScenarioResult) -> ScenarioResult:
        status = result.tx.outcome if result.tx else result.decision.value
        self.store.finish_run(result.run_id, status)
        await self._emit(result.run_id, "run.completed", {"decision": result.decision.value, "outcome": status})
        return result

    async def _pay(self, run_id, intent, evaluation, config, quote, trace, *, approval=None, override=False):
        if not self.store.reserve(intent.from_account, run_id, evaluation.notional_usd,
                                  self.policy.config.daily_cap_usd, override=override):
            check = RuleCheck("daily_cap", RuleStatus.FAIL, "daily budget was reserved by another payment")
            refused = replace(evaluation, decision=Decision.REFUSE,
                              checks=evaluation.checks + (check,), reason=check.detail)
            await self._commit(run_id, intent, refused, config, quote, trace, approval)
            await self._emit(run_id, "rule.check", {"name": check.name, "status": "fail", "detail": check.detail, "passed": False})
            await self._emit(run_id, "policy.refused", {"reason": check.detail, "failed": [check.name]})
            return ScenarioResult(run_id, Decision.REFUSE, intent, refused)
        submission_started = False
        try:
            root = await self._commit(run_id, intent, evaluation, config, quote, trace, approval)
            await self._emit(run_id, "ledger.submitting", {})
            submission_started = True
            tx = await asyncio.to_thread(self.xrpl.multisign_and_submit, intent, root,
                                         before_sign=lambda: self.quotes.assert_fresh(quote))
        except BaseException:
            # Includes cancellation: the worker thread may still submit.
            self.store.resolve(run_id, "unknown" if submission_started else "failed")
            self.store.finish_run(run_id, "unknown" if submission_started else "error")
            raise
        self.store.save_transaction(run_id, _tx_dict(tx))
        self.store.resolve(run_id, tx.outcome)
        if tx.outcome == "success":
            await self._emit(run_id, "signature.agent", {"by": "key_a"})
            await self._emit(run_id, "signature.policy", {"by": "key_b"})
        event = {"success": "ledger.settled", "unknown": "ledger.unknown"}.get(tx.outcome, "ledger.failed")
        await self._emit(run_id, event, _tx_dict(tx))
        return ScenarioResult(run_id, Decision.ALLOW, intent, evaluation, tx=tx)


@dataclass
class SubmitIntentUseCase(_Workflow):
    agent: OpenAIAgentAdapter

    async def run(self, user_message: str, attempt_single_sig_on_refuse: bool = True,
                  run_id: str | None = None) -> ScenarioResult:
        run_id = run_id or uuid4().hex
        await self._emit(run_id, "run.started", {"user_message": user_message})
        await self._emit(run_id, "agent.thinking", {})
        proposed = await asyncio.to_thread(self.agent.propose, user_message)
        intent = proposed.intent
        await self._emit(run_id, "agent.intent", {"intent": _intent_dict(intent), "raw_tool_args": proposed.raw_tool_args})
        evaluation, config, quote = await self._evaluate(intent)
        for check in evaluation.checks:
            await self._emit(run_id, "rule.check", {
                "name": check.name, "status": check.status.value,
                "detail": check.detail, "passed": check.passed,
            })
            await asyncio.sleep(RULE_STREAM_DELAY_S)
        if evaluation.decision == Decision.REFUSE:
            root = await self._commit(run_id, intent, evaluation, config, quote, proposed.trace)
            await self._emit(run_id, "policy.refused", {"reason": evaluation.reason, "failed": [c.name for c in evaluation.failed_checks]})
            tx = None
            if attempt_single_sig_on_refuse:
                await self._emit(run_id, "ledger.single_sig_attempt", {})
                tx = await asyncio.to_thread(self.xrpl.attempt_single_sig_submit, intent, root)
                self.store.save_transaction(run_id, _tx_dict(tx))
                await self._emit(run_id, "ledger.single_sig_result", _tx_dict(tx))
            return await self._complete(ScenarioResult(run_id, Decision.REFUSE, intent, evaluation, tx=tx))

        if evaluation.decision == Decision.ESCALATE:
            await self._commit(run_id, intent, evaluation, config, quote, proposed.trace)
            esc_id = uuid4().hex
            self.escalations.put(esc_id, _PendingEscalation(run_id, intent, proposed.trace, evaluation, config, quote))
            await self._emit(run_id, "policy.escalated", {
                "escalation_id": esc_id, "reason": evaluation.reason,
                "intent": _intent_dict(intent), "notional_usd": evaluation.notional_usd,
            })
            return await self._complete(ScenarioResult(run_id, Decision.ESCALATE, intent, evaluation, escalation_id=esc_id))

        return await self._complete(await self._pay(run_id, intent, evaluation, config, quote, proposed.trace))


@dataclass
class ApproveEscalationUseCase(_Workflow):
    async def approve(self, escalation_id: str) -> ScenarioResult:
        pending = self.escalations.claim(escalation_id)
        try:
            # Refresh valuation/integrity checks; outages leave approval pending.
            evaluation, config, quote = await self._evaluate(pending.intent)
            if evaluation.decision == Decision.REFUSE:
                await self._commit(pending.run_id, pending.intent, evaluation, config, quote, pending.trace)
                await self._emit(pending.run_id, "policy.refused", {
                    "reason": evaluation.reason, "failed": [c.name for c in evaluation.failed_checks],
                })
                self.escalations.pop(escalation_id)
                await self._emit(pending.run_id, "escalation.rejected", {"escalation_id": escalation_id, "reason": evaluation.reason})
                return await self._complete(ScenarioResult(pending.run_id, Decision.REFUSE, pending.intent, evaluation, escalation_id=escalation_id))
            approval = {"kind": "local_operator", "action": "approve", "escalation_id": escalation_id,
                        "approved_at": datetime.now(timezone.utc).isoformat()}
            # Consume before any submission; a lost HTTP response must not permit a duplicate.
            self.escalations.pop(escalation_id)
            await self._emit(pending.run_id, "escalation.approved", {"escalation_id": escalation_id})
            result = await self._pay(pending.run_id, pending.intent, evaluation, config, quote,
                                     pending.trace, approval=approval, override=True)
            result.escalation_id = escalation_id
            return await self._complete(result)
        finally:
            self.escalations.busy.discard(escalation_id)

    async def reject(self, escalation_id: str, reason: str = "operator rejected") -> ScenarioResult:
        pending = self.escalations.claim(escalation_id)
        try:
            evaluation = replace(pending.evaluation, decision=Decision.REFUSE, reason=reason)
            approval = {"kind": "local_operator", "action": "reject", "reason": reason,
                        "escalation_id": escalation_id, "rejected_at": datetime.now(timezone.utc).isoformat()}
            await self._commit(pending.run_id, pending.intent, evaluation, pending.config,
                               pending.quote, pending.trace, approval)
            self.escalations.pop(escalation_id)
            await self._emit(pending.run_id, "escalation.rejected", {"escalation_id": escalation_id, "reason": reason})
            return await self._complete(ScenarioResult(pending.run_id, Decision.REFUSE, pending.intent, evaluation, escalation_id=escalation_id))
        finally:
            self.escalations.busy.discard(escalation_id)


def _intent_dict(intent: Intent) -> dict:
    return {"id": intent.id, "from": intent.from_account, "to": intent.to_account,
            "amount": float(intent.amount), "asset": intent.asset, "rationale": intent.rationale}


def _tx_dict(tx: TxResult) -> dict:
    return {"tx_hash": tx.tx_hash, "explorer_url": tx.explorer_url, "memo_hex": tx.memo_hex,
            "engine_result": tx.engine_result, "validated": tx.validated, "outcome": tx.outcome}
