"""Off-chain trading bot package.

This package is intentionally separate from the MT5 orchestration layer so the
same bot logic can run against CEX APIs, Web3 RPC endpoints, or paper/demo
simulators without mixing secrets or execution concerns into the domain layer.
"""

from .bot import OffchainTradingBot
from .config import OffchainBotSettings
from .models import ExecutionReceipt, MarketQuote, RiskDecision, TradeOpportunity

__all__ = [
    "ExecutionReceipt",
    "MarketQuote",
    "OffchainBotSettings",
    "OffchainTradingBot",
    "RiskDecision",
    "TradeOpportunity",
]
