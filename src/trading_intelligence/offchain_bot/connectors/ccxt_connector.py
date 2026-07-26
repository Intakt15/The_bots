"""CCXT-based market data and execution connectors.

Security notes:
- API credentials are passed in from environment-backed settings only.
- The connector never prints secrets or includes them in raised exceptions.
- Live order placement is only enabled when the caller intentionally selects
  live mode; paper/demo mode should continue to use the simulated connector.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from trading_intelligence.offchain_bot.models import (
    ExecutionReceipt,
    MarketQuote,
    TradeOpportunity,
)

logger = logging.getLogger(__name__)


def _load_ccxt():
    try:
        import ccxt  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError("ccxt is required for CEX integration. Install the package before using live mode.") from exc
    return ccxt


class CcxtMarketDataConnector:
    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        password: str = "",
    ) -> None:
        self._exchange_id = exchange_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._password = password
        self._exchange = None

    def connect(self) -> bool:
        ccxt = _load_ccxt()
        exchange_factory = getattr(ccxt, self._exchange_id, None)
        if exchange_factory is None:
            logger.error("Unsupported exchange id: %s", self._exchange_id)
            return False

        self._exchange = exchange_factory(
            {
                "apiKey": self._api_key,
                "secret": self._api_secret,
                "password": self._password or None,
                "enableRateLimit": True,
                "timeout": 20000,
            }
        )
        self._exchange.load_markets()
        return True

    def get_quote(self, symbol: str, timeframe: str) -> MarketQuote:
        if self._exchange is None:
            raise RuntimeError("CCXT market connector not connected")

        ticker = self._exchange.fetch_ticker(symbol)
        now = datetime.now(timezone.utc)
        last = Decimal(str(ticker.get("last") or ticker.get("close") or 0))
        bid = Decimal(str(ticker.get("bid") or (last * Decimal("0.9995") if last > 0 else 0)))
        ask = Decimal(str(ticker.get("ask") or (last * Decimal("1.0005") if last > 0 else 0)))
        if bid <= 0 or ask <= 0:
            raise RuntimeError(f"Exchange {self._exchange_id} returned an invalid quote for {symbol}")

        return MarketQuote(symbol=symbol, timestamp=now, bid=bid, ask=ask, source=f"ccxt:{self._exchange_id}:{timeframe}")

    def close(self) -> None:
        if self._exchange is not None:
            close = getattr(self._exchange, "close", None)
            if callable(close):
                close()
            self._exchange = None


class CcxtExecutionConnector:
    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        password: str = "",
    ) -> None:
        self._exchange_id = exchange_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._password = password
        self._exchange = None

    def connect(self) -> bool:
        ccxt = _load_ccxt()
        exchange_factory = getattr(ccxt, self._exchange_id, None)
        if exchange_factory is None:
            logger.error("Unsupported exchange id: %s", self._exchange_id)
            return False

        self._exchange = exchange_factory(
            {
                "apiKey": self._api_key,
                "secret": self._api_secret,
                "password": self._password or None,
                "enableRateLimit": True,
                "timeout": 20000,
            }
        )
        self._exchange.load_markets()
        return True

    def execute(self, opportunity: TradeOpportunity, approved_size_usd: Decimal) -> ExecutionReceipt:
        now = datetime.now(timezone.utc)
        if self._exchange is None:
            return ExecutionReceipt(False, None, now, "CCXT execution connector not connected", paper=False)

        amount = approved_size_usd / opportunity.quote.mid
        if amount <= Decimal("0"):
            return ExecutionReceipt(False, None, now, "Calculated order amount is invalid", paper=False)

        side = opportunity.direction
        try:
            order = self._exchange.create_order(
                opportunity.symbol,
                "market",
                side,
                float(amount),
            )
        except Exception as exc:
            return ExecutionReceipt(False, None, now, f"CCXT order failed: {exc}", paper=False)

        order_id = str(order.get("id") or order.get("orderId") or "") or None
        logger.info(
            "Live execution: %s %s size_usd=%s order_id=%s",
            opportunity.symbol,
            side,
            approved_size_usd,
            order_id,
        )
        return ExecutionReceipt(True, order_id, now, f"Order submitted via {self._exchange_id}", paper=False)

    def close(self) -> None:
        if self._exchange is not None:
            close = getattr(self._exchange, "close", None)
            if callable(close):
                close()
            self._exchange = None
