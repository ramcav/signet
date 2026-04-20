"""Intent value object — what an agent proposes to do on-chain."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import uuid4


class IntentAction(str, Enum):
    PAYMENT = "payment"


@dataclass(frozen=True)
class Intent:
    action: IntentAction
    from_account: str
    to_account: str
    amount: float
    asset: str
    rationale: str
    id: str = field(default_factory=lambda: uuid4().hex)
    raw_agent_output: Optional[str] = None

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError("amount must be positive")
        if not self.from_account or not self.to_account:
            raise ValueError("accounts required")
        if not self.asset:
            raise ValueError("asset required")

    def notional_usd(self, price_table: dict[str, float]) -> float:
        price = price_table.get(self.asset)
        if price is None:
            raise KeyError(f"no price for asset {self.asset}")
        return self.amount * price
