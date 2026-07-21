"""MT5 Execution Gateway adapter.

Implements the ExecutionGateway protocol for MetaTrader 5.
Handles order placement, SL/TP, idempotency, and broker acknowledgement.

Imports cleanly on macOS/Linux — only raises errors when
connect() is called without the MetaTrader5 package installed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from trading_intelligence.config import get_settings
from trading_intelligence.domain import ExecutionReport, TradeDecision

logger = logging.getLogger(__name__)

_MT5_IMPORT_ERROR: str | None = None


def _get_mt5():
    """Lazy import — only fails when actually trying to use MT5."""
    global _MT5_IMPORT_ERROR
    if _MT5_IMPORT_ERROR:
        raise ImportError(_MT5_IMPORT_ERROR)
    try:
        import MetaTrader5 as mt5  # type: ignore[import-untyped]
        return mt5
    except ImportError:
        _MT5_IMPORT_ERROR = (
            "MetaTrader5 package not available on this platform. "
            "Install with: pip install MetaTrader5 (Windows only). "
            "Use PaperExecutionGateway on macOS/Linux for development."
        )
        raise ImportError(_MT5_IMPORT_ERROR)


class Mt5ExecutionGateway:
    """Places real orders through MetaTrader 5.

    Requires MT5 terminal to be running and logged in.
    Imports cleanly on all platforms — only connect() requires MT5.
    """

    def __init__(self) -> None:
        self._submitted_ids: set[str] = set()
        self._connected = False

    def connect(self) -> bool:
        """Initialize and log into MT5 terminal."""
        mt5 = _get_mt5()
        settings = get_settings()

        if not mt5.initialize(path=settings.mt5_terminal_path or None):
            logger.error("MT5 initialize failed: %s", mt5.last_error())
            return False

        if settings.mt5_login:
            authorized = mt5.login(
                login=settings.mt5_login,
                password=settings.mt5_password.get_secret_value(),
                server=settings.mt5_server or "",
            )
            if not authorized:
                logger.error("MT5 login failed: %s", mt5.last_error())
                mt5.shutdown()
                return False

        self._connected = True
        logger.info("MT5 connected. Account: %s", mt5.account_info())
        return True

    def disconnect(self) -> None:
        if self._connected:
            _get_mt5().shutdown()
            self._connected = False
            logger.info("MT5 disconnected.")

    def submit(self, decision: TradeDecision, idempotency_key: str) -> ExecutionReport:
        mt5 = _get_mt5()
        now = datetime.now(timezone.utc)

        if idempotency_key in self._submitted_ids:
            logger.warning("Duplicate submission blocked: %s", idempotency_key)
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False, broker_order_id=None, timestamp=now,
                detail=f"Duplicate submission: {idempotency_key} already processed",
            )

        if not self._connected:
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False, broker_order_id=None, timestamp=now,
                detail="MT5 not connected",
            )

        symbol = decision.symbol
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if decision.side.value == "buy" else tick.bid
        if price is None:
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False, broker_order_id=None, timestamp=now,
                detail=f"No price available for {symbol}",
            )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(decision.quantity),
            "type": mt5.ORDER_TYPE_BUY if decision.side.value == "buy" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": 10,
            "magic": 0,
            "comment": f"TI:{idempotency_key[:8]}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        if decision.signal and decision.signal.stop_loss:
            request["sl"] = float(decision.signal.stop_loss)
        if decision.signal and decision.signal.take_profit:
            request["tp"] = float(decision.signal.take_profit)

        result = mt5.order_send(request)
        if result is None:
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False, broker_order_id=None, timestamp=now,
                detail="MT5 order_send returned None",
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
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
            "MT5 order: %s %s %.2f @ %s | id=%s",
            decision.symbol, decision.side.value,
            float(decision.quantity), price, broker_id,
        )

        return ExecutionReport(
            decision_id=decision.decision_id,
            accepted=True,
            broker_order_id=broker_id,
            timestamp=now,
            detail=f"Filled at {price}",
        )
