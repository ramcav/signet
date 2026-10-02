"""Offline tests for XRPL adapter payload construction."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from xrpl.models.transactions import Payment
from xrpl.utils import xrp_to_drops
from xrpl.wallet import Wallet

from signet.adapters.xrpl_adapter import XRPLAdapter, WalletSet, _to_result
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
    assert bytes.fromhex(payment.memos[0].memo_type).decode() == "signet/payment-receipt/v1"


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


def test_payment_source_must_match_committed_intent(adapter, wallets):
    intent = Intent(IntentAction.PAYMENT, wallets.agent.classic_address,
                    VALID_TREASURY, "1", "XRP", "wrong source")
    with patch("signet.adapters.xrpl_adapter.autofill") as filling:
        with pytest.raises(ValueError, match="source"):
            adapter.build_payment(intent, "aa" * 32)
    filling.assert_not_called()


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


def protected_response(wallets):
    return {
        "validated": True,
        "account_data": {
            "Account": wallets.master.classic_address,
            "Flags": 0x00100000,
            "Balance": "100000000",
        },
        "signer_lists": [{
            "SignerQuorum": 2,
            "SignerEntries": [
                {"SignerEntry": {"Account": wallets.agent.classic_address, "SignerWeight": 1}},
                {"SignerEntry": {"Account": wallets.policy.classic_address, "SignerWeight": 1}},
            ],
        }],
    }


@pytest.fixture
def protected_adapter(wallets):
    client = Mock()
    client.request.return_value = SimpleNamespace(result=protected_response(wallets))
    return XRPLAdapter(wallets, client)


def intent_for(wallets, destination=VALID_TREASURY):
    return Intent(action=IntentAction.PAYMENT,
                  from_account=wallets.master.classic_address,
                  to_account=destination, amount=1, asset="XRP", rationale="test")


def test_protection_audit_requests_validated_signer_list(protected_adapter):
    protected_adapter.assert_protected()
    request = protected_adapter.client.request.call_args.args[0]
    assert request.ledger_index == "validated"
    assert request.signer_lists is True


@pytest.mark.parametrize("tamper", [
    lambda data: data.update(validated=False),
    lambda data: data["account_data"].update(Flags=0),
    lambda data: data["account_data"].update(RegularKey=VALID_TREASURY),
    lambda data: data["account_data"].update(Account=VALID_TREASURY),
    lambda data: data.update(signer_lists=[]),
    lambda data: data["signer_lists"][0].update(SignerQuorum=1),
    lambda data: data["signer_lists"][0]["SignerEntries"][0]["SignerEntry"].update(SignerWeight=2),
    lambda data: data["signer_lists"][0]["SignerEntries"][0]["SignerEntry"].update(Account=VALID_TREASURY),
    lambda data: data["signer_lists"].append(data["signer_lists"][0]),
])
def test_unsafe_wallet_fails_before_any_signing(protected_adapter, wallets, tamper):
    tamper(protected_adapter.client.request.return_value.result)
    with patch("signet.adapters.xrpl_adapter.sign") as signing, \
            patch("signet.adapters.xrpl_adapter.submit_and_wait") as submitting:
        result = protected_adapter.multisign_and_submit(intent_for(wallets), "aa" * 32)
    assert result.outcome == "failed"
    assert result.engine_result == "wallet_unprotected"
    signing.assert_not_called()
    submitting.assert_not_called()


@pytest.mark.parametrize("raw,expected", [
    ({"validated": True, "meta": {"TransactionResult": "tesSUCCESS"}}, "success"),
    ({"validated": False, "meta": {"TransactionResult": "tesSUCCESS"}}, "unknown"),
    ({"validated": True, "meta": {"TransactionResult": "tecUNFUNDED_PAYMENT"}}, "rejected"),
    ({"validated": False, "engine_result": "tecUNFUNDED_PAYMENT"}, "unknown"),
    ({"engine_result": "terQUEUED"}, "unknown"),
    ({}, "unknown"),
])
def test_result_only_claims_success_for_validated_tessuccess(raw, expected):
    assert _to_result(raw, "aa" * 32).outcome == expected


def test_multisig_signs_real_payment_and_preserves_success(protected_adapter, wallets):
    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=_autofill_stub), \
            patch("signet.adapters.xrpl_adapter.submit_and_wait") as submitting:
        submitting.return_value.result = {
            "validated": True, "hash": "A" * 64,
            "meta": {"TransactionResult": "tesSUCCESS"},
        }
        result = protected_adapter.multisign_and_submit(intent_for(wallets), "aa" * 32)
    payment = submitting.call_args.args[0]
    assert len(payment.signers) == 2
    assert all(s.txn_signature for s in payment.signers)
    assert result.outcome == "success"


def test_before_sign_runs_after_autofill_and_before_any_signatures(protected_adapter, wallets):
    from xrpl.transaction import sign as real_sign

    order = []

    def filling(tx, *args, **kwargs):
        assert protected_adapter.client.request.called
        order.append("autofill")
        return _autofill_stub(tx)

    def before_sign():
        order.append("recheck")

    def signing(*args, **kwargs):
        assert "recheck" in order
        order.append("sign")
        return real_sign(*args, **kwargs)

    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=filling), \
            patch("signet.adapters.xrpl_adapter.sign", side_effect=signing), \
            patch("signet.adapters.xrpl_adapter.submit_and_wait") as submitting:
        submitting.return_value.result = {"validated": True, "meta": {"TransactionResult": "tesSUCCESS"}}
        result = protected_adapter.multisign_and_submit(intent_for(wallets), "aa" * 32, before_sign=before_sign)
    assert result.outcome == "success"
    assert order == ["autofill", "recheck", "sign", "sign"]


def test_before_sign_failure_never_signs_or_submits(protected_adapter, wallets):
    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=_autofill_stub), \
            patch("signet.adapters.xrpl_adapter.sign") as signing, \
            patch("signet.adapters.xrpl_adapter.submit_and_wait") as submitting:
        result = protected_adapter.multisign_and_submit(
            intent_for(wallets), "aa" * 32,
            before_sign=Mock(side_effect=ValueError("quote expired while waiting")),
        )
    assert result.outcome == "failed"
    assert result.engine_result == "pre_submit_failed"
    signing.assert_not_called()
    submitting.assert_not_called()


@pytest.mark.parametrize("method", ["multisign_and_submit", "attempt_single_sig_submit"])
def test_malformed_destination_is_local_failure(protected_adapter, wallets, method):
    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=_autofill_stub), \
            patch("signet.adapters.xrpl_adapter.submit_and_wait") as submitting:
        result = getattr(protected_adapter, method)(intent_for(wallets, "fabricated"), "aa" * 32)
    assert result.outcome == "failed"
    assert result.engine_result == "pre_submit_failed"
    submitting.assert_not_called()


def test_multisig_transport_failure_remains_unknown_with_hash(protected_adapter, wallets):
    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=_autofill_stub), \
            patch("signet.adapters.xrpl_adapter.submit_and_wait", side_effect=TimeoutError("timed out")):
        result = protected_adapter.multisign_and_submit(intent_for(wallets), "aa" * 32)
    assert result.outcome == "unknown"
    assert len(result.tx_hash) == 64
    assert result.engine_result == "submission_unknown"


@pytest.mark.parametrize("code,expected", [
    ("tefBAD_QUORUM", "rejected"),
    ("tefBAD_SIGNATURE", "rejected"),
    ("tesSUCCESS", "unknown"),
    ("tecUNFUNDED_PAYMENT", "unknown"),
    ("terQUEUED", "unknown"),
])
def test_single_signature_uses_actual_engine_response(protected_adapter, wallets, code, expected):
    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=_autofill_stub), \
            patch("signet.adapters.xrpl_adapter.submit") as submitting:
        submitting.return_value.result = {"engine_result": code}
        result = protected_adapter.attempt_single_sig_submit(intent_for(wallets), "aa" * 32)
    submitted = submitting.call_args.args[0]
    assert len(submitted.signers) == 1
    assert submitted.signers[0].account == wallets.agent.classic_address
    assert submitting.call_args.kwargs["fail_hard"] is True
    assert result.outcome == expected
    assert result.engine_result == code


def test_exception_text_cannot_impersonate_a_ledger_rejection(protected_adapter, wallets):
    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=_autofill_stub), \
            patch("signet.adapters.xrpl_adapter.submit", side_effect=TimeoutError("tefBAD_QUORUM")):
        result = protected_adapter.attempt_single_sig_submit(intent_for(wallets), "aa" * 32)
    assert result.outcome == "unknown"
    assert result.engine_result == "submission_unknown"


def test_protection_is_rechecked_before_each_submission(protected_adapter, wallets):
    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=_autofill_stub), \
            patch("signet.adapters.xrpl_adapter.submit_and_wait") as submitting:
        submitting.return_value.result = {"validated": True, "meta": {"TransactionResult": "tesSUCCESS"}}
        first = protected_adapter.multisign_and_submit(intent_for(wallets), "aa" * 32)
        protected_adapter.client.request.return_value.result["account_data"]["Flags"] = 0
        second = protected_adapter.multisign_and_submit(intent_for(wallets), "bb" * 32)
    assert first.outcome == "success"
    assert second.outcome == "failed"
    assert submitting.call_count == 1


def test_same_account_adapters_serialize_autofill_through_submission(wallets):
    clients = [Mock(), Mock()]
    for client in clients:
        client.request.return_value.result = protected_response(wallets)
    adapters = [XRPLAdapter(wallets, client) for client in clients]
    first_submitted = Event()
    release_first = Event()
    second_attempted = Event()
    guard = Lock()
    autofill_count = 0

    def filling(tx, *args, **kwargs):
        nonlocal autofill_count
        with guard:
            autofill_count += 1
        return _autofill_stub(tx)

    def submitting(*args, **kwargs):
        if not first_submitted.is_set():
            first_submitted.set()
            assert release_first.wait(3)
        return SimpleNamespace(result={"validated": True, "meta": {"TransactionResult": "tesSUCCESS"}})

    def second():
        second_attempted.set()
        return adapters[1].multisign_and_submit(intent_for(wallets), "bb" * 32)

    with patch("signet.adapters.xrpl_adapter.autofill", side_effect=filling), \
            patch("signet.adapters.xrpl_adapter.submit_and_wait", side_effect=submitting), \
            ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(adapters[0].multisign_and_submit, intent_for(wallets), "aa" * 32)
        assert first_submitted.wait(3)
        second_future = pool.submit(second)
        assert second_attempted.wait(3)
        try:
            assert not second_future.done()
            assert autofill_count == 1
        finally:
            release_first.set()
        assert first.result().outcome == second_future.result().outcome == "success"
