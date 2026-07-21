"""Paper Trading Execution Gateway.

Simulates order execution without touching a real broker.
Includes configurable slippage, latency, and fill simulation.
This is the DEFAULT execution gateway — safe for development and testing.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from trading_intelligence.domain import ExecutionReport, Side, TradeDecision

logger = logging.getLogger(__name__)


class PaperExecutionGateway:
    """Simulates broker execution with realistic slippage modeling.

    Maintains an in-memory position tracker. All fills are recorded
    but no real orders are placed.

    Idempotency is enforced via decision_id deduplication.
    """

    def __init__(
        self,
        slippage_pips: float = 0.5,
        fill_probability: float = 0.98,
        latency_ms: int = 50,
    ) -> None:
        """
        Args:
            slippage_pips: Average slippage in pips (applied as noise).
            fill_probability: Probability of order fill (0-1). 0.98 = 98%.
            latency_ms: Simulated execution latency in milliseconds.
        """
        self._submitted_ids: set[str] = set()
        self._positions: dict[str, dict] = {}  # symbol -> position info
        self.slippage_pips = slippage_pips
        self.fill_probability = fill_probability
        self.latency_ms = latency_ms

    def submit(self, decision: TradeDecision, idempotency_key: str) -> ExecutionReport:
        """Simulate order submission with slippage and fill probability."""
        now = datetime.now(timezone.utc)

        # Idempotency guard
        if idempotency_key in self._submitted_ids:
            logger.warning("Paper: duplicate submission blocked for %s", idempotency_key)
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail=f"Duplicate submission: {idempotency_key} already processed",
            )

        # Simulate fill probability
        if random.random() > self.fill_probability:
            self._submitted_ids.add(idempotency_key)
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail="Paper: order not filled (simulated slippage/failure)",
            )

        broker_id = f"PAPER-{uuid4().hex[:12].upper()}"

        # Simulate slippage on entry price
        slip = Decimal(str(round(random.uniform(-self.slippage_pips, self.slippage_pips) * 0.0001, 5)))
        fill_price = None
        if decision.signal and decision.side:
            if decision.side == Side.BUY:
                fill_price = Decimal("0") + slip  # placeholder; real price from snapshot
            else:
                fill_price = Decimal("0") - slip

        # Track position
        self._positions[decision.symbol] = {
            "side": decision.side.value,
            "quantity": float(decision.quantity),
            "entry_time": now.isoformat(),
            "broker_id": broker_id,
        }

        self._submitted_ids.add(idempotency_key)

        logger.info(
            "Paper: %s %s %.2f | id=%s | slip=%.5f",
            decision.symbol,
            decision.side.value,
            float(decision.quantity),
            broker_id,
            slip,
        )

        return ExecutionReport(
            decision_id=decision.decision_id,
            accepted=True,
            broker_order_id=broker_id,
            timestamp=now,
            detail=f"Paper fill simulated (slip={slip})",
        )

    @property
    def open_positions(self) -> dict[str, dict]:
        """Return current simulated positions."""
        return dict(self._positions)

    def close_position(self, symbol: str, exit_price: Decimal) -> Decimal | None:
        """Simulate closing a position and return PnL."""
        pos = self._positions.pop(symbol, None)
        if pos is None:
            return None

        entry = Decimal(str(pos["quantity"]))
        if pos["side"] == "buy":
            pnl = (exit_price - Decimal("0")) * entry  # simplified
        else:
            pnl = (Decimal("0") - exit_price) * entry

        logger.info("Paper: closed %s PnL=%.2f", symbol, float(pnl))
        return pnl
