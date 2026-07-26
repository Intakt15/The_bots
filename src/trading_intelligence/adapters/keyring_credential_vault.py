"""Keyring-backed credential storage.

Secrets are stored in the operating system credential store instead of plaintext
files. Each profile can hold multiple fields such as API key, secret, and pin.
"""

from __future__ import annotations

from typing import Any

from trading_intelligence.interfaces.ports import CredentialStore

_SERVICE_NAME = "multi-agent-trading-intelligence"


class KeyringCredentialVault(CredentialStore):
    """Store and load credentials from the OS keyring."""

    def __init__(self, service_name: str = _SERVICE_NAME) -> None:
        self._service_name = service_name

    def _key(self, profile_name: str, field_name: str) -> str:
        return f"{profile_name}:{field_name}"

    def _keyring(self) -> Any:
        try:
            import keyring  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ImportError(
                "keyring is required for secure credential storage. Install with: pip install keyring"
            ) from exc
        return keyring

    def save(self, profile_name: str, values: dict[str, str]) -> None:
        keyring = self._keyring()
        for field_name, value in values.items():
            if value:
                keyring.set_password(self._service_name, self._key(profile_name, field_name), value)

    def load(self, profile_name: str) -> dict[str, str]:
        keyring = self._keyring()
        values: dict[str, str] = {}
        for field_name in ("api_key", "api_secret", "access_pin", "account_id", "bearer_token"):
            value = keyring.get_password(self._service_name, self._key(profile_name, field_name))
            if value:
                values[field_name] = value
        return values

    def delete(self, profile_name: str) -> None:
        keyring = self._keyring()
        for field_name in ("api_key", "api_secret", "access_pin", "account_id", "bearer_token"):
            try:
                keyring.delete_password(self._service_name, self._key(profile_name, field_name))
            except keyring.errors.PasswordDeleteError:  # type: ignore[attr-defined]
                pass
            except Exception:  # pragma: no cover - defensive cleanup
                pass
