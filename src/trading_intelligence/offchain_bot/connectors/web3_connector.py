"""Web3-based market data connector.

This connector is intentionally read-only. It uses a price oracle contract as a
safe source of on-chain pricing data and does not assume any trading rights.
When no oracle is configured, it should not be used for live execution.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from trading_intelligence.offchain_bot.models import MarketQuote

logger = logging.getLogger(__name__)

_CHAINLINK_AGGREGATOR_ABI = [
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"internalType": "uint80", "name": "roundId", "type": "uint80"},
            {"internalType": "int256", "name": "answer", "type": "int256"},
            {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
            {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
            {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


def _load_web3():
    try:
        from web3 import Web3  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError("web3 is required for RPC-based market data. Install the package before using the Web3 backend.") from exc
    return Web3


class Web3OracleMarketDataConnector:
    def __init__(self, rpc_url: str, oracle_address: str, assumed_spread_bps: Decimal = Decimal("20")) -> None:
        self._rpc_url = rpc_url
        self._oracle_address = oracle_address
        self._assumed_spread_bps = assumed_spread_bps
        self._web3 = None
        self._oracle = None

    def connect(self) -> bool:
        if not self._rpc_url or not self._oracle_address:
            logger.error("RPC URL and oracle address are required for the Web3 backend")
            return False

        Web3 = _load_web3()
        self._web3 = Web3(Web3.HTTPProvider(self._rpc_url))
        if not self._web3.is_connected():
            logger.error("Unable to connect to Web3 RPC endpoint")
            return False

        self._oracle = self._web3.eth.contract(address=self._web3.to_checksum_address(self._oracle_address), abi=_CHAINLINK_AGGREGATOR_ABI)
        return True

    def get_quote(self, symbol: str, timeframe: str) -> MarketQuote:
        if self._oracle is None:
            raise RuntimeError("Web3 oracle connector not connected")

        latest = self._oracle.functions.latestRoundData().call()
        decimals = int(self._oracle.functions.decimals().call())
        answer = Decimal(str(latest[1]))
        if answer <= Decimal("0"):
            raise RuntimeError("Oracle returned a non-positive price")

        scale = Decimal("10") ** Decimal(str(decimals))
        mid = answer / scale
        spread_fraction = self._assumed_spread_bps / Decimal("10000")
        half_spread = mid * spread_fraction / Decimal("2")
        now = datetime.now(timezone.utc)
        return MarketQuote(
            symbol=symbol,
            timestamp=now,
            bid=mid - half_spread,
            ask=mid + half_spread,
            source=f"web3-oracle:{timeframe}",
        )

    def close(self) -> None:
        self._web3 = None
        self._oracle = None
