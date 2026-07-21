"""Main Trading Engine Orchestrator.

Wires all components together and runs the decision loop:
1. Fetch market snapshots per instrument
2. Run each specialized AI agent
3. Pass through consensus → risk → execution pipeline
4. Log results and persist to database

Supports paper trading (default) and live MT5 modes.
Error isolation: one instrument failure doesn't crash the engine.
"""

from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from trading_intelligence.agents.learning_ai import LearningAI
from trading_intelligence.agents.news_ai import NewsAI
from trading_intelligence.agents.risk_ai import RiskManager
from trading_intelligence.agents.session_ai import SessionAI
from trading_intelligence.agents.signal_ai import SignalAI
from trading_intelligence.application.pipeline import (
    DecisionPipeline,
    FixedRiskPolicy,
    WeightedConsensus,
)
from trading_intelligence.config import Settings, get_settings
from trading_intelligence.database.sqlite_repository import SqliteDecisionRepository
from trading_intelligence.domain import (
    AccountState,
    AgentAssessment,
    ExecutionReport,
    MarketSnapshot,
    Signal,
    TradeDecision,
)
from trading_intelligence.interfaces.ports import ExecutionGateway, MarketDataProvider

logger = logging.getLogger(__name__)


class TradingEngine:
    """Main orchestrator for the multi-agent trading system.

    Runs a polling loop that:
    1. Fetches market data for each configured instrument
    2. Runs SignalAI, NewsAI, SessionAI on each snapshot
    3. Passes results through the DecisionPipeline
    4. Records everything to the database

    Example:
        engine = TradingEngine(settings, market_provider, execution_gateway)
        engine.run()  # blocking loop
    """

    def __init__(
        self,
        settings: Settings,
        market_provider: MarketDataProvider,
        execution_gateway: ExecutionGateway,
    ) -> None:
        self._settings = settings
        self._market = market_provider
        self._execution = execution_gateway
        self._running = False

        # Initialize repository
        self._repository = SqliteDecisionRepository()
        self._repository.initialize()

        # Initialize agents
        self._signal_ai = SignalAI()
        self._news_ai = NewsAI()
        self._session_ai = SessionAI()
        self._risk_manager = RiskManager()
        self._learning_ai = LearningAI()

        # Initialize pipeline
        risk_policy = FixedRiskPolicy(
            max_daily_drawdown=Decimal(str(settings.max_daily_drawdown)),
            max_positions=settings.max_positions,
            quantity=Decimal(str(settings.default_position_size)),
        )
        self._pipeline = DecisionPipeline(
            consensus=WeightedConsensus(),
            risk=risk_policy,
            execution=execution_gateway,
            repository=self._repository,
        )

        # Account state (simplified — real impl would fetch from broker)
        self._account = AccountState(
            equity=Decimal("10000"),
            balance=Decimal("10000"),
            open_risk=Decimal("0"),
            daily_drawdown=Decimal("0"),
            open_positions=0,
        )

        logger.info(
            "TradingEngine initialized: env=%s instruments=%s interval=%ds",
            settings.trading_environment,
            settings.instrument_whitelist,
            settings.polling_interval_seconds,
        )

    # ── Main loop ────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the main trading loop. Blocks until stopped."""
        self._running = True
        logger.info("TradingEngine started. Press Ctrl+C to stop.")

        # Graceful shutdown on SIGINT/SIGTERM
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        while self._running:
            try:
                self._tick()
            except Exception:
                logger.exception("Unhandled error in tick — continuing")
                # Error isolation: one bad tick doesn't crash the engine

            self._sleep(self._settings.polling_interval_seconds)

        self._shutdown()

    def _tick(self) -> None:
        """One iteration of the decision loop."""
        now = datetime.now(timezone.utc)

        for symbol in self._settings.instrument_whitelist:
            try:
                self._process_instrument(symbol, now)
            except Exception:
                logger.exception("Error processing %s — skipping", symbol)

    def _process_instrument(self, symbol: str, at: datetime) -> None:
        """Run full decision pipeline for one instrument."""
        # 1. Fetch market snapshot
        snapshot = self._fetch_snapshot(symbol)
        if snapshot is None:
            return

        # 2. Run specialist agents
        signal = self._signal_ai.evaluate(snapshot)
        news_assessment = self._news_ai.evaluate(snapshot)
        session_assessment = self._session_ai.evaluate(snapshot)
        assessments = [news_assessment, session_assessment]

        # Log agent outputs
        logger.debug(
            "%s: signal=%s news=%.1f session=%.1f",
            symbol,
            signal.side.value if signal else "NONE",
            float(news_assessment.score),
            float(session_assessment.score),
        )

        # 3. Run pipeline (consensus → risk → execution)
        decision, report = self._pipeline.process(
            signal, assessments, self._account, at
        )

        # 4. Update risk tracker on execution
        if report and report.accepted:
            self._risk_manager.record_open(symbol)
            self._account = AccountState(
                equity=self._account.equity,
                balance=self._account.balance,
                open_risk=self._account.open_risk,
                daily_drawdown=self._account.daily_drawdown,
                open_positions=self._account.open_positions + 1,
            )

        # 5. Log decision summary
        status = decision.status.value
        if status == "approved":
            logger.info(
                "✓ %s %s %s conf=%.1f qty=%s",
                symbol, decision.side.value, status,
                float(decision.confidence), decision.quantity,
            )
        elif status == "rejected":
            logger.info(
                "✗ %s rejected: %s",
                symbol, decision.rationale[:100],
            )

    # ── Helpers ──────────────────────────────────────────────────────

    def _fetch_snapshot(self, symbol: str) -> MarketSnapshot | None:
        """Fetch market snapshot, handling errors gracefully."""
        for timeframe in self._settings.instrument_timeframes[:1]:  # primary TF
            try:
                return self._market.snapshot(symbol, timeframe)
            except Exception:
                logger.warning(
                    "Failed to fetch snapshot for %s/%s",
                    symbol, timeframe,
                )
        return None

    def _sleep(self, seconds: int) -> None:
        """Sleep with interrupt support."""
        try:
            time.sleep(seconds)
        except (KeyboardInterrupt, InterruptedError):
            self._running = False

    def _handle_shutdown(self, signum: int, frame: object) -> None:
        """Signal handler for graceful shutdown."""
        logger.info("Received signal %d — shutting down", signum)
        self._running = False

    def _shutdown(self) -> None:
        """Clean up resources."""
        logger.info("TradingEngine shutting down...")
        self._repository.close()

        # Run learning analysis on shutdown
        self._run_learning_cycle()

        logger.info("TradingEngine stopped.")

    def _run_learning_cycle(self) -> None:
        """Run offline learning analysis on closed outcomes."""
        logger.info("Running learning cycle...")
        summary = self._repository.get_outcomes_summary()
        logger.info(
            "Outcomes: %d trades, PnL=%.2f, win_rate=%.0f%%",
            summary["total_trades"],
            summary["total_pnl"],
            summary["win_rate"] * 100,
        )

        # In production, fetch outcomes from DB and pass to learning AI
        # recommendations = self._learning_ai.analyze(outcomes)
        # for rec in recommendations:
        #     logger.info("Learning recommendation: %s", rec)

    # ── Status ───────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return engine status for dashboard/monitoring."""
        return {
            "running": self._running,
            "instruments": self._settings.instrument_whitelist,
            "environment": self._settings.trading_environment,
            "risk": self._risk_manager.status_summary(),
            "database": self._repository.health_check(),
            "account": {
                "equity": str(self._account.equity),
                "balance": str(self._account.balance),
                "open_positions": self._account.open_positions,
            },
        }
