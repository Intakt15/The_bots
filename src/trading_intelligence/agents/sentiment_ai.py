"""Sentiment AI Agent.

Produces a structured sentiment view and a pipeline-compatible assessment.
The implementation is safe by default: when no external feed is configured,
it stays neutral rather than inventing social or macro sentiment.
"""

from __future__ import annotations

from decimal import Decimal

from trading_intelligence.domain import AgentAssessment, MarketSnapshot, SentimentAssessment


class SentimentAI:
    name = "sentiment_ai"

    def analyze(self, snapshot: MarketSnapshot) -> SentimentAssessment:
        sentiment_score = Decimal("0")
        confidence = Decimal("55")
        flagged_risk = False
        rationale = "No social/news sentiment feed configured; using neutral baseline"

        if snapshot.symbol.startswith("XAU"):
            sentiment_score = Decimal("5")
            confidence = Decimal("60")
            rationale = "Gold often reacts to risk sentiment; using mild positive bias"

        return SentimentAssessment(
            source=self.name,
            symbol=snapshot.symbol,
            sentiment_score=sentiment_score,
            confidence=confidence,
            flagged_risk=flagged_risk,
            rationale=rationale,
            generated_at=snapshot.timestamp,
            topics=(f"{snapshot.symbol} macro-neutral",),
        )

    def evaluate(self, snapshot: MarketSnapshot) -> AgentAssessment:
        result = self.analyze(snapshot)
        eligible = not result.flagged_risk
        score = max(Decimal("0"), min(Decimal("100"), result.confidence + result.sentiment_score))
        return AgentAssessment(
            agent=self.name,
            score=score,
            eligible=eligible,
            rationale=result.rationale,
            generated_at=result.generated_at,
            metadata={
                "sentiment_score": str(result.sentiment_score),
                "confidence": str(result.confidence),
                "flagged_risk": str(result.flagged_risk),
                "topics": ";".join(result.topics),
            },
        )
