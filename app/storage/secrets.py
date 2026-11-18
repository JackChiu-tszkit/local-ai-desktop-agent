"""OS-protected secret storage. Values are not placed in SQLite or settings.json."""

from __future__ import annotations

from typing import Protocol

SERVICE_NAME = "local-ai-desktop-agent"
API_KEY_NAME = "cloud_api_key"


class SecretBackend(Protocol):
    def set_password(self, service: str, name: str, secret: str) -> None: ...

    def get_password(self, service: str, name: str) -> str | None: ...

    def delete_password(self, service: str, name: str) -> None: ...


class MemorySecretBackend:
    """Test and fallback backend. Not used for the normal desktop session."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, name: str, secret: str) -> None:
        self._items[(service, name)] = secret

    def get_password(self, service: str, name: str) -> str | None:
        return self._items.get((service, name))

    def delete_password(self, service: str, name: str) -> None:
        self._items.pop((service, name), None)


def _keyring_backend() -> SecretBackend:
    import keyring

    return keyring


def store_api_key(secret: str, backend: SecretBackend | None = None) -> None:
    target = backend or _keyring_backend()
    if secret:
        target.set_password(SERVICE_NAME, API_KEY_NAME, secret)
    else:
        try:
            target.delete_password(SERVICE_NAME, API_KEY_NAME)
        except Exception:
            return


def load_api_key(backend: SecretBackend | None = None) -> str:
    target = backend or _keyring_backend()
    try:
        return target.get_password(SERVICE_NAME, API_KEY_NAME) or ""
    except Exception:
        return ""


def delete_api_key(backend: SecretBackend | None = None) -> None:
    target = backend or _keyring_backend()
    try:
        target.delete_password(SERVICE_NAME, API_KEY_NAME)
    except Exception:
        return
