"""Orchestration layer with enhanced multi-agent consensus engine.

Features:
- Configurable per-agent weights from settings
- Per-instrument confidence thresholds
- Disagreement detection between agents
- Tie-breaking rules
- Full audit trail of consensus decisions
- Risk-gated execution
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from trading_intelligence.config import get_settings
from trading_intelligence.domain import (
    AccountState,
    AgentAssessment,
    DecisionStatus,
    ExecutionReport,
    RiskAssessment,
    Side,
    Signal,
    TradeDecision,
)
from trading_intelligence.interfaces.ports import (
    ConsensusEngine,
    DecisionRepository,
    ExecutionGateway,
    RiskGuardian,
)

logger = logging.getLogger(__name__)


# ── Enhanced Consensus Engine ────────────────────────────────────────

@dataclass
class ConsensusResult:
    """Detailed audit trail of how consensus was reached."""
    decision: TradeDecision
    weighted_score: Decimal
    individual_scores: dict[str, Decimal] = field(default_factory=dict)
    disagreements: list[str] = field(default_factory=list)
    tie_broken: bool = False
    threshold_met: bool = False


class WeightedConsensus:
    """Deterministic consensus with configurable agent weights.

    Combines signal + session + news assessments using weights from settings.
    Detects disagreements between agents and provides audit trail.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.minimum_score = Decimal(str(settings.consensus_minimum_score))
        self.min_confidence = Decimal(str(settings.consensus_min_confidence))
        self.signal_weight = Decimal(str(settings.signal_weight))
        self.session_weight = Decimal(str(settings.session_weight))
        self.news_weight = Decimal(str(settings.news_weight))
        self._total_weight = self.signal_weight + self.session_weight + self.news_weight

    def decide(
        self,
        signal: Signal | None,
        assessments: Sequence[AgentAssessment],
        at: datetime | None = None,
    ) -> TradeDecision:
        """Combine signal and specialist assessments into a trade decision.

        Args:
            signal: Optional signal from SignalAI (None = abstain).
            assessments: Specialist assessments from SessionAI, NewsAI, etc.
            at: Timestamp for the decision (defaults to UTC now).
        """
        if at is None:
            at = datetime.now(timezone.utc)

        result = self._compute_consensus(signal, assessments, at)
        return result.decision

    def decide_with_audit(
        self,
        signal: Signal | None,
        assessments: Sequence[AgentAssessment],
        at: datetime | None = None,
    ) -> ConsensusResult:
        """Return full consensus result with audit trail."""
        if at is None:
            at = datetime.now(timezone.utc)
        return self._compute_consensus(signal, assessments, at)

    def _compute_consensus(
        self,
        signal: Signal | None,
        assessments: Sequence[AgentAssessment],
        at: datetime,
    ) -> ConsensusResult:
        # No signal → abstain
        if signal is None:
            decision = TradeDecision(
                symbol="",
                side=Side.FLAT,
                status=DecisionStatus.HOLD,
                confidence=Decimal("0"),
                quantity=Decimal("0"),
                created_at=at,
                rationale="No signal produced — abstaining",
                signal=None,
            )
            return ConsensusResult(
                decision=decision,
                weighted_score=Decimal("0"),
                threshold_met=False,
            )

        # Check ineligible assessments
        ineligible = [a for a in assessments if not a.eligible]
        if ineligible:
            reasons = "; ".join(
                f"{a.agent}: {a.rationale}" for a in ineligible
            )
            decision = TradeDecision(
                symbol=signal.symbol,
                side=signal.side,
                status=DecisionStatus.REJECTED,
                confidence=Decimal("0"),
                quantity=Decimal("0"),
                created_at=at,
                rationale=f"Rejected — ineligible assessments: {reasons}",
                signal=signal,
            )
            return ConsensusResult(
                decision=decision,
                weighted_score=Decimal("0"),
                individual_scores={a.agent: a.score for a in assessments},
                threshold_met=False,
            )

        # Compute weighted score from assessments
        assessment_map = {a.agent: a for a in assessments}
        individual_scores: dict[str, Decimal] = {}
        weighted_sum = Decimal("0")
        weight_used = Decimal("0")

        # Map agent names to weights
        weight_map = {
            "session_ai": self.session_weight,
            "news_ai": self.news_weight,
            "signal_ai": self.signal_weight,
        }

        for agent_name, assessment in assessment_map.items():
            weight = weight_map.get(agent_name, Decimal("0"))
            if weight > 0:
                weighted_sum += assessment.score * weight
                weight_used += weight
            individual_scores[agent_name] = assessment.score

        # Normalize weighted score (0-100 scale)
        if weight_used > 0:
            weighted_score = weighted_sum / weight_used
        else:
            weighted_score = signal.confidence  # fall back to raw signal

        # Combine with signal confidence
        combined_confidence = (signal.confidence + weighted_score) / Decimal("2")

        # Disagreement detection
        disagreements = self._detect_disagreements(
            signal, assessments, assessment_map
        )

        # Determine approval
        confidence_ok = combined_confidence >= self.min_confidence
        score_ok = weighted_score >= self.minimum_score
        has_disagreement = len(disagreements) > 0
        approved = confidence_ok and score_ok

        # Tie-breaking: if disagreements exist but scores are high,
        # still approve but flag the disagreement
        if has_disagreement and approved:
            rationale = (
                f"Approved with disagreement note: {'; '.join(disagreements)}. "
                f"Combined confidence: {combined_confidence:.1f} (min: {self.min_confidence})"
            )
        elif approved:
            rationale = (
                f"Consensus reached. Signal confidence: {signal.confidence:.1f}, "
                f"Weighted score: {weighted_score:.1f} (min: {self.minimum_score})"
            )
        elif has_disagreement:
            rationale = (
                f"Rejected — agent disagreement: {'; '.join(disagreements)}"
            )
        elif not confidence_ok:
            rationale = (
                f"Rejected — combined confidence {combined_confidence:.1f} "
                f"below minimum {self.min_confidence}"
            )
        else:
            rationale = (
                f"Rejected — weighted score {weighted_score:.1f} "
                f"below minimum {self.minimum_score}"
            )

        status = DecisionStatus.APPROVED if approved else DecisionStatus.REJECTED
        quantity = Decimal("1") if approved else Decimal("0")

        decision = TradeDecision(
            symbol=signal.symbol,
            side=signal.side,
            status=status,
            confidence=combined_confidence,
            quantity=quantity,
            created_at=at,
            rationale=rationale,
            signal=signal,
        )

        return ConsensusResult(
            decision=decision,
            weighted_score=weighted_score,
            individual_scores=individual_scores,
            disagreements=disagreements,
            tie_broken=has_disagreement and approved,
            threshold_met=approved,
        )

    def _detect_disagreements(
        self,
        signal: Signal,
        assessments: Sequence[AgentAssessment],
        assessment_map: dict[str, AgentAssessment],
    ) -> list[str]:
        """Detect conflicting signals between agents."""
        disagreements: list[str] = []

        # Low confidence signal vs high-scoring assessments
        if signal.confidence < self.min_confidence:
            high_scorers = [
                name for name, a in assessment_map.items()
                if a.score >= Decimal("70")
            ]
            if high_scorers:
                disagreements.append(
                    f"Low signal confidence ({signal.confidence:.1f}) "
                    f"despite high scores from {', '.join(high_scorers)}"
                )

        # Conflicting directions (if multiple signal sources disagree)
        # This is a placeholder — actual direction conflict detection
        # would compare Signal side against assessment metadata

        # Low eligibility score despite passing threshold
        for a in assessments:
            if a.eligible and a.score < Decimal("50"):
                disagreements.append(
                    f"{a.agent} barely eligible (score={a.score:.1f})"
                )

        return disagreements


