import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from signet.adapters.audit_store import AuditStore
from signet.api.app import Services, build_app
from signet.application.events import EventBus


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
