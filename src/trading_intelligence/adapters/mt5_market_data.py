"""MT5 Market Data Provider adapter.

Implements the MarketDataProvider protocol for MetaTrader 5.
Fetches real-time bid/ask quotes, OHLCV history, and computes
technical indicators (RSI, MACD, EMA, ATR, Bollinger Bands, etc.)
using the 'ta' library.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import ClassVar

import pandas as pd
import ta

from trading_intelligence.config import get_settings
from trading_intelligence.domain import MarketSnapshot

logger = logging.getLogger(__name__)

TIMEFRAME_MAP: dict[str, int] = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440, "W1": 10080,
}


class Mt5MarketDataProvider:
    """Fetches market data from a running MetaTrader 5 terminal.

    Connects to MT5, retrieves OHLCV bars for configured timeframes,
    computes technical indicators, and returns MarketSnapshot objects.
    """

    _import_error: ClassVar[str | None] = None

    def __init__(self) -> None:
        self._settings = get_settings()
        self._mt5 = self._import_mt5()
        self._connected = False

    @staticmethod
    def _import_mt5():
        try:
            import MetaTrader5 as mt5  # type: ignore[import-untyped]
            return mt5
        except ImportError as exc:
            msg = (
                "MetaTrader5 package not available on this platform. "
                "Install with: pip install MetaTrader5 (Windows only)."
            )
            Mt5MarketDataProvider._import_error = msg
            raise ImportError(msg) from exc

    def connect(self) -> bool:
        if self._import_error:
            raise RuntimeError(self._import_error)
        s = self._settings
        if not self._mt5.initialize(path=s.mt5_terminal_path or None):
            logger.error("MT5 initialize failed: %s", self._mt5.last_error())
            return False
        if s.mt5_login:
            if not self._mt5.login(
                login=s.mt5_login,
                password=s.mt5_password.get_secret_value(),
                server=s.mt5_server or "",
            ):
                logger.error("MT5 login failed: %s", self._mt5.last_error())
                self._mt5.shutdown()
                return False
        self._connected = True
        logger.info("MT5 data connected.")
        return True

    def disconnect(self) -> None:
        if self._connected:
            self._mt5.shutdown()
            self._connected = False

    def ensure_connected(self) -> None:
        if not self._connected and not self.connect():
            raise ConnectionError("Failed to connect to MT5 terminal")

    # ── MarketDataProvider protocol ──────────────────────────────────

    def snapshot(
        self, symbol: str, timeframe: str = "H1", bars_count: int = 100
    ) -> MarketSnapshot:
        self.ensure_connected()
        tf = TIMEFRAME_MAP.get(timeframe.upper(), 60)

        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ValueError(f"No tick data for {symbol}.")

        bid = Decimal(str(tick.bid))
        ask = Decimal(str(tick.ask))
        now = datetime.now(timezone.utc)

        bars = self._mt5.copy_rates_from_pos(symbol, tf, 0, bars_count)
        if bars is None or len(bars) == 0:
            return MarketSnapshot(symbol=symbol, timestamp=now, bid=bid, ask=ask, timeframe=timeframe, indicators={})

        df = pd.DataFrame(bars)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        indicators = self._compute_indicators(df)
        return MarketSnapshot(symbol=symbol, timestamp=now, bid=bid, ask=ask, timeframe=timeframe, indicators=indicators)

    def get_account_info(self) -> dict:
        self.ensure_connected()
        info = self._mt5.account_info()
        if info is None:
            return {}
        return {
            "login": info.login, "balance": info.balance, "equity": info.equity,
            "currency": info.currency, "margin": info.margin,
            "free_margin": info.margin_free, "leverage": info.leverage,
        }

    def get_open_positions(self) -> list[dict]:
        self.ensure_connected()
        positions = self._mt5.positions_get()
        if positions is None:
            return []
        return [
            {
                "ticket": p.ticket, "symbol": p.symbol,
                "type": "buy" if p.type == 0 else "sell",
                "volume": p.volume, "open_price": p.price_open,
                "current_price": p.price_current, "sl": p.sl, "tp": p.tp,
                "profit": p.profit,
            }
            for p in positions
        ]

    # ── Technical Indicators ─────────────────────────────────────────

    def _compute_indicators(self, df: pd.DataFrame) -> dict[str, Decimal]:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        indicators: dict[str, Decimal] = {}

        try:
            # RSI 14
            rsi = ta.momentum.RSIIndicator(close=close, window=14).rsi()
            if not rsi.empty and not pd.isna(rsi.iloc[-1]):
                indicators["RSI_14"] = Decimal(str(round(rsi.iloc[-1], 2)))

            # MACD
            macd = ta.trend.MACD(close=close)
            if not macd.macd().empty:
                indicators["MACD"] = Decimal(str(round(macd.macd().iloc[-1], 6)))
            if not macd.macd_signal().empty:
                indicators["MACD_SIGNAL"] = Decimal(str(round(macd.macd_signal().iloc[-1], 6)))

            # EMAs
            for p in [12, 26, 50]:
                ema = ta.trend.EMAIndicator(close=close, window=p).ema_indicator()
                if not ema.empty:
                    indicators[f"EMA_{p}"] = Decimal(str(round(ema.iloc[-1], 6)))

            # ATR 14
            atr = ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
            if not atr.empty:
                indicators["ATR_14"] = Decimal(str(round(atr.iloc[-1], 6)))

            # Bollinger Bands
            bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
            if not bb.bollinger_hband().empty:
                indicators["BB_UPPER"] = Decimal(str(round(bb.bollinger_hband().iloc[-1], 6)))
                indicators["BB_MIDDLE"] = Decimal(str(round(bb.bollinger_mavg().iloc[-1], 6)))
                indicators["BB_LOWER"] = Decimal(str(round(bb.bollinger_lband().iloc[-1], 6)))

            # Pivot Points (classic daily)
            if len(df) >= 2:
                ph, pl, pc = float(high.iloc[-2]), float(low.iloc[-2]), float(close.iloc[-2])
                pivot = (ph + pl + pc) / 3
                indicators["PIVOT"] = Decimal(str(round(pivot, 6)))
                indicators["R1"] = Decimal(str(round(2 * pivot - pl, 6)))
                indicators["S1"] = Decimal(str(round(2 * pivot - ph, 6)))

            # ADX 14
            adx = ta.trend.ADXIndicator(high=high, low=low, close=close, window=14).adx()
            if not adx.empty:
                indicators["ADX_14"] = Decimal(str(round(adx.iloc[-1], 2)))
        except Exception:
            logger.exception("Error computing indicators")

        return indicators
