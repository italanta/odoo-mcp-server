"""
Odoo MCP Server — unified endpoint for all Odoo domain tools.

This server exposes foundational (generic) Odoo tools plus domain-specific tools
registered from separate modules under ``src.mcp.odoo.tools``.

A single ``OdooClient`` instance is shared via the lifespan context — all domain
tool modules reuse it, avoiding duplicate connections.

Domain tool modules:
- ``tools.sales``    — CRM pipeline, leads, contacts (8 tools)
- ``tools.projects`` — Fixed-scope projects, tasks, milestones (6 tools)

Resources:
- ``odoo://models``              — List all available Odoo models.
- ``odoo://model/{model_name}``  — Introspect a specific model's fields.

Generic tools:
- ``odoo_ping``             — Validate connectivity and show authenticated user context.
- ``odoo_search_read``      — Read records with an Odoo domain filter.
- ``odoo_read_records``     — Read explicit records by model + IDs.
- ``odoo_write_records``    — Safety-checked write updates.
- ``odoo_log_internal_note``— Post chatter notes with ``message_type='note'`` only.
- ``odoo_schedule_activity``— Create internal reminder activities.
- ``odoo_fields_get``       — Introspect field definitions for a model.
- ``odoo_create_record``    — Safety-checked record creation.
- ``odoo_search_count``     — Count records matching a domain filter.

Run:
    python -m src.mcp.odoo.server
"""

from __future__ import annotations

import json
from importlib import metadata
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.mcp.odoo.utils.client import OdooClient
from src.core.credentials import CONFIG_PATH, store_odoo_credentials_file, setup_advice


# ── Lifespan ──


@dataclass
class AppContext:
    """Application context holding the shared OdooClient."""

    odoo: OdooClient | None
    auth_error: str | None = None


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize and share a single OdooClient for the server session.

    Never crash on auth failure — store the error on AppContext so every
    tool can return it to Claude, who will relay the setup instruction.
    """
    client = OdooClient()
    auth_error: str | None = None
    try:
        await client.authenticate()
    except (RuntimeError, Exception) as exc:
        auth_error = (
            f"Elewa Odoo is not authenticated: {exc}  "
            + setup_advice()
        )
        client = None
    try:
        yield AppContext(odoo=client, auth_error=auth_error)
    finally:
        pass


mcp = FastMCP(
    "elewa_odoo_mcp",
    lifespan=app_lifespan,
)


def _odoo(ctx: Context) -> OdooClient | str:
    """Extract the OdooClient from the lifespan context.

    Returns the client if authenticated, or an error string if auth failed.
    Tools should check: if isinstance(result, str): return result
    """
    context: AppContext = ctx.request_context.lifespan_context
    if context.auth_error:
        return context.auth_error
    return context.odoo


# ── MCP Resources ──


@mcp.resource("odoo://models", description="List all available models in the Odoo system")
async def list_models(ctx: Context) -> str:
    """Resource: list all installed Odoo model names."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    records = await odoo.search_read(
        "ir.model", [], fields=["model", "name"], limit=0
    )
    models = sorted(records, key=lambda r: r["model"])
    return json.dumps(
        {"count": len(models), "models": [{"model": r["model"], "name": r["name"]} for r in models]},
        indent=2,
    )


