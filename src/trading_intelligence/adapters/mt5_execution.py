"""MT5 Execution Gateway adapter.

Implements the ExecutionGateway protocol for MetaTrader 5.
Handles order placement, SL/TP, idempotency, and broker acknowledgement.

MT5 is Windows-only; this adapter raises clear errors on other platforms.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import ClassVar

from trading_intelligence.config import get_settings
from trading_intelligence.domain import ExecutionReport, TradeDecision

logger = logging.getLogger(__name__)


class Mt5ExecutionGateway:
    """Places real orders through MetaTrader 5.

    Requires MT5 terminal to be running and logged in.
    Only instantiated when trading_environment == 'live'.
    """

    _import_error: ClassVar[str | None] = None

    def __init__(self) -> None:
        self._mt5 = self._import_mt5()
        self._submitted_ids: set[str] = set()
        self._connected = False

    @staticmethod
    def _import_mt5():
        """Lazy import with clear error message for non-Windows platforms."""
        try:
            import MetaTrader5 as mt5  # type: ignore[import-untyped]
            return mt5
        except ImportError as exc:
            msg = (
                "MetaTrader5 package is not installed or not available on this platform. "
                "Install with: pip install MetaTrader5  (Windows only). "
                "Use PaperExecutionGateway for development on macOS/Linux."
            )
            Mt5ExecutionGateway._import_error = msg
            raise ImportError(msg) from exc

    def connect(self) -> bool:
        """Initialize and log into MT5 terminal."""
        if self._import_error:
            raise RuntimeError(self._import_error)

        settings = get_settings()

        if not self._mt5.initialize(path=settings.mt5_terminal_path or None):
            error = self._mt5.last_error()
            logger.error("MT5 initialize failed: %s", error)
            return False

        if settings.mt5_login:
            authorized = self._mt5.login(
                login=settings.mt5_login,
                password=settings.mt5_password.get_secret_value(),
                server=settings.mt5_server or "",
            )
            if not authorized:
                error = self._mt5.last_error()
                logger.error("MT5 login failed: %s", error)
                self._mt5.shutdown()
                return False

        self._connected = True
        logger.info("MT5 connected successfully. Account: %s", self._mt5.account_info())
        return True

    def disconnect(self) -> None:
        if self._connected:
            self._mt5.shutdown()
            self._connected = False
            logger.info("MT5 disconnected.")

    # ── ExecutionGateway protocol ────────────────────────────────────

    def submit(self, decision: TradeDecision, idempotency_key: str) -> ExecutionReport:
        """Place an order, enforcing idempotency via decision_id."""
        now = datetime.now(timezone.utc)

        # Idempotency guard
        if idempotency_key in self._submitted_ids:
            logger.warning("Duplicate submission blocked: %s", idempotency_key)
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail=f"Duplicate submission: {idempotency_key} already processed",
            )

        if not self._connected:
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail="MT5 not connected",
            )

        # Build MT5 order request
        symbol = decision.symbol
        price = (
            self._mt5.symbol_info_tick(symbol).ask
            if decision.side.value == "buy"
            else self._mt5.symbol_info_tick(symbol).bid
        )
        if price is None:
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail=f"No price available for {symbol}",
            )

        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(decision.quantity),
            "type": (
                self._mt5.ORDER_TYPE_BUY
                if decision.side.value == "buy"
                else self._mt5.ORDER_TYPE_SELL
            ),
            "price": price,
            "deviation": 10,
            "magic": 0,
            "comment": f"TI:{idempotency_key[:8]}",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }

        # Optional SL/TP from signal
        if decision.signal and decision.signal.stop_loss:
            request["sl"] = float(decision.signal.stop_loss)
        if decision.signal and decision.signal.take_profit:
            request["tp"] = float(decision.signal.take_profit)

        result = self._mt5.order_send(request)
        if result is None:
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail="MT5 order_send returned None",
            )

        if result.retcode != self._mt5.TRADE_RETCODE_DONE:
            self._submitted_ids.add(idempotency_key)
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=str(result.order) if result.order else None,
                timestamp=now,
                detail=f"Order rejected: {result.comment or 'unknown error'} (code={result.retcode})",
            )

        self._submitted_ids.add(idempotency_key)
        broker_id = str(result.order)
        logger.info(
            "MT5 order placed: %s %s %.2f @ %s | order_id=%s",
            decision.symbol,
            decision.side.value,
            float(decision.quantity),
            price,
            broker_id,
        )

        return ExecutionReport(
            decision_id=decision.decision_id,
            accepted=True,
            broker_order_id=broker_id,
            timestamp=now,
            detail=f"Filled at {price}",
        )
