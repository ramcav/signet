"""Top up the existing master wallet from the testnet faucet."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from xrpl.clients import JsonRpcClient  # noqa: E402
from xrpl.wallet import generate_faucet_wallet  # noqa: E402

from signet.adapters.xrpl_adapter import TESTNET_JSON_RPC, load_wallets  # noqa: E402


def main(rounds: int = 10) -> None:
    wallets = load_wallets()
    client = JsonRpcClient(TESTNET_JSON_RPC)
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
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