@mcp.resource(
    "odoo://model/{model_name}",
    description="Get information about a specific model including field definitions",
)
async def get_model_info(model_name: str, ctx: Context) -> str:
    """Resource: introspect a single Odoo model's metadata and fields."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    model_info = await odoo.search_read(
        "ir.model", [("model", "=", model_name)], fields=["model", "name"], limit=1
    )
    if not model_info:
        return json.dumps({"error": f"Model '{model_name}' not found"}, indent=2)

    fields = await odoo.fields_get(model=model_name)
    return json.dumps(
        {
            "model": model_info[0]["model"],
            "name": model_info[0]["name"],
            "fields": fields,
        },
        indent=2,
    )


# ── Pydantic Input Schemas ──


class OdooSearchReadInput(BaseModel):
    """Input schema for read-only search_read queries."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name, e.g. 'crm.lead'")
    domain: list[Any] = Field(
        default_factory=list,
        description="Odoo domain filter as a list of tuples/lists, e.g. [['active','=',True]]",
    )
    fields: list[str] = Field(
        default_factory=list,
        description="Fields to return. Empty list returns Odoo defaults.",
    )
    limit: int = Field(default=80, ge=1, le=500, description="Maximum records to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    order: str | None = Field(default=None, description="Optional sort order, e.g. 'create_date desc'")


class OdooGetRecordInput(BaseModel):
    """Input schema for reading records by ID."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name")
    ids: list[int] = Field(..., description="Record IDs to read", min_length=1)
    fields: list[str] = Field(default_factory=list, description="Fields to include in the response")


class OdooWriteInput(BaseModel):
    """Input schema for safety-checked writes."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name")
    ids: list[int] = Field(..., description="Record IDs to update", min_length=1)
    values: dict[str, Any] = Field(..., description="Field values to write")


class OdooLogNoteInput(BaseModel):
    """Input schema for internal chatter notes."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name, e.g. 'crm.lead'")
    record_id: int = Field(..., ge=1, description="Target record ID")
    body: str = Field(..., min_length=1, description="HTML or text body for the internal note")


class OdooScheduleActivityInput(BaseModel):
    """Input schema for scheduling internal activities."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name, e.g. 'crm.lead'")
    record_id: int = Field(..., ge=1, description="Target record ID")
    summary: str = Field(..., min_length=1, description="Short activity summary")
    date_deadline: str = Field(..., description="Deadline date in YYYY-MM-DD format")
    activity_type_id: int = Field(default=4, ge=1, description="Odoo activity type ID (4=To-Do by default)")
    user_id: int | None = Field(default=None, ge=1, description="Optional assignee user ID")
    note: str = Field(default="", description="Optional longer description")

    @field_validator("date_deadline")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            _date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD.")
        return v


@mcp.tool(
    name="odoo_ping",
    description="Validate Odoo connectivity and return the authenticated user profile.",
    annotations={"title": "Ping Odoo", "readOnlyHint": True, "destructiveHint": False},
)
async def odoo_ping(ctx: Context) -> dict[str, Any] | str:
    """Tool: check Odoo connectivity and identity."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    user = await odoo.get_current_user()
    return {
        "ok": True,
        "message": "Connected to Odoo successfully.",
        "user": user,
    }


@mcp.tool(
    name="odoo_search_read",
    description="Read Odoo records using a domain filter (safe, read-only).",
    annotations={"title": "Search and Read Records", "readOnlyHint": True, "destructiveHint": False},
)
async def odoo_search_read(input: OdooSearchReadInput, ctx: Context) -> list[dict[str, Any]] | str:
    """Tool: perform Odoo search_read against any model with strict input validation."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    fields = input.fields or None
    return await odoo.search_read(
        model=input.model,
        domain=input.domain,
        fields=fields,
        limit=input.limit,
        offset=input.offset,
        order=input.order,
    )


@mcp.tool(
    name="odoo_read_records",
    description="Read specific Odoo records by ID (safe, read-only).",
    annotations={"title": "Read Records By ID", "readOnlyHint": True, "destructiveHint": False},
)
async def odoo_read_records(input: OdooGetRecordInput, ctx: Context) -> list[dict[str, Any]] | str:
    """Tool: read one or more records for a given model and ID list."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    fields = input.fields or None
    return await odoo.read(model=input.model, ids=input.ids, fields=fields)


@mcp.tool(
    name="odoo_write_records",
    description="Write field updates on existing records (SafetyGuard enforced).",
    annotations={"title": "Write Records", "readOnlyHint": False, "destructiveHint": True},
)
async def odoo_write_records(input: OdooWriteInput, ctx: Context) -> dict[str, Any] | str:
    """Tool: update records after safety validation in OdooClient/SafetyGuard."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    ok = await odoo.write(model=input.model, ids=input.ids, values=input.values)
    return {
        "ok": ok,
        "updated_model": input.model,
        "updated_ids": input.ids,
    }


