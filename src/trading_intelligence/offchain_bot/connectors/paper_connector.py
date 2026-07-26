"""Paper/demo execution connector.

This connector never sends an order to an external venue. It simulates fills
with a bounded amount of slippage and a configurable fill probability so the
same strategy code can be validated safely before live trading.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from trading_intelligence.offchain_bot.models import ExecutionReceipt, TradeOpportunity

logger = logging.getLogger(__name__)


class PaperExecutionConnector:
    def __init__(self, slippage_bps: Decimal = Decimal("5"), fill_probability: float = 0.98) -> None:
        self._slippage_bps = slippage_bps
        self._fill_probability = fill_probability
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def execute(self, opportunity: TradeOpportunity, approved_size_usd: Decimal) -> ExecutionReceipt:
        now = datetime.now(timezone.utc)
        if not self._connected:
            return ExecutionReceipt(False, None, now, "Paper connector not initialized", paper=True)

        if random.random() > self._fill_probability:
            return ExecutionReceipt(False, None, now, "Simulated paper fill rejection", paper=True)

        slip_fraction = self._slippage_bps / Decimal("10000")
        slip = opportunity.quote.mid * slip_fraction
        fill_price = opportunity.quote.ask + slip if opportunity.direction == "buy" else opportunity.quote.bid - slip
        order_id = f"PAPER-{uuid4().hex[:12].upper()}"
        logger.info(
            "Paper execution: %s %s size_usd=%s fill_price=%s order_id=%s",
            opportunity.symbol,
            opportunity.direction,
            approved_size_usd,
            fill_price,
            order_id,
        )
        return ExecutionReceipt(True, order_id, now, f"Simulated fill at {fill_price}", paper=True)

    def close(self) -> None:
        self._connected = False
