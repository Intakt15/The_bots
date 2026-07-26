"""Opportunity scanning logic for the off-chain trading bot.

The scanner keeps a short rolling history and only emits a trade idea when the
current price deviates enough from the recent average to justify the risk.
This keeps the bot conservative by default.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal

from trading_intelligence.offchain_bot.config import OffchainBotSettings
from trading_intelligence.offchain_bot.models import MarketQuote, TradeOpportunity


class MomentumOpportunityScanner:
    """Generate a simple directional opportunity from a rolling price window."""

    def __init__(self, settings: OffchainBotSettings) -> None:
        self._settings = settings
        self._mid_history: deque[Decimal] = deque(maxlen=settings.lookback_window)

    def analyze(self, quote: MarketQuote) -> TradeOpportunity | None:
        self._mid_history.append(quote.mid)
        if len(self._mid_history) < 3:
            return None

        rolling_average = sum(self._mid_history, Decimal("0")) / Decimal(len(self._mid_history))
        if rolling_average <= Decimal("0"):
            return None

        edge_bps = ((quote.mid - rolling_average) / rolling_average) * Decimal("10000")
        abs_edge = abs(edge_bps)
        if abs_edge < Decimal("12"):
            return None

        direction = "buy" if edge_bps > 0 else "sell"
        confidence = min(Decimal("95"), Decimal("50") + abs_edge * Decimal("1.5"))
        suggested_size = min(
            self._settings.max_trade_size_usd,
            self._settings.max_trade_size_usd * (confidence / Decimal("100")),
        )

        if direction == "buy":
            stop_loss = quote.mid * (Decimal("1") - self._settings.stop_loss_pct)
            take_profit = quote.mid * (Decimal("1") + self._settings.take_profit_pct)
        else:
            stop_loss = quote.mid * (Decimal("1") + self._settings.stop_loss_pct)
            take_profit = quote.mid * (Decimal("1") - self._settings.take_profit_pct)

        rationale = (
            f"mid-price deviation {edge_bps:.2f} bps versus rolling average over "
            f"{len(self._mid_history)} samples"
        )

        return TradeOpportunity(
            symbol=quote.symbol,
            direction=direction,
            confidence=confidence,
            expected_edge_bps=edge_bps,
            suggested_size_usd=suggested_size,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            rationale=rationale,
            quote=quote,
        )
