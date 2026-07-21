"""Tests for all specialist AI agents."""

from datetime import datetime, timezone
from decimal import Decimal

from trading_intelligence.agents.learning_ai import LearningAI, LearningRecommendation
from trading_intelligence.agents.news_ai import NewsAI
from trading_intelligence.agents.risk_ai import RiskManager
from trading_intelligence.agents.session_ai import SessionAI
from trading_intelligence.agents.signal_ai import SignalAI
from trading_intelligence.domain import (
    AccountState,
    AgentAssessment,
    DecisionStatus,
    MarketSnapshot,
    Side,
    TradeDecision,
    TradeOutcome,
)
from uuid import UUID


# ── SignalAI Tests ───────────────────────────────────────────────────

def make_snapshot(
    symbol: str = "EURUSD",
    bid: float = 1.0850,
    ask: float = 1.0852,
    indicators: dict[str, Decimal] | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        timeframe="H1",
        indicators=indicators or {},
    )


def test_signal_ai_abstains_with_no_indicators():
    ai = SignalAI()
    snapshot = make_snapshot()
    result = ai.evaluate(snapshot)
    assert result is None  # No indicators = no signal


def test_signal_ai_bullish_with_trend_and_momentum():
    ai = SignalAI()
    snapshot = make_snapshot(indicators={
        "EMA_12": Decimal("1.0900"),
        "EMA_26": Decimal("1.0850"),
        "EMA_50": Decimal("1.0800"),
        "RSI_14": Decimal("28"),
        "BB_UPPER": Decimal("1.0900"),
        "BB_LOWER": Decimal("1.0790"),
        "BB_MIDDLE": Decimal("1.0845"),
        "PIVOT": Decimal("1.0850"),
        "S1": Decimal("1.0800"),
        "R1": Decimal("1.0900"),
        "ATR_14": Decimal("0.0010"),
    })
    result = ai.evaluate(snapshot)
    # Trend bullish + Momentum oversold = at least 2 buy signals
    assert result is not None
    assert result.side == Side.BUY


def test_signal_ai_bearish_with_trend_and_momentum():
    ai = SignalAI()
    snapshot = make_snapshot(indicators={
        "EMA_12": Decimal("1.0800"),
        "EMA_26": Decimal("1.0850"),
        "EMA_50": Decimal("1.0900"),
        "RSI_14": Decimal("75"),
        "BB_UPPER": Decimal("1.0900"),
        "BB_LOWER": Decimal("1.0790"),
        "BB_MIDDLE": Decimal("1.0845"),
        "PIVOT": Decimal("1.0850"),
        "S1": Decimal("1.0800"),
        "R1": Decimal("1.0900"),
        "ATR_14": Decimal("0.0010"),
    })
    result = ai.evaluate(snapshot)
    assert result is not None
    assert result.side == Side.SELL


def test_signal_ai_includes_stop_loss_take_profit():
    ai = SignalAI()
    snapshot = make_snapshot(indicators={
        "EMA_12": Decimal("1.0900"),
        "EMA_26": Decimal("1.0850"),
        "RSI_14": Decimal("28"),
        "ATR_14": Decimal("0.0010"),
        "BB_UPPER": Decimal("1.0900"),
        "BB_LOWER": Decimal("1.0790"),
        "BB_MIDDLE": Decimal("1.0845"),
        "PIVOT": Decimal("1.0850"),
    })
    result = ai.evaluate(snapshot)
    assert result is not None
    assert result.stop_loss is not None
    assert result.take_profit is not None
    assert result.stop_loss < result.take_profit  # buy: SL < TP


# ── NewsAI Tests ─────────────────────────────────────────────────────

def test_news_ai_defaults_to_eligible_when_no_calendar():
    ai = NewsAI()
    snapshot = make_snapshot()
    result = ai.evaluate(snapshot)
    assert isinstance(result, AgentAssessment)
    assert result.eligible is True
    assert result.agent == "news_ai"


# ── SessionAI Tests ──────────────────────────────────────────────────

def test_session_ai_detect_active_session():
    ai = SessionAI()
    # During London hours
    london_time = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    snapshot = make_snapshot()
    snapshot = MarketSnapshot(
        symbol="EURUSD",
        timestamp=london_time,
        bid=Decimal("1.0850"),
        ask=Decimal("1.0852"),
        timeframe="H1",
    )
    result = ai.evaluate(snapshot)
    assert result.eligible is True
    assert "london" in result.metadata["active_sessions"]


def test_session_ai_weekend_detection():
    ai = SessionAI()
    saturday = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)  # Saturday
    assert ai.is_weekend(saturday) is True

    monday = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    assert ai.is_weekend(monday) is False


