import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from signet.adapters.audit_store import AuditStore
from signet.api.app import Services, build_app
from signet.application.events import EventBus


def test_startup_wallet_audit_explains_how_to_migrate(monkeypatch):
    from signet.api import app as api_module
    from signet.adapters.xrpl_adapter import WalletProtectionError

    wallets = SimpleNamespace(agent=SimpleNamespace(classic_address="saved_agent"))
    monkeypatch.setattr(api_module, "load_dotenv", lambda _: None)
    monkeypatch.setattr(api_module, "load_wallets", lambda **_: wallets)

    class UnprotectedWallet:
        def __init__(self, _):
            pass

        def assert_protected(self):
            raise WalletProtectionError("Expected exactly one 2-of-2 signer list")

    monkeypatch.setattr(api_module, "XRPLAdapter", UnprotectedWallet)
    with pytest.raises(WalletProtectionError) as failure:
        api_module.compose_services()
    assert "uv run python ../scripts/fund_wallets.py --secure-existing" in str(failure.value)
    assert "from backend/" in str(failure.value)
    assert "Expected exactly one 2-of-2 signer list" in str(failure.value)


def test_missing_agent_key_allows_startup_but_rejects_runs_before_acceptance(monkeypatch, tmp_path):
    from signet.api import app as api_module

    wallets = SimpleNamespace(**{
        role: SimpleNamespace(classic_address=f"saved_{role}")
        for role in ("master", "agent", "policy")
    })
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SIGNET_DEMO_XRP_USD", "0.50")
    monkeypatch.setenv("SIGNET_STATE_DB", str(tmp_path / "startup.sqlite3"))
    monkeypatch.setattr(api_module, "load_dotenv", lambda _: None)
    monkeypatch.setattr(api_module, "load_wallets", lambda **_: wallets)
    monkeypatch.setattr(api_module, "XRPLAdapter", lambda _: SimpleNamespace(
        assert_protected=lambda: None, get_balance_xrp=lambda _: 100,
    ))
    with TestClient(build_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["agent_configured"] is False
        assert "OPENAI_API_KEY" in health.json()["configuration_error"]
        response = client.post("/intents", json={"run_id": "not_accepted", "user_message": "send"})
        assert response.status_code == 503
        assert "backend/.env" in response.json()["detail"]
        assert client.get("/runs/not_accepted").status_code == 404
        assert not client.app.state.tasks


def finish_background_tasks(client):
    async def finish():
        tasks = list(client.app.state.tasks)
        if tasks:
            await asyncio.gather(*tasks)
    client.portal.call(finish)


@pytest.fixture
def api(tmp_path):
    calls = []
    bus = EventBus()
    store = AuditStore(tmp_path / "audit.sqlite3")

    async def run(message, **kwargs):
        calls.append((message, kwargs))
        if message == "fail":
            raise RuntimeError("offline agent failure")

    async def missing(_):
        raise KeyError("not found")

    services = Services(SimpleNamespace(run=run), SimpleNamespace(approve=missing, reject=missing),
                        bus, store, lambda: {"ok": True})
    with TestClient(build_app(services)) as client:
        yield client, services, calls


def test_client_run_id_is_idempotent(api):
    client, _, calls = api
    body = {"run_id": "client_run_123", "user_message": "send"}
    assert client.post("/intents", json=body).status_code == 202
    assert client.post("/intents", json=body).status_code == 202
    response = client.post("/intents", json={**body, "user_message": "different"})
    assert response.status_code == 409
    finish_background_tasks(client)
    assert len(calls) == 1


def test_run_exception_emits_terminal_error(api):
    client, services, _ = api
    client.post("/intents", json={"run_id": "failing_run", "user_message": "fail"})
    finish_background_tasks(client)
    error = services.bus._history[-1]
    assert error.type == "run.error"
    assert error.run_id == "failing_run"
    assert error.data["outcome_unknown"] is False


def test_approval_and_rejection_unknown_id_are_errors(api):
    client, _, _ = api
    for action in ("approve", "reject"):
        assert client.post(f"/escalations/missing/{action}").status_code == 404


def test_receipt_download_is_persisted_document(api):
    client, services, _ = api
    receipt = {"root": "abc", "payload": {"intent": {"amount": "5"}}}
    services.store.save_receipt("receipt_run", receipt)
    response = client.get("/runs/receipt_run/receipt")
    assert response.status_code == 200
    assert response.json() == receipt
    assert "attachment" in response.headers["content-disposition"]
    assert client.get("/runs/missing/receipt").status_code == 404


def test_invalid_request_does_not_start_run(api):
    client, _, calls = api
    assert client.post("/intents", json={"user_message": ""}).status_code == 422
    assert client.post("/intents", json={"user_message": "send", "run_id": "../bad"}).status_code == 422
    assert calls == []


def test_run_snapshot_restores_receipt_and_pending_approval(api):
    client, services, _ = api
    services.store.accept_run("snapshot_run", {"user_message": "send"})
    services.store.finish_run("snapshot_run", "escalate")
    receipt = {"root": "abc", "payload": {"evaluation": {"decision": "escalate"}}}
    services.store.save_receipt("snapshot_run", receipt)
    services.approve.escalations = SimpleNamespace(pending={
        "approval-id": SimpleNamespace(run_id="snapshot_run"),
    })
    snapshot = client.get("/runs/snapshot_run").json()
    assert snapshot["receipt"] == receipt
    assert snapshot["escalation_id"] == "approval-id"
    assert snapshot["status"] == "escalate"
    services.approve.escalations.pending.clear()
    assert client.get("/runs/snapshot_run").json()["escalation_id"] is None
