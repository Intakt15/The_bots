"""SQLite Decision Repository.

Implements DecisionRepository protocol with full audit trail.
All decisions, signals, assessments, executions, and outcomes are persisted.
Uses aiosqlite for async-compatible database access.

Schema tables:
  - signals: raw signal data from SignalAI
  - assessments: specialist agent evaluations
  - decisions: consensus + risk-gated trade decisions
  - executions: broker execution reports
  - outcomes: closed trade PnL and exit reasons
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from trading_intelligence.config import get_settings
from trading_intelligence.domain import (
    AgentAssessment,
    ExecutionReport,
    Signal,
    TradeDecision,
    TradeOutcome,
)

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    confidence REAL NOT NULL,
    generated_at TEXT NOT NULL,
    thesis TEXT NOT NULL,
    stop_loss REAL,
    take_profit REAL,
    evidence TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT,
    agent TEXT NOT NULL,
    score REAL NOT NULL,
    eligible INTEGER NOT NULL DEFAULT 1,
    rationale TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    quantity REAL NOT NULL,
    created_at TEXT NOT NULL,
    rationale TEXT NOT NULL,
    signal_json TEXT,
    created_db_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL,
    accepted INTEGER NOT NULL DEFAULT 0,
    broker_order_id TEXT,
    timestamp TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id)
);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL,
    closed_at TEXT NOT NULL,
    realized_pnl REAL NOT NULL,
    exit_reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id)
);

CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol);
CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status);
CREATE INDEX IF NOT EXISTS idx_executions_decision_id ON executions(decision_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_decision_id ON outcomes(decision_id);
"""


