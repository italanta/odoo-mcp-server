from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

from src.core.credentials import OdooCredentials


def parse_odoo_major(version_text: str) -> int | None:
    """Extract Odoo major version from a version string like '19.0+e'."""
    cleaned = version_text.strip()
    if not cleaned:
        return None
    head = cleaned.split(".", 1)[0]
    digits = "".join(ch for ch in head if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def transport_from_env() -> str:
    # Resolve transport once from process config so the higher-level client can
    # pin a single backend for its whole lifetime.
    value = os.environ.get("ODOO_TRANSPORT", "xmlrpc").strip().lower()
    if value not in {"xmlrpc", "json2"}:
        raise RuntimeError(
            f"Unsupported ODOO_TRANSPORT={value!r}. Use 'xmlrpc' or 'json2'."
        )
    return value


class BaseTransportClient(ABC):
    """Transport-specific low-level client contract.

    The facade delegates all wire-level behavior to subclasses of this base.
    That keeps transport-specific authentication, connection lifecycle, and
    method-call encoding out of the business-facing ``OdooClient`` API.
    """

    # Concrete transports expose a short machine-readable name that the facade
    # can surface through runtime diagnostics.
    transport_name: str

    def __init__(self, credentials: OdooCredentials):
        # Store immutable credentials once; transports should treat these as
        # session configuration rather than something to mutate at runtime.
        self._creds = credentials

    @abstractmethod
    async def authenticate(self) -> int:
        """Authenticate transport and return current user id when available."""

    @abstractmethod
    async def close(self) -> None:
        """Release transport resources."""

    @abstractmethod
    async def execute(self, model: str, method: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a model method through the concrete transport."""

    @property
    def compatibility_hints(self) -> list[str]:
        # Subclasses can override this to describe transport-specific caveats
        # without forcing callers to special-case transport classes directly.
        return []