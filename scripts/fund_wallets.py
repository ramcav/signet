"""Fund and protect XRPL testnet wallets; audit existing wallets by default.

Run once:
    uv run python scripts/fund_wallets.py
Writes backend/config/wallets.json.
Use --secure-existing to resume setup or secure a saved wallet explicitly.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from xrpl.clients import JsonRpcClient  # noqa: E402

from signet.adapters.xrpl_adapter import (  # noqa: E402
    TESTNET_JSON_RPC,
    WALLETS_FILE,
    bootstrap_wallets,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallets", type=Path, default=WALLETS_FILE)
    parser.add_argument("--secure-existing", action="store_true", help="Configure the saved account and disable master/regular-key bypasses")
    args = parser.parse_args(argv)
    client = JsonRpcClient(TESTNET_JSON_RPC)
    wallets = bootstrap_wallets(client, path=args.wallets, secure_existing=args.secure_existing)
    print("\n=== wallets ===")
    print(f"master : {wallets.master.classic_address}")
    print(f"agent  : {wallets.agent.classic_address}")
    print(f"policy : {wallets.policy.classic_address}")
    print("\nVerified: 2-of-2 agent + policy, master disabled, no RegularKey.")
    print(f"Saved wallets: {args.wallets}")


if __name__ == "__main__":
    main()
