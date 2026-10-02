"""XRPL testnet payments requiring agent and policy signatures.

Runtime verifies the validated signer list, disabled master key, and absence
of a regular key. Wallet setup persists seeds before any ledger configuration.
"""
from __future__ import annotations

from collections.abc import Callable
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, RLock
from typing import Optional

from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo
from xrpl.models.transactions import (
    AccountSet, AccountSetAsfFlag, Memo, Payment, SetRegularKey, SignerEntry,
    SignerListSet,
)
from xrpl.transaction import autofill, multisign, sign, submit, submit_and_wait
from xrpl.utils import xrp_to_drops
from xrpl.wallet import Wallet, generate_faucet_wallet

from ..domain import Intent, IntentAction

log = logging.getLogger(__name__)

TESTNET_JSON_RPC = "https://s.altnet.rippletest.net:51234"
TESTNET_EXPLORER = "https://testnet.xrpl.org/transactions/{tx_hash}"

WALLETS_FILE = Path(__file__).resolve().parents[3] / "config" / "wallets.json"
DISABLE_MASTER_FLAG = 0x00100000
_account_locks: dict[str, RLock] = {}
_account_locks_guard = Lock()


def _account_lock(address: str):
    # Cover every adapter instance using the same source account in this process.
    with _account_locks_guard:
        return _account_locks.setdefault(address, RLock())


class WalletProtectionError(RuntimeError):
    """The validated account configuration does not enforce both signers."""


@dataclass(frozen=True)
class TxResult:
    tx_hash: str
    explorer_url: str
    memo_hex: str
    engine_result: str
    validated: bool
    raw: dict
    classification: Optional[str] = None

    @property
    def outcome(self) -> str:
        if self.validated and self.engine_result == "tesSUCCESS":
            return "success"
        if self.validated and self.engine_result.startswith("tec"):
            return "rejected"
        if self.classification in {"rejected", "failed"}:
            return self.classification
        return "unknown"


@dataclass
class AccountAddress:
    """Runtime holder for a source address, with no master signing material."""

    classic_address: str


@dataclass
class WalletSet:
    master: Wallet | AccountAddress
    agent: Wallet
    policy: Wallet

    def to_json(self) -> dict:
        return {
            "master": {"seed": getattr(self.master, "seed", None), "address": self.master.classic_address},
            "agent": {"seed": self.agent.seed, "address": self.agent.classic_address},
            "policy": {"seed": self.policy.seed, "address": self.policy.classic_address},
        }

    @classmethod
    def from_json(cls, d: dict, *, include_master_seed: bool = True) -> "WalletSet":
        def read_wallet(role):
            wallet = Wallet.from_seed(d[role]["seed"])
            if wallet.classic_address != d[role].get("address", wallet.classic_address):
                raise ValueError(f"{role} address does not match its saved seed")
            return wallet

        master = read_wallet("master") if include_master_seed else AccountAddress(d["master"]["address"])
        wallets = cls(master=master, agent=read_wallet("agent"), policy=read_wallet("policy"))
        _assert_distinct_wallets(wallets)
        return wallets


def load_wallets(path: Path = WALLETS_FILE, *, include_master_seed: bool = True) -> WalletSet:
    return WalletSet.from_json(json.loads(path.read_text()), include_master_seed=include_master_seed)


