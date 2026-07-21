"""Technology-neutral interfaces. Adapters implement these protocols."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

from trading_intelligence.domain import (
    AccountState, AgentAssessment, ExecutionReport, MarketSnapshot, RiskAssessment,
    Signal, TradeDecision, TradeOutcome,
)


class MarketDataProvider(Protocol):
    def snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot: ...


class NewsProvider(Protocol):
    def assessments(self, symbol: str, at: datetime) -> Sequence[AgentAssessment]: ...


class SignalAgent(Protocol):
    name: str
    def evaluate(self, snapshot: MarketSnapshot) -> Signal | None: ...


class AssessmentAgent(Protocol):
    name: str
    def evaluate(self, snapshot: MarketSnapshot) -> AgentAssessment: ...


class ConsensusEngine(Protocol):
    def decide(self, signal: Signal | None, assessments: Sequence[AgentAssessment], at: datetime) -> TradeDecision: ...


class RiskGuardian(Protocol):
    def assess(self, decision: TradeDecision, account: AccountState) -> RiskAssessment: ...


class ExecutionGateway(Protocol):
    def submit(self, decision: TradeDecision, idempotency_key: str) -> ExecutionReport: ...


class DecisionRepository(Protocol):
    def save_decision(self, decision: TradeDecision, assessments: Sequence[AgentAssessment]) -> None: ...
    def save_execution(self, report: ExecutionReport) -> None: ...
    def save_outcome(self, outcome: TradeOutcome) -> None: ...


class LearningAgent(Protocol):
    def analyze(self, outcomes: Sequence[TradeOutcome]) -> Sequence[str]: ...


class DashboardQueryService(Protocol):
    def health_summary(self) -> dict[str, str | int | float]: ...
