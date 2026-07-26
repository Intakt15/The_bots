"""Generic REST execution gateway.

This adapter is for any trading platform that exposes an AI-trading-friendly
HTTP API. It is intentionally generic: credentials are loaded from the OS
keyring and the order payload is extensible through standard fields.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from trading_intelligence.domain import ExecutionReport, TradeDecision
from trading_intelligence.interfaces.ports import CredentialStore, ExecutionGateway
from trading_intelligence.adapters.keyring_credential_vault import KeyringCredentialVault

logger = logging.getLogger(__name__)


class RestExecutionGateway(ExecutionGateway):
    """Submit approved decisions to a generic REST trading platform."""

    def __init__(
        self,
        base_url: str,
        profile_name: str = "default",
        order_path: str = "/orders",
        account_path: str = "/account",
        api_key_field: str = "api_key",
        api_secret_field: str = "api_secret",
        access_pin_field: str = "access_pin",
        credential_store: CredentialStore | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._profile_name = profile_name
        self._order_path = order_path
        self._account_path = account_path
        self._api_key_field = api_key_field
        self._api_secret_field = api_secret_field
        self._access_pin_field = access_pin_field
        self._credential_store = credential_store or KeyringCredentialVault()
        self._timeout_seconds = timeout_seconds
        self._connected = False
        self._submitted_ids: set[str] = set()
        self._credentials: dict[str, str] = {}

    def connect(self) -> bool:
        if not self._base_url:
            logger.error("REST execution gateway requires a base URL.")
            return False

        self._credentials = self._credential_store.load(self._profile_name)
        if not self._credentials:
            logger.error("No credentials found for profile %s.", self._profile_name)
            return False

        self._connected = True
        logger.info(
            "REST platform connected: profile=%s base=%s account_path=%s",
            self._profile_name,
            self._base_url,
            self._account_path,
        )
        return True

    def disconnect(self) -> None:
        self._connected = False

    def submit(self, decision: TradeDecision, idempotency_key: str) -> ExecutionReport:
        now = datetime.now(timezone.utc)

        if idempotency_key in self._submitted_ids:
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail=f"Duplicate submission: {idempotency_key} already processed",
            )

        if not self._connected:
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail="REST platform not connected",
            )

        url = urljoin(self._base_url + "/", self._order_path.lstrip("/"))
        payload = {
            "decision_id": str(decision.decision_id),
            "idempotency_key": idempotency_key,
            "symbol": decision.symbol,
            "side": decision.side.value,
            "quantity": float(decision.quantity),
            "confidence": float(decision.confidence),
            "status": decision.status.value,
            "rationale": decision.rationale,
        }
        if decision.signal and decision.signal.stop_loss is not None:
            payload["stop_loss"] = float(decision.signal.stop_loss)
        if decision.signal and decision.signal.take_profit is not None:
            payload["take_profit"] = float(decision.signal.take_profit)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "multi-agent-trading-intelligence/1.0",
        }
        api_key = self._credentials.get(self._api_key_field)
        api_secret = self._credentials.get(self._api_secret_field)
        access_pin = self._credentials.get(self._access_pin_field)
        if api_key:
            headers["X-API-Key"] = api_key
        if api_secret:
            headers["X-API-Secret"] = api_secret
        if access_pin:
            headers["X-Access-Pin"] = access_pin

        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
        except HTTPError as exc:
            self._submitted_ids.add(idempotency_key)
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail=f"REST order rejected: HTTP {exc.code} {exc.reason}",
            )
        except URLError as exc:
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail=f"REST order connection error: {exc.reason}",
            )
        except Exception as exc:  # pragma: no cover - defensive API boundary
            return ExecutionReport(
                decision_id=decision.decision_id,
                accepted=False,
                broker_order_id=None,
                timestamp=now,
                detail=f"REST order failed: {exc}",
            )

        self._submitted_ids.add(idempotency_key)
        broker_order_id = str(data.get("order_id") or data.get("id") or data.get("orderId") or "") or None
        detail = data.get("message") or data.get("status") or f"Submitted to {url}"
        return ExecutionReport(
            decision_id=decision.decision_id,
            accepted=True,
            broker_order_id=broker_order_id,
            timestamp=now,
            detail=str(detail),
        )
