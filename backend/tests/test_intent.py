import pytest

from signet.domain import Intent, IntentAction


def make(**over):
    base = dict(
        action=IntentAction.PAYMENT,
        from_account="rAgentAccount",
        to_account="rDest",
        amount=100.0,
        asset="XRP",
        rationale="test",
    )
    base.update(over)
    return Intent(**base)


def test_intent_constructs():
    intent = make()
    assert intent.amount == 100.0
    assert intent.id  # has generated id


def test_intent_rejects_nonpositive_amount():
    with pytest.raises(ValueError):
        make(amount=0)
    with pytest.raises(ValueError):
        make(amount=-1)


def test_intent_requires_accounts_and_asset():
    with pytest.raises(ValueError):
        make(to_account="")
    with pytest.raises(ValueError):
        make(from_account="")
    with pytest.raises(ValueError):
        make(asset="")


def test_notional_usd():
    intent = make(amount=5000, asset="XRP")
    assert intent.notional_usd({"XRP": 0.5}) == 2500


def test_notional_missing_price():
    intent = make(asset="BTC")
    with pytest.raises(KeyError):
        intent.notional_usd({"XRP": 0.5})