# ── RiskManager Tests ─────────────────────────────────────────────────

def test_risk_rejects_when_drawdown_limit_reached():
    now = datetime.now(timezone.utc)
    risk = RiskManager()
    decision = TradeDecision(
        symbol="XAUUSD",
        side=Side.BUY,
        status="approved",
        confidence=Decimal("90"),
        quantity=Decimal("1"),
        created_at=now,
        rationale="test",
    )
    account = AccountState(
        equity=Decimal("10000"),
        balance=Decimal("10000"),
        open_risk=Decimal("0"),
        daily_drawdown=Decimal("500"),  # 5% drawdown
        open_positions=0,
    )
    result = risk.assess(decision, account)
    assert result.approved is False
    assert any("drawdown" in r for r in result.reasons)


def test_risk_rejects_when_max_positions_reached():
    now = datetime.now(timezone.utc)
    risk = RiskManager()
    # Open 3 positions (max from config)
    risk.record_open("EURUSD")
    risk.record_open("GBPUSD")
    risk.record_open("USDJPY")

    decision = TradeDecision(
        symbol="XAUUSD",
        side=Side.BUY,
        status="approved",
        confidence=Decimal("90"),
        quantity=Decimal("1"),
        created_at=now,
        rationale="test",
    )
    account = AccountState(
        equity=Decimal("10000"),
        balance=Decimal("10000"),
        open_risk=Decimal("0"),
        daily_drawdown=Decimal("0"),
        open_positions=3,
    )
    result = risk.assess(decision, account)
    assert result.approved is False
    assert any("positions" in r for r in result.reasons)


def test_risk_approves_when_all_clear():
    now = datetime.now(timezone.utc)
    risk = RiskManager()
    decision = TradeDecision(
        symbol="EURUSD",
        side=Side.BUY,
        status="approved",
        confidence=Decimal("90"),
        quantity=Decimal("1"),
        created_at=now,
        rationale="test",
    )
    account = AccountState(
        equity=Decimal("10000"),
        balance=Decimal("10000"),
        open_risk=Decimal("0"),
        daily_drawdown=Decimal("0"),
        open_positions=0,
    )
    result = risk.assess(decision, account)
    assert result.approved is True
    assert result.approved_quantity > Decimal("0")


def test_risk_correlation_basket_check():
    now = datetime.now(timezone.utc)
    risk = RiskManager()
    # Open EURUSD and EURJPY — both EUR basket
    risk.record_open("EURUSD")
    risk.record_open("EURJPY")

    decision = TradeDecision(
        symbol="EURGBP",  # Also EUR basket — would be 3rd EUR
        side=Side.BUY,
        status="approved",
        confidence=Decimal("90"),
        quantity=Decimal("1"),
        created_at=now,
        rationale="test",
    )
    account = AccountState(
        equity=Decimal("10000"),
        balance=Decimal("10000"),
        open_risk=Decimal("0"),
        daily_drawdown=Decimal("0"),
        open_positions=2,
    )
    result = risk.assess(decision, account)
    assert result.approved is False
    assert any("correlation" in r for r in result.reasons)


# ── LearningAI Tests ─────────────────────────────────────────────────

def make_outcomes(pnls):
    return [
        TradeOutcome(
            decision_id=f"test-{i}",
            closed_at=datetime.now(timezone.utc),
            realized_pnl=Decimal(str(p)),
            exit_reason="test",
        )
        for i, p in enumerate(pnls)
    ]


def test_learning_ai_requires_min_sample():
    ai = LearningAI()
    outcomes = make_outcomes([10, -5, 20, -3])  # 4 trades, need 30
    result = ai.analyze(outcomes)
    assert len(result) == 1
    assert "Insufficient data" in result[0]


def test_learning_ai_analyzes_performance():
    ai = LearningAI()
    outcomes = make_outcomes([10] * 20 + [-5] * 20)  # 40 trades, 50% win
    perf = ai.analyze_performance(outcomes)
    assert perf["total_trades"] == 40
    assert perf["win_rate"] == 0.5


def test_learning_ai_recommendations_not_auto_applied():
    rec = LearningRecommendation(
        category="strategy",
        priority="high",
        action="Test action",
        rationale="Test rationale",
        confidence=0.9,
    )
    assert rec.requires_review is True


def test_learning_ai_regime_detection():
    ai = LearningAI()
    trending = ai.detect_regime([30, 35, 28, 32, 31])
    assert trending == "trending"

    ranging = ai.detect_regime([10, 15, 12, 8, 14])
    assert ranging == "ranging"
