"""Configuration for the off-chain trading bot.

All secrets are read from environment variables only. In production, populate
those variables from a secret manager such as Azure Key Vault or your container
orchestrator's secret injection mechanism.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class OffchainBotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OFFCHAIN_", env_file=None, extra="ignore")

    trading_mode: Literal["paper", "demo", "live"] = "paper"
    market_backend: Literal["ccxt", "web3"] = "ccxt"
    exchange_id: str = "binance"
    symbol: str = "ETH/USDT"
    timeframe: str = "1m"
    poll_interval_seconds: int = 30
    lookback_window: int = 20

    max_trade_size_usd: Decimal = Decimal("100")
    max_slippage_bps: Decimal = Decimal("50")
    stop_loss_pct: Decimal = Decimal("0.01")
    take_profit_pct: Decimal = Decimal("0.02")
    kill_switch_drawdown_pct: Decimal = Decimal("0.05")
    min_liquidity_usd: Decimal = Decimal("1000")
    assumed_spread_bps: Decimal = Decimal("20")

    paper_fill_probability: float = 0.98
    paper_slippage_bps: Decimal = Decimal("5")

    rpc_url: SecretStr = Field(default_factory=lambda: SecretStr(""))
    oracle_address: str = ""
    exchange_api_key: SecretStr = Field(default_factory=lambda: SecretStr(""))
    exchange_api_secret: SecretStr = Field(default_factory=lambda: SecretStr(""))
    exchange_api_password: SecretStr = Field(default_factory=lambda: SecretStr(""))
    wallet_private_key: SecretStr = Field(default_factory=lambda: SecretStr(""))
    api_passphrase: SecretStr = Field(default_factory=lambda: SecretStr(""))

    data_dir: Path = Path("data")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @property
    def is_paper(self) -> bool:
        return self.trading_mode in {"paper", "demo"}

    @property
    def is_live(self) -> bool:
        return self.trading_mode == "live"
