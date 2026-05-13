"""
Credential management — config file per user.

Credentials are stored in ~/.config/my-odoo/credentials.json (mode 600).

Written by the 'odoo_setup_credentials' MCP tool — users set up credentials
directly from a Claude conversation without needing shell access.

Each user in Claude Cowork gets their own sandbox home directory, so the
file is naturally per-user and invisible to other users.

Usage:
    # In Claude Cowork: tell Claude "set up my Odoo credentials"
    # Claude calls the odoo_setup_credentials tool → writes config file

    # In code
    from src.core.credentials import get_odoo_credentials
    creds = get_odoo_credentials()
"""

import json
import stat
from dataclasses import dataclass
from pathlib import Path

# Config file path — per user, in their home directory
CONFIG_PATH = Path.home() / ".config" / "my-odoo" / "credentials.json"


def setup_advice() -> str:
    """Return the canonical user-facing credential setup instruction."""
    return (
        "Tell Claude: 'Set up my Odoo credentials'. "
        "Claude will run the 'odoo_setup_credentials' tool and ask for URL, database, email, and API key."
    )


@dataclass(frozen=True)
class OdooCredentials:
    """Immutable credential container. Never serialized, never logged."""

    url: str       # e.g. https://elewa.odoo.com
    db: str        # e.g. elewa-main-16488...
    username: str  # e.g. jente@elewa.ke
    api_key: str   # Odoo API key (Settings > API Keys)

    def __repr__(self) -> str:
        """Never expose credentials in logs or repr."""
        return f"OdooCredentials(url={self.url!r}, db={self.db!r}, username={self.username!r}, api_key='***')"


def get_odoo_credentials() -> OdooCredentials:
    """Read credentials from ~/.config/my-odoo/credentials.json.

    Raises:
        RuntimeError: File missing or incomplete — user needs to run odoo_setup_credentials.
    """
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            f"Odoo credentials not found at {CONFIG_PATH}. "
            + setup_advice()
        )

    try:
        data = json.loads(CONFIG_PATH.read_text())
    except Exception as exc:
        raise RuntimeError(f"Failed to read credentials file {CONFIG_PATH}: {exc}") from exc

    url = data.get("url")
    db = data.get("db")
    username = data.get("username")
    api_key = data.get("api_key")

    missing = [k for k, v in [("url", url), ("db", db), ("username", username), ("api_key", api_key)] if not v]
    if missing:
        raise RuntimeError(
            f"Credentials file is incomplete — missing: {', '.join(missing)}. "
            + setup_advice()
        )

    return OdooCredentials(url=url.rstrip("/"), db=db, username=username, api_key=api_key)


def store_odoo_credentials_file(url: str, db: str, username: str, api_key: str) -> None:
    """Write credentials to ~/.config/my-odoo/credentials.json (mode 600).

    Called by the odoo_setup_credentials MCP tool.
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps({"url": url, "db": db, "username": username, "api_key": api_key}, indent=2)
    )
    CONFIG_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 — owner read/write only