class SqliteDecisionRepository:
    """SQLite-based repository implementing DecisionRepository protocol.

    Usage:
        repo = SqliteDecisionRepository("data/trading.sqlite3")
        await repo.initialize()  # creates tables if needed
        repo.save_decision(decision, assessments)
    """

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            settings = get_settings()
            raw_url = settings.database_url
            if raw_url.startswith("sqlite:///"):
                db_path = raw_url[len("sqlite:///"):]
            else:
                db_path = "data/trading_intelligence.sqlite3"

        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # ── Lifecycle ────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Create database directory and tables."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()
        logger.info("SQLite database initialized at %s", self._db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("SQLite database connection closed.")

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    # ── DecisionRepository protocol ──────────────────────────────────

    def save_decision(
        self, decision: TradeDecision, assessments: Sequence[AgentAssessment]
    ) -> None:
        """Persist a trade decision and all associated assessments."""
        conn = self.connection

        # Save signal if present
        signal_json = None
        if decision.signal:
            signal_json = json.dumps({
                "source": decision.signal.source,
                "symbol": decision.signal.symbol,
                "side": decision.signal.side.value,
                "confidence": float(decision.signal.confidence),
                "thesis": decision.signal.thesis,
                "stop_loss": float(decision.signal.stop_loss) if decision.signal.stop_loss else None,
                "take_profit": float(decision.signal.take_profit) if decision.signal.take_profit else None,
                "evidence": dict(decision.signal.evidence),
            })
            conn.execute(
                """INSERT OR REPLACE INTO signals
                   (source, symbol, side, confidence, generated_at, thesis, stop_loss, take_profit, evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision.signal.source,
                    decision.signal.symbol,
                    decision.signal.side.value,
                    float(decision.signal.confidence),
                    decision.signal.generated_at.isoformat(),
                    decision.signal.thesis,
                    float(decision.signal.stop_loss) if decision.signal.stop_loss else None,
                    float(decision.signal.take_profit) if decision.signal.take_profit else None,
                    json.dumps(dict(decision.signal.evidence)),
                ),
            )

        # Save assessments
        for assessment in assessments:
            conn.execute(
                """INSERT INTO assessments
                   (decision_id, agent, score, eligible, rationale, generated_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(decision.decision_id),
                    assessment.agent,
                    float(assessment.score),
                    1 if assessment.eligible else 0,
                    assessment.rationale,
                    assessment.generated_at.isoformat(),
                    json.dumps(dict(assessment.metadata)),
                ),
            )

        # Save decision
        conn.execute(
            """INSERT OR REPLACE INTO decisions
               (decision_id, symbol, side, status, confidence, quantity, created_at, rationale, signal_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(decision.decision_id),
                decision.symbol,
                decision.side.value,
                decision.status.value,
                float(decision.confidence),
                float(decision.quantity),
                decision.created_at.isoformat(),
                decision.rationale,
                signal_json,
            ),
        )

        conn.commit()
        logger.debug(
            "Saved decision %s (%s %s) with %d assessments",
            decision.decision_id,
            decision.symbol,
            decision.status.value,
            len(assessments),
        )

    def save_execution(self, report: ExecutionReport) -> None:
        """Persist an execution report."""
        conn = self.connection
        conn.execute(
            """INSERT INTO executions
               (decision_id, accepted, broker_order_id, timestamp, detail)
               VALUES (?, ?, ?, ?, ?)""",
            (
                str(report.decision_id),
                1 if report.accepted else 0,
                report.broker_order_id,
                report.timestamp.isoformat(),
                report.detail,
            ),
        )
        conn.commit()
        logger.debug(
            "Saved execution for decision %s (accepted=%s, broker=%s)",
            report.decision_id,
            report.accepted,
            report.broker_order_id,
        )

    def save_outcome(self, outcome: TradeOutcome) -> None:
        """Persist a closed trade outcome."""
        conn = self.connection
        conn.execute(
            """INSERT INTO outcomes
               (decision_id, closed_at, realized_pnl, exit_reason)
               VALUES (?, ?, ?, ?)""",
            (
                str(outcome.decision_id),
                outcome.closed_at.isoformat(),
                float(outcome.realized_pnl),
                outcome.exit_reason,
            ),
        )
        conn.commit()
        logger.debug(
            "Saved outcome for decision %s (PnL=%.2f)",
            outcome.decision_id,
            float(outcome.realized_pnl),
        )

    # ── Query methods (for dashboard / reporting) ────────────────────

    def get_recent_decisions(self, limit: int = 50) -> list[dict]:
        """Retrieve most recent decisions."""
        conn = self.connection
        rows = conn.execute(
            """SELECT decision_id, symbol, side, status, confidence, quantity,
                      created_at, rationale
               FROM decisions
               ORDER BY created_db_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "decision_id": r[0],
                "symbol": r[1],
                "side": r[2],
                "status": r[3],
                "confidence": r[4],
                "quantity": r[5],
                "created_at": r[6],
                "rationale": r[7],
            }
            for r in rows
        ]

    def get_outcomes_summary(self) -> dict:
        """Return aggregate outcome statistics."""
        conn = self.connection
        row = conn.execute(
            """SELECT COUNT(*), SUM(realized_pnl), AVG(realized_pnl),
                      SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END),
                      SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END)
               FROM outcomes"""
        ).fetchone()

        if row and row[0] > 0:
            return {
                "total_trades": row[0],
                "total_pnl": row[1] or 0,
                "avg_pnl": row[2] or 0,
                "wins": row[3] or 0,
                "losses": row[4] or 0,
                "win_rate": (row[3] / row[0]) if row[0] > 0 else 0,
            }
        return {"total_trades": 0, "total_pnl": 0, "avg_pnl": 0, "wins": 0, "losses": 0, "win_rate": 0}

    def decision_count(self) -> int:
        """Total number of decisions recorded."""
        row = self.connection.execute("SELECT COUNT(*) FROM decisions").fetchone()
        return row[0] if row else 0

    def execution_count(self) -> int:
        """Total number of executions recorded."""
        row = self.connection.execute("SELECT COUNT(*) FROM executions").fetchone()
        return row[0] if row else 0

    def health_check(self) -> dict:
        """Quick database health summary."""
        return {
            "database_path": str(self._db_path),
            "decisions": self.decision_count(),
            "executions": self.execution_count(),
            "outcomes_summary": self.get_outcomes_summary(),
        }
