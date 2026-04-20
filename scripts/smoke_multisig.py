"""Smoke-test: send 1 XRP master→agent via 2-of-2 multisig, with a fake
Merkle root in the memo. Proves the adapter end-to-end on testnet."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from signet.adapters.xrpl_adapter import XRPLAdapter, load_wallets  # noqa: E402
from signet.domain import Intent, IntentAction, ReasoningTrace  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    wallets = load_wallets()
    adapter = XRPLAdapter(wallets=wallets)

    intent = Intent(
        action=IntentAction.PAYMENT,
        from_account=wallets.master.classic_address,
        to_account=wallets.agent.classic_address,  # send back to agent for smoke
        amount=1.0,
        asset="XRP",
        rationale="smoke test",
    )
    root = ReasoningTrace(
        steps=("user intent: smoke", "policy: allow", "submit")
    ).commit().root

    print(f"submitting multisig payment, merkle root = {root}")
    result = adapter.multisign_and_submit(intent, root)
    print(f"tx hash       : {result.tx_hash}")
    print(f"engine        : {result.engine_result}")
    print(f"validated     : {result.validated}")
    print(f"explorer      : {result.explorer_url}")
    print(f"memo (hex)    : {result.memo_hex}")


if __name__ == "__main__":
    main()
