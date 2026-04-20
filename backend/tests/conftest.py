import pytest

from signet.domain import PolicyConfig, PolicyEngine
from signet.domain.policy import InMemoryKYT

TREASURY = "rTreasuryVaultXXXXXXXXXXXXXXXXXXXXXXXX"
ATTACKER = "rAttacker42HJKLXXXXXXXXXXXXXXXXXXXXX"


@pytest.fixture
def config() -> PolicyConfig:
    return PolicyConfig.from_dict(
        {
            "allowlist_destinations": [TREASURY],
            "allowlist_assets": ["XRP", "RLUSD"],
            "per_tx_cap_usd": 25_000,
            "daily_cap_usd": 100_000,
            "escalation_tier_threshold_usd": 100_000,
            "xrp_usd_price": 0.50,
        }
    )


@pytest.fixture
def engine(config: PolicyConfig) -> PolicyEngine:
    return PolicyEngine(config=config, kyt=InMemoryKYT(blocklist=frozenset({ATTACKER})))
