"""Connector protocols for the off-chain bot."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from trading_intelligence.offchain_bot.models import ExecutionReceipt, MarketQuote, TradeOpportunity


class MarketDataConnector(Protocol):
    def connect(self) -> bool: ...

    def get_quote(self, symbol: str, timeframe: str) -> MarketQuote: ...

    def close(self) -> None: ...


class ExecutionConnector(Protocol):
    def connect(self) -> bool: ...

    def execute(self, opportunity: TradeOpportunity, approved_size_usd: Decimal) -> ExecutionReceipt: ...

    def close(self) -> None: ...