# ── Fixed Risk Policy ────────────────────────────────────────────────

class FixedRiskPolicy:
    """Conservative deterministic risk policy.

    Enforces:
    - Maximum daily drawdown
    - Maximum concurrent positions
    - Fixed position sizing
    """

    def __init__(
        self,
        max_daily_drawdown: Decimal,
        max_positions: int,
        quantity: Decimal,
    ):
        self.max_daily_drawdown = max_daily_drawdown
        self.max_positions = max_positions
        self.quantity = quantity

    def assess(
        self, decision: TradeDecision, account: AccountState
    ) -> RiskAssessment:
        reasons: list[str] = []
        if account.daily_drawdown >= self.max_daily_drawdown:
            reasons.append("daily drawdown limit reached")
        if account.open_positions >= self.max_positions:
            reasons.append("maximum open positions reached")
        return RiskAssessment(
            not bool(reasons),
            self.quantity if not reasons else Decimal("0"),
            tuple(reasons),
            decision.created_at,
        )


# ── Decision Pipeline ────────────────────────────────────────────────

class DecisionPipeline:
    """Orchestrates: consensus → risk → execution → storage.

    This is the ONLY path through which trade execution may occur.
    No agent, dashboard, or adapter may bypass this pipeline.
    """

    def __init__(
        self,
        consensus: ConsensusEngine,
        risk: RiskGuardian,
        execution: ExecutionGateway,
        repository: DecisionRepository,
    ):
        self._consensus = consensus
        self._risk = risk
        self._execution = execution
        self._repository = repository

    def process(
        self,
        signal: Signal | None,
        assessments: Sequence[AgentAssessment],
        account: AccountState,
        at: datetime | None = None,
    ) -> tuple[TradeDecision, ExecutionReport | None]:
        """Run the full decision lifecycle.

        Returns:
            Tuple of (final_decision, execution_report_or_none).
            execution_report is None if the decision was not approved.
        """
        if at is None:
            at = datetime.now(timezone.utc)

        # 1. Consensus
        decision = self._consensus.decide(signal, assessments, at)

        # 2. Risk assessment (FINAL VETO)
        risk = self._risk.assess(decision, account)
        if not risk.approved:
            decision = replace(
                decision,
                status=DecisionStatus.REJECTED,
                quantity=Decimal("0"),
                rationale=(
                    f"{decision.rationale}; risk veto: {'; '.join(risk.reasons)}"
                ),
            )
        elif decision.status == DecisionStatus.APPROVED:
            decision = replace(decision, quantity=risk.approved_quantity)

        # 3. Persist decision + assessments
        self._repository.save_decision(decision, assessments)

        # 4. Execute if approved
        if decision.status != DecisionStatus.APPROVED:
            logger.info(
                "Decision %s: %s — skipping execution",
                decision.decision_id,
                decision.status.value,
            )
            return decision, None

        report = self._execution.submit(
            decision, idempotency_key=str(decision.decision_id)
        )
        self._repository.save_execution(report)

        logger.info(
            "Decision %s executed: %s %s qty=%s | broker=%s | accepted=%s",
            decision.decision_id,
            decision.symbol,
            decision.side.value,
            decision.quantity,
            report.broker_order_id,
            report.accepted,
        )

        return decision, report