def save_wallets(wallets: WalletSet, path: Path = WALLETS_FILE) -> None:
    """Create a wallet backup once; never replace existing recovery material."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_EXCL also prevents two concurrent setup processes replacing each other.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as saved:
        json.dump(wallets.to_json(), saved, indent=2)
        saved.flush()
        os.fsync(saved.fileno())


# ── bootstrap ────────────────────────────────────────────────────────────────
def bootstrap_wallets(
    client: JsonRpcClient, path: Path = WALLETS_FILE, *, secure_existing: bool = False,
) -> WalletSet:
    """Create and secure new wallets, or audit/resume the saved wallets.

    Existing wallets are audit-only unless secure_existing is explicitly set.
    If any step is uncertain or interrupted, the original seeds remain saved;
    a later explicit resume audits current validated state before continuing.
    """
    if path.exists():
        wallets = load_wallets(path)
        if not secure_existing:
            XRPLAdapter(wallets, client).assert_protected()
            return wallets
    else:
        wallets = WalletSet(master=Wallet.create(), agent=Wallet.create(), policy=Wallet.create())
        _assert_distinct_wallets(wallets)
        save_wallets(wallets, path)

    with _account_lock(wallets.master.classic_address):
        # Funding is resumable too: only a confirmed absent account gets faucet
        # funds. Transport errors must not be mistaken for missing accounts.
        for wallet in (wallets.master, wallets.agent, wallets.policy):
            info = client.request(AccountInfo(account=wallet.classic_address, ledger_index="validated")).result
            if info.get("error") == "actNotFound":
                generate_faucet_wallet(client, wallet=wallet, debug=False)
            elif info.get("validated") is not True or "account_data" not in info:
                raise WalletProtectionError("Unable to verify funding state; saved wallets were retained")
        _secure_wallets(wallets, client)
    return wallets


def _secure_wallets(wallets: WalletSet, client: JsonRpcClient) -> None:
    _assert_distinct_wallets(wallets)
    account = wallets.master.classic_address
    state = _account_state(client, account)
    disabled = bool(int(state["account_data"].get("Flags", 0)) & DISABLE_MASTER_FLAG)
    try:
        _assert_signer_list(state, wallets)
    except WalletProtectionError:
        if disabled:
            raise WalletProtectionError("Master is disabled and the expected signer list is unavailable; cannot safely resume")
        _submit_setup(SignerListSet(
            account=account, signer_quorum=2,
            signer_entries=[
                SignerEntry(account=wallets.agent.classic_address, signer_weight=1),
                SignerEntry(account=wallets.policy.classic_address, signer_weight=1),
            ],
        ), client, wallets)
        state = _account_state(client, account)
        _assert_signer_list(state, wallets)

    # Verify signer list before removing any alternative authorization route.
    if "RegularKey" in state["account_data"]:
        _submit_setup(SetRegularKey(account=account), client, wallets, multisigned=disabled)
        state = _account_state(client, account)
        _assert_signer_list(state, wallets)
        if "RegularKey" in state["account_data"]:
            raise WalletProtectionError("RegularKey removal was not confirmed")
    if not disabled:
        _submit_setup(AccountSet(
            account=account, set_flag=AccountSetAsfFlag.ASF_DISABLE_MASTER,
        ), client, wallets)
    XRPLAdapter(wallets, client).assert_protected()


def _submit_setup(transaction, client, wallets: WalletSet, *, multisigned: bool = False) -> None:
    if multisigned:
        transaction = autofill(transaction, client, signers_count=2)
        combined = multisign(transaction, [
            sign(transaction, wallets.agent, multisign=True),
            sign(transaction, wallets.policy, multisign=True),
        ])
        response = submit_and_wait(combined, client)
    else:
        if not isinstance(wallets.master, Wallet):
            raise WalletProtectionError("Securing the account requires the saved master seed")
        response = submit_and_wait(transaction, client, wallets.master)
    if _to_result(response.result, "").outcome != "success":
        raise WalletProtectionError("Wallet configuration transaction did not confirm validated success; resume from saved wallets")


def _assert_distinct_wallets(wallets: WalletSet) -> None:
    if len({wallets.master.classic_address, wallets.agent.classic_address, wallets.policy.classic_address}) != 3:
        raise WalletProtectionError("Master, agent and policy must use distinct keys")


# ── submit ───────────────────────────────────────────────────────────────────
class XRPLAdapter:
    def __init__(
        self,
        wallets: WalletSet,
        client: Optional[JsonRpcClient] = None,
    ) -> None:
        self.wallets = wallets
        self.client = client or JsonRpcClient(TESTNET_JSON_RPC)
        self._submission_lock = _account_lock(wallets.master.classic_address)

    def assert_protected(self) -> None:
        """Fail closed unless validated state requires agent AND policy keys."""
        state = _account_state(self.client, self.wallets.master.classic_address)
        _assert_signer_list(state, self.wallets)
        account = state["account_data"]
        if not int(account.get("Flags", 0)) & DISABLE_MASTER_FLAG:
            raise WalletProtectionError("Master key is enabled; explicitly secure the wallet first")
        if "RegularKey" in account:
            raise WalletProtectionError("RegularKey bypasses the required policy signer")

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
        if intent.from_account != self.wallets.master.classic_address:
            raise ValueError("intent source account does not match the protected wallet")

        memo = Memo(
            memo_type=_hex("signet/payment-receipt/v1"),
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
        self, intent: Intent, merkle_root_hex: str, *,
        before_sign: Callable[[], None] | None = None,
    ) -> TxResult:
        """Serialize protection check, sequence allocation, signatures and submission."""
        with self._submission_lock:
            try:
                self.assert_protected()
                payment = self.build_payment(intent, merkle_root_hex)
                if before_sign is not None:
                    before_sign()
                tx_agent = sign(payment, self.wallets.agent, multisign=True)
                tx_policy = sign(payment, self.wallets.policy, multisign=True)
                multi_tx = multisign(payment, [tx_agent, tx_policy])
                tx_hash = multi_tx.get_hash()
            except Exception as exc:
                return _failure_result(exc, merkle_root_hex, submitted=False)
            try:
                resp = submit_and_wait(multi_tx, self.client)
                return _to_result(resp.result, merkle_root_hex, tx_hash)
            except Exception as exc:
                # The request may have reached the ledger. Keep the hash for
                # reconciliation, and never claim that funds were not spent.
                return _failure_result(exc, merkle_root_hex, submitted=True, tx_hash=tx_hash)

    def attempt_single_sig_submit(
        self, intent: Intent, merkle_root_hex: str
    ) -> TxResult:
        """Return a real quorum refusal only when reported by the submit response."""
        with self._submission_lock:
            try:
                self.assert_protected()
                payment = self.build_payment(intent, merkle_root_hex)
                tx_agent = sign(payment, self.wallets.agent, multisign=True)
                single = multisign(payment, [tx_agent])
                tx_hash = single.get_hash()
            except Exception as exc:
                return _failure_result(exc, merkle_root_hex, submitted=False)
            try:
                # fail_hard asks the receiving server not to relay a failed attempt.
                resp = submit(single, self.client, fail_hard=True)
                return _to_result(resp.result, merkle_root_hex, tx_hash, single_sig=True)
            except Exception as exc:
                return _failure_result(exc, merkle_root_hex, submitted=True, tx_hash=tx_hash)


# ── helpers ──────────────────────────────────────────────────────────────────
def _hex(s: str) -> str:
    return s.encode("utf-8").hex().upper()


def _to_result(result: dict, merkle_root_hex: str, tx_hash: str = "", *, single_sig: bool = False) -> TxResult:
    meta = result.get("meta")
    engine = (meta.get("TransactionResult") if isinstance(meta, dict) else None) or result.get("engine_result", "unknown")
    tx_hash = result.get("hash") or result.get("tx_json", {}).get("hash") or tx_hash
    classification = None
    if single_sig and engine in {"tefBAD_QUORUM", "tefBAD_SIGNATURE"}:
        classification = "rejected"
    elif engine.startswith("tem"):
        classification = "rejected"
    return TxResult(
        tx_hash=tx_hash,
        explorer_url=TESTNET_EXPLORER.format(tx_hash=tx_hash) if tx_hash else "",
        memo_hex=merkle_root_hex.upper(),
        engine_result=engine,
        validated=result.get("validated") is True,
        raw=result,
        classification=classification,
    )


def _failure_result(exc: Exception, root: str, *, submitted: bool, tx_hash: str = "") -> TxResult:
    engine = "submission_unknown" if submitted else "pre_submit_failed"
    if isinstance(exc, WalletProtectionError):
        engine = "wallet_unprotected"
    return TxResult(
        tx_hash=tx_hash,
        explorer_url=TESTNET_EXPLORER.format(tx_hash=tx_hash) if tx_hash else "",
        memo_hex=root.upper(), engine_result=engine, validated=False,
        raw={"error": str(exc)[:400], "submitted": submitted},
        classification="unknown" if submitted else "failed",
    )


def _account_state(client: JsonRpcClient, address: str) -> dict:
    try:
        result = client.request(AccountInfo(
            account=address, ledger_index="validated", signer_lists=True,
        )).result
        if result.get("validated") is not True:
            raise WalletProtectionError("Account configuration is not validated")
        if result.get("account_data", {}).get("Account") != address:
            raise WalletProtectionError("Validated account configuration is unavailable")
        return result
    except WalletProtectionError:
        raise
    except Exception as exc:
        raise WalletProtectionError("Unable to verify wallet protection") from exc


def _assert_signer_list(state: dict, wallets: WalletSet) -> None:
    lists = state.get("signer_lists", state.get("account_data", {}).get("signer_lists", []))
    expected = {wallets.agent.classic_address, wallets.policy.classic_address}
    if len(expected) != 2 or wallets.master.classic_address in expected:
        raise WalletProtectionError("Master, agent and policy must use distinct keys")
    if len(lists) != 1 or lists[0].get("SignerQuorum") != 2:
        raise WalletProtectionError("Expected exactly one 2-of-2 signer list")
    entries = lists[0].get("SignerEntries", [])
    actual = [entry.get("SignerEntry", {}) for entry in entries]
    if len(actual) != 2 or {entry.get("Account") for entry in actual} != expected:
        raise WalletProtectionError("Signer list must contain only the agent and policy")
    if any(entry.get("SignerWeight") != 1 for entry in actual):
        raise WalletProtectionError("Both signer weights must be 1")
