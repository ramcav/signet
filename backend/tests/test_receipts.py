import json
from pathlib import Path
import subprocess
import sys

import pytest

import signet.domain as domain
from signet.domain import Intent, IntentAction, PolicyEngine, ReasoningTrace
from signet.domain.policy import InMemoryKYT
from .conftest import TREASURY


def receipt(config, **overrides):
    payment = Intent(IntentAction.PAYMENT, "rAgent", TREASURY, "1.123456", "XRP", "treasury transfer", id="receipt-test")
    params = dict(intent=payment, evaluation=PolicyEngine(config, InMemoryKYT()).evaluate(payment), config=config,
                  quote={"price_usd": 0.5, "source": "test-provider", "as_of": "2026-09-29T08:00:00Z", "demo": False},
                  trace=ReasoningTrace(("user request", "resolved treasury alias")), approval=None)
    params.update(overrides)
    return domain.build_receipt(**params)


def test_receipt_api_is_available():
    assert hasattr(domain, "build_receipt"), "a portable payment receipt must commit the resolved decision"


def test_receipt_round_trip_binds_resolved_fields(config):
    value = receipt(config)
    document = json.loads(json.dumps(value.to_dict()))
    assert document["schema"] == "signet.payment-receipt"
    assert document["version"] == 1
    assert document["payload"]["intent"]["amount"] == "1.123456"
    assert document["payload"]["intent"]["to_account"] == TREASURY
    assert document["payload"]["policy"]["version"] == "1"
    assert document["payload"]["trace"]["kind"] == "recorded_evidence"
    assert document["root"] == value.root
    assert domain.verify_receipt(document, value.root.upper()) is True


def test_refusal_receipt_preserves_invalid_proposed_destination(config):
    payment = Intent(IntentAction.PAYMENT, "rAgent", "unknown_vault", "1", "XRP", "invalid proposal")
    evaluation = PolicyEngine(config, InMemoryKYT()).evaluate(payment)
    assert evaluation.decision == domain.Decision.REFUSE
    value = receipt(config, intent=payment, evaluation=evaluation)
    assert value.to_dict()["payload"]["intent"]["to_account"] == "unknown_vault"
    assert domain.verify_receipt(value.to_dict(), value.root)


@pytest.mark.parametrize("decision", [domain.Decision.ALLOW, domain.Decision.ESCALATE])
def test_signable_receipts_still_require_resolved_addresses(config, decision):
    from dataclasses import replace

    payment = Intent(IntentAction.PAYMENT, "rAgent", "unknown_vault", "1", "XRP", "invalid proposal")
    evaluation = replace(PolicyEngine(config, InMemoryKYT()).evaluate(payment), decision=decision)
    with pytest.raises(ValueError, match="resolved"):
        receipt(config, intent=payment, evaluation=evaluation)


@pytest.mark.parametrize("section,key,new_value", [
    ("intent", "amount", "1.123457"), ("intent", "to_account", "rAttacker"),
    ("policy", "daily_cap_usd", "999999"), ("policy", "version", "2"),
    ("quote", "price_usd", "0.6"), ("quote", "as_of", "2026-09-30T08:00:00Z"),
    ("evaluation", "decision", "refuse"), ("trace", "steps", ["different evidence"]),
    ("approval", "operator", "mallory"),
])
def test_tampering_is_detected(config, section, key, new_value):
    value = receipt(config, approval={"operator": "local operator", "action": "approve", "approved_at": "2026-09-29T08:01:00Z"})
    changed = value.to_dict()
    changed["payload"][section][key] = new_value
    with pytest.raises(ValueError):
        domain.verify_receipt(changed, value.root)


def test_new_receipt_root_cannot_be_substituted_for_independent_memo(config):
    first = receipt(config)
    changed = receipt(config, approval={"action": "approve"})
    assert first.root != changed.root
    with pytest.raises(ValueError, match="memo"):
        domain.verify_receipt(changed.to_dict(), first.root)


def test_canonical_encoding_is_independent_of_mapping_order_and_decimal_spelling(config):
    first = receipt(config)
    second = receipt(config, quote={"demo": False, "as_of": "2026-09-29T08:00:00+00:00", "source": "test-provider", "price_usd": "0.5000"})
    assert first.root == second.root


@pytest.mark.parametrize("field,value", [("version", 2), ("version", True), ("schema", "unknown"), ("root", "xyz")])
def test_schema_and_version_are_validated(config, field, value):
    document = receipt(config).to_dict()
    document[field] = value
    with pytest.raises(ValueError):
        domain.verify_receipt(document, "0" * 64)


def transaction(value):
    return {"TransactionType": "Payment", "Account": "rAgent", "Destination": TREASURY, "Amount": "1123456",
            "Memos": [{"Memo": {"MemoType": "signet/payment-receipt/v1".encode().hex(), "MemoData": value.root.upper()}}]}


def test_receipt_verifies_against_supplied_xrpl_transaction(config):
    value = receipt(config)
    assert domain.verify_receipt(value.to_dict(), value.root, transaction(value))


@pytest.mark.parametrize("key,new_value", [("Amount", "1123457"), ("Destination", "rAttacker"), ("Account", "rOther"), ("TransactionType", "OfferCreate"), ("Memos", [])])
def test_receipt_rejects_mismatched_transaction(config, key, new_value):
    value = receipt(config)
    tx = transaction(value)
    tx[key] = new_value
    with pytest.raises(ValueError):
        domain.verify_receipt(value.to_dict(), value.root, tx)


def test_trace_leaf_count_and_approval_are_committed(config):
    first = receipt(config, trace=ReasoningTrace(("a", "b", "c")))
    second = receipt(config, trace=ReasoningTrace(("a", "b", "c", "c")))
    assert first.root != second.root
    assert receipt(config, approval={"action": "approve"}).root != receipt(config).root


def test_receipt_copy_does_not_mutate_original(config):
    value = receipt(config)
    changed = value.to_dict()
    changed["payload"]["intent"]["amount"] = "99"
    assert domain.verify_receipt(value.to_dict(), value.root)


def test_cli_verifies_without_network_or_application_imports(config, tmp_path):
    value = receipt(config)
    filename = tmp_path / "receipt.json"
    filename.write_text(json.dumps(value.to_dict()), encoding="utf-8")
    cli = Path(__file__).resolve().parents[2] / "scripts" / "verify_receipt.py"
    result = subprocess.run([sys.executable, str(cli), str(filename), "--memo", value.root], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "verified" in result.stdout.lower()
    rejected = subprocess.run([sys.executable, str(cli), str(filename), "--memo", "0" * 64], capture_output=True, text=True)
    assert rejected.returncode == 1
