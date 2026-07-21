"""News AI Agent — Economic Calendar & Event Risk Assessment.

Evaluates tradability based on:
- High-impact economic events (NFP, FOMC, CPI, GDP, PMI)
- Time proximity to events (±15 min blackout)
- Expected volatility impact
- Produces AgentAssessment with eligibility score
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

from trading_intelligence.config import get_settings
from trading_intelligence.domain import AgentAssessment, MarketSnapshot

logger = logging.getLogger(__name__)

# Default high-impact events key
HIGH_IMPACT_KEYWORDS = {
    "NFP", "Non-Farm", "Nonfarm", "Employment Change",
    "FOMC", "Federal Reserve", "Interest Rate Decision",
    "CPI", "Consumer Price Index", "Inflation",
    "GDP", "Gross Domestic Product",
    "PMI", "Purchasing Managers",
    "Retail Sales", "Unemployment",
}


class NewsAI:
    """Assesses tradability based on economic calendar proximity.

    Checks if high-impact news is imminent and adjusts eligibility.
    Uses a CSV economic calendar data source.
    """

    name = "news_ai"

    def __init__(self) -> None:
        s = get_settings()
        self._calendar_path = s.economic_calendar_path
        self._events: list[dict] = []
        self._load_calendar()

    def _load_calendar(self) -> None:
        """Load economic calendar from CSV."""
        path = Path(self._calendar_path)
        if not path.exists():
            logger.warning("Economic calendar not found at %s — using default open eligibility", path)
            return

        try:
            with open(path) as f:
                reader = csv.DictReader(f)
                self._events = list(reader)
            logger.info("Loaded %d economic events from %s", len(self._events), path)
        except Exception:
            logger.exception("Failed to load economic calendar — using default eligibility")

    def evaluate(self, snapshot: MarketSnapshot) -> AgentAssessment:
        """Assess news risk for the given snapshot time."""
        now = snapshot.timestamp

        # Check for high-impact events within the blackout window
        blackout_minutes = 15
        for event in self._events:
            event_time_str = event.get("datetime") or event.get("date_time") or event.get("time")
            if not event_time_str:
                continue

            try:
                event_time = datetime.fromisoformat(event_time_str)
            except (ValueError, TypeError):
                continue

            time_diff = abs((now - event_time).total_seconds()) / 60

            if time_diff <= blackout_minutes:
                event_desc = event.get("event", event.get("name", "Unknown"))
                currency = event.get("currency", event.get("country", ""))
                impact = event.get("impact", "medium")

                # Check if it's high-impact
                is_high = (
                    impact.lower() == "high" or
                    any(kw.lower() in event_desc.lower() for kw in HIGH_IMPACT_KEYWORDS)
                )

                if is_high:
                    time_left = blackout_minutes - time_diff
                    logger.info(
                        "NewsAI: high-impact event '%s' %s %.0fm away — reducing eligibility",
                        event_desc, currency, time_diff,
                    )
                    return AgentAssessment(
                        agent=self.name,
                        score=Decimal("0"),
                        eligible=False,
                        rationale=f"In {blackout_minutes}min blackout for: {event_desc} ({currency}) — {time_left:.0f}min remaining",
                        generated_at=now,
                    )

        # If we have a calendar loaded but no events nearby
        if self._events:
            return AgentAssessment(
                agent=self.name,
                score=Decimal("80"),
                eligible=True,
                rationale="No high-impact events in blackout window",
                generated_at=now,
                metadata={"events_loaded": str(len(self._events))},
            )

        # No calendar loaded — default to open (with lower confidence)
        return AgentAssessment(
            agent=self.name,
            score=Decimal("60"),
            eligible=True,
            rationale="No economic calendar configured — default eligibility",
            generated_at=now,
            metadata={"calendar_status": "not_loaded"},
        )

    def reload_calendar(self) -> int:
        """Reload the calendar data. Returns number of events loaded."""
        self._events = []
        self._load_calendar()
        return len(self._events)
