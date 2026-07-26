"""Liquidity / whale-flow AI agent.

This agent is intentionally feed-agnostic. If no order-book or on-chain feed is
attached, it returns a conservative neutral assessment rather than fabricating
institutional flow.
"""

from __future__ import annotations

from decimal import Decimal

from trading_intelligence.domain import AgentAssessment, LiquidityAssessment, MarketSnapshot


class LiquidityAI:
    name = "liquidity_ai"

    def analyze(self, snapshot: MarketSnapshot) -> LiquidityAssessment:
        spread = snapshot.ask - snapshot.bid
        mid = (snapshot.ask + snapshot.bid) / Decimal("2")
        depth_score = Decimal("50")
        imbalance_score = Decimal("50")
        whale_activity = False
        rationale = "No order-book or on-chain feed configured; using spread-based neutral liquidity estimate"

        if spread > mid * Decimal("0.0005"):
            depth_score = Decimal("35")
            imbalance_score = Decimal("40")
            rationale = "Wide spread suggests thinner liquidity"

        return LiquidityAssessment(
            source=self.name,
            symbol=snapshot.symbol,
            depth_score=depth_score,
            imbalance_score=imbalance_score,
            confidence=Decimal("50"),
            whale_activity=whale_activity,
            rationale=rationale,
            generated_at=snapshot.timestamp,
            venues=("spot",),
        )

    def evaluate(self, snapshot: MarketSnapshot) -> AgentAssessment:
        result = self.analyze(snapshot)
        score = (result.depth_score + result.imbalance_score) / Decimal("2")
        return AgentAssessment(
            agent=self.name,
            score=score,
            eligible=True,
            rationale=result.rationale,
            generated_at=result.generated_at,
            metadata={
                "depth_score": str(result.depth_score),
                "imbalance_score": str(result.imbalance_score),
                "whale_activity": str(result.whale_activity),
                "venues": ";".join(result.venues),
            },
        )
