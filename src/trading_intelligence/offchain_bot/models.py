"""Dataclasses used by the off-chain trading bot.

These models deliberately stay framework-free so they can be used by CEX, DEX,
paper, and containerized deployments without pulling in infrastructure code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class MarketQuote:
    symbol: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    source: str

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def spread_bps(self) -> Decimal:
        mid = self.mid
        if mid <= Decimal("0"):
            return Decimal("0")
        return (self.spread / mid) * Decimal("10000")


@dataclass(frozen=True, slots=True)
class TradeOpportunity:
    symbol: str
    direction: Literal["buy", "sell"]
    confidence: Decimal
    expected_edge_bps: Decimal
    suggested_size_usd: Decimal
    stop_loss_price: Decimal
    take_profit_price: Decimal
    rationale: str
    quote: MarketQuote


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    executable_size_usd: Decimal
    reason: str
    kill_switch_triggered: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    accepted: bool
    order_id: str | None
    executed_at: datetime
    details: str
    paper: bool
