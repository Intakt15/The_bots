"""Learning AI Agent — Outcome Analysis & Advisory Recommendations.

Analyzes closed trade outcomes offline:
- Win rate, profit factor, Sharpe ratio
- Per-strategy and per-instrument performance
- Regime detection (trending vs. ranging via ADX)
- Advisory-only recommendations (NEVER auto-applied)

All recommendations require explicit human review before adoption.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from math import sqrt
from typing import Sequence

from trading_intelligence.config import get_settings
from trading_intelligence.domain import TradeOutcome

logger = logging.getLogger(__name__)


@dataclass
class StrategyPerformance:
    """Per-strategy performance metrics."""
    strategy: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: Decimal = Decimal("0")
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    max_consecutive_losses: int = 0
    current_consecutive_losses: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades if self.total_trades > 0 else 0.0

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(
            float(o.realized_pnl) for o in []
        )  # populated externally
        return 0.0  # computed in aggregate


@dataclass
class LearningRecommendation:
    """Advisory recommendation — NEVER auto-applied."""
    category: str  # "strategy", "risk", "instrument", "session"
    priority: str  # "high", "medium", "low"
    action: str
    rationale: str
    confidence: float  # 0-1
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    requires_review: bool = True


class LearningAI:
    """Analyzes trade outcomes and generates advisory recommendations.

    IMPORTANT: Recommendations are ADVISORY ONLY.
    They must NOT be automatically applied to live trading.
    All policy changes require explicit human review.
    """

    name = "learning_ai"

    def __init__(self) -> None:
        s = get_settings()
        self._min_sample = s.learning_min_sample_size
        self._rec_confidence = s.learning_recommendation_confidence

    # ── LearningAgent protocol ───────────────────────────────────────

    def analyze(self, outcomes: Sequence[TradeOutcome]) -> list[str]:
        """Analyze outcomes and return string recommendations."""
        if len(outcomes) < self._min_sample:
            return [
                f"Insufficient data for analysis ({len(outcomes)} trades, "
                f"need {self._min_sample}). Recommendations withheld."
            ]

        recs = self.generate_recommendations(outcomes)
        return [f"[{r.priority.upper()}] {r.action}: {r.rationale} (confidence={r.confidence:.0%})"
                for r in recs]

    # ── Core analysis ────────────────────────────────────────────────

    def analyze_performance(
        self, outcomes: Sequence[TradeOutcome]
    ) -> dict:
        """Compute comprehensive performance metrics."""
        if not outcomes:
            return {"error": "No outcomes to analyze"}

        pnls = [float(o.realized_pnl) for o in outcomes]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        n = len(pnls)

        # Basic stats
        total_pnl = sum(pnls)
        avg_pnl = total_pnl / n if n > 0 else 0
        win_rate = len(wins) / n if n > 0 else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        # Profit factor
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Max consecutive losses
        max_consec = 0
        current_consec = 0
        for p in pnls:
            if p <= 0:
                current_consec += 1
                max_consec = max(max_consec, current_consec)
            else:
                current_consec = 0

        # Sharpe ratio (requires risk-free rate from config)
        if n > 1:
            mean_ret = avg_pnl
            variance = sum((r - mean_ret) ** 2 for r in pnls) / (n - 1)
            std_dev = sqrt(variance) if variance > 0 else 0
            sharpe = (mean_ret - 0) / std_dev if std_dev > 0 else 0
        else:
            sharpe = 0

        # Expectancy
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))

        return {
            "total_trades": n,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "expectancy": expectancy,
            "max_consecutive_losses": max_consec,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
        }

    def generate_recommendations(
        self, outcomes: Sequence[TradeOutcome]
    ) -> list[LearningRecommendation]:
        """Generate advisory recommendations from outcome analysis.

        Returns empty list if sample size is insufficient.
        """
        if len(outcomes) < self._min_sample:
            logger.info(
                "LearningAI: insufficient data (%d < %d), skipping recommendations",
                len(outcomes),
                self._min_sample,
            )
            return []

        perf = self.analyze_performance(outcomes)
        recommendations: list[LearningRecommendation] = []

        # Check win rate
        win_rate = perf["win_rate"]
        if win_rate < 0.35:
            recommendations.append(LearningRecommendation(
                category="strategy",
                priority="high",
                action="Review strategy viability",
                rationale=f"Win rate critically low ({win_rate:.0%}). "
                          f"Consider disabling underperforming strategies or "
                          f"tightening entry criteria.",
                confidence=0.90,
            ))
        elif win_rate < 0.45:
            recommendations.append(LearningRecommendation(
                category="strategy",
                priority="medium",
                action="Investigate win rate decline",
                rationale=f"Win rate below target ({win_rate:.0%}). "
                          f"Analyze by instrument and timeframe.",
                confidence=0.75,
            ))

        # Check profit factor
        pf = perf["profit_factor"]
        if pf < 1.0 and perf["total_trades"] >= self._min_sample:
            recommendations.append(LearningRecommendation(
                category="risk",
                priority="high",
                action="Halt or reduce position sizing",
                rationale=f"Profit factor {pf:.2f} is below breakeven. "
                          f"Total PnL: {perf['total_pnl']:.2f}.",
                confidence=0.95,
            ))
        elif pf < 1.5:
            recommendations.append(LearningRecommendation(
                category="risk",
                priority="medium",
                action="Review risk-reward ratios",
                rationale=f"Profit factor {pf:.2f} is marginal. "
                          f"Consider increasing minimum RR ratio.",
                confidence=0.70,
            ))

        # Check consecutive losses
        max_consec = perf["max_consecutive_losses"]
        if max_consec >= 5:
            recommendations.append(LearningRecommendation(
                category="risk",
                priority="high",
                action="Activate drawdown circuit breaker",
                rationale=f"{max_consec} consecutive losses detected. "
                          f"Recommend pausing trading and reviewing recent decisions.",
                confidence=0.85,
            ))

        # Check Sharpe ratio
        sharpe = perf["sharpe_ratio"]
        if sharpe < 0:
            recommendations.append(LearningRecommendation(
                category="strategy",
                priority="high",
                action="Strategy produces negative risk-adjusted returns",
                rationale=f"Sharpe ratio {sharpe:.2f}. Consider strategy overhaul.",
                confidence=0.80,
            ))
        elif sharpe < 0.5:
            recommendations.append(LearningRecommendation(
                category="strategy",
                priority="medium",
                action="Improve risk-adjusted returns",
                rationale=f"Sharpe ratio {sharpe:.2f} is below threshold. "
                          f"Consider reducing trade frequency or sizing.",
                confidence=0.60,
            ))

        # Check expectancy
        if perf["expectancy"] < 0 and perf["total_trades"] >= self._min_sample:
            recommendations.append(LearningRecommendation(
                category="strategy",
                priority="high",
                action="Negative expectancy detected",
                rationale=f"Expectancy {perf['expectancy']:.4f} is negative. "
                          f"System is expected to lose money over time.",
                confidence=0.95,
            ))

        # Check sample size adequacy
        if perf["total_trades"] < self._min_sample * 2:
            for rec in recommendations:
                rec.confidence *= 0.5
                rec.rationale += " (Low sample size — reduced confidence)"
                rec.priority = "low"

        logger.info(
            "LearningAI: generated %d recommendations from %d trades",
            len(recommendations),
            perf["total_trades"],
        )

        return recommendations

    def detect_regime(
        self,
        adx_values: Sequence[float],
        threshold: float = 25.0,
    ) -> str:
        """Detect market regime from ADX values.

        Args:
            adx_values: Recent ADX readings.
            threshold: ADX above this = trending, below = ranging.

        Returns:
            "trending", "ranging", or "unknown".
        """
        if not adx_values:
            return "unknown"

        avg_adx = sum(adx_values) / len(adx_values)

        if avg_adx > threshold:
            return "trending"
        return "ranging"

    def instrument_performance(
        self, outcomes: Sequence[TradeOutcome]
    ) -> dict[str, dict]:
        """Group performance by instrument (requires instrument metadata).

        Since TradeOutcome doesn't carry instrument directly,
        this is a placeholder that returns aggregate.
        In production, join with decisions table to get instrument.
        """
        return {"aggregate": self.analyze_performance(outcomes)}

    def status_summary(self) -> dict:
        """Return current learning AI status for dashboard."""
        return {
            "min_sample_size": self._min_sample,
            "recommendation_confidence": self._rec_confidence,
            "status": "idle",
            "last_analysis": None,
        }
