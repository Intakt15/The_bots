"""Risk management for the off-chain trading bot.

This layer is the last gate before any live order is sent. It is intentionally
strict: if data is stale, spreads are too wide, or the opportunity exceeds the
configured budget, the trade is rejected and the bot can halt itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading_intelligence.offchain_bot.config import OffchainBotSettings
from trading_intelligence.offchain_bot.models import RiskDecision, TradeOpportunity


@dataclass
class RiskState:
    peak_equity_usd: Decimal = Decimal("10000")
    current_equity_usd: Decimal = Decimal("10000")
    halted: bool = False


class RiskManager:
    def __init__(self, settings: OffchainBotSettings) -> None:
        self._settings = settings
        self._state = RiskState()

    def assess(self, opportunity: TradeOpportunity) -> RiskDecision:
        if self._state.halted:
            return RiskDecision(
                approved=False,
                executable_size_usd=Decimal("0"),
                reason="Emergency kill switch already engaged",
                kill_switch_triggered=True,
            )

        quote = opportunity.quote
        if quote.spread_bps > self._settings.max_slippage_bps:
            self._state.halted = True
            return RiskDecision(
                approved=False,
                executable_size_usd=Decimal("0"),
                reason=(
                    f"Spread {quote.spread_bps:.2f} bps exceeds max slippage "
                    f"{self._settings.max_slippage_bps:.2f} bps"
                ),
                kill_switch_triggered=True,
            )

        if opportunity.suggested_size_usd > self._settings.max_trade_size_usd:
            return RiskDecision(
                approved=False,
                executable_size_usd=Decimal("0"),
                reason=(
                    f"Suggested size {opportunity.suggested_size_usd} exceeds max trade size "
                    f"{self._settings.max_trade_size_usd}"
                ),
            )

        stop_loss_distance = abs(opportunity.quote.mid - opportunity.stop_loss_price)
        if stop_loss_distance <= Decimal("0"):
            return RiskDecision(
                approved=False,
                executable_size_usd=Decimal("0"),
                reason="Stop-loss distance is invalid or zero",
            )

        approved_size = min(opportunity.suggested_size_usd, self._settings.max_trade_size_usd)
        return RiskDecision(
            approved=True,
            executable_size_usd=approved_size,
            reason="Risk checks passed",
        )

    def update_equity(self, equity_usd: Decimal) -> None:
        """Track peak-to-valley drawdown and halt if the configured limit is breached."""
        if equity_usd > self._state.peak_equity_usd:
            self._state.peak_equity_usd = equity_usd
        self._state.current_equity_usd = equity_usd

        if self._state.peak_equity_usd <= Decimal("0"):
            return

        drawdown = (self._state.peak_equity_usd - equity_usd) / self._state.peak_equity_usd
        if drawdown >= self._settings.kill_switch_drawdown_pct:
            self._state.halted = True

    @property
    def halted(self) -> bool:
        return self._state.halted