@mcp.tool(
    name="odoo_log_internal_note",
    description="Post an internal chatter note using message_type='note' (never outbound email).",
    annotations={"title": "Log Internal Note", "readOnlyHint": False, "destructiveHint": False},
)
async def odoo_log_internal_note(input: OdooLogNoteInput, ctx: Context) -> dict[str, Any] | str:
    """Tool: create a safe internal note on an Odoo record."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    message_id = await odoo.log_note(model=input.model, record_id=input.record_id, body=input.body)
    return {
        "ok": True,
        "message_id": message_id,
        "model": input.model,
        "record_id": input.record_id,
    }


@mcp.tool(
    name="odoo_schedule_activity",
    description="Create an internal Odoo activity/reminder (SafetyGuard enforced).",
    annotations={"title": "Schedule Activity", "readOnlyHint": False, "destructiveHint": False},
)
async def odoo_schedule_activity(input: OdooScheduleActivityInput, ctx: Context) -> dict[str, Any] | str:
    """Tool: schedule an internal follow-up activity on an Odoo record."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    activity_id = await odoo.schedule_activity(
        model=input.model,
        record_id=input.record_id,
        summary=input.summary,
        date_deadline=input.date_deadline,
        activity_type_id=input.activity_type_id,
        user_id=input.user_id,
        note=input.note,
    )
    return {
        "ok": True,
        "activity_id": activity_id,
        "model": input.model,
        "record_id": input.record_id,
    }


# ── Additional tools ──


class OdooFieldsGetInput(BaseModel):
    """Input schema for model field introspection."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name, e.g. 'crm.lead'")
    attributes: list[str] = Field(
        default_factory=lambda: ["string", "type", "help", "required", "selection"],
        description="Field metadata attributes to return",
    )


class OdooCreateInput(BaseModel):
    """Input schema for safety-checked record creation."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name")
    values: dict[str, Any] = Field(..., description="Field values for the new record")


class OdooSearchCountInput(BaseModel):
    """Input schema for counting records."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name, e.g. 'crm.lead'")
    domain: list[Any] = Field(
        default_factory=list,
        description="Odoo domain filter as a list of tuples/lists",
    )


@mcp.tool(
    name="odoo_fields_get",
    description="Introspect field definitions for an Odoo model (names, types, help text).",
    annotations={"title": "Get Model Fields", "readOnlyHint": True, "destructiveHint": False},
)
async def odoo_fields_get(input: OdooFieldsGetInput, ctx: Context) -> dict[str, Any] | str:
    """Tool: retrieve field metadata for a given Odoo model."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    return await odoo.fields_get(model=input.model, attributes=input.attributes)


@mcp.tool(
    name="odoo_create_record",
    description="Create a new Odoo record (SafetyGuard enforced).",
    annotations={"title": "Create Record", "readOnlyHint": False, "destructiveHint": False},
)
async def odoo_create_record(input: OdooCreateInput, ctx: Context) -> dict[str, Any] | str:
    """Tool: create a record after safety validation."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    record_id = await odoo.create(model=input.model, values=input.values)
    return {
        "ok": True,
        "created_model": input.model,
        "created_id": record_id,
    }


@mcp.tool(
    name="odoo_search_count",
    description="Count Odoo records matching a domain filter (safe, read-only).",
    annotations={"title": "Count Records", "readOnlyHint": True, "destructiveHint": False},
)
async def odoo_search_count(input: OdooSearchCountInput, ctx: Context) -> dict[str, Any] | str:
    """Tool: count records matching a domain filter."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo
    count = await odoo.search_count(model=input.model, domain=input.domain)
    return {"model": input.model, "count": count}


