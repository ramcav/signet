"""Timestamped XRP/USD quotes with bounded freshness and explicit demo mode."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import httpx

from ..domain.numbers import positive_float

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=ripple&vs_currencies=usd&include_last_updated_at=true"
)


class PriceUnavailable(RuntimeError):
    """No valid quote is available within the configured freshness window."""


@dataclass(frozen=True)
class PriceQuote:
    price_usd: float
    source: str
    as_of: datetime
    demo: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "price_usd", positive_float(self.price_usd, "quote price"))
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("quote source required")
        if not isinstance(self.as_of, datetime) or self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("quote as_of must be timezone-aware")
        if not isinstance(self.demo, bool):
            raise ValueError("quote demo flag must be boolean")
        object.__setattr__(self, "as_of", self.as_of.astimezone(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "price_usd": self.price_usd,
            "source": self.source,
            "as_of": self.as_of.isoformat().replace("+00:00", "Z"),
            "demo": self.demo,
        }


def fetch_xrp_quote(timeout: float = 3.0) -> PriceQuote:
    try:
        response = httpx.get(COINGECKO_URL, timeout=timeout)
        response.raise_for_status()
        value = response.json()["ripple"]
        timestamp = positive_float(value["last_updated_at"], "provider timestamp")
        return PriceQuote(value["usd"], "coingecko", datetime.fromtimestamp(timestamp, timezone.utc))
    except Exception as exc:
        raise PriceUnavailable("XRP/USD quote unavailable from CoinGecko") from exc


def fetch_xrp_usd(timeout: float = 3.0) -> float:
    """Legacy price helper, deliberately without any implicit fallback."""
    return fetch_xrp_quote(timeout).price_usd


class PriceService:
    def __init__(
        self,
        fetcher: Callable[[], float | PriceQuote] | None = None,
        clock: Callable[[], datetime] | None = None,
        ttl_seconds: float = 60.0,
        demo_price: float | None = None,
    ) -> None:
        self.fetcher = fetcher or fetch_xrp_quote
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.ttl_seconds = positive_float(ttl_seconds, "quote TTL")
        self.demo_price = None if demo_price is None else positive_float(demo_price, "demo price")
        self._quote: PriceQuote | None = None

    def _fresh(self, quote: PriceQuote, now: datetime) -> bool:
        return 0 <= (now - quote.as_of).total_seconds() < self.ttl_seconds

    def assert_fresh(self, quote: PriceQuote) -> None:
        """Check the evaluated quote again immediately before signing."""
        try:
            if not isinstance(quote, PriceQuote) or not self._fresh(quote, self.clock()):
                raise ValueError("quote is stale or has a future timestamp")
        except Exception as exc:
            raise PriceUnavailable("evaluated XRP/USD quote is no longer fresh") from exc

    def get_quote(self) -> PriceQuote:
        try:
            now = self.clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("quote clock must be timezone-aware")
            if self._quote is not None and self._fresh(self._quote, now):
                return self._quote
            if self.demo_price is not None:
                quote = PriceQuote(self.demo_price, "explicit-demo", now, demo=True)
            else:
                fetched = self.fetcher()
                quote = fetched if isinstance(fetched, PriceQuote) else PriceQuote(fetched, "injected-provider", now)
            self.assert_fresh(quote)
            self._quote = quote
            return quote
        except Exception as exc:
            raise PriceUnavailable("fresh XRP/USD quote unavailable") from exc


def price_table(xrp_usd: float | None = None) -> dict[str, float]:
    return {"XRP": positive_float(fetch_xrp_usd() if xrp_usd is None else xrp_usd, "XRP price")}
