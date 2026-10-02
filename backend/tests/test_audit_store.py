from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from signet.adapters.audit_store import AuditStore


def test_atomic_reservations_across_connections(tmp_path):
    path = tmp_path / "audit.sqlite3"
    first = AuditStore(path)
    second = AuditStore(path)
    assert first.reserve("wallet", "previous", 99600, 100000)
    first.resolve("previous", "success")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda pair: pair[0].reserve("wallet", pair[1], 250, 100000),
            [(first, "one"), (second, "two")],
        ))
    assert sorted(results) == [False, True]
    assert first.used("wallet") == Decimal("99850")


def test_rollover_preserves_uncertain_reservations_and_restart(tmp_path):
    now = [datetime(2026, 9, 29, 23, 59, tzinfo=timezone.utc)]
    path = tmp_path / "audit.sqlite3"
    store = AuditStore(path, clock=lambda: now[0])
    store.reserve("wallet", "paid", 100, 1000)
    store.resolve("paid", "success")
    store.reserve("wallet", "uncertain", 200, 1000)
    store.resolve("uncertain", "unknown")
    now[0] += timedelta(minutes=2)
    restarted = AuditStore(path, clock=lambda: now[0])
    assert restarted.used("wallet") == 200
    assert restarted.reserve("wallet", "new", 800, 1000)
    assert not restarted.reserve("wallet", "excess", 1, 1000)


def test_confirmed_failure_releases_but_unknown_does_not(tmp_path):
    store = AuditStore(tmp_path / "audit.sqlite3")
    for run in ("rejected", "failed", "unknown"):
        assert store.reserve("wallet", run, 100, 1000)
        store.resolve(run, run)
    assert store.used("wallet") == 100
    with pytest.raises(ValueError):
        store.reserve("wallet", "unknown", 101, 1000)


def test_idempotency_key_cannot_change_request(tmp_path):
    store = AuditStore(tmp_path / "audit.sqlite3")
    assert store.accept_run("id", {"user_message": "one"})
    assert not store.accept_run("id", {"user_message": "one"})
    with pytest.raises(ValueError):
        store.accept_run("id", {"user_message": "different"})


def test_exported_receipt_survives_restart(tmp_path):
    path = tmp_path / "audit.sqlite3"
    store = AuditStore(path)
    document = {"root": "abcd", "payload": {"intent": {"amount": "1"}}}
    store.save_receipt("run", document)
    assert AuditStore(path).get_receipt("run") == document
    assert store.get_receipt("missing") is None


def test_override_is_explicit_and_still_accounted(tmp_path):
    store = AuditStore(tmp_path / "audit.sqlite3")
    assert not store.reserve("wallet", "ordinary", 200, 100)
    assert store.reserve("wallet", "approved", 200, 100, override=True)
    store.resolve("approved", "success")
    assert store.used("wallet") == 200


def test_payment_settled_after_midnight_counts_on_settlement_day(tmp_path):
    now = [datetime(2026, 9, 29, 23, 59, tzinfo=timezone.utc)]
    store = AuditStore(tmp_path / "audit.sqlite3", clock=lambda: now[0])
    store.reserve("wallet", "cross_midnight", 100, 1000)
    now[0] += timedelta(minutes=2)
    store.resolve("cross_midnight", "success")
    assert store.used("wallet") == 100


def test_restart_recovers_interrupted_runs_without_resubmission(tmp_path):
    path = tmp_path / "audit.sqlite3"
    store = AuditStore(path)
    for run_id in ("proposing", "submitting", "settled", "pending"):
        store.accept_run(run_id, {"user_message": run_id})
    store.reserve("wallet", "submitting", 100, 1000)
    store.reserve("wallet", "settled", 200, 1000)
    store.resolve("settled", "success")
    store.finish_run("pending", "escalate")
    restarted = AuditStore(path)
    restarted.recover_interrupted_runs()
    assert restarted.get_run("proposing")["status"] == "error"
    assert restarted.get_run("submitting")["status"] == "unknown"
    assert restarted.get_run("settled")["status"] == "success"
    assert restarted.get_run("pending")["status"] == "error"
    assert restarted.used("wallet") == 300
