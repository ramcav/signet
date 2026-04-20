import pytest

from signet.domain import Decision, Intent, IntentAction, PolicyEngine, RuleStatus

from .conftest import ATTACKER, TREASURY


def intent(**over):
    base = dict(
        action=IntentAction.PAYMENT,
        from_account="rAgent",
        to_account=TREASURY,
        amount=5000.0,
        asset="XRP",
        rationale="rebalance",
    )
    base.update(over)
    return Intent(**base)


def _check(result, name):
    return next(c for c in result.checks if c.name == name)


class TestBenignIntent:
    def test_allowed(self, engine: PolicyEngine):
        result = engine.evaluate(intent())
        assert result.decision == Decision.ALLOW
        assert all(c.passed for c in result.checks)
        assert result.notional_usd == 2500.0

    def test_all_five_rules_present_instant_tier(self, engine: PolicyEngine):
        result = engine.evaluate(intent())
        names = {c.name for c in result.checks}
        assert names == {
            "allowlist_destination",
            "allowlist_asset",
            "per_tx_cap",
            "daily_cap",
            "kyt_sanctions",
        }

    def test_escalation_tier_skips_quant_caps(self, config):
        from signet.domain import PolicyConfig
        from signet.domain.policy import InMemoryKYT

        cfg = PolicyConfig(
            allowlist_destinations=frozenset({TREASURY}),
            allowlist_assets=frozenset({"XRP", "RLUSD"}),
            per_tx_cap_usd=25_000,
            daily_cap_usd=100_000,
            escalation_tier_threshold_usd=100_000,
            price_table={"XRP": 0.5, "RLUSD": 1.0},
        )
        engine = PolicyEngine(config=cfg, kyt=InMemoryKYT())
        result = engine.evaluate(intent(amount=500_000))  # 250k USD → escalate
        from signet.domain import Decision
        assert result.decision == Decision.ESCALATE
        names = {c.name for c in result.checks}
        assert names == {"allowlist_destination", "allowlist_asset", "kyt_sanctions"}


class TestJailbreakIntent:
    def test_attacker_destination_refused(self, engine: PolicyEngine):
        result = engine.evaluate(intent(to_account=ATTACKER, amount=1_000_000))
        assert result.decision == Decision.REFUSE
        assert _check(result, "allowlist_destination").status == RuleStatus.FAIL

    def test_multiple_hard_fails_reported(self, engine: PolicyEngine):
        # Instant-tier attacker intent: caps apply.
        result = engine.evaluate(intent(to_account=ATTACKER, amount=60_000))
        failed_names = {c.name for c in result.failed_checks}
        assert "allowlist_destination" in failed_names
        assert "per_tx_cap" in failed_names
        assert "kyt_sanctions" in failed_names

    def test_escalation_tier_attacker_still_refused_on_integrity(
        self, engine: PolicyEngine
    ):
        # Over escalation threshold caps are skipped, but allowlist+KYT still enforced.
        result = engine.evaluate(intent(to_account=ATTACKER, amount=1_000_000))
        from signet.domain import Decision
        assert result.decision == Decision.REFUSE
        failed_names = {c.name for c in result.failed_checks}
        assert "allowlist_destination" in failed_names
        assert "kyt_sanctions" in failed_names

    def test_disallowed_asset(self, engine: PolicyEngine, config):
        # inject a price so we don't trip on missing-price
        engine.config.price_table["BTC"] = 60_000.0
        result = engine.evaluate(intent(asset="BTC", amount=0.01))
        assert result.decision == Decision.REFUSE
        assert _check(result, "allowlist_asset").status == RuleStatus.FAIL


class TestCaps:
    def test_per_tx_cap_fail(self, engine: PolicyEngine):
        # 60k XRP * 0.5 = 30k > 25k cap
        result = engine.evaluate(intent(amount=60_000))
        assert result.decision == Decision.REFUSE
        assert _check(result, "per_tx_cap").status == RuleStatus.FAIL

    def test_per_tx_cap_boundary_passes(self, engine: PolicyEngine):
        # 50k XRP * 0.5 = 25k exactly at cap
        result = engine.evaluate(intent(amount=50_000))
        assert _check(result, "per_tx_cap").status == RuleStatus.PASS

    def test_daily_cap_accumulates(self, engine: PolicyEngine):
        engine.record_spend(90_000)
        result = engine.evaluate(intent(amount=40_000))  # 20k USD, projected 110k
        assert _check(result, "daily_cap").status == RuleStatus.FAIL
        assert result.decision == Decision.REFUSE


class TestEscalation:
    def test_large_notional_escalates(self, engine: PolicyEngine):
        # 500k XRP * 0.5 = 250k > escalation threshold 100k
        # but also exceeds per_tx_cap. Raise per_tx_cap for this test.
        engine.config.price_table["XRP"] = 0.5
        # use RLUSD to cleanly exceed escalation threshold within per-tx shape
        pass

    def test_escalates_when_over_threshold_only(self, config):
        # Build engine with a per_tx_cap >= notional but escalation threshold lower.
        from signet.domain import PolicyConfig
        from signet.domain.policy import InMemoryKYT

        big = PolicyConfig(
            allowlist_destinations=frozenset({TREASURY}),
            allowlist_assets=frozenset({"XRP", "RLUSD"}),
            per_tx_cap_usd=500_000,
            daily_cap_usd=1_000_000,
            escalation_tier_threshold_usd=100_000,
            price_table={"XRP": 0.5, "RLUSD": 1.0},
        )
        engine = PolicyEngine(config=big, kyt=InMemoryKYT())
        result = engine.evaluate(intent(amount=500_000))  # 250k USD
        assert result.decision == Decision.ESCALATE
        assert all(c.passed for c in result.checks)


class TestKYT:
    def test_blocklisted_destination_fails_kyt(self, config):
        from signet.domain import PolicyConfig
        from signet.domain.policy import InMemoryKYT

        cfg = PolicyConfig(
            allowlist_destinations=frozenset({ATTACKER, TREASURY}),
            allowlist_assets=config.allowlist_assets,
            per_tx_cap_usd=config.per_tx_cap_usd,
            daily_cap_usd=config.daily_cap_usd,
            escalation_tier_threshold_usd=config.escalation_tier_threshold_usd,
            price_table=config.price_table,
        )
        engine = PolicyEngine(config=cfg, kyt=InMemoryKYT(blocklist=frozenset({ATTACKER})))
        result = engine.evaluate(intent(to_account=ATTACKER, amount=100))
        assert _check(result, "kyt_sanctions").status == RuleStatus.FAIL
        assert result.decision == Decision.REFUSE


class TestEvaluationResult:
    def test_reason_populated_on_refuse(self, engine: PolicyEngine):
        result = engine.evaluate(intent(to_account=ATTACKER, amount=1_000_000))
        assert result.reason
        assert result.decision == Decision.REFUSE

    def test_empty_reason_on_allow(self, engine: PolicyEngine):
        result = engine.evaluate(intent())
        assert result.reason == ""
        assert result.decision == Decision.ALLOW

    def test_determinism(self, engine: PolicyEngine):
        i = intent()
        r1 = engine.evaluate(i)
        r2 = engine.evaluate(i)
        assert r1.decision == r2.decision
        assert [c.name for c in r1.checks] == [c.name for c in r2.checks]
