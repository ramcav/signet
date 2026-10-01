from datetime import datetime, timedelta, timezone

import pytest

from signet.adapters import prices


NOW = datetime(2026, 9, 29, 8, tzinfo=timezone.utc)


def test_price_service_exists():
    assert hasattr(prices, "PriceService"), "quotes must be refreshed and validated before evaluation"


@pytest.mark.parametrize("value", [True, False, 0, -1, float("nan"), float("inf")])
def test_quotes_reject_invalid_prices(value):
    with pytest.raises(ValueError):
        prices.PriceQuote(value, "test", NOW)


def test_quote_requires_timezone_and_source():
    with pytest.raises(ValueError):
        prices.PriceQuote(1, "test", NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        prices.PriceQuote(1, "", NOW)


def test_cache_expires_and_refreshes_quote():
    clock = [NOW]
    values = iter([0.50, 0.75])
    service = prices.PriceService(fetcher=lambda: next(values), clock=lambda: clock[0], ttl_seconds=60)
    first = service.get_quote()
    clock[0] += timedelta(seconds=59)
    assert service.get_quote() is first
    clock[0] += timedelta(seconds=1)
    second = service.get_quote()
    assert second.price_usd == 0.75
    assert second.as_of == clock[0]
    assert second.demo is False


def test_stale_cache_is_not_used_after_refresh_failure():
    clock = [NOW]
    calls = [0]

    def fetch():
        calls[0] += 1
        if calls[0] > 1:
            raise RuntimeError("rate limited")
        return 0.5

    service = prices.PriceService(fetcher=fetch, clock=lambda: clock[0], ttl_seconds=10)
    service.get_quote()
    clock[0] += timedelta(seconds=11)
    with pytest.raises(prices.PriceUnavailable, match="unavailable"):
        service.get_quote()


@pytest.mark.parametrize("offset", [-61, 1])
def test_provider_stale_or_future_timestamp_is_rejected(offset):
    service = prices.PriceService(fetcher=lambda: prices.PriceQuote(1, "provider", NOW + timedelta(seconds=offset)), clock=lambda: NOW, ttl_seconds=60)
    with pytest.raises(prices.PriceUnavailable):
        service.get_quote()


def test_explicit_demo_quote_is_marked_and_does_not_fetch():
    def forbidden_fetch():
        raise AssertionError("demo must not fetch")

    service = prices.PriceService(fetcher=forbidden_fetch, clock=lambda: NOW, demo_price=0.5)
    quote = service.get_quote()
    assert quote.to_dict() == {"price_usd": 0.5, "source": "explicit-demo", "as_of": "2026-09-29T08:00:00Z", "demo": True}


def test_fetch_has_no_implicit_fallback(monkeypatch):
    def failure(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(prices.httpx, "get", failure)
    with pytest.raises(prices.PriceUnavailable):
        prices.fetch_xrp_usd()


def test_price_table_contains_only_native_xrp():
    assert prices.price_table(0.5) == {"XRP": 0.5}


def test_quote_must_still_be_fresh_at_signing_time():
    clock = [NOW]
    service = prices.PriceService(fetcher=lambda: 0.5, clock=lambda: clock[0], ttl_seconds=10)
    quote = service.get_quote()
    assert service.assert_fresh(quote) is None
    clock[0] += timedelta(seconds=10)
    with pytest.raises(prices.PriceUnavailable):
        service.assert_fresh(quote)


def test_signing_freshness_check_rejects_future_quote():
    service = prices.PriceService(clock=lambda: NOW, ttl_seconds=10)
    with pytest.raises(prices.PriceUnavailable):
        service.assert_fresh(prices.PriceQuote(0.5, "test", NOW + timedelta(seconds=1)))
