import pytest
from decimal import Decimal

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


@pytest.mark.parametrize("amount", [True, False, float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", 0.0000001, "1.0000001"])
def test_rejects_invalid_native_amount(amount):
    with pytest.raises(ValueError):
        make(amount=amount)


def test_amount_preserves_exact_decimal_drops():
    value = make(amount="12345.123456")
    assert isinstance(value.amount, Decimal)
    assert value.amount == Decimal("12345.123456")
    assert make(amount="0.000001").amount == Decimal("0.000001")


def test_native_amount_cannot_exceed_protocol_maximum():
    assert make(amount="100000000000").amount == Decimal("100000000000")
    with pytest.raises(ValueError, match="maximum"):
        make(amount="100000000000.000001")


@pytest.mark.parametrize("value", ["1e10000", "1e-10000", "0e10000", "1e1024", "1" * 1025])
def test_canonical_decimal_size_is_bounded_before_formatting(value):
    from signet.domain.numbers import decimal_text

    with pytest.raises(ValueError, match="size"):
        decimal_text(value)


def test_unsupported_asset_amount_cannot_expand_an_unbounded_receipt():
    with pytest.raises(ValueError, match="size"):
        make(asset="UNKNOWN", amount="1e10000")


@pytest.mark.parametrize("price", [True, 0, -1, float("nan"), float("inf")])
def test_notional_rejects_invalid_prices(price):
    with pytest.raises(ValueError):
        make().notional_usd({"XRP": price})


def test_agent_rejects_boolean_amount_before_numeric_conversion():
    from types import SimpleNamespace
    from signet.adapters.agent import OpenAIAgentAdapter

    call = SimpleNamespace(function=SimpleNamespace(name="submit_payment", arguments='{"destination":"treasury_vault","amount":true,"asset":"XRP","rationale":"test"}'))
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], content=None))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    adapter = OpenAIAgentAdapter("rMaster", "rTreasury", "rIssuer", client=client)
    with pytest.raises(ValueError):
        adapter.propose("send")
