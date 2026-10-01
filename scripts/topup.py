"""Top up the existing master wallet from the testnet faucet."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from xrpl.clients import JsonRpcClient  # noqa: E402
from xrpl.wallet import generate_faucet_wallet  # noqa: E402

from signet.adapters.xrpl_adapter import (  # noqa: E402
    TESTNET_JSON_RPC, WALLETS_FILE, XRPLAdapter, bootstrap_wallets, load_wallets,
)


def main(rounds: int = 10, *, path: Path = WALLETS_FILE, secure_existing: bool = False) -> None:
    if rounds < 1:
        raise ValueError("rounds must be positive")
    wallets = load_wallets(path)
    client = JsonRpcClient(TESTNET_JSON_RPC)
    if secure_existing:
        wallets = bootstrap_wallets(client, path=path, secure_existing=True)
    XRPLAdapter(wallets, client).assert_protected()
    for i in range(rounds):
        print(f"round {i+1}/{rounds} — requesting faucet for master …")
        generate_faucet_wallet(client, wallet=wallets.master, debug=False)
    from xrpl.models.requests import AccountInfo

    info = client.request(
        AccountInfo(account=wallets.master.classic_address, ledger_index="validated")
    )
    drops = int(info.result["account_data"]["Balance"])
    print(f"master balance: {drops/1_000_000:.2f} XRP")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rounds", nargs="?", type=int, default=10)
    parser.add_argument("--wallets", type=Path, default=WALLETS_FILE)
    parser.add_argument("--secure-existing", action="store_true")
    args = parser.parse_args()
    main(args.rounds, path=args.wallets, secure_existing=args.secure_existing)
