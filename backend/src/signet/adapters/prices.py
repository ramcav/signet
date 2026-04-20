"""Live XRP/USD price via CoinGecko, with fallback."""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price?ids=ripple&vs_currencies=usd"
)
FALLBACK_XRP_USD = 0.50


def fetch_xrp_usd(timeout: float = 3.0) -> float:
    try:
        r = httpx.get(COINGECKO_URL, timeout=timeout)
        r.raise_for_status()
        return float(r.json()["ripple"]["usd"])
    except Exception as exc:  # network / shape / rate-limit
        log.warning("coingecko fetch failed: %s — falling back to $%.2f", exc, FALLBACK_XRP_USD)
        return FALLBACK_XRP_USD


def price_table(xrp_usd: float | None = None) -> dict[str, float]:
    if xrp_usd is None:
        xrp_usd = fetch_xrp_usd()
    return {"XRP": xrp_usd, "RLUSD": 1.0}
