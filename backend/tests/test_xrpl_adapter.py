"""Offline tests for XRPL adapter payload construction."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from xrpl.models.transactions import Payment
from xrpl.utils import xrp_to_drops
from xrpl.wallet import Wallet

from signet.adapters.xrpl_adapter import XRPLAdapter, WalletSet
from signet.domain import Intent, IntentAction

# Valid classic address (from xrpl-py examples — deterministic test placeholder).
VALID_TREASURY = "rH438jEAzTs5PYtV6CHZqpDpwCKQmPW9Cg"


@pytest.fixture
def wallets() -> WalletSet:
    return WalletSet(
        master=Wallet.create(),
        agent=Wallet.create(),
        policy=Wallet.create(),
    )


@pytest.fixture
def adapter(wallets: WalletSet) -> XRPLAdapter:
    return XRPLAdapter(wallets=wallets)


def _autofill_stub(tx, *_args, **_kwargs):
    # Bypass network: return tx with required fields filled deterministically.
    d = tx.to_dict()
    d["sequence"] = 1
    d["fee"] = "36000"
    d["last_ledger_sequence"] = 99_999_999
    return Payment.from_dict(d)


def test_build_payment_has_memo_and_destination(adapter: XRPLAdapter, wallets):
    intent = Intent(
        action=IntentAction.PAYMENT,
        from_account=wallets.master.classic_address,
        to_account=VALID_TREASURY,
        amount=100.0,
        asset="XRP",
        rationale="test",
    )
    root = "a" * 64
    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=_autofill_stub):
        payment = adapter.build_payment(intent, root)
    assert payment.destination == VALID_TREASURY
    assert payment.amount == xrp_to_drops(100)
    assert payment.memos and payment.memos[0].memo_data == root.upper()


def test_non_xrp_asset_not_supported(adapter: XRPLAdapter, wallets):
    intent = Intent(
        action=IntentAction.PAYMENT,
        from_account=wallets.master.classic_address,
        to_account=VALID_TREASURY,
        amount=100.0,
        asset="RLUSD",
        rationale="test",
    )
    with pytest.raises(NotImplementedError):
        adapter.build_payment(intent, "deadbeef")


def test_multisign_combines_two_signers(adapter: XRPLAdapter, wallets):
    from xrpl.transaction import multisign, sign

    intent = Intent(
        action=IntentAction.PAYMENT,
        from_account=wallets.master.classic_address,
        to_account=VALID_TREASURY,
        amount=1.0,
        asset="XRP",
        rationale="test",
    )
    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=_autofill_stub):
        payment = adapter.build_payment(intent, "ff" * 32)
    tx_a = sign(payment, wallets.agent, multisign=True)
    tx_b = sign(payment, wallets.policy, multisign=True)
    combined = multisign(payment, [tx_a, tx_b])
    assert combined.signers is not None and len(combined.signers) == 2
    accounts = {s.account for s in combined.signers}
    assert accounts == {wallets.agent.classic_address, wallets.policy.classic_address}
