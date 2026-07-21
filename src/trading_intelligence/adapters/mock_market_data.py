"""Mock Market Data Provider for development and testing.

Produces realistic but synthetic market data with configurable
price, spread, and volatility. Usable on any platform.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from decimal import Decimal

from trading_intelligence.domain import MarketSnapshot

logger = logging.getLogger(__name__)


class MockMarketDataProvider:
    """Generates synthetic market data for development/testing.

    Simulates realistic bid/ask with spread and computed technical
    indicators. Useful when MT5 is not available (macOS/Linux).
    """

    def __init__(
        self,
        spread_pips: float = 1.0,
        volatility_pct: float = 0.001,
    ):
        self._prices: dict[str, float] = {}
        self._base_prices = {
            "EURUSD": 1.0850, "GBPUSD": 1.2700, "USDJPY": 150.00,
            "XAUUSD": 2420.00, "AUDUSD": 0.6650, "USDCHF": 0.8950,
            "USDCAD": 1.3650, "NZDUSD": 0.6100, "EURJPY": 163.00,
            "GBPJPY": 191.00,
        }
        self._spread = spread_pips
        self._volatility = volatility_pct

    def snapshot(self, symbol: str, timeframe: str = "H1") -> MarketSnapshot:
        now = datetime.now(timezone.utc)
        if symbol not in self._prices:
            self._prices[symbol] = self._base_prices.get(symbol, 100.0)
        change = random.gauss(0, self._volatility * 0.5)
        self._prices[symbol] *= (1 + change)
        mid = self._prices[symbol]
        half_spread = self._spread * 0.00005
        bid = Decimal(str(round(mid - half_spread, 5)))
        ask = Decimal(str(round(mid + half_spread, 5)))
        indicators = self._mock_indicators(Decimal(str(mid)))
        return MarketSnapshot(
            symbol=symbol, timestamp=now, bid=bid, ask=ask,
            timeframe=timeframe, indicators=indicators,
        )

    def _mock_indicators(self, price: Decimal) -> dict[str, Decimal]:
        p = float(price)
        return {
            "RSI_14": Decimal(str(round(random.uniform(35, 65), 2))),
            "MACD": Decimal(str(round(random.uniform(-0.001, 0.001), 6))),
            "MACD_SIGNAL": Decimal(str(round(random.uniform(-0.001, 0.001), 6))),
            "EMA_12": Decimal(str(round(p * random.uniform(0.998, 1.002), 6))),
            "EMA_26": Decimal(str(round(p * random.uniform(0.996, 1.004), 6))),
            "EMA_50": Decimal(str(round(p * random.uniform(0.994, 1.006), 6))),
            "ATR_14": Decimal(str(round(p * 0.005, 6))),
            "BB_UPPER": Decimal(str(round(p * 1.02, 6))),
            "BB_MIDDLE": Decimal(str(round(p, 6))),
            "BB_LOWER": Decimal(str(round(p * 0.98, 6))),
            "PIVOT": Decimal(str(round(p, 6))),
            "R1": Decimal(str(round(p * 1.01, 6))),
            "S1": Decimal(str(round(p * 0.99, 6))),
            "ADX_14": Decimal(str(round(random.uniform(15, 35), 2))),
        }
