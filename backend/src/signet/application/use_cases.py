"""Use cases: orchestrate agent → policy → XRPL and stream events."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from ..adapters.agent import AgentResult, OpenAIAgentAdapter
from ..adapters.xrpl_adapter import TxResult, XRPLAdapter
from ..domain import Decision, EvaluationResult, Intent, PolicyEngine
from .events import Event, EventBus

log = logging.getLogger(__name__)

RULE_STREAM_DELAY_S = 0.25


@dataclass
class ScenarioResult:
    run_id: str
    decision: Decision
    intent: Optional[Intent]
    evaluation: Optional[EvaluationResult]
    tx: Optional[TxResult] = None
    escalation_id: Optional[str] = None
    raw_agent_output: str = ""


@dataclass
class _PendingEscalation:
    run_id: str
    intent: Intent
    merkle_root: str
    evaluation: EvaluationResult


@dataclass
class EscalationRegistry:
    pending: dict[str, _PendingEscalation] = field(default_factory=dict)

    def put(self, esc_id: str, pending: _PendingEscalation) -> None:
        self.pending[esc_id] = pending

    def pop(self, esc_id: str) -> _PendingEscalation:
        return self.pending.pop(esc_id)


@dataclass
class SubmitIntentUseCase:
    agent: OpenAIAgentAdapter
    policy: PolicyEngine
    xrpl: XRPLAdapter
    bus: EventBus
    escalations: EscalationRegistry

    async def run(
        self,
        user_message: str,
        attempt_single_sig_on_refuse: bool = True,
        run_id: Optional[str] = None,
    ) -> ScenarioResult:
        run_id = run_id or uuid4().hex[:12]
        log.info("run[%s] starting: %r", run_id, user_message[:80])
        await self._emit(run_id, "run.started", {"user_message": user_message})

        # 1. agent
        await self._emit(run_id, "agent.thinking", {})
        agent_result = await asyncio.to_thread(self.agent.propose, user_message)
        await self._emit(
            run_id,
            "agent.intent",
            {
                "intent": _intent_dict(agent_result.intent),
                "raw_tool_args": agent_result.raw_tool_args,
            },
        )

        # 2. policy rules, streamed one by one
        evaluation = self.policy.evaluate(agent_result.intent)
        for check in evaluation.checks:
            await self._emit(
                run_id,
                "rule.check",
                {
                    "name": check.name,
                    "status": check.status.value,
                    "detail": check.detail,
                    "passed": check.passed,
                },
            )
            await asyncio.sleep(RULE_STREAM_DELAY_S)

        merkle_root = agent_result.trace.commit().root
        await self._emit(
            run_id,
            "reasoning.commit",
            {"merkle_root": merkle_root, "step_count": len(agent_result.trace.steps)},
        )

        if evaluation.decision == Decision.REFUSE:
            await self._emit(
                run_id,
                "policy.refused",
                {"reason": evaluation.reason, "failed": [c.name for c in evaluation.failed_checks]},
            )
            if attempt_single_sig_on_refuse:
                await self._emit(run_id, "ledger.single_sig_attempt", {})
                tx = await asyncio.to_thread(
                    self.xrpl.attempt_single_sig_submit, agent_result.intent, merkle_root
                )
                await self._emit(run_id, "ledger.single_sig_result", _tx_dict(tx))
                return ScenarioResult(
                    run_id=run_id,
                    decision=Decision.REFUSE,
                    intent=agent_result.intent,
                    evaluation=evaluation,
                    tx=tx,
                    raw_agent_output=agent_result.intent.raw_agent_output or "",
                )
            return ScenarioResult(
                run_id=run_id,
                decision=Decision.REFUSE,
                intent=agent_result.intent,
                evaluation=evaluation,
                raw_agent_output=agent_result.intent.raw_agent_output or "",
            )

        if evaluation.decision == Decision.ESCALATE:
            esc_id = uuid4().hex[:12]
            self.escalations.put(
                esc_id,
                _PendingEscalation(
                    run_id=run_id,
                    intent=agent_result.intent,
                    merkle_root=merkle_root,
                    evaluation=evaluation,
                ),
            )
            await self._emit(
                run_id,
                "policy.escalated",
                {
                    "escalation_id": esc_id,
                    "reason": evaluation.reason,
                    "intent": _intent_dict(agent_result.intent),
                    "notional_usd": evaluation.notional_usd,
                },
            )
            return ScenarioResult(
                run_id=run_id,
                decision=Decision.ESCALATE,
                intent=agent_result.intent,
                evaluation=evaluation,
                escalation_id=esc_id,
                raw_agent_output=agent_result.intent.raw_agent_output or "",
            )

        # ALLOW
        await self._emit(run_id, "signature.agent", {"by": "key_a"})
        await asyncio.sleep(RULE_STREAM_DELAY_S)
        await self._emit(run_id, "signature.policy", {"by": "key_b"})
        await self._emit(run_id, "ledger.submitting", {})
        tx = await asyncio.to_thread(
            self.xrpl.multisign_and_submit, agent_result.intent, merkle_root
        )
        if tx.validated:
            self.policy.record_spend(evaluation.notional_usd)
        await self._emit(run_id, "ledger.settled", _tx_dict(tx))
        return ScenarioResult(
            run_id=run_id,
            decision=Decision.ALLOW,
            intent=agent_result.intent,
            evaluation=evaluation,
            tx=tx,
            raw_agent_output=agent_result.intent.raw_agent_output or "",
        )

    async def _emit(self, run_id: str, typ: str, data: dict) -> None:
        log.info("event[%s] %s", run_id, typ)
        await self.bus.publish(Event(type=typ, run_id=run_id, data=data))


@dataclass
class ApproveEscalationUseCase:
    policy: PolicyEngine
    xrpl: XRPLAdapter
    bus: EventBus
    escalations: EscalationRegistry

    async def approve(self, escalation_id: str) -> ScenarioResult:
        pending = self.escalations.pop(escalation_id)
        run_id = pending.run_id

        await self._emit(run_id, "escalation.approved", {"escalation_id": escalation_id})
        await self._emit(run_id, "signature.agent", {"by": "key_a"})
        await asyncio.sleep(RULE_STREAM_DELAY_S)
        await self._emit(run_id, "signature.policy", {"by": "key_b"})
        await self._emit(run_id, "ledger.submitting", {})

        tx = await asyncio.to_thread(
            self.xrpl.multisign_and_submit, pending.intent, pending.merkle_root
        )
        if tx.validated:
            self.policy.record_spend(pending.evaluation.notional_usd)
        await self._emit(run_id, "ledger.settled", _tx_dict(tx))

        return ScenarioResult(
            run_id=run_id,
            decision=Decision.ALLOW,
            intent=pending.intent,
            evaluation=pending.evaluation,
            tx=tx,
            escalation_id=escalation_id,
        )

    async def reject(self, escalation_id: str, reason: str = "operator rejected") -> ScenarioResult:
        pending = self.escalations.pop(escalation_id)
        await self._emit(
            pending.run_id,
            "escalation.rejected",
            {"escalation_id": escalation_id, "reason": reason},
        )
        return ScenarioResult(
            run_id=pending.run_id,
            decision=Decision.REFUSE,
            intent=pending.intent,
            evaluation=pending.evaluation,
            escalation_id=escalation_id,
        )

    async def _emit(self, run_id: str, typ: str, data: dict) -> None:
        await self.bus.publish(Event(type=typ, run_id=run_id, data=data))


def _intent_dict(intent: Intent) -> dict:
    return {
        "id": intent.id,
        "from": intent.from_account,
        "to": intent.to_account,
        "amount": intent.amount,
        "asset": intent.asset,
        "rationale": intent.rationale,
    }


def _tx_dict(tx: TxResult) -> dict:
    return {
        "tx_hash": tx.tx_hash,
        "explorer_url": tx.explorer_url,
        "memo_hex": tx.memo_hex,
        "engine_result": tx.engine_result,
        "validated": tx.validated,
    }
