"""
Odoo API Client.

Authenticated XML-RPC client for Odoo 19 with built-in safety guard.
All write operations are validated against the outbound communication blocker
before execution.

Usage:
    from src.mcp.odoo.utils.client import OdooClient

    async with OdooClient() as odoo:
        # Read operations — no approval needed
        leads = await odoo.search_read("crm.lead", [("user_id", "=", uid)], ["name", "stage_id"])

        # Write operations — safety-checked, still needs human approval upstream
        await odoo.write("crm.lead", [lead_id], {"stage_id": new_stage_id})

        # Internal notes — safe
        await odoo.log_note("crm.lead", lead_id, "Updated stage based on email analysis")
"""

import asyncio
import logging
import ssl
import xmlrpc.client
from typing import Any
from functools import partial

import certifi

from src.core.credentials import get_odoo_credentials, OdooCredentials, setup_advice
from src.mcp.odoo.utils.safety import SafetyGuard, SafetyViolation

logger = logging.getLogger(__name__)


class OdooClient:
    """
    Async-compatible Odoo XML-RPC client with safety guard.

    All XML-RPC calls are run in a thread executor to avoid blocking the event loop.
    All write operations pass through SafetyGuard before execution.
    """

    _model_id_cache: dict[str, int] = {}

    def __init__(self, credentials: OdooCredentials | None = None):
        """
        Initialize with credentials from per-user config file (default) or explicit credentials.

        Args:
            credentials: Optional explicit credentials. If None, reads from get_odoo_credentials().
        """
        self._creds = credentials or get_odoo_credentials()
        self._uid: int | None = None
        self._common: xmlrpc.client.ServerProxy | None = None
        self._models: xmlrpc.client.ServerProxy | None = None
        self._safety = SafetyGuard()

    async def __aenter__(self) -> "OdooClient":
        """Authenticate and return client."""
        await self.authenticate()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Cleanup."""
        self._common = None
        self._models = None

    async def authenticate(self) -> int:
        """
        Authenticate with Odoo and return user ID.

        Returns:
            User ID (uid) for the authenticated user.

        Raises:
            ConnectionError: If authentication fails.
        """
        loop = asyncio.get_running_loop()
        ssl_context = ssl.create_default_context(cafile=certifi.where())

        self._common = xmlrpc.client.ServerProxy(
            f"{self._creds.url}/xmlrpc/2/common", context=ssl_context
        )
        self._models = xmlrpc.client.ServerProxy(
            f"{self._creds.url}/xmlrpc/2/object", context=ssl_context
        )

        uid = await loop.run_in_executor(
            None,
            partial(
                self._common.authenticate,
                self._creds.db,
                self._creds.username,
                self._creds.api_key,
                {},
            ),
        )

        if not uid:
            raise ConnectionError(
                f"Odoo authentication failed for {self._creds.username} at {self._creds.url}. "
                + setup_advice()
            )

        self._uid = uid
        logger.info(f"Authenticated as uid={uid} on {self._creds.url}")
        return uid

    async def _execute(self, model: str, method: str, *args: Any, **kwargs: Any) -> Any:
        """
        Execute an Odoo XML-RPC call in a thread executor.

        Args:
            model: Odoo model name (e.g. 'crm.lead')
            method: Method to call (e.g. 'search_read')
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from Odoo API
        """
        if not self._uid or not self._models:
            raise RuntimeError("Not authenticated. " + setup_advice())

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            partial(
                self._models.execute_kw,
                self._creds.db,
                self._uid,
                self._creds.api_key,
                model,
                method,
                list(args) if args else [],
                kwargs if kwargs else {},
            ),
        )

    # ── Read Operations (no safety check needed) ──

    async def search(self, model: str, domain: list, limit: int = 80, offset: int = 0) -> list[int]:
        """Search for record IDs matching a domain filter."""
        return await self._execute(model, "search", domain, limit=limit, offset=offset)

    async def read(self, model: str, ids: list[int], fields: list[str] | None = None) -> list[dict]:
        """Read specific records by ID."""
        kwargs = {"fields": fields} if fields else {}
        return await self._execute(model, "read", ids, **kwargs)

    async def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str] | None = None,
        limit: int = 80,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict]:
        """Search and read in one call. Most common read operation."""
        kwargs: dict[str, Any] = {"limit": limit, "offset": offset}
        if fields:
            kwargs["fields"] = fields
        if order:
            kwargs["order"] = order
        return await self._execute(model, "search_read", domain, **kwargs)

    async def search_count(self, model: str, domain: list) -> int:
        """Count records matching a domain filter."""
        return await self._execute(model, "search_count", domain)

    async def fields_get(self, model: str, attributes: list[str] | None = None) -> dict:
        """Get field definitions for a model."""
        attrs = attributes or ["string", "type", "help", "required", "selection"]
        return await self._execute(model, "fields_get", attributes=attrs)

    # ── Write Operations (safety-checked) ──

    async def write(self, model: str, ids: list[int], values: dict[str, Any]) -> bool:
        """
        Update records. Safety-checked against outbound communication rules.

        Args:
            model: Odoo model name
            ids: Record IDs to update
            values: Field values to write

        Returns:
            True if successful

        Raises:
            SafetyViolation: If the write would trigger outbound communication
        """
        self._safety.validate_write(model, "write", values)
        return await self._execute(model, "write", ids, values)

    async def create(self, model: str, values: dict[str, Any]) -> int:
        """
        Create a record. Safety-checked.

        Returns:
            ID of the created record

        Raises:
            SafetyViolation: If creating this model would trigger outbound communication
        """
        self._safety.validate_write(model, "create", values)
        return await self._execute(model, "create", values)

    async def log_note(self, model: str, record_id: int, body: str) -> int:
        """
        Post an internal log note. This is the SAFE way to add notes to records.

        Uses Odoo 19 pattern: message_type='comment' + subtype_id=2 (internal Note).
        The subtype_id=2 ensures the message is internal-only — no email sent.

        Falls back to Odoo 18 pattern (message_type='note') if Odoo 19 call fails.

        Args:
            model: Odoo model (e.g. 'crm.lead')
            record_id: Record ID to post note on
            body: HTML body of the note

        Returns:
            Message ID
        """
        # Odoo 19 pattern: comment + internal Note subtype
        kwargs = {
            "body": body,
            "message_type": "comment",
            "subtype_id": 2,  # "Note" subtype (internal=True) — no email sent
        }
        self._safety.validate_write(model, "message_post", kwargs)
        try:
            return await self._execute(model, "message_post", [record_id], **kwargs)
        except Exception:
            # Fallback to Odoo 18 pattern
            kwargs_v18 = {
                "body": body,
                "message_type": "note",
                "subtype_xmlid": "mail.mt_note",
            }
            self._safety.validate_write(model, "message_post", kwargs_v18)
            return await self._execute(model, "message_post", [record_id], **kwargs_v18)

    async def schedule_activity(
        self,
        model: str,
        record_id: int,
        summary: str,
        date_deadline: str,
        activity_type_id: int = 4,  # 4 = To-Do in standard Odoo
        user_id: int | None = None,
        note: str = "",
    ) -> int:
        """
        Schedule an internal activity (to-do / reminder).

        Activities are SAFE: they only appear in the user's Odoo activity feed
        and never send external emails.

        Args:
            model: Odoo model (e.g. 'crm.lead')
            record_id: Record to attach activity to
            summary: Short activity title
            date_deadline: Due date as 'YYYY-MM-DD'
            activity_type_id: Activity type (4=To-Do, 1=Email, 2=Call, 3=Meeting)
            user_id: Assigned user ID (defaults to current user)
            note: Optional longer description

        Returns:
            Activity ID
        """
        # Activities are internal — safety check passes
        self._safety.validate_model_access("mail.activity", "create")

        values: dict[str, Any] = {
            "res_model_id": await self._get_model_id(model),
            "res_id": record_id,
            "summary": summary,
            "date_deadline": date_deadline,
            "activity_type_id": activity_type_id,
            "note": note,
        }
        if user_id:
            values["user_id"] = user_id

        return await self._execute("mail.activity", "create", values)

    async def _get_model_id(self, model_name: str) -> int:
        """Get the ir.model ID for a model name (cached)."""
        if model_name in self._model_id_cache:
            return self._model_id_cache[model_name]
        result = await self.search_read(
            "ir.model", [("model", "=", model_name)], ["id"], limit=1
        )
        if not result:
            raise ValueError(f"Model '{model_name}' not found in Odoo")
        self._model_id_cache[model_name] = result[0]["id"]
        return result[0]["id"]

    # ── Convenience Methods ──

    async def get_current_user(self) -> dict:
        """Get the currently authenticated user's profile."""
        if not self._uid:
            raise RuntimeError("Not authenticated. " + setup_advice())
        users = await self.read("res.users", [self._uid], ["name", "email", "company_id"])
        return users[0] if users else {}

    async def get_company_ids(self) -> list[dict]:
        """Get all companies the user has access to."""
        return await self.search_read("res.company", [], ["name", "id"])
