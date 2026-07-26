"""Framework-free, immutable contracts shared by every component."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Mapping
from uuid import UUID, uuid4


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


class DecisionStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    HOLD = "hold"


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    symbol: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    timeframe: str
    indicators: Mapping[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Signal:
    source: str
    symbol: str
    side: Side
    confidence: Decimal
    generated_at: datetime
    thesis: str
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    evidence: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentAssessment:
    agent: str
    score: Decimal  # 0 through 100
    eligible: bool
    rationale: str
    generated_at: datetime
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SentimentAssessment:
    source: str
    symbol: str
    sentiment_score: Decimal
    confidence: Decimal
    flagged_risk: bool
    rationale: str
    generated_at: datetime
    topics: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class LiquidityAssessment:
    source: str
    symbol: str
    depth_score: Decimal
    imbalance_score: Decimal
    confidence: Decimal
    whale_activity: bool
    rationale: str
    generated_at: datetime
    venues: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ArbitrageOpportunity:
    source: str
    symbol: str
    venue_a: str
    venue_b: str
    spread_bps: Decimal
    edge_score: Decimal
    profitable: bool
    rationale: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class ComplianceAssessment:
    source: str
    symbol: str
    allowed: bool
    policy_version: str
    violations: tuple[str, ...] = field(default_factory=tuple)
    rate_limit_remaining: int | None = None
    rationale: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class AccountState:
    equity: Decimal
    balance: Decimal
    open_risk: Decimal
    daily_drawdown: Decimal
    open_positions: int


@dataclass(frozen=True, slots=True)
class TradeDecision:
    symbol: str
    side: Side
    status: DecisionStatus
    confidence: Decimal
    quantity: Decimal
    created_at: datetime
    rationale: str
    signal: Signal | None = None
    decision_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    approved: bool
    approved_quantity: Decimal
    reasons: tuple[str, ...]
    assessed_at: datetime


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    decision_id: UUID
    accepted: bool
    broker_order_id: str | None
    timestamp: datetime
    detail: str


@dataclass(frozen=True, slots=True)
class TradeOutcome:
    decision_id: UUID
    closed_at: datetime
    realized_pnl: Decimal
    exit_reason: str
