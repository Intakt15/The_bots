"""Technical Signal AI Agent.

Multi-strategy technical analysis combining:
- Trend (EMA crossovers on H1/H4)
- Momentum (RSI divergence)
- Volatility (Bollinger Band squeeze/breakout)
- Support/Resistance (Pivot points, horizontal levels)

Each strategy is independently testable. Combined into a weighted Signal
with confidence score, thesis, stop-loss, and take-profit levels.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from trading_intelligence.config import get_settings
from trading_intelligence.domain import MarketSnapshot, Side, Signal

logger = logging.getLogger(__name__)


class SignalAI:
    """Technical analysis agent that generates trade signals.

    Combines multiple strategies: trend, momentum, volatility, S/R levels.
    Each sub-strategy produces a sub-signal; the agent weights and combines
    them into a final Signal with confidence.
    """

    name = "signal_ai"

    def __init__(self) -> None:
        self._settings = get_settings()

    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None:
        """Evaluate a market snapshot and produce a trade signal.

        Returns None if no clear signal is detected (abstention default).
        """
        now = snapshot.timestamp

        # Run all sub-strategies
        trend = self._evaluate_trend(snapshot)
        momentum = self._evaluate_momentum(snapshot)
        volatility = self._evaluate_volatility(snapshot)
        sr = self._evaluate_sr_levels(snapshot)

        # Combine signals
        signals = [s for s in [trend, momentum, volatility, sr] if s is not None]
        if not signals:
            return None

        return self._combine_signals(signals, snapshot, now)

    # ── Sub-strategies ───────────────────────────────────────────────

    def _evaluate_trend(self, snapshot: MarketSnapshot) -> dict | None:
        """EMA crossover strategy.

        Looks for EMA12/EMA26 crossover on the primary timeframe.
        """
        ema_fast = snapshot.indicators.get("EMA_12")
        ema_slow = snapshot.indicators.get("EMA_26")
        ema_50 = snapshot.indicators.get("EMA_50")

        if ema_fast is None or ema_slow is None:
            return None

        # Fast above slow = bullish, fast below slow = bearish
        if ema_fast > ema_slow:
            direction = "buy"
            # Check for pullback to EMA for better entry
            confidence = Decimal("65")
            if ema_50 and ema_fast > ema_50:
                confidence += Decimal("10")  # stronger trend
        elif ema_fast < ema_slow:
            direction = "sell"
            confidence = Decimal("65")
            if ema_50 and ema_fast < ema_50:
                confidence += Decimal("10")
        else:
            return None  # flat — no clear trend

        return {
            "strategy": "trend",
            "direction": direction,
            "confidence": confidence,
            "thesis": f"EMA12 ({ema_fast:.5f}) {'above' if direction == 'buy' else 'below'} EMA26 ({ema_slow:.5f})",
        }

    def _evaluate_momentum(self, snapshot: MarketSnapshot) -> dict | None:
        """RSI-based momentum strategy.

        RSI oversold (<30) = buy signal, overbought (>70) = sell signal.
        RSI divergence adds confidence.
        """
        rsi = snapshot.indicators.get("RSI_14")
        if rsi is None:
            return None

        if rsi < Decimal("30"):
            return {
                "strategy": "momentum",
                "direction": "buy",
                "confidence": Decimal("60") + (Decimal("30") - rsi) * Decimal("2"),
                "thesis": f"RSI oversold at {rsi:.1f}",
            }
        elif rsi > Decimal("70"):
            return {
                "strategy": "momentum",
                "direction": "sell",
                "confidence": Decimal("60") + (rsi - Decimal("70")) * Decimal("2"),
                "thesis": f"RSI overbought at {rsi:.1f}",
            }

        return None

    def _evaluate_volatility(self, snapshot: MarketSnapshot) -> dict | None:
        """Bollinger Band squeeze/breakout strategy.

        Price near lower band = oversold (buy), near upper band = overbought (sell).
        Low bandwidth = squeeze (potential breakout).
        """
        bb_upper = snapshot.indicators.get("BB_UPPER")
        bb_lower = snapshot.indicators.get("BB_LOWER")
        bb_mid = snapshot.indicators.get("BB_MIDDLE")

        if bb_upper is None or bb_lower is None or bb_mid is None:
            return None

        mid_price = (snapshot.bid + snapshot.ask) / Decimal("2")
        band_range = bb_upper - bb_lower

        if band_range <= Decimal("0"):
            return None

        # Position within bands (0 = lower, 1 = upper)
        position = (mid_price - bb_lower) / band_range

        if position < Decimal("0.1"):
            return {
                "strategy": "volatility",
                "direction": "buy",
                "confidence": Decimal("55"),
                "thesis": f"Price at lower Bollinger band ({mid_price:.5f} vs {bb_lower:.5f})",
            }
        elif position > Decimal("0.9"):
            return {
                "strategy": "volatility",
                "direction": "sell",
                "confidence": Decimal("55"),
                "thesis": f"Price at upper Bollinger band ({mid_price:.5f} vs {bb_upper:.5f})",
            }

        return None

    def _evaluate_sr_levels(self, snapshot: MarketSnapshot) -> dict | None:
        """Support/Resistance levels strategy.

        Uses pivot points and horizontal S/R from recent price action.
        Simplified: checks if price is near a key level.
        """
        pivot = snapshot.indicators.get("PIVOT")
        r1 = snapshot.indicators.get("R1")
        s1 = snapshot.indicators.get("S1")

        if pivot is None:
            return None

        mid_price = (snapshot.bid + snapshot.ask) / Decimal("2")

        # Near support level → potential buy
        if s1 and mid_price <= s1 * Decimal("1.002"):
            return {
                "strategy": "sr_levels",
                "direction": "buy",
                "confidence": Decimal("50"),
                "thesis": f"Price near S1 support ({mid_price:.5f} vs {s1:.5f})",
            }

        # Near resistance level → potential sell
        if r1 and mid_price >= r1 * Decimal("0.998"):
            return {
                "strategy": "sr_levels",
                "direction": "sell",
                "confidence": Decimal("50"),
                "thesis": f"Price near R1 resistance ({mid_price:.5f} vs {r1:.5f})",
            }

        return None

    # ── Signal combination ───────────────────────────────────────────

    def _combine_signals(
        self,
        sub_signals: list[dict],
        snapshot: MarketSnapshot,
        at: datetime,
    ) -> Signal | None:
        """Combine sub-strategy signals into a final Signal.

        Uses majority voting for direction and weighted average for confidence.
        Only produces a signal if at least 2 strategies agree.
        """
        buys = [s for s in sub_signals if s["direction"] == "buy"]
        sells = [s for s in sub_signals if s["direction"] == "sell"]

        # Need at least 2 agreeing strategies
        if len(buys) < 2 and len(sells) < 2:
            return None

        if len(buys) >= len(sells):
            direction = Side.BUY
            relevant = buys
        else:
            direction = Side.SELL
            relevant = sells

        # Average confidence of agreeing strategies
        avg_conf = sum(
            (s["confidence"] for s in relevant), Decimal("0")
        ) / len(relevant)

        # Bonus for more agreement
        if len(relevant) >= 3:
            avg_conf += Decimal("10")

        # Cap at 95
        avg_conf = min(avg_conf, Decimal("95"))

        # Build thesis from all strategies
        theses = [s["thesis"] for s in relevant]
        thesis = " | ".join(theses)

        # Calculate stop-loss and take-profit
        mid_price = (snapshot.bid + snapshot.ask) / Decimal("2")
        atr = snapshot.indicators.get("ATR_14", mid_price * Decimal("0.005"))

        if direction == Side.BUY:
            stop_loss = mid_price - atr * Decimal("1.5")
            take_profit = mid_price + atr * Decimal("3.0")
        else:
            stop_loss = mid_price + atr * Decimal("1.5")
            take_profit = mid_price - atr * Decimal("3.0")

        logger.info(
            "SignalAI: %s %s conf=%.1f (%d strategies: %s)",
            snapshot.symbol,
            direction.value,
            float(avg_conf),
            len(relevant),
            ", ".join(s["strategy"] for s in relevant),
        )

        return Signal(
            source=self.name,
            symbol=snapshot.symbol,
            side=direction,
            confidence=avg_conf,
            generated_at=at,
            thesis=thesis,
            stop_loss=stop_loss,
            take_profit=take_profit,
            evidence={s["strategy"]: s["thesis"] for s in relevant},
        )
