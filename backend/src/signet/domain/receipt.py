"""Portable commitments to recorded payment evidence, not model internals.

Verification proves that a document matches an independently supplied memo.
It does not authenticate an operator's identity, validate policy correctness,
prove genuine private reasoning, or independently establish ledger inclusion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import re
from typing import Any

from .intent import Intent
from .numbers import decimal_text, decimal_value
from .policy import EvaluationResult, PolicyConfig
from .reasoning import ReasoningTrace

SCHEMA = "signet.payment-receipt"
VERSION = 1
DOMAIN = b"signet:payment-receipt:v1\0"
MEMO_TYPE = "signet/payment-receipt/v1"


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float, Decimal)):
        return decimal_text(value)
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _normalize(item) for key, item in value.items()}
    raise ValueError("receipt values must be JSON values with string object keys")


def _encode(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _timestamp(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("quote timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid quote timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("quote timestamp must include timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _fields(value: object, names: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError(f"invalid {label} schema")
    return value


def _text(value: object, label: str, *, empty: bool = False) -> None:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(f"invalid {label}")


def _number(value: object, label: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or decimal_text(value) != value:
        raise ValueError(f"{label} must be a canonical decimal string")
    return decimal_value(value, label, positive=positive)


def _validate_payload(payload: object) -> None:
    payload = _fields(payload, {"intent", "policy", "quote", "evaluation", "trace", "approval"}, "payload")
    intent = _fields(payload["intent"], {"id", "action", "from_account", "to_account", "amount", "asset", "rationale", "raw_agent_output"}, "intent")
    for name in ("id", "from_account", "to_account", "asset"):
        _text(intent[name], name)
    if intent["action"] != "payment":
        raise ValueError("unsupported receipt action")
    _text(intent["rationale"], "rationale", empty=True)
    if intent["raw_agent_output"] is not None:
        _text(intent["raw_agent_output"], "raw_agent_output", empty=True)
    _number(intent["amount"], "amount", positive=True)
    Intent(**intent)

    policy = _fields(payload["policy"], {"version", "allowlist_destinations", "allowlist_assets", "per_tx_cap_usd", "daily_cap_usd", "escalation_tier_threshold_usd", "price_table"}, "policy")
    _text(policy["version"], "policy version")
    for name in ("allowlist_destinations", "allowlist_assets"):
        items = policy[name]
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items) or items != sorted(set(items)):
            raise ValueError(f"invalid canonical {name}")
    for name in ("per_tx_cap_usd", "daily_cap_usd", "escalation_tier_threshold_usd"):
        _number(policy[name], name, positive=True)
    if not isinstance(policy["price_table"], dict):
        raise ValueError("invalid price table")
    for asset, price in policy["price_table"].items():
        _text(asset, "price asset")
        _number(price, "asset price", positive=True)

    quote = _fields(payload["quote"], {"price_usd", "source", "as_of", "demo"}, "quote")
    _number(quote["price_usd"], "quote price", positive=True)
    _text(quote["source"], "quote source")
    if _timestamp(quote["as_of"]) != quote["as_of"] or not isinstance(quote["demo"], bool):
        raise ValueError("invalid canonical quote")

    evaluation = _fields(payload["evaluation"], {"decision", "notional_usd", "reason", "checks"}, "evaluation")
    if evaluation["decision"] not in ("allow", "refuse", "escalate"):
        raise ValueError("invalid decision")
    # Refusals retain invalid proposals as evidence; only signable decisions
    # require addresses that have passed alias resolution.
    if evaluation["decision"] != "refuse" and (
        not intent["from_account"].startswith("r") or not intent["to_account"].startswith("r")
    ):
        raise ValueError("signable receipt accounts must be resolved XRPL addresses")
    if _number(evaluation["notional_usd"], "notional") < 0:
        raise ValueError("notional must not be negative")
    _text(evaluation["reason"], "reason", empty=True)
    if not isinstance(evaluation["checks"], list):
        raise ValueError("invalid evaluation checks")
    for check in evaluation["checks"]:
        _fields(check, {"name", "status", "detail"}, "rule check")
        _text(check["name"], "rule name")
        _text(check["detail"], "rule detail", empty=True)
        if check["status"] not in ("pass", "fail"):
            raise ValueError("invalid rule status")

    trace = _fields(payload["trace"], {"kind", "steps"}, "trace")
    if trace["kind"] != "recorded_evidence" or not isinstance(trace["steps"], list) or not all(isinstance(step, str) for step in trace["steps"]):
        raise ValueError("invalid recorded evidence")
    if payload["approval"] is not None and not isinstance(payload["approval"], dict):
        raise ValueError("approval must be an operator-action record or null")
    if _normalize(payload) != payload:
        raise ValueError("receipt numbers must use canonical decimal strings")


@dataclass(frozen=True)
class PaymentReceipt:
    root: str
    _envelope_json: str

    def to_dict(self) -> dict:
        """Return an independent JSON-compatible copy of this receipt."""
        return {**json.loads(self._envelope_json), "root": self.root}


def build_receipt(
    intent: Intent,
    evaluation: EvaluationResult,
    config: PolicyConfig,
    quote: dict,
    trace: ReasoningTrace,
    approval: dict | None = None,
) -> PaymentReceipt:
    quote = dict(quote)
    quote["as_of"] = _timestamp(quote.get("as_of"))
    quote["price_usd"] = decimal_text(quote.get("price_usd"))
    payload = _normalize({
        "intent": {
            "id": intent.id, "action": intent.action.value, "from_account": intent.from_account,
            "to_account": intent.to_account, "amount": intent.amount, "asset": intent.asset,
            "rationale": intent.rationale, "raw_agent_output": intent.raw_agent_output,
        },
        "policy": {
            "version": config.version, "allowlist_destinations": sorted(config.allowlist_destinations),
            "allowlist_assets": sorted(config.allowlist_assets), "per_tx_cap_usd": config.per_tx_cap_usd,
            "daily_cap_usd": config.daily_cap_usd, "escalation_tier_threshold_usd": config.escalation_tier_threshold_usd,
            "price_table": config.price_table,
        },
        "quote": quote,
        "evaluation": {
            "decision": evaluation.decision.value, "notional_usd": evaluation.notional_usd,
            "reason": evaluation.reason,
            "checks": [{"name": check.name, "status": check.status.value, "detail": check.detail} for check in evaluation.checks],
        },
        "trace": {"kind": "recorded_evidence", "steps": trace.steps},
        "approval": approval,
    })
    _validate_payload(payload)
    envelope = _encode({"schema": SCHEMA, "version": VERSION, "payload": payload})
    return PaymentReceipt(hashlib.sha256(DOMAIN + envelope.encode("utf-8")).hexdigest(), envelope)


def _hex_root(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ValueError(f"invalid {label}: expected 32-byte hexadecimal commitment")
    return value.lower()


def _verify_transaction(transaction: dict, payload: dict, root: str) -> None:
    tx = transaction
    if not isinstance(tx, dict):
        raise ValueError("transaction must be a JSON object")
    if "result" in tx:
        tx = tx["result"]
    if isinstance(tx, dict):
        tx = tx.get("tx_json", tx.get("transaction", tx))
    if not isinstance(tx, dict):
        raise ValueError("invalid transaction document")
    intent = payload["intent"]
    whole, _, fraction = intent["amount"].partition(".")
    drops = str(int(whole + fraction.ljust(6, "0")))
    if intent["asset"] != "XRP" or tx.get("TransactionType") != "Payment":
        raise ValueError("transaction must be a native XRP Payment")
    expected = {"Account": intent["from_account"], "Destination": intent["to_account"], "Amount": drops}
    for field, value in expected.items():
        actual = tx.get(field, tx.get("DeliverMax") if field == "Amount" else None)
        if actual != value:
            raise ValueError(f"transaction {field} does not match receipt")
    memos = tx.get("Memos", [])
    if not isinstance(memos, list):
        raise ValueError("invalid transaction memos")
    for item in memos:
        memo = item.get("Memo", {}) if isinstance(item, dict) else {}
        data, memo_type = memo.get("MemoData"), memo.get("MemoType")
        if isinstance(data, str) and isinstance(memo_type, str) and data.lower() == root and memo_type.lower() == MEMO_TYPE.encode().hex():
            return
    raise ValueError("transaction receipt memo does not match commitment")


def verify_receipt(document: dict, memo_hex: str, transaction: dict | None = None) -> bool:
    """Return True on integrity success, otherwise raise ValueError.

    Supply a memo obtained independently from XRPL for a meaningful anchor.
    Supplying document['root'] only checks internal document consistency.
    """
    _fields(document, {"schema", "version", "payload", "root"}, "receipt")
    if document["schema"] != SCHEMA or type(document["version"]) is not int or document["version"] != VERSION:
        raise ValueError("unsupported receipt schema or version")
    _validate_payload(document["payload"])
    root = _hex_root(document["root"], "receipt root")
    memo = _hex_root(memo_hex, "memo")
    envelope = {key: document[key] for key in ("schema", "version", "payload")}
    calculated = hashlib.sha256(DOMAIN + _encode(envelope).encode("utf-8")).hexdigest()
    if not hmac.compare_digest(root, calculated):
        raise ValueError("receipt commitment mismatch: document has changed")
    if not hmac.compare_digest(root, memo):
        raise ValueError("receipt root does not match independent memo")
    if transaction is not None:
        _verify_transaction(transaction, document["payload"], root)
    return True
