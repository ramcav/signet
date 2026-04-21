"""XRPL testnet adapter — 2-of-2 multisigned Payment submission.

Wallet roles:
  agent_wallet  : owns key_a, signs as regular signer on a SignerList
  policy_wallet : owns key_b, signs as regular signer on a SignerList
  master_wallet : the account that holds the funds; has a 2-of-2 SignerList
                  (agent + policy), and its MasterKey can optionally be
                  disabled so only the SignerList can move funds.

For demo simplicity the `master_wallet` is a third testnet account funded
from the faucet; its SignerListSet configures both agent_wallet and
policy_wallet as required signers (weight 1 each, quorum 2).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo
from xrpl.models.transactions import Memo, Payment, SignerEntry, SignerListSet
from xrpl.transaction import autofill, multisign, sign, submit_and_wait
from xrpl.utils import xrp_to_drops
from xrpl.wallet import Wallet, generate_faucet_wallet

from ..domain import Intent, IntentAction

log = logging.getLogger(__name__)

TESTNET_JSON_RPC = "https://s.altnet.rippletest.net:51234"
TESTNET_EXPLORER = "https://testnet.xrpl.org/transactions/{tx_hash}"

WALLETS_FILE = Path(__file__).resolve().parents[3] / "config" / "wallets.json"


@dataclass(frozen=True)
class TxResult:
    tx_hash: str
    explorer_url: str
    memo_hex: str
    engine_result: str
    validated: bool
    raw: dict


@dataclass
class WalletSet:
    master: Wallet
    agent: Wallet
    policy: Wallet

    def to_json(self) -> dict:
        return {
            "master": {"seed": self.master.seed, "address": self.master.classic_address},
            "agent": {"seed": self.agent.seed, "address": self.agent.classic_address},
            "policy": {"seed": self.policy.seed, "address": self.policy.classic_address},
        }

    @classmethod
    def from_json(cls, d: dict) -> "WalletSet":
        return cls(
            master=Wallet.from_seed(d["master"]["seed"]),
            agent=Wallet.from_seed(d["agent"]["seed"]),
            policy=Wallet.from_seed(d["policy"]["seed"]),
        )


def load_wallets(path: Path = WALLETS_FILE) -> WalletSet:
    return WalletSet.from_json(json.loads(path.read_text()))


def save_wallets(wallets: WalletSet, path: Path = WALLETS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(wallets.to_json(), indent=2))


# ── bootstrap ────────────────────────────────────────────────────────────────
def bootstrap_wallets(client: JsonRpcClient) -> WalletSet:
    """Fund three testnet wallets and configure 2-of-2 SignerList on master."""
    log.info("requesting faucet funds for master, agent, policy …")
    master = generate_faucet_wallet(client, debug=False)
    agent = generate_faucet_wallet(client, debug=False)
    policy = generate_faucet_wallet(client, debug=False)

    sl = SignerListSet(
        account=master.classic_address,
        signer_quorum=2,
        signer_entries=[
            SignerEntry(account=agent.classic_address, signer_weight=1),
            SignerEntry(account=policy.classic_address, signer_weight=1),
        ],
    )
    log.info("submitting SignerListSet for 2-of-2 quorum on %s", master.classic_address)
    resp = submit_and_wait(sl, client, master)
    if resp.result.get("meta", {}).get("TransactionResult") != "tesSUCCESS":
        raise RuntimeError(f"SignerListSet failed: {resp.result}")
    return WalletSet(master=master, agent=agent, policy=policy)


# ── submit ───────────────────────────────────────────────────────────────────
class XRPLAdapter:
    def __init__(
        self,
        wallets: WalletSet,
        client: Optional[JsonRpcClient] = None,
    ) -> None:
        self.wallets = wallets
        self.client = client or JsonRpcClient(TESTNET_JSON_RPC)

    def get_balance_xrp(self, address: str) -> float:
        try:
            r = self.client.request(AccountInfo(account=address, ledger_index="validated"))
            return int(r.result["account_data"]["Balance"]) / 1_000_000
        except Exception:
            return 0.0

    def build_payment(self, intent: Intent, merkle_root_hex: str) -> Payment:
        if intent.action != IntentAction.PAYMENT:
            raise ValueError("only payment intents supported")
        if intent.asset != "XRP":
            raise NotImplementedError("demo XRPL adapter supports native XRP only")

        memo = Memo(
            memo_type=_hex("signet/reasoningCommit"),
            memo_data=merkle_root_hex.upper(),
            memo_format=_hex("application/octet-stream"),
        )
        payment = Payment(
            account=self.wallets.master.classic_address,
            destination=intent.to_account,
            amount=xrp_to_drops(intent.amount),
            memos=[memo],
        )
        return autofill(payment, self.client, signers_count=2)

    def multisign_and_submit(
        self, intent: Intent, merkle_root_hex: str
    ) -> TxResult:
        """Build → agent signs → policy signs → combine → submit."""
        payment = self.build_payment(intent, merkle_root_hex)

        tx_agent = sign(payment, self.wallets.agent, multisign=True)
        tx_policy = sign(payment, self.wallets.policy, multisign=True)
        multi_tx = multisign(payment, [tx_agent, tx_policy])

        log.info("submitting 2-of-2 multisigned Payment …")
        resp = submit_and_wait(multi_tx, self.client)
        return _to_result(resp.result, merkle_root_hex)

    def attempt_single_sig_submit(
        self, intent: Intent, merkle_root_hex: str
    ) -> TxResult:
        """Scenario B: submit with only sig_a. Expected: ledger refuses (quorum).

        If the destination address itself is malformed (LLM fabricated one),
        we still surface a clean refusal message — that is itself an
        independent layer catching the compromise before the ledger.
        """
        try:
            payment = self.build_payment(intent, merkle_root_hex)
            tx_agent = sign(payment, self.wallets.agent, multisign=True)
            single = multisign(payment, [tx_agent])
            resp = submit_and_wait(single, self.client)
            return _to_result(resp.result, merkle_root_hex)
        except Exception as exc:
            # Extract the rippled engine code if present in the exception msg.
            msg = str(exc)
            code = "ledger_rejected"
            for token in ("tefBAD_QUORUM", "tecNO_PERMISSION", "tefBAD_SIGNATURE", "tecUNFUNDED_PAYMENT"):
                if token in msg:
                    code = token
                    break
            return TxResult(
                tx_hash="",
                explorer_url="",
                memo_hex=merkle_root_hex.upper(),
                engine_result=code,
                validated=False,
                raw={"error": msg[:400]},
            )


# ── helpers ──────────────────────────────────────────────────────────────────
def _hex(s: str) -> str:
    return s.encode("utf-8").hex().upper()


def _to_result(result: dict, merkle_root_hex: str) -> TxResult:
    engine = result.get("meta", {}).get("TransactionResult", "unknown")
    tx_hash = result.get("hash") or result.get("tx_json", {}).get("hash", "")
    return TxResult(
        tx_hash=tx_hash,
        explorer_url=TESTNET_EXPLORER.format(tx_hash=tx_hash) if tx_hash else "",
        memo_hex=merkle_root_hex.upper(),
        engine_result=engine,
        validated=bool(result.get("validated", False)),
        raw=result,
    )
