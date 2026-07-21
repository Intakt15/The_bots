"""Session AI Agent — Forex Market Session Intelligence.

Evaluates trade eligibility based on:
- Active market session (Asian, London, NY, overlaps)
- Instrument-to-session appropriateness
- Liquidity profiles and spread expectations
- Session transition risk windows

Session times are configurable via settings (UTC hours).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from trading_intelligence.config import get_settings
from trading_intelligence.domain import AgentAssessment, MarketSnapshot

logger = logging.getLogger(__name__)

# Default instrument - best session mapping
INSTRUMENT_SESSIONS = {
    "EURUSD": ["london", "ny", "overlap"],
    "GBPUSD": ["london", "ny", "overlap"],
    "EURGBP": ["london", "overlap"],
    "USDJPY": ["asian", "ny", "overlap"],
    "AUDUSD": ["asian", "overlap"],
    "NZDUSD": ["asian", "overlap"],
    "USDCAD": ["ny", "overlap"],
    "USDCHF": ["london", "ny", "overlap"],
    "XAUUSD": ["london", "ny", "overlap"],
    "EURJPY": ["asian", "london", "overlap"],
    "GBPJPY": ["london", "overlap"],
    "AUDJPY": ["asian", "overlap"],
}


class SessionAI:
    """Determines trade eligibility based on forex market sessions.

    Asian: 00:00-09:00 UTC
    London: 08:00-17:00 UTC
    NY: 13:00-22:00 UTC

    Overlap periods get highest eligibility scores.
    """

    name = "session_ai"

    def __init__(self) -> None:
        s = get_settings()
        self._session_asian_start = s.session_asian_start
        self._session_asian_end = s.session_asian_end
        self._session_london_start = s.session_london_start
        self._session_london_end = s.session_london_end
        self._session_ny_start = s.session_ny_start
        self._session_ny_end = s.session_ny_end

    def evaluate(self, snapshot: MarketSnapshot) -> AgentAssessment:
        """Assess session eligibility for the snapshot timestamp."""
        now = snapshot.timestamp.astimezone(timezone.utc)
        hour = now.hour + now.minute / 60.0

        # Determine active sessions
        sessions: list[str] = []
        if self._session_asian_start <= hour < self._session_asian_end:
            sessions.append("asian")
        if self._session_london_start <= hour < self._session_london_end:
            sessions.append("london")
        if self._session_ny_start <= hour < self._session_ny_end:
            sessions.append("ny")

        # Detect overlaps
        overlap = len(sessions) >= 2
        if overlap:
            sessions.append("overlap")

        # Check instrument-session match
        symbol = snapshot.symbol
        preferred = INSTRUMENT_SESSIONS.get(symbol, [])

        active_set = set(sessions)
        preferred_set = set(preferred)

        # Scoring
        if active_set & preferred_set:
            if overlap and "overlap" in preferred_set:
                score = Decimal("90")
                eligibility = True
                rationale = f"In preferred overlap session: {', '.join(sessions)} - optimal liquidity"
            elif "overlap" in sessions:
                score = Decimal("85")
                eligibility = True
                rationale = f"In overlap session: {', '.join(s for s in sessions if s != 'overlap')} - high liquidity"
            else:
                score = Decimal("75")
                eligibility = True
                rationale = f"In preferred session: {', '.join(sessions)}"
        elif active_set:
            score = Decimal("50")
            eligibility = True
            rationale = f"Trading outside preferred session for {symbol} ({', '.join(sessions)})"
        else:
            score = Decimal("0")
            eligibility = False
            rationale = f"Outside all active sessions (hour={hour:.1f}h UTC)"

        logger.debug(
            "SessionAI: %s sessions=%s preferred=%s score=%.0f eligible=%s",
            symbol,
            sessions,
            preferred,
            float(score),
            eligibility,
        )

        return AgentAssessment(
            agent=self.name,
            score=score,
            eligible=eligibility,
            rationale=rationale,
            generated_at=now,
            metadata={"active_sessions": ",".join(sessions), "overlap": str(overlap)},
        )

    def active_sessions(self, at: datetime | None = None) -> list[str]:
        """Return list of currently active sessions."""
        if at is None:
            at = datetime.now(timezone.utc)
        hour = at.hour + at.minute / 60.0
        sessions: list[str] = []
        if self._session_asian_start <= hour < self._session_asian_end:
            sessions.append("asian")
        if self._session_london_start <= hour < self._session_london_end:
            sessions.append("london")
        if self._session_ny_start <= hour < self._session_ny_end:
            sessions.append("ny")
        if len(sessions) >= 2:
            sessions.append("overlap")
        return sessions

    def is_weekend(self, at: datetime | None = None) -> bool:
        """Check if it is the forex weekend (Fri 22:00 - Sun 22:00 UTC)."""
        if at is None:
            at = datetime.now(timezone.utc)
        weekday = at.weekday()
        hour = at.hour
        if weekday == 4 and hour >= 22:
            return True
        if weekday == 5:
            return True
        if weekday == 6 and hour < 22:
            return True
        return False
