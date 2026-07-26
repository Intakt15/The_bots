from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from trading_intelligence.offchain_bot.bot import OffchainTradingBot
from trading_intelligence.offchain_bot.config import OffchainBotSettings
from trading_intelligence.offchain_bot.models import ExecutionReceipt, MarketQuote
from trading_intelligence.offchain_bot.models import TradeOpportunity
from trading_intelligence.offchain_bot.risk import RiskManager
from trading_intelligence.offchain_bot.strategy import MomentumOpportunityScanner


class FakeMarketDataConnector:
    def __init__(self, quotes: list[MarketQuote]) -> None:
        self._quotes = quotes
        self._index = 0

    def connect(self) -> bool:
        return True

    def get_quote(self, symbol: str, timeframe: str) -> MarketQuote:
        quote = self._quotes[min(self._index, len(self._quotes) - 1)]
        self._index += 1
        return quote

    def close(self) -> None:
        pass


class FakeExecutionConnector:
    def __init__(self) -> None:
        self.orders: list[tuple[str, Decimal]] = []

    def connect(self) -> bool:
        return True

    def execute(self, opportunity, approved_size_usd: Decimal) -> ExecutionReceipt:
        self.orders.append((opportunity.symbol, approved_size_usd))
        return ExecutionReceipt(True, "FAKE-ORDER", datetime.now(timezone.utc), "accepted", paper=True)

    def close(self) -> None:
        pass


def _quote(mid: str, spread_bps: str = "15") -> MarketQuote:
    mid_value = Decimal(mid)
    spread_fraction = Decimal(spread_bps) / Decimal("10000")
    half = mid_value * spread_fraction / Decimal("2")
    return MarketQuote(
        symbol="ETH/USDT",
        timestamp=datetime.now(timezone.utc),
        bid=mid_value - half,
        ask=mid_value + half,
        source="test",
    )


def test_scanner_emits_opportunity_after_rolling_window() -> None:
    settings = OffchainBotSettings(lookback_window=5)
    scanner = MomentumOpportunityScanner(settings)
    for price in ["100", "101", "102"]:
        opportunity = scanner.analyze(_quote(price))
    assert opportunity is not None
    assert opportunity.direction == "buy"


def test_risk_manager_triggers_kill_switch_for_wide_spread() -> None:
    settings = OffchainBotSettings(max_slippage_bps=Decimal("10"))
    quote = _quote("100", spread_bps="50")
    opportunity = TradeOpportunity(
        symbol=quote.symbol,
        direction="buy",
        confidence=Decimal("75"),
        expected_edge_bps=Decimal("20"),
        suggested_size_usd=Decimal("50"),
        stop_loss_price=quote.mid * Decimal("0.99"),
        take_profit_price=quote.mid * Decimal("1.02"),
        rationale="forced risk test",
        quote=quote,
    )
    risk = RiskManager(settings).assess(opportunity)
    assert risk.approved is False
    assert risk.kill_switch_triggered is True


def test_offchain_bot_executes_paper_trade() -> None:
    settings = OffchainBotSettings(trading_mode="paper", market_backend="ccxt", lookback_window=3)
    market = FakeMarketDataConnector([_quote("100"), _quote("101"), _quote("103")])
    execution = FakeExecutionConnector()
    bot = OffchainTradingBot(settings, market, execution)
    assert bot.connect() is True

    bot.run_once()
    bot.run_once()
    result = bot.run_once()

    assert result.opportunity is not None
    assert result.risk is not None
    assert result.execution is not None
    assert result.execution.accepted is True
    assert execution.orders
