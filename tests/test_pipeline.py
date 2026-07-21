from datetime import datetime, timezone
from decimal import Decimal

from trading_intelligence.application import FixedRiskPolicy, WeightedConsensus
from trading_intelligence.domain import AccountState, AgentAssessment, DecisionStatus, Side, Signal


def test_consensus_abstains_when_no_signal():
    decision = WeightedConsensus().decide(None, [], datetime.now(timezone.utc))
    assert decision.status == DecisionStatus.HOLD
    assert decision.side == Side.FLAT


def test_risk_rejects_when_drawdown_limit_is_reached():
    now = datetime.now(timezone.utc)
    signal = Signal("test", "XAUUSD", Side.BUY, Decimal("90"), now, "test")
    assessment = AgentAssessment("test", Decimal("90"), True, "test", now)
    decision = WeightedConsensus().decide(signal, [assessment], now)
    account = AccountState(Decimal("10000"), Decimal("10000"), Decimal("0"), Decimal("500"), 0)
    result = FixedRiskPolicy(Decimal("500"), 2, Decimal("0.01")).assess(decision, account)
    assert not result.approved
