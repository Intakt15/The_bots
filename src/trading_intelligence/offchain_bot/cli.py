"""CLI entry point for the off-chain trading bot."""

from __future__ import annotations

import argparse
import logging

from trading_intelligence.offchain_bot.bot import OffchainTradingBot
from trading_intelligence.offchain_bot.config import OffchainBotSettings
from trading_intelligence.offchain_bot.connectors.ccxt_connector import (
    CcxtExecutionConnector,
    CcxtMarketDataConnector,
)
from trading_intelligence.offchain_bot.connectors.paper_connector import PaperExecutionConnector
from trading_intelligence.offchain_bot.connectors.web3_connector import Web3OracleMarketDataConnector

logger = logging.getLogger(__name__)


def _setup_logging(settings: OffchainBotSettings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _build_market_connector(settings: OffchainBotSettings):
    if settings.market_backend == "ccxt":
        return CcxtMarketDataConnector(
            exchange_id=settings.exchange_id,
            api_key=settings.exchange_api_key.get_secret_value(),
            api_secret=settings.exchange_api_secret.get_secret_value(),
            password=settings.exchange_api_password.get_secret_value(),
        )

    return Web3OracleMarketDataConnector(
        rpc_url=settings.rpc_url.get_secret_value(),
        oracle_address=settings.oracle_address,
        assumed_spread_bps=settings.assumed_spread_bps,
    )


def _build_execution_connector(settings: OffchainBotSettings):
    if settings.is_paper:
        return PaperExecutionConnector(
            slippage_bps=settings.paper_slippage_bps,
            fill_probability=settings.paper_fill_probability,
        )

    if settings.market_backend != "ccxt":
        raise SystemExit(
            "Live trading is only enabled for the ccxt backend in this scaffold. "
            "Use paper/demo with the Web3 backend or wire a dedicated DEX execution adapter."
        )

    return CcxtExecutionConnector(
        exchange_id=settings.exchange_id,
        api_key=settings.exchange_api_key.get_secret_value(),
        api_secret=settings.exchange_api_secret.get_secret_value(),
        password=settings.exchange_api_password.get_secret_value(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Off-chain trading bot")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--symbol", type=str, default=None, help="Override the configured symbol")
    parser.add_argument("--mode", type=str, choices=["paper", "demo", "live"], default=None, help="Override trading mode")
    parser.add_argument("--backend", type=str, choices=["ccxt", "web3"], default=None, help="Override the market backend")
    args = parser.parse_args()

    settings = OffchainBotSettings()
    if args.symbol:
        settings = settings.model_copy(update={"symbol": args.symbol})
    if args.mode:
        settings = settings.model_copy(update={"trading_mode": args.mode})
    if args.backend:
        settings = settings.model_copy(update={"market_backend": args.backend})

    _setup_logging(settings)
    logger.info(
        "Off-chain bot starting: mode=%s backend=%s symbol=%s",
        settings.trading_mode,
        settings.market_backend,
        settings.symbol,
    )

    market = _build_market_connector(settings)
    execution = _build_execution_connector(settings)
    bot = OffchainTradingBot(settings, market, execution)
    if not bot.connect():
        raise SystemExit("Failed to initialize the bot connectors")

    try:
        if args.once:
            bot.run_once()
        else:
            bot.run_forever()
    finally:
        bot.close()


if __name__ == "__main__":
    main()
