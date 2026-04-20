"""PolicyEngine — pure, deterministic rule evaluation. No I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol

from .intent import Intent


class RuleStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class Decision(str, Enum):
    ALLOW = "allow"
    REFUSE = "refuse"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class RuleCheck:
    name: str
    status: RuleStatus
    detail: str

    @property
    def passed(self) -> bool:
        return self.status == RuleStatus.PASS


@dataclass(frozen=True)
class EvaluationResult:
    decision: Decision
    checks: tuple[RuleCheck, ...]
    notional_usd: float
    reason: str = ""

    @property
    def failed_checks(self) -> tuple[RuleCheck, ...]:
        return tuple(c for c in self.checks if not c.passed)


@dataclass(frozen=True)
class PolicyConfig:
    allowlist_destinations: frozenset[str]
    allowlist_assets: frozenset[str]
    per_tx_cap_usd: float
    daily_cap_usd: float
    escalation_tier_threshold_usd: float
    price_table: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "PolicyConfig":
        return cls(
            allowlist_destinations=frozenset(d["allowlist_destinations"]),
            allowlist_assets=frozenset(d["allowlist_assets"]),
            per_tx_cap_usd=float(d["per_tx_cap_usd"]),
            daily_cap_usd=float(d["daily_cap_usd"]),
            escalation_tier_threshold_usd=float(d["escalation_tier_threshold_usd"]),
            price_table={"XRP": float(d.get("xrp_usd_price", 0.5)), "RLUSD": 1.0},
        )


class KYTPort(Protocol):
    def score(self, address: str) -> float: ...


@dataclass
class InMemoryKYT:
    """Mock KYT: deterministic score from address hash. Default for domain tests."""
    blocklist: frozenset[str] = frozenset()

    def score(self, address: str) -> float:
        if address in self.blocklist:
            return 1.0
        return (sum(address.encode("utf-8")) % 100) / 1000.0  # 0.0..0.099


KYT_THRESHOLD = 0.75


@dataclass
class PolicyEngine:
    config: PolicyConfig
    kyt: KYTPort
    daily_spent_usd: float = 0.0

    def evaluate(self, intent: Intent) -> EvaluationResult:
        notional = intent.notional_usd(self.config.price_table)
        requires_escalation = notional >= self.config.escalation_tier_threshold_usd

        checks: list[RuleCheck] = []
        # Integrity rules apply to every tier.
        checks.append(self._check_destination(intent))
        checks.append(self._check_asset(intent))
        checks.append(self._check_kyt(intent))
        # Quantitative caps apply only to the instant tier; over-threshold
        # trades are routed to human approval and evaluated under a
        # different authority.
        if not requires_escalation:
            checks.append(self._check_per_tx_cap(intent, notional))
            checks.append(self._check_daily_cap(notional))

        hard_failed = [c for c in checks if not c.passed]
        if hard_failed:
            return EvaluationResult(
                decision=Decision.REFUSE,
                checks=tuple(checks),
                notional_usd=notional,
                reason="; ".join(c.detail for c in hard_failed),
            )

        if requires_escalation:
            return EvaluationResult(
                decision=Decision.ESCALATE,
                checks=tuple(checks),
                notional_usd=notional,
                reason=f"notional ${notional:,.0f} exceeds escalation threshold ${self.config.escalation_tier_threshold_usd:,.0f}",
            )

        return EvaluationResult(
            decision=Decision.ALLOW,
            checks=tuple(checks),
            notional_usd=notional,
        )

    def record_spend(self, usd: float) -> None:
        self.daily_spent_usd += usd

    # rules
    def _check_destination(self, intent: Intent) -> RuleCheck:
        ok = intent.to_account in self.config.allowlist_destinations
        return RuleCheck(
            name="allowlist_destination",
            status=RuleStatus.PASS if ok else RuleStatus.FAIL,
            detail=(
                f"destination {intent.to_account} on allowlist"
                if ok
                else f"destination {intent.to_account} NOT on allowlist"
            ),
        )

    def _check_asset(self, intent: Intent) -> RuleCheck:
        ok = intent.asset in self.config.allowlist_assets
        return RuleCheck(
            name="allowlist_asset",
            status=RuleStatus.PASS if ok else RuleStatus.FAIL,
            detail=(
                f"asset {intent.asset} on allowlist"
                if ok
                else f"asset {intent.asset} NOT on allowlist"
            ),
        )

    def _check_per_tx_cap(self, intent: Intent, notional: float) -> RuleCheck:
        ok = notional <= self.config.per_tx_cap_usd
        return RuleCheck(
            name="per_tx_cap",
            status=RuleStatus.PASS if ok else RuleStatus.FAIL,
            detail=(
                f"notional ${notional:,.0f} within per-tx cap ${self.config.per_tx_cap_usd:,.0f}"
                if ok
                else f"notional ${notional:,.0f} exceeds per-tx cap ${self.config.per_tx_cap_usd:,.0f}"
            ),
        )

    def _check_daily_cap(self, notional: float) -> RuleCheck:
        projected = self.daily_spent_usd + notional
        ok = projected <= self.config.daily_cap_usd
        return RuleCheck(
            name="daily_cap",
            status=RuleStatus.PASS if ok else RuleStatus.FAIL,
            detail=(
                f"projected daily spend ${projected:,.0f} within cap ${self.config.daily_cap_usd:,.0f}"
                if ok
                else f"projected daily spend ${projected:,.0f} exceeds cap ${self.config.daily_cap_usd:,.0f}"
            ),
        )

    def _check_kyt(self, intent: Intent) -> RuleCheck:
        score = self.kyt.score(intent.to_account)
        ok = score < KYT_THRESHOLD
        return RuleCheck(
            name="kyt_sanctions",
            status=RuleStatus.PASS if ok else RuleStatus.FAIL,
            detail=(
                f"KYT score {score:.2f} below threshold {KYT_THRESHOLD}"
                if ok
                else f"KYT score {score:.2f} at/above threshold {KYT_THRESHOLD}"
            ),
        )
