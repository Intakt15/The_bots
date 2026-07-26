"""Compliance AI agent.

This agent acts as a policy guardrail: if a future venue, region, or API-rule
violation is detected, it can veto execution before the trade reaches the broker.
"""

from __future__ import annotations

from decimal import Decimal

from trading_intelligence.domain import AgentAssessment, ComplianceAssessment, MarketSnapshot


class ComplianceAI:
    name = "compliance_ai"

    def __init__(self, policy_version: str = "v1") -> None:
        self._policy_version = policy_version

    def analyze(self, snapshot: MarketSnapshot) -> ComplianceAssessment:
        violations: list[str] = []
        if not snapshot.symbol:
            violations.append("missing symbol")

        allowed = len(violations) == 0
        rationale = "Policy checks passed" if allowed else "; ".join(violations)

        return ComplianceAssessment(
            source=self.name,
            symbol=snapshot.symbol,
            allowed=allowed,
            policy_version=self._policy_version,
            violations=tuple(violations),
            rate_limit_remaining=100,
            rationale=rationale,
            generated_at=snapshot.timestamp,
        )

    def evaluate(self, snapshot: MarketSnapshot) -> AgentAssessment:
        result = self.analyze(snapshot)
        return AgentAssessment(
            agent=self.name,
            score=Decimal("100") if result.allowed else Decimal("0"),
            eligible=result.allowed,
            rationale=result.rationale,
            generated_at=result.generated_at,
            metadata={
                "policy_version": result.policy_version,
                "violations": ";".join(result.violations),
                "rate_limit_remaining": str(result.rate_limit_remaining or 0),
            },
        )
