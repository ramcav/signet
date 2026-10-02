"""Send 1 XRP master to agent on testnet and save a verifiable receipt.

This smoke test uses an explicit demo price and smoke-test policy, with mock
KYT. It verifies the adapter and receipt path without an OpenAI request.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from signet.adapters.xrpl_adapter import (  # noqa: E402
    WALLETS_FILE, XRPLAdapter, bootstrap_wallets, load_wallets,
)
from signet.domain import (  # noqa: E402
    Decision, Intent, IntentAction, PolicyConfig, PolicyEngine, ReasoningTrace,
    build_receipt,
)
from signet.domain.policy import InMemoryKYT  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallets", type=Path, default=WALLETS_FILE)
    parser.add_argument("--secure-existing", action="store_true")
    parser.add_argument("--receipt", type=Path, help="New JSON file for the portable smoke-test receipt")
    args = parser.parse_args(argv)
    wallets = load_wallets(args.wallets, include_master_seed=False)
    adapter = XRPLAdapter(wallets=wallets)
    if args.secure_existing:
        bootstrap_wallets(adapter.client, path=args.wallets, secure_existing=True)
    adapter.assert_protected()

    intent = Intent(
        action=IntentAction.PAYMENT,
        from_account=wallets.master.classic_address,
        to_account=wallets.agent.classic_address,  # send back to agent for smoke
        amount=1.0,
        asset="XRP",
        rationale="smoke test",
    )
    config = PolicyConfig(
        allowlist_destinations=frozenset({wallets.agent.classic_address}),
        allowlist_assets=frozenset({"XRP"}),
        per_tx_cap_usd=1, daily_cap_usd=1, escalation_tier_threshold_usd=2,
        price_table={"XRP": 1}, version="smoke-demo-v1",
    )
    evaluation = PolicyEngine(config, InMemoryKYT()).evaluate(intent)
    if evaluation.decision != Decision.ALLOW:
        raise RuntimeError(f"Smoke-test policy refused payment: {evaluation.reason}")
    receipt = build_receipt(
        intent, evaluation, config,
        quote={
            "price_usd": 1, "source": "smoke-test-demo",
            "as_of": datetime.now(timezone.utc).isoformat(), "demo": True,
        },
        trace=ReasoningTrace(steps=(
            "Operator invoked the testnet smoke test for 1 XRP to the agent account.",
            "Valuation uses an explicit demo price of 1 USD per XRP; KYT is mocked.",
            "The smoke-demo-v1 policy evaluated the recorded payment and allowed it.",
        )),
    )
    receipt_path = args.receipt or ROOT / "backend" / "data" / "smoke-receipts" / f"{intent.id}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with receipt_path.open("x", encoding="utf-8") as saved:
        json.dump(receipt.to_dict(), saved, indent=2)

    print(f"receipt       : {receipt_path}")
    print(f"submitting multisig payment, receipt root = {receipt.root}")
    result = adapter.multisign_and_submit(intent, receipt.root)
    print(f"tx hash       : {result.tx_hash}")
    print(f"engine        : {result.engine_result}")
    print(f"outcome       : {result.outcome}")
    print(f"validated     : {result.validated}")
    print(f"explorer      : {result.explorer_url}")
    print(f"memo (hex)    : {result.memo_hex}")
    if result.outcome != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
