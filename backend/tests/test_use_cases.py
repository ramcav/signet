import asyncio
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from signet.adapters.agent import AgentResult
from signet.adapters.audit_store import AuditStore
from signet.application.events import EventBus
from signet.application.use_cases import ApproveEscalationUseCase, EscalationRegistry, SubmitIntentUseCase
from signet.domain import Decision, Intent, IntentAction, PolicyConfig, PolicyEngine, ReasoningTrace
from signet.domain.policy import InMemoryKYT


class FakeQuotes:
    def assert_fresh(self, quote):
        pass

    def get_quote(self):
        return SimpleNamespace(price_usd=0.5, to_dict=lambda: {
            "price_usd": 0.5, "source": "test", "as_of": datetime.now(timezone.utc).isoformat(), "demo": True,
        })


class FakeAgent:
    amount = 500
    destination = "rTreasury"

    def propose(self, message):
        intent = Intent(IntentAction.PAYMENT, "rMaster", self.destination, self.amount, "XRP", message)
        return AgentResult(intent, ReasoningTrace().append("test evidence"), {})


class FakeLedger:
    calls = 0
    outcome = "success"
    raises = False

    def multisign_and_submit(self, intent, root, *, before_sign=None):
        self.calls += 1
        if before_sign:
            before_sign()
        if self.raises:
            raise TimeoutError("unknown submission state")
        return SimpleNamespace(outcome=self.outcome, validated=self.outcome == "success",
            engine_result="tesSUCCESS" if self.outcome == "success" else "timeout",
            tx_hash="hash", explorer_url="", memo_hex=root)


@pytest.fixture
def services(tmp_path, monkeypatch):
    monkeypatch.setattr("signet.application.use_cases.RULE_STREAM_DELAY_S", 0)
    cfg = PolicyConfig(frozenset({"rTreasury"}), frozenset({"XRP"}), 25000, 100000, 1000, {"XRP": 0.5})
    common = dict(policy=PolicyEngine(cfg, InMemoryKYT()), xrpl=FakeLedger(), bus=EventBus(),
                  escalations=EscalationRegistry(), store=AuditStore(tmp_path / "audit.sqlite3"), quotes=FakeQuotes())
    submit = SubmitIntentUseCase(agent=FakeAgent(), **common)
    approve = ApproveEscalationUseCase(**common)
    return submit, approve


@pytest.mark.asyncio
async def test_concurrent_runs_reserve_before_submission(services):
    submit, _ = services
    submit.store.reserve("rMaster", "previous", 99600, 100000)
    submit.store.resolve("previous", "success")
    results = await asyncio.gather(submit.run("one", False), submit.run("two", False))
    assert sorted(result.decision.value for result in results) == ["allow", "refuse"]
    assert submit.xrpl.calls == 1
    assert submit.store.used("rMaster") == 99850


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,used,event", [("success", 250, "ledger.settled"), ("failed", 0, "ledger.failed"), ("unknown", 250, "ledger.unknown")])
async def test_submission_outcome_accounting_and_events(services, outcome, used, event):
    submit, _ = services
    submit.xrpl.outcome = outcome
    result = await submit.run("payment", False)
    assert submit.store.used("rMaster") == used
    assert event in [ev.type for ev in submit.bus._history]
    assert submit.bus._history[-1].type == "run.completed"
    assert submit.store.get_receipt(result.run_id)["root"] == result.tx.memo_hex


@pytest.mark.asyncio
async def test_submission_exception_preserves_reservation(services):
    submit, _ = services
    submit.xrpl.raises = True
    with pytest.raises(TimeoutError):
        await submit.run("payment", False)
    assert submit.store.used("rMaster") == 250


@pytest.mark.asyncio
async def test_escalation_is_single_use_and_receipt_binds_approval(services):
    submit, approve = services
    submit.agent.amount = 5000
    pending = await submit.run("large payment", False)
    assert pending.decision == Decision.ESCALATE
    result = await approve.approve(pending.escalation_id)
    with pytest.raises(KeyError):
        await approve.approve(pending.escalation_id)
    assert submit.xrpl.calls == 1
    receipt = submit.store.get_receipt(result.run_id)
    assert receipt["payload"]["approval"]["kind"] == "local_operator"


@pytest.mark.asyncio
async def test_approval_refresh_failure_keeps_pending(services):
    submit, approve = services
    submit.agent.amount = 5000
    pending = await submit.run("large payment", False)
    def unavailable():
        raise RuntimeError("quote unavailable")
    approve.quotes = SimpleNamespace(get_quote=unavailable)
    with pytest.raises(RuntimeError):
        await approve.approve(pending.escalation_id)
    assert pending.escalation_id in approve.escalations.pending
    assert submit.xrpl.calls == 0


@pytest.mark.asyncio
async def test_rejection_exports_final_decision_without_price_fetch(services):
    submit, approve = services
    submit.agent.amount = 5000
    pending = await submit.run("large payment", False)
    def unavailable():
        raise AssertionError("rejection must not need a price")
    approve.quotes = SimpleNamespace(get_quote=unavailable)
    result = await approve.reject(pending.escalation_id, "not today")
    receipt = submit.store.get_receipt(result.run_id)
    assert receipt["payload"]["evaluation"]["decision"] == "refuse"
    assert receipt["payload"]["approval"]["action"] == "reject"
    assert receipt["payload"]["approval"]["reason"] == "not today"
    assert submit.xrpl.calls == 0


@pytest.mark.asyncio
async def test_cancellation_preserves_unknown_run_and_reservation(services):
    submit, _ = services
    entered, release = threading.Event(), threading.Event()
    original = submit.xrpl.multisign_and_submit
    def blocked(*args, **kwargs):
        entered.set()
        release.wait(timeout=5)
        return original(*args, **kwargs)
    submit.xrpl.multisign_and_submit = blocked
    submit.store.accept_run("cancelled_run", {"user_message": "send"})
    task = asyncio.create_task(submit.run("send", False, "cancelled_run"))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert submit.store.get_run("cancelled_run")["status"] == "unknown"
        assert submit.store.get_reservation("cancelled_run")["status"] == "unknown"
    finally:
        release.set()


@pytest.mark.asyncio
async def test_unknown_destination_is_recorded_as_refusal(services):
    submit, _ = services
    submit.agent.destination = "unknown_vault"
    result = await submit.run("send to unknown alias", False)
    assert result.decision == Decision.REFUSE
    assert submit.xrpl.calls == 0
    receipt = submit.store.get_receipt(result.run_id)
    assert receipt["payload"]["evaluation"]["decision"] == "refuse"
    assert receipt["payload"]["intent"]["to_account"] == "unknown_vault"
    assert "policy.refused" in [event.type for event in submit.bus._history]
