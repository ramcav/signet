"""Verify a Signet receipt against an independently obtained XRPL memo offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Domain verification has no application startup, secrets, or network dependency.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from signet.domain.receipt import verify_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path, help="exported receipt JSON file")
    parser.add_argument("--memo", required=True, help="32-byte memo hex obtained independently from XRPL")
    parser.add_argument("--transaction", type=Path, help="optional independent XRPL transaction JSON file")
    args = parser.parse_args()
    try:
        document = json.loads(args.receipt.read_text(encoding="utf-8"))
        transaction = json.loads(args.transaction.read_text(encoding="utf-8")) if args.transaction else None
        verify_receipt(document, args.memo, transaction)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1
    print("Verified: receipt commitment matches the supplied memo." + (" Transaction payment fields and receipt memo also match." if transaction is not None else ""))
    print("This checks recorded evidence integrity, not operator identity, private model reasoning, or ledger inclusion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
