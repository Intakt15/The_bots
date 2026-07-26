from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from trading_intelligence.adapters.rest_execution import RestExecutionGateway
from trading_intelligence.adapters.rest_market_data import RestMarketDataProvider
from trading_intelligence.domain import DecisionStatus, Side, Signal, TradeDecision


class FakeCredentialStore:
    def __init__(self, values: dict[str, str]):
        self.values = values

    def save(self, profile_name: str, values: dict[str, str]) -> None:
        self.values.update(values)

    def load(self, profile_name: str) -> dict[str, str]:
        return dict(self.values)

    def delete(self, profile_name: str) -> None:
        self.values.clear()


class FakeResponse:
    def __init__(self, payload: dict[str, str | int]) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_rest_execution_gateway_submits_to_generic_api(monkeypatch):
    store = FakeCredentialStore({"api_key": "k", "api_secret": "s", "access_pin": "1234"})
    gateway = RestExecutionGateway(
        base_url="https://example.test",
        profile_name="default",
        credential_store=store,
    )

    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"order_id": "ABC123", "message": "accepted"})

    monkeypatch.setattr("trading_intelligence.adapters.rest_execution.urlopen", fake_urlopen)

    assert gateway.connect() is True

    now = datetime.now(timezone.utc)
    signal = Signal("signal_ai", "EURUSD", Side.BUY, Decimal("80"), now, "test")
    decision = TradeDecision(
        symbol="EURUSD",
        side=Side.BUY,
        status=DecisionStatus.APPROVED,
        confidence=Decimal("82"),
        quantity=Decimal("1"),
        created_at=now,
        rationale="test",
        signal=signal,
    )

    report = gateway.submit(decision, "decision-1")

    assert report.accepted is True
    assert report.broker_order_id == "ABC123"
    assert captured["url"] == "https://example.test/orders"
    assert captured["body"]["symbol"] == "EURUSD"


def test_rest_market_data_provider_parses_snapshot(monkeypatch):
    store = FakeCredentialStore({"api_key": "k", "api_secret": "s", "access_pin": "1234"})
    provider = RestMarketDataProvider(
        base_url="https://example.test",
        profile_name="default",
        credential_store=store,
    )

    def fake_urlopen(request, timeout=0):
        return FakeResponse(
            {
                "symbol": "EURUSD",
                "timeframe": "H1",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "bid": "1.0849",
                "ask": "1.0851",
                "indicators": {"RSI_14": 45.2, "ATR_14": 0.0012},
            }
        )

    monkeypatch.setattr("trading_intelligence.adapters.rest_market_data.urlopen", fake_urlopen)
    assert provider.connect() is True

    snapshot = provider.snapshot("EURUSD", "H1")
    assert snapshot.symbol == "EURUSD"
    assert snapshot.bid == Decimal("1.0849")
    assert snapshot.indicators["RSI_14"] == Decimal("45.2")
