"""Main orchestration for the off-chain trading bot."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from trading_intelligence.offchain_bot.connectors.base import ExecutionConnector, MarketDataConnector
from trading_intelligence.offchain_bot.models import ExecutionReceipt, RiskDecision, TradeOpportunity
from trading_intelligence.offchain_bot.risk import RiskManager
from trading_intelligence.offchain_bot.strategy import MomentumOpportunityScanner
from trading_intelligence.offchain_bot.config import OffchainBotSettings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BotRunResult:
    quote_source: str
    opportunity: TradeOpportunity | None
    risk: RiskDecision | None
    execution: ExecutionReceipt | None


class OffchainTradingBot:
    """Coordinate market data, strategy, risk, and execution.

    The bot is deliberately conservative: it only executes when the scanner,
    risk manager, and backend all agree that the trade is acceptable.
    """

    def __init__(
        self,
        settings: OffchainBotSettings,
        market_data: MarketDataConnector,
        execution: ExecutionConnector,
    ) -> None:
        self._settings = settings
        self._market_data = market_data
        self._execution = execution
        self._scanner = MomentumOpportunityScanner(settings)
        self._risk = RiskManager(settings)

    def connect(self) -> bool:
        market_ok = self._market_data.connect()
        execution_ok = self._execution.connect()
        return market_ok and execution_ok

    def run_once(self) -> BotRunResult:
        quote = self._market_data.get_quote(self._settings.symbol, self._settings.timeframe)
        logger.info(
            "Market quote %s mid=%s spread_bps=%.2f source=%s",
            quote.symbol,
            quote.mid,
            float(quote.spread_bps),
            quote.source,
        )

        opportunity = self._scanner.analyze(quote)
        if opportunity is None:
            logger.info("No trade opportunity detected for %s", quote.symbol)
            return BotRunResult(quote.source, None, None, None)

        risk = self._risk.assess(opportunity)
        if not risk.approved:
            logger.warning("Trade rejected for %s: %s", quote.symbol, risk.reason)
            if risk.kill_switch_triggered:
                logger.error("Emergency kill switch activated; stopping the bot")
            return BotRunResult(quote.source, opportunity, risk, None)

        execution = self._execution.execute(opportunity, risk.executable_size_usd)

        if execution.accepted:
            logger.info(
                "Trade executed %s %s size_usd=%s order_id=%s",
                opportunity.symbol,
                opportunity.direction,
                risk.executable_size_usd,
                execution.order_id,
            )
        else:
            logger.warning("Execution failed for %s: %s", opportunity.symbol, execution.details)

        return BotRunResult(quote.source, opportunity, risk, execution)

    def run_forever(self) -> None:
        logger.info("Off-chain trading bot started in %s mode", self._settings.trading_mode)
        while not self._risk.halted:
            self.run_once()
            time.sleep(self._settings.poll_interval_seconds)
        logger.error("Bot stopped because the risk layer halted trading")

    def close(self) -> None:
        self._market_data.close()
        self._execution.close()
