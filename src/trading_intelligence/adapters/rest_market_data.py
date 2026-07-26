"""Generic REST market data provider.

This adapter supports platforms that expose AI-trading market endpoints over
HTTP. It is intentionally conservative: if the remote API does not return a
full market snapshot, the caller should continue using the local mock provider.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from trading_intelligence.adapters.keyring_credential_vault import KeyringCredentialVault
from trading_intelligence.domain import MarketSnapshot
from trading_intelligence.interfaces.ports import CredentialStore

logger = logging.getLogger(__name__)


class RestMarketDataProvider:
    """Fetch market snapshots from a REST trading platform."""

    def __init__(
        self,
        base_url: str,
        profile_name: str = "default",
        market_path: str = "/market/snapshot",
        api_key_field: str = "api_key",
        api_secret_field: str = "api_secret",
        access_pin_field: str = "access_pin",
        credential_store: CredentialStore | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._profile_name = profile_name
        self._market_path = market_path
        self._api_key_field = api_key_field
        self._api_secret_field = api_secret_field
        self._access_pin_field = access_pin_field
        self._timeout_seconds = timeout_seconds
        self._credential_store = credential_store or KeyringCredentialVault()
        self._connected = False
        self._credentials: dict[str, str] = {}

    def connect(self) -> bool:
        if not self._base_url:
            logger.error("REST market data provider requires a base URL.")
            return False

        self._credentials = self._credential_store.load(self._profile_name)
        if not self._credentials:
            logger.error("No REST market credentials found for profile %s.", self._profile_name)
            return False

        self._connected = True
        return True

    def snapshot(self, symbol: str, timeframe: str) -> MarketSnapshot:
        if not self._connected:
            raise RuntimeError("REST market provider not connected")

        url = urljoin(self._base_url + "/", self._market_path.lstrip("/"))
        payload = {"symbol": symbol, "timeframe": timeframe}
        headers = {"Content-Type": "application/json"}
        if self._api_key_field in self._credentials:
            headers["X-API-Key"] = self._credentials[self._api_key_field]
        if self._api_secret_field in self._credentials:
            headers["X-API-Secret"] = self._credentials[self._api_secret_field]
        if self._access_pin_field in self._credentials:
            headers["X-Access-Pin"] = self._credentials[self._access_pin_field]

        request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
        except HTTPError as exc:
            raise RuntimeError(f"REST market data request rejected: HTTP {exc.code} {exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"REST market data connection error: {exc.reason}") from exc

        return self._parse_snapshot(symbol, timeframe, data)

    def _parse_snapshot(self, symbol: str, timeframe: str, data: dict[str, object]) -> MarketSnapshot:
        timestamp_raw = data.get("timestamp") or data.get("time")
        if isinstance(timestamp_raw, str):
            timestamp = datetime.fromisoformat(timestamp_raw)
        else:
            timestamp = datetime.now(timezone.utc)

        bid = Decimal(str(data.get("bid") or data.get("best_bid") or "0"))
        ask = Decimal(str(data.get("ask") or data.get("best_ask") or "0"))

        raw_indicators = data.get("indicators") if isinstance(data.get("indicators"), dict) else {}
        indicators: dict[str, Decimal] = {}
        if isinstance(raw_indicators, dict):
            for key, value in raw_indicators.items():
                try:
                    indicators[str(key)] = Decimal(str(value))
                except Exception:
                    continue

        return MarketSnapshot(
            symbol=str(data.get("symbol") or symbol),
            timestamp=timestamp.astimezone(timezone.utc),
            bid=bid,
            ask=ask,
            timeframe=str(data.get("timeframe") or timeframe),
            indicators=indicators,
        )