"""Wallet setup acceptance tests: network calls are mocked, signatures are real."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from xrpl.models.transactions import AccountSet, SetRegularKey, SignerListSet, Transaction
from xrpl.wallet import Wallet

from signet.adapters import xrpl_adapter as xrpl


@pytest.fixture
def wallets():
    return xrpl.WalletSet(Wallet.create(), Wallet.create(), Wallet.create())


def state_for(wallets, *, protected=False, regular_key=None):
    data = {
        "validated": True,
        "account_data": {
            "Account": wallets.master.classic_address,
            "Flags": 0x00100000 if protected else 0,
            "Balance": "100000000",
        },
        "signer_lists": [],
    }
    if regular_key:
        data["account_data"]["RegularKey"] = regular_key
    if protected:
        data["signer_lists"] = [{"SignerQuorum": 2, "SignerEntries": [
            {"SignerEntry": {"Account": wallets.agent.classic_address, "SignerWeight": 1}},
            {"SignerEntry": {"Account": wallets.policy.classic_address, "SignerWeight": 1}},
        ]}]
    return data


class Ledger:
    def __init__(self, wallets, *, protected=False, regular_key=None):
        self.state = state_for(wallets, protected=protected, regular_key=regular_key)
        self.client = Mock()
        self.client.request.side_effect = self.request
        self.submissions = []

    def request(self, request):
        assert request.ledger_index == "validated"
        return SimpleNamespace(result=copy.deepcopy(self.state))

    def submit(self, transaction, client, wallet=None):
        self.submissions.append(transaction)
        if isinstance(transaction, SignerListSet):
            self.state["signer_lists"] = [{
                "SignerQuorum": transaction.signer_quorum,
                "SignerEntries": [{"SignerEntry": {
                    "Account": signer.account, "SignerWeight": signer.signer_weight,
                }} for signer in transaction.signer_entries],
            }]
        elif isinstance(transaction, SetRegularKey):
            assert transaction.regular_key is None
            self.state["account_data"].pop("RegularKey", None)
        elif isinstance(transaction, AccountSet):
            assert self.state["signer_lists"][0]["SignerQuorum"] == 2
            assert "RegularKey" not in self.state["account_data"]
            assert wallet is not None  # only the master can disable itself
            assert transaction.set_flag == 4
            self.state["account_data"]["Flags"] |= 0x00100000
        else:
            raise AssertionError(type(transaction))
        return SimpleNamespace(result={"validated": True, "meta": {"TransactionResult": "tesSUCCESS"}})


def test_save_wallets_never_overwrites_existing_seeds(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        xrpl.save_wallets(xrpl.WalletSet(Wallet.create(), Wallet.create(), Wallet.create()), path)
    assert path.read_bytes() == before


def test_runtime_can_load_master_address_without_private_key(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    runtime = xrpl.load_wallets(path, include_master_seed=False)
    assert runtime.master.classic_address == wallets.master.classic_address
    assert not getattr(runtime.master, "seed", None)
    assert not getattr(runtime.master, "private_key", None)
    assert runtime.agent.private_key == wallets.agent.private_key
    xrpl.XRPLAdapter(runtime, Ledger(wallets, protected=True).client).assert_protected()


def test_wallet_file_mismatched_address_is_refused(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    data = wallets.to_json()
    data["agent"]["address"] = wallets.policy.classic_address
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="address"):
        xrpl.load_wallets(path)


def test_existing_unprotected_wallet_refuses_without_explicit_securing(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    before = path.read_bytes()
    ledger = Ledger(wallets)
    with patch.object(xrpl, "submit_and_wait") as submitting, \
            patch.object(xrpl, "generate_faucet_wallet") as faucet:
        with pytest.raises(xrpl.WalletProtectionError):
            xrpl.bootstrap_wallets(ledger.client, path=path)
    submitting.assert_not_called()
    faucet.assert_not_called()
    assert path.read_bytes() == before


def test_existing_protected_wallet_is_audit_only(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    before = path.read_bytes()
    with patch.object(xrpl, "submit_and_wait") as submitting, \
            patch.object(xrpl, "generate_faucet_wallet") as faucet:
        result = xrpl.bootstrap_wallets(Ledger(wallets, protected=True).client, path=path)
    assert result.master.classic_address == wallets.master.classic_address
    submitting.assert_not_called()
    faucet.assert_not_called()
    assert path.read_bytes() == before


def test_explicit_secure_removes_regular_key_and_disables_master(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    before = path.read_bytes()
    ledger = Ledger(wallets, regular_key=Wallet.create().classic_address)
    with patch.object(xrpl, "submit_and_wait", side_effect=ledger.submit), \
            patch.object(xrpl, "generate_faucet_wallet") as faucet:
        xrpl.bootstrap_wallets(ledger.client, path=path, secure_existing=True)
    assert [type(tx) for tx in ledger.submissions] == [SignerListSet, SetRegularKey, AccountSet]
    xrpl.XRPLAdapter(wallets, ledger.client).assert_protected()
    faucet.assert_not_called()
    assert path.read_bytes() == before


def test_setup_must_confirm_signer_list_before_disabling_master(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    ledger = Ledger(wallets)
    # A purported success without the expected validated state is insufficient.
    with patch.object(xrpl, "submit_and_wait", return_value=SimpleNamespace(result={
        "validated": True, "meta": {"TransactionResult": "tesSUCCESS"},
    })) as submitting:
        with pytest.raises(xrpl.WalletProtectionError):
            xrpl.bootstrap_wallets(ledger.client, path=path, secure_existing=True)
    assert submitting.call_count == 1
    assert isinstance(submitting.call_args.args[0], SignerListSet)


def test_setup_does_not_accept_unvalidated_success(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    with patch.object(xrpl, "submit_and_wait", return_value=SimpleNamespace(result={
        "validated": False, "meta": {"TransactionResult": "tesSUCCESS"},
    })) as submitting:
        with pytest.raises(RuntimeError):
            xrpl.bootstrap_wallets(Ledger(wallets).client, path=path, secure_existing=True)
    assert submitting.call_count == 1


def test_new_seeds_are_saved_before_funding_and_irreversible_setup(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    ledger = Ledger(wallets)
    funded = set()

    def request(req):
        if req.account not in funded:
            return SimpleNamespace(result={"error": "actNotFound"})
        return ledger.request(req)

    def faucet(client, wallet, debug=False):
        assert xrpl.load_wallets(path).to_json() == wallets.to_json()
        funded.add(wallet.classic_address)
        return wallet

    ledger.client.request.side_effect = request
    with patch.object(xrpl.Wallet, "create", side_effect=[wallets.master, wallets.agent, wallets.policy]), \
            patch.object(xrpl, "generate_faucet_wallet", side_effect=faucet), \
            patch.object(xrpl, "submit_and_wait", side_effect=ledger.submit):
        result = xrpl.bootstrap_wallets(ledger.client, path=path)
    assert result.to_json() == wallets.to_json()
    assert len(funded) == 3
    xrpl.XRPLAdapter(result, ledger.client).assert_protected()


def test_failed_configuration_resumes_with_original_seeds(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    original = path.read_bytes()
    ledger = Ledger(wallets)

    def uncertain_submit(*args, **kwargs):
        ledger.submit(*args, **kwargs)
        raise TimeoutError("confirmation unavailable")

    with patch.object(xrpl, "submit_and_wait", side_effect=uncertain_submit):
        with pytest.raises(TimeoutError):
            xrpl.bootstrap_wallets(ledger.client, path=path, secure_existing=True)
    with patch.object(xrpl, "submit_and_wait", side_effect=ledger.submit):
        xrpl.bootstrap_wallets(ledger.client, path=path, secure_existing=True)
    assert path.read_bytes() == original
    assert [type(tx) for tx in ledger.submissions] == [SignerListSet, AccountSet]
    xrpl.XRPLAdapter(wallets, ledger.client).assert_protected()


def test_disabled_master_with_regular_key_can_be_secured_by_multisign(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    ledger = Ledger(wallets, protected=True, regular_key=Wallet.create().classic_address)

    def fill(transaction, *args, **kwargs):
        data = transaction.to_dict()
        data.update(sequence=1, fee="36", last_ledger_sequence=1000)
        return Transaction.from_dict(data)

    with patch.object(xrpl, "autofill", side_effect=fill), \
            patch.object(xrpl, "submit_and_wait", side_effect=ledger.submit):
        xrpl.bootstrap_wallets(ledger.client, path=path, secure_existing=True)
    assert len(ledger.submissions) == 1
    assert len(ledger.submissions[0].signers) == 2
    assert all(s.txn_signature for s in ledger.submissions[0].signers)
    xrpl.XRPLAdapter(wallets, ledger.client).assert_protected()


def script_module(name):
    path = Path(__file__).parents[2] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fund_script_audits_existing_wallet_instead_of_overwriting(tmp_path, wallets):
    script = script_module("fund_wallets")
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    original = path.read_bytes()
    with patch.object(script, "JsonRpcClient", return_value=Ledger(wallets).client), \
            patch.object(xrpl, "submit_and_wait") as submitting, \
            patch.object(xrpl, "generate_faucet_wallet") as faucet:
        with pytest.raises(xrpl.WalletProtectionError):
            script.main(["--wallets", str(path)])
    submitting.assert_not_called()
    faucet.assert_not_called()
    assert path.read_bytes() == original


def test_fund_script_supports_explicit_secure_existing(tmp_path, wallets):
    script = script_module("fund_wallets")
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    ledger = Ledger(wallets)
    with patch.object(script, "JsonRpcClient", return_value=ledger.client), \
            patch.object(xrpl, "submit_and_wait", side_effect=ledger.submit):
        script.main(["--wallets", str(path), "--secure-existing"])
    xrpl.XRPLAdapter(wallets, ledger.client).assert_protected()


def test_topup_refuses_unprotected_wallet_before_faucet(tmp_path, wallets):
    script = script_module("topup")
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    with patch.object(script, "JsonRpcClient", return_value=Ledger(wallets).client), \
            patch.object(script, "generate_faucet_wallet") as faucet:
        with pytest.raises(xrpl.WalletProtectionError):
            script.main(rounds=1, path=path)
    faucet.assert_not_called()


def test_smoke_refuses_unprotected_wallet_before_submit(tmp_path, wallets):
    script = script_module("smoke_multisig")
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    adapter = xrpl.XRPLAdapter(wallets, Ledger(wallets).client)
    with patch.object(script, "XRPLAdapter", return_value=adapter), \
            patch.object(adapter, "multisign_and_submit") as submitting:
        with pytest.raises(xrpl.WalletProtectionError):
            script.main(["--wallets", str(path)])
    submitting.assert_not_called()


@pytest.mark.parametrize("validated", [True, False])
def test_smoke_persists_real_demo_receipt_before_submission(tmp_path, wallets, validated):
    from signet.domain import verify_receipt

    script = script_module("smoke_multisig")
    path = tmp_path / "wallets.json"
    receipt_path = tmp_path / "receipt.json"
    xrpl.save_wallets(wallets, path)
    adapter = xrpl.XRPLAdapter(wallets, Ledger(wallets, protected=True).client)

    def submitting(intent, root):
        document = json.loads(receipt_path.read_text())
        assert verify_receipt(document, root)
        assert document["payload"]["intent"]["from_account"] == wallets.master.classic_address
        assert document["payload"]["intent"]["amount"] == "1"
        assert document["payload"]["quote"]["demo"] is True
        assert document["payload"]["evaluation"]["decision"] == "allow"
        return xrpl.TxResult("a" * 64, "", root, "tesSUCCESS", validated, {})

    with patch.object(script, "XRPLAdapter", return_value=adapter), \
            patch.object(adapter, "multisign_and_submit", side_effect=submitting):
        arguments = ["--wallets", str(path), "--receipt", str(receipt_path)]
        if validated:
            script.main(arguments)
        else:
            with pytest.raises(SystemExit) as failure:
                script.main(arguments)
            assert failure.value.code == 1
    assert receipt_path.exists()


@pytest.mark.parametrize("name", ["fund_wallets", "topup", "smoke_multisig"])
def test_script_entry_points_have_safe_help(name):
    path = Path(__file__).parents[2] / "scripts" / f"{name}.py"
    with patch("sys.argv", [str(path), "--help"]):
        with pytest.raises(SystemExit) as result:
            runpy.run_path(str(path), run_name="__main__")
    assert result.value.code == 0


def test_setup_with_unknown_funding_state_never_requests_faucet(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    client = Mock()
    client.request.return_value.result = {"error": "tooBusy"}
    with patch.object(xrpl, "generate_faucet_wallet") as faucet, \
            patch.object(xrpl, "submit_and_wait") as submitting:
        with pytest.raises(xrpl.WalletProtectionError):
            xrpl.bootstrap_wallets(client, path=path, secure_existing=True)
    faucet.assert_not_called()
    submitting.assert_not_called()


def test_disabled_master_and_unexpected_signers_refuses_mutation(tmp_path, wallets):
    path = tmp_path / "wallets.json"
    xrpl.save_wallets(wallets, path)
    ledger = Ledger(wallets, protected=True)
    ledger.state["signer_lists"][0]["SignerQuorum"] = 1
    with patch.object(xrpl, "submit_and_wait") as submitting:
        with pytest.raises(xrpl.WalletProtectionError):
            xrpl.bootstrap_wallets(ledger.client, path=path, secure_existing=True)
    submitting.assert_not_called()