# ── Credential Setup Tool (Claude Cowork per-user onboarding) ──


class OdooSetupCredentialsInput(BaseModel):
    """Input schema for user credential setup."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., description="Odoo URL, e.g. https://elewa.odoo.com")
    db: str = Field(..., description="Odoo database name")
    username: str = Field(..., description="Your Odoo login email")
    api_key: str = Field(..., description="Your Odoo API key (Settings > Users > API Keys tab)")


@mcp.tool(
    name="odoo_setup_credentials",
    description=(
        "Save your personal Odoo credentials so Elewa Odoo tools can connect on your behalf. "
        "Run this once. Credentials are stored in your user home directory (~/.config/my-odoo/) "
        "and are only accessible to you. To generate an API key: go to Odoo Settings > "
        "Users > your profile > API Keys tab > New API Key."
    ),
    annotations={"title": "Set Up Odoo Credentials", "readOnlyHint": False, "destructiveHint": False},
)
async def odoo_setup_credentials(input: OdooSetupCredentialsInput) -> str:
    """Tool: write per-user Odoo credentials to ~/.config/my-odoo/credentials.json.

    Validates the credentials against Odoo before storing them.
    Does not require an existing authenticated session.
    """
    import re

    # Basic input validation
    if not re.match(r"^https?://", input.url):
        return "Error: URL must start with https:// (e.g. https://elewa.odoo.com)"
    if "@" not in input.username:
        return "Error: username must be an email address"
    if not input.db.strip():
        return "Error: database name is required"
    if not input.api_key.strip():
        return "Error: API key is required"

    # Validate credentials against Odoo before storing
    from src.core.credentials import OdooCredentials
    from src.mcp.odoo.utils.client import OdooClient

    test_creds = OdooCredentials(
        url=input.url.rstrip("/"),
        db=input.db.strip(),
        username=input.username.strip(),
        api_key=input.api_key.strip(),
    )
    test_client = OdooClient(credentials=test_creds)
    try:
        await test_client.authenticate()
    except Exception as exc:
        return (
            f"Credentials rejected by Odoo: {exc}. "
            "Double-check your URL, database name, email, and API key."
        )

    store_odoo_credentials_file(
        url=test_creds.url,
        db=test_creds.db,
        username=test_creds.username,
        api_key=test_creds.api_key,
    )
    return (
        f"Credentials saved for {test_creds.username}. "
        "Odoo tools are now active for your account. "
        "You only need to do this once — credentials persist across sessions."
    )


@mcp.tool(
    name="odoo_runtime_info",
    description="Show runtime diagnostics: package version, server module path, and credential file status.",
    annotations={"title": "Odoo Runtime Diagnostics", "readOnlyHint": True, "destructiveHint": False},
)
async def odoo_runtime_info() -> dict[str, Any]:
    """Tool: help verify which plugin build/environment Claude is currently running."""
    try:
        package_version = metadata.version("odoo-mcp-server")
    except Exception:
        package_version = "unknown"

    config_path = Path(CONFIG_PATH)
    file_exists = config_path.exists()
    file_mode = None
    if file_exists:
        file_mode = oct(config_path.stat().st_mode & 0o777)

    return {
        "package": "odoo-mcp-server",
        "package_version": package_version,
        "server_module": __file__,
        "credentials_backend": "file",
        "credentials_path": str(config_path),
        "credentials_file_exists": file_exists,
        "credentials_file_mode": file_mode,
    }


# ── Domain tool registration ──
# Each module's register() adds its tools to the shared `mcp` instance,
# reusing `_odoo` to access the single shared OdooClient.

from src.mcp.odoo.tools import sales, projects  # noqa: E402

sales.register(mcp, _odoo)
projects.register(mcp, _odoo)


def main() -> None:
    """Console script entry point — called by odoo-mcp-server command."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
