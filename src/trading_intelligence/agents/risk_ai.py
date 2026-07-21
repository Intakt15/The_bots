"""Risk Management AI Agent — FINAL VETO authority.

Enforces:
- Maximum daily and total drawdown
- Maximum concurrent positions (global + per instrument)
- Correlation exposure limits
- ATR-based dynamic position sizing
- Volatility kill-switch (spread anomaly detection)
- Account-level equity checks

No agent, dashboard, or adapter may bypass this guardian.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from trading_intelligence.config import get_settings
from trading_intelligence.domain import (
    AccountState,
    MarketSnapshot,
    RiskAssessment,
    TradeDecision,
)

logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """Snapshot of current risk limits from config."""
    max_daily_drawdown_pct: Decimal
    max_total_drawdown_pct: Decimal
    max_positions: int
    max_per_instrument: int
    default_quantity: Decimal
    atr_period: int
    atr_multiplier: Decimal
    correlation_limit: Decimal
    volatility_kill_switch: Decimal


class RiskManager:
    """Comprehensive risk guardian with final veto authority.

    Evaluates every TradeDecision against account state, market conditions,
    and correlation exposure before allowing execution.
    """

    name = "risk_ai"

    def __init__(self) -> None:
        s = get_settings()
        self._limits = RiskLimits(
            max_daily_drawdown_pct=Decimal(str(s.max_daily_drawdown)),
            max_total_drawdown_pct=Decimal(str(s.max_total_drawdown)),
            max_positions=s.max_positions,
            max_per_instrument=s.max_positions_per_instrument,
            default_quantity=Decimal(str(s.default_position_size)),
            atr_period=s.atr_period,
            atr_multiplier=Decimal(str(s.atr_multiplier)),
            correlation_limit=Decimal(str(s.correlation_exposure_limit)),
            volatility_kill_switch=Decimal(str(s.volatility_kill_switch)),
        )
        # Track intra-day drawdown
        self._peak_equity: Decimal | None = None
        self._daily_pnl: Decimal = Decimal("0")
        self._open_instruments: dict[str, int] = {}  # symbol -> position count
        self._avg_spreads: dict[str, Decimal] = {}   # symbol -> avg spread

    # ── RiskGuardian protocol ────────────────────────────────────────

    def assess(
        self,
        decision: TradeDecision,
        account: AccountState,
        snapshot: MarketSnapshot | None = None,
    ) -> RiskAssessment:
        """Evaluate a trade decision against all risk rules.

        Args:
            decision: The proposed trade from consensus.
            account: Current account state.
            snapshot: Optional market snapshot for dynamic sizing.

        Returns:
            RiskAssessment with approval, adjusted quantity, and reasons.
        """
        now = datetime.now(timezone.utc)
        reasons: list[str] = []

        # 1. Drawdown checks
        self._check_drawdown(account, reasons)

        # 2. Position count checks
        self._check_positions(decision, reasons)

        # 3. Correlation exposure check
        self._check_correlation(decision.symbol, reasons)

        # 4. Volatility kill-switch (if snapshot provided)
        if snapshot:
            self._check_volatility(snapshot, reasons)

        # 5. Dynamic position sizing (ATR-based)
        adjusted_qty = self._compute_position_size(decision, snapshot)

        approved = len(reasons) == 0 and adjusted_qty > Decimal("0")

        return RiskAssessment(
            approved=approved,
            approved_quantity=adjusted_qty if approved else Decimal("0"),
            reasons=tuple(reasons),
            assessed_at=now,
        )

    # ── Individual checks ────────────────────────────────────────────

    def _check_drawdown(self, account: AccountState, reasons: list[str]) -> None:
        limits = self._limits

        if account.equity <= Decimal("0"):
            reasons.append("account equity is zero or negative")
            return

        # Track peak equity
        if self._peak_equity is None or account.equity > self._peak_equity:
            self._peak_equity = account.equity

        if self._peak_equity and self._peak_equity > Decimal("0"):
            total_dd = (self._peak_equity - account.equity) / self._peak_equity
            if total_dd >= limits.max_total_drawdown_pct:
                reasons.append(
                    f"total drawdown {total_dd:.1%} exceeds limit "
                    f"{limits.max_total_drawdown_pct:.1%}"
                )

        # Daily drawdown from provided account state
        if account.daily_drawdown > Decimal("0") and account.balance > Decimal("0"):
            daily_pct = account.daily_drawdown / account.balance
            if daily_pct >= limits.max_daily_drawdown_pct:
                reasons.append(
                    f"daily drawdown {daily_pct:.1%} exceeds limit "
                    f"{limits.max_daily_drawdown_pct:.1%}"
                )

    def _check_positions(
        self, decision: TradeDecision, reasons: list[str]
    ) -> None:
        limits = self._limits
        total = sum(self._open_instruments.values())

        if total >= limits.max_positions:
            reasons.append(
                f"max positions reached ({total}/{limits.max_positions})"
            )

        symbol_count = self._open_instruments.get(decision.symbol, 0)
        if symbol_count >= limits.max_per_instrument:
            reasons.append(
                f"max positions for {decision.symbol} reached "
                f"({symbol_count}/{limits.max_per_instrument})"
            )

    def _check_correlation(self, symbol: str, reasons: list[str]) -> None:
        """Check if adding this symbol would create over-concentration.

        Uses a simplified basket check: if more than 2 positions already
        share a highly correlated basket with this symbol, reject.
        """
        # Define simple correlation baskets for major forex pairs
        baskets = {
            "EURUSD": "EUR", "EURGBP": "EUR", "EURJPY": "EUR",
            "EURCHF": "EUR", "EURNZD": "EUR", "EURAUD": "EUR",
            "GBPUSD": "GBP", "GBPJPY": "GBP", "GBPCHF": "GBP",
            "USDJPY": "USD", "USDCAD": "USD", "USDCHF": "USD",
            "AUDUSD": "AUD", "AUDJPY": "AUD", "AUDNZD": "AUD",
            "NZDUSD": "NZD", "NZDCAD": "NZD", "NZDJPY": "NZD",
            "XAUUSD": "XAU", "XAGUSD": "XAG",
        }

        basket = baskets.get(symbol)
        if basket is None:
            return  # Unknown symbol, allow for now

        # Count how many open positions share this basket
        basket_count = sum(
            1 for sym in self._open_instruments
            if baskets.get(sym) == basket
        )

        if basket_count >= 2:  # Already 2+ correlated positions
            reasons.append(
                f"correlation limit exceeded for basket {basket} "
                f"({basket_count} positions already open)"
            )

    def _check_volatility(
        self, snapshot: MarketSnapshot, reasons: list[str]
    ) -> None:
        """Kill-switch: if current spread exceeds threshold, halt trading."""
        spread = snapshot.ask - snapshot.bid

        if snapshot.symbol in self._avg_spreads:
            avg = self._avg_spreads[snapshot.symbol]
            if avg > Decimal("0") and spread > avg * self._limits.volatility_kill_switch:
                reasons.append(
                    f"volatility kill-switch: spread {spread} > "
                    f"{self._limits.volatility_kill_switch}x avg ({avg})"
                )

        # Update rolling average spread
        if snapshot.symbol not in self._avg_spreads:
            self._avg_spreads[snapshot.symbol] = spread
        else:
            # Exponential moving average (alpha=0.1)
            old = self._avg_spreads[snapshot.symbol]
            self._avg_spreads[snapshot.symbol] = old * Decimal("0.9") + spread * Decimal("0.1")

    def _compute_position_size(
        self,
        decision: TradeDecision,
        snapshot: MarketSnapshot | None,
    ) -> Decimal:
        """ATR-based dynamic position sizing.

        Position = default_qty * (base_atr / current_atr)
        This reduces size in volatile conditions and increases in calm ones.
        """
        if snapshot is None:
            return self._limits.default_quantity

        atr_key = f"ATR_{self._limits.atr_period}"
        current_atr = snapshot.indicators.get(atr_key)

        if current_atr is None:
            return self._limits.default_quantity

        # Base ATR: use 1% of price as reference
        mid_price = (snapshot.bid + snapshot.ask) / Decimal("2")
        base_atr = mid_price * Decimal("0.01")  # 1% of price

        if current_atr <= Decimal("0") or base_atr <= Decimal("0"):
            return self._limits.default_quantity

        # Adjust size: smaller in high vol, larger in low vol
        ratio = base_atr / current_atr
        adjusted = self._limits.default_quantity * ratio

        # Clamp to reasonable bounds
        min_qty = self._limits.default_quantity * Decimal("0.5")
        max_qty = self._limits.default_quantity * Decimal("2.0")
        clamped = max(min_qty, min(max_qty, adjusted))

        logger.debug(
            "ATR sizing for %s: base_atr=%.5f current_atr=%.5f "
            "ratio=%.2f qty=%.4f",
            snapshot.symbol,
            float(base_atr),
            float(current_atr),
            float(ratio),
            float(clamped),
        )

        return clamped

    # ── Position tracking (called by engine after execution) ─────────

    def record_open(self, symbol: str) -> None:
        """Record that a position was opened on this symbol."""
        self._open_instruments[symbol] = self._open_instruments.get(symbol, 0) + 1

    def record_close(self, symbol: str) -> None:
        """Record that a position was closed."""
        count = self._open_instruments.get(symbol, 0)
        if count > 1:
            self._open_instruments[symbol] = count - 1
        else:
            self._open_instruments.pop(symbol, None)

    def update_account(self, equity: Decimal) -> None:
        """Update peak equity tracking."""
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity

    def reset_daily(self) -> None:
        """Reset daily tracking (called at session start)."""
        self._peak_equity = None
        self._daily_pnl = Decimal("0")

    def status_summary(self) -> dict:
        """Return current risk status for dashboard."""
        return {
            "open_positions_total": sum(self._open_instruments.values()),
            "open_instruments": dict(self._open_instruments),
            "peak_equity": str(self._peak_equity) if self._peak_equity else "N/A",
            "average_spreads": {
                k: str(v) for k, v in self._avg_spreads.items()
            },
            "limits": {
                "max_daily_drawdown": str(self._limits.max_daily_drawdown_pct),
                "max_total_drawdown": str(self._limits.max_total_drawdown_pct),
                "max_positions": self._limits.max_positions,
                "max_per_instrument": self._limits.max_per_instrument,
                "default_quantity": str(self._limits.default_quantity),
                "atr_multiplier": str(self._limits.atr_multiplier),
                "correlation_limit": str(self._limits.correlation_limit),
                "volatility_kill_switch": str(self._limits.volatility_kill_switch),
            },
        }
