"""Arbitrage AI agent.

In the current single-venue MT5 setup, this agent stays inactive unless a
cross-venue price map is supplied later. The model is in place now so the
architecture can grow without rework.
"""

from __future__ import annotations

from decimal import Decimal

from trading_intelligence.domain import ArbitrageOpportunity, AgentAssessment, MarketSnapshot


class ArbitrageAI:
    name = "arbitrage_ai"

    def analyze(self, snapshot: MarketSnapshot) -> ArbitrageOpportunity:
        mid = (snapshot.ask + snapshot.bid) / Decimal("2")
        spread_bps = (snapshot.ask - snapshot.bid) / mid * Decimal("10000") if mid > Decimal("0") else Decimal("0")
        return ArbitrageOpportunity(
            source=self.name,
            symbol=snapshot.symbol,
            venue_a="mt5",
            venue_b="mt5",
            spread_bps=spread_bps,
            edge_score=Decimal("0"),
            profitable=False,
            rationale="Single-venue feed detected; no arbitrage path available",
            generated_at=snapshot.timestamp,
        )

    def evaluate(self, snapshot: MarketSnapshot) -> AgentAssessment:
        result = self.analyze(snapshot)
        return AgentAssessment(
            agent=self.name,
            score=Decimal("50"),
            eligible=True,
            rationale=result.rationale,
            generated_at=result.generated_at,
            metadata={
                "spread_bps": str(result.spread_bps),
                "edge_score": str(result.edge_score),
                "profitable": str(result.profitable),
            },
        )
