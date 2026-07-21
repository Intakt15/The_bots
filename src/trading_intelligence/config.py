"""Typed configuration system using pydantic-settings.

All secrets use SecretStr to prevent accidental logging.
Configuration is loaded from environment variables and .env file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Trading environment ──────────────────────────────────────────
    trading_environment: Literal["paper", "live"] = "paper"
    """Must be 'paper' for simulation or 'live' for real MT5 execution."""

    # ── MetaTrader 5 ─────────────────────────────────────────────────
    mt5_terminal_path: str = ""
    """Path to MT5 terminal executable. Required only for live mode on Windows."""

    mt5_login: int = 0
    mt5_password: SecretStr = Field(default_factory=lambda: SecretStr(""))
    mt5_server: str = ""

    # ── Database ─────────────────────────────────────────────────────
    database_url: str = "sqlite:///data/trading_intelligence.sqlite3"
    """SQLite by default; swap to postgresql+asyncpg://... for production."""

    # ── Risk parameters ──────────────────────────────────────────────
    max_daily_drawdown: float = 0.05
    """Maximum daily drawdown as a fraction of equity (0.05 = 5%)."""

    max_total_drawdown: float = 0.15
    """Maximum total drawdown as a fraction of equity (0.15 = 15%)."""

    max_positions: int = 3
    """Maximum concurrent open positions across all instruments."""

    max_positions_per_instrument: int = 1
    """Maximum concurrent positions on a single instrument."""

    default_position_size: float = 0.01
    """Default lot size when no dynamic sizing is available."""

    atr_period: int = 14
    """ATR period for dynamic position sizing."""

    atr_multiplier: float = 1.5
    """ATR multiplier for stop-loss distance calculation."""

    correlation_exposure_limit: float = 0.70
    """Max allowed correlation between any two open positions (absolute value)."""

    volatility_kill_switch: float = 3.0
    """If spread exceeds this multiple of average spread, halt trading for that symbol."""

    # ── Session configuration ────────────────────────────────────────
    session_asian_start: int = 0  # UTC hour
    session_asian_end: int = 9
    session_london_start: int = 8
    session_london_end: int = 17
    session_ny_start: int = 13
    session_ny_end: int = 22

    # ── Instrument whitelist ─────────────────────────────────────────
    instrument_whitelist: list[str] = Field(default_factory=lambda: ["EURUSD", "XAUUSD"])
    """Instruments the engine is allowed to trade."""

    instrument_timeframes: list[str] = Field(
        default_factory=lambda: ["M5", "M15", "H1", "H4", "D1"]
    )
    """Timeframes to fetch and analyze per instrument."""

    # ── Agent weights (0-100, used in consensus) ─────────────────────
    signal_weight: float = 40.0
    session_weight: float = 30.0
    news_weight: float = 30.0

    # ── Consensus thresholds ─────────────────────────────────────────
    consensus_minimum_score: float = 70.0
    consensus_min_confidence: float = 60.0
    """Minimum signal confidence (0-100) for a trade to be considered."""

    # ── Learning AI ──────────────────────────────────────────────────
    learning_min_sample_size: int = 30
    """Minimum number of closed trades before learning produces recommendations."""

    learning_recommendation_confidence: float = 0.80
    """Minimum statistical confidence for auto-generated recommendations."""

    # ── Polling & scheduling ─────────────────────────────────────────
    polling_interval_seconds: int = 60
    """Seconds between market data polls and pipeline runs."""

    # ── Logging ──────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "text"

    # ── Paths ────────────────────────────────────────────────────────
    data_dir: Path = Path("data")
    economic_calendar_path: Path = Path("data/economic_calendar.csv")

    @property
    def is_paper(self) -> bool:
        return self.trading_environment == "paper"

    @property
    def risk_free_rate(self) -> float:
        """Used in Sharpe ratio calculations (default 5% annual)."""
        return 0.05


# Singleton — load once at startup
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def reload_settings() -> Settings:
    global _settings
    _settings = Settings()  # type: ignore[call-arg]
    return _settings
