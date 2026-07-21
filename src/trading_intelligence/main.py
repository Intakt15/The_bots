#!/usr/bin/env python3
"""Multi-Agent MT5 Trading Intelligence — Main Entry Point.

Wires all components together and starts the trading engine.

Usage:
    # Paper trading with mock data (safe default, works on any OS)
    python -m trading_intelligence.main

    # Live MT5 trading (Windows only, requires MT5 terminal running)
    TRADING_ENVIRONMENT=live python -m trading_intelligence.main

    # Single tick (useful for cron/scheduled runs)
    python -m trading_intelligence.main --once

    # Print status and exit
    python -m trading_intelligence.main --status
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from trading_intelligence.config import get_settings, reload_settings, Settings
from trading_intelligence.application.engine import TradingEngine

logger = logging.getLogger(__name__)


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt)
    logging.getLogger("ta").setLevel(logging.WARNING)


def create_market_provider(settings: Settings):
    if settings.is_paper:
        from trading_intelligence.adapters.mock_market_data import MockMarketDataProvider
        return MockMarketDataProvider()
    else:
        from trading_intelligence.adapters.mt5_market_data import Mt5MarketDataProvider
        provider = Mt5MarketDataProvider()
        if not provider.connect():
            logger.error("Failed to connect to MT5. Is the terminal running?")
            sys.exit(1)
        return provider


def create_execution_gateway(settings: Settings):
    if settings.is_paper:
        from trading_intelligence.adapters.paper_execution import PaperExecutionGateway
        return PaperExecutionGateway()
    else:
        from trading_intelligence.adapters.mt5_execution import Mt5ExecutionGateway
        gateway = Mt5ExecutionGateway()
        if not gateway.connect():
            logger.error("Failed to connect to MT5 execution.")
            sys.exit(1)
        return gateway


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-Agent MT5 Trading Intelligence Engine",
    )
    parser.add_argument("--env", type=Path, default=None, help="Path to .env file")
    parser.add_argument("--once", action="store_true", help="Run a single tick and exit")
    parser.add_argument("--interval", type=int, default=None, help="Override polling interval (seconds)")
    parser.add_argument("--instruments", type=str, default=None, help="Comma-separated instrument list")
    parser.add_argument("--status", action="store_true", help="Print engine status and exit")
    args = parser.parse_args()

    if args.env:
        import os
        os.environ["ENV_FILE"] = str(args.env)
    settings = reload_settings()

    if args.interval:
        settings = settings.model_copy(update={"polling_interval_seconds": args.interval})
    if args.instruments:
        settings = settings.model_copy(
            update={"instrument_whitelist": [s.strip() for s in args.instruments.split(",")]}
        )

    setup_logging(settings)

    logger.info("=" * 60)
    logger.info("Multi-Agent MT5 Trading Intelligence")
    logger.info("Environment: %s", settings.trading_environment.upper())
    logger.info("Instruments: %s", ", ".join(settings.instrument_whitelist))
    logger.info("Interval: %ds", settings.polling_interval_seconds)
    logger.info("=" * 60)

    if settings.trading_environment == "live":
        logger.warning("LIVE TRADING MODE - real orders will be placed!")
        if settings.mt5_login == 0:
            logger.error("MT5_LOGIN not set. Cannot connect in live mode.")
            sys.exit(1)

    market_provider = create_market_provider(settings)
    execution_gateway = create_execution_gateway(settings)
    engine = TradingEngine(settings, market_provider, execution_gateway)

    if args.status:
        print(json.dumps(engine.status(), indent=2, default=str))
        return

    if args.once:
        logger.info("Running single tick...")
        engine._tick()
        engine._shutdown()
    else:
        engine.run()


if __name__ == "__main__":
    main()
