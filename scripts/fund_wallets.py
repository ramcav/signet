"""Fund three XRPL testnet wallets and set 2-of-2 SignerList on master.

Run once:
    uv run python scripts/fund_wallets.py
Writes backend/config/wallets.json.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from xrpl.clients import JsonRpcClient  # noqa: E402

from signet.adapters.xrpl_adapter import (  # noqa: E402
    TESTNET_JSON_RPC,
    bootstrap_wallets,
    save_wallets,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    client = JsonRpcClient(TESTNET_JSON_RPC)
    wallets = bootstrap_wallets(client)
    save_wallets(wallets)
    print("\n=== wallets ===")
    print(f"master : {wallets.master.classic_address}")
    print(f"agent  : {wallets.agent.classic_address}")
    print(f"policy : {wallets.policy.classic_address}")
    print("\nSignerList: 2-of-2 (agent + policy) configured on master.")
    print(f"Saved to backend/config/wallets.json")


if __name__ == "__main__":
    main()
