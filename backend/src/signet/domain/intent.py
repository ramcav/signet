"""Intent value object — what an agent proposes to do on-chain."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, localcontext
import math
from enum import Enum
from typing import Optional
from uuid import uuid4

from .numbers import decimal_value

# XRPL protocol maximum: 10^11 XRP, represented as 10^17 drops.
# https://xrpl.org/docs/references/protocol/data-types/currency-formats
MAX_XRP_AMOUNT = Decimal("100000000000")


class IntentAction(str, Enum):
    PAYMENT = "payment"


@dataclass(frozen=True)
class Intent:
    action: IntentAction
    from_account: str
    to_account: str
    amount: Decimal
    asset: str
    rationale: str
    id: str = field(default_factory=lambda: uuid4().hex)
    raw_agent_output: Optional[str] = None

    def __post_init__(self) -> None:
        amount = decimal_value(self.amount, "amount", positive=True)
        if self.asset == "XRP":
            if amount > MAX_XRP_AMOUNT:
                raise ValueError("XRP amount exceeds the protocol maximum of 100000000000 XRP")
            parts = amount.as_tuple()
            if parts.exponent < -6 and any(parts.digits[parts.exponent + 6:]):
                raise ValueError("XRP amount must be an exact number of drops (at most six decimal places)")
        object.__setattr__(self, "amount", amount)
        if not all(isinstance(account, str) and account.strip() for account in (self.from_account, self.to_account)):
            raise ValueError("accounts required")
        if not isinstance(self.asset, str) or not self.asset.strip():
            raise ValueError("asset required")

    def notional_usd(self, price_table: dict[str, float]) -> float:
        price = price_table.get(self.asset)
        if price is None:
            raise KeyError(f"no price for asset {self.asset}")
        price_decimal = decimal_value(price, "price", positive=True)
        with localcontext() as context:
            context.prec = max(28, len(self.amount.as_tuple().digits) + len(price_decimal.as_tuple().digits))
            notional = float(self.amount * price_decimal)
        if not math.isfinite(notional) or notional <= 0:
            raise ValueError("notional must be finite and positive")
        return notional
