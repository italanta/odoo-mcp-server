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
- ``odoo_log_internal_note``— Post chatter notes with ``message_type='note'`` only.
- ``odoo_schedule_activity``— Create internal reminder activities.
- ``odoo_fields_get``       — Introspect field definitions for a model.
- ``odoo_search_count``     — Count records matching a domain filter.

Run:
    python -m src.mcp.odoo.server
"""

from __future__ import annotations

import json
import os
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
from src.mcp.odoo.utils.diagnostics import diagnose_odoo_call
from src.mcp.odoo.utils.safety import SafetyGuard, SafetyViolation
from src.mcp.odoo.utils.write_approvals import ApprovalStore


_approval_store = ApprovalStore(ttl_seconds=600)
# Token -> validated payload map kept in process memory for same-session execution.
_validated_payloads: dict[str, dict[str, Any]] = {}


def _truthy_env(name: str) -> bool:
    # Standard truthy env parser used for runtime safety gates.
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


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
            f"Odoo is not authenticated: {exc}  "
            + setup_advice()
        )
        client = None
    try:
        yield AppContext(odoo=client, auth_error=auth_error)
    finally:
        pass


mcp = FastMCP(
    "odoo_mcp",
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
    name="odoo_log_internal_note",
    description="Post an internal chatter note directly (never outbound email).",
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
        "tool": "odoo_log_internal_note",
        "message_id": message_id,
        "model": input.model,
        "record_id": input.record_id,
    }


@mcp.tool(
    name="odoo_schedule_activity",
    description="Build an internal activity proposal payload for staged approval. Does not execute directly.",
    annotations={"title": "Schedule Activity", "readOnlyHint": False, "destructiveHint": False},
)
async def odoo_schedule_activity(input: OdooScheduleActivityInput, ctx: Context) -> dict[str, Any] | str:
    """Tool: build an internal activity create payload for staged approval flow."""
    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo

    # Resolve model id now so the staged payload can be executed as plain create.
    model_ref = await odoo.search_read("ir.model", [("model", "=", input.model)], ["id"], limit=1)
    if not model_ref:
        return {
            "ok": False,
            "tool": "odoo_schedule_activity",
            "error": f"Model '{input.model}' not found in ir.model.",
        }

    values: dict[str, Any] = {
        "res_model_id": model_ref[0]["id"],
        "res_id": input.record_id,
        "summary": input.summary,
        "date_deadline": input.date_deadline,
        "activity_type_id": input.activity_type_id,
        "note": input.note,
    }
    if input.user_id:
        values["user_id"] = input.user_id

    payload = {
        "model": "mail.activity",
        "operation": "create",
        "record_ids": [],
        "values": values,
    }
    return {
        "ok": True,
        "tool": "odoo_schedule_activity",
        "mode": "proposal_only",
        "payload": payload,
        "next": [
            "Run odoo_preview_write with this payload.",
            "Run odoo_validate_write with the same payload.",
            "After explicit user approval, run odoo_execute_approved_write.",
        ],
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


class OdooSearchCountInput(BaseModel):
    """Input schema for counting records."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name, e.g. 'crm.lead'")
    domain: list[Any] = Field(
        default_factory=list,
        description="Odoo domain filter as a list of tuples/lists",
    )


class OdooDiagnoseCallInput(BaseModel):
    """Input schema for non-executing call diagnostics."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name, e.g. 'crm.lead'")
    method: str = Field(..., description="Odoo method name, e.g. 'search_read', 'write'")
    args: list[Any] = Field(default_factory=list, description="Positional args you plan to pass")
    kwargs: dict[str, Any] = Field(default_factory=dict, description="Keyword args you plan to pass")


class OdooPreviewWriteInput(BaseModel):
    """Input schema for staged write preview."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name")
    operation: str = Field(..., description="One of: create, write, call")
    record_ids: list[int] = Field(default_factory=list, description="Required for write")
    values: dict[str, Any] = Field(default_factory=dict, description="Field payload for create/write")
    method: str | None = Field(default=None, description="Required for call operation, e.g. message_post")
    args: list[Any] = Field(default_factory=list, description="Positional args for call operation")
    kwargs: dict[str, Any] = Field(default_factory=dict, description="Keyword args for call operation")


class OdooValidateWriteInput(BaseModel):
    """Input schema for staged write validation."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Odoo model name")
    operation: str = Field(..., description="One of: create, write, call")
    record_ids: list[int] = Field(default_factory=list, description="Required for write")
    values: dict[str, Any] = Field(default_factory=dict, description="Field payload for create/write")
    method: str | None = Field(default=None, description="Required for call operation, e.g. message_post")
    args: list[Any] = Field(default_factory=list, description="Positional args for call operation")
    kwargs: dict[str, Any] = Field(default_factory=dict, description="Keyword args for call operation")


class OdooExecuteApprovedWriteInput(BaseModel):
    """Input schema for approved write execution."""

    model_config = ConfigDict(extra="forbid")

    approval_token: str = Field(..., description="Token returned by odoo_validate_write")
    confirm: bool = Field(..., description="Must be true to execute")


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


@mcp.tool(
    name="odoo_diagnose_call",
    description="Dry-run analysis of a planned Odoo model call: validates basic payload shape, classifies method risk (read/destructive/side-effect), and returns issues/recommendations without executing anything.",
    annotations={"title": "Diagnose Odoo Call", "readOnlyHint": True, "destructiveHint": False},
)
async def odoo_diagnose_call(input: OdooDiagnoseCallInput) -> dict[str, Any]:
    """Tool: return non-executing diagnostics for a planned Odoo call."""
    return diagnose_odoo_call(
        model=input.model,
        method=input.method,
        args=input.args,
        kwargs=input.kwargs,
    )


@mcp.tool(
    name="odoo_preview_write",
    description="Dry-run step 1: create a canonical mutation draft (create/write/call) for human review; does not validate against live metadata and does not execute any Odoo call.",
    annotations={"title": "Preview Write", "readOnlyHint": True, "destructiveHint": False},
)
async def odoo_preview_write(input: OdooPreviewWriteInput) -> dict[str, Any]:
    """Tool: generate a non-executing write draft for staged approval flow."""
    # Step 1: normalize and return a canonical payload draft for human/agent review.
    operation = input.operation.strip().lower()
    if operation not in {"create", "write", "call"}:
        return {
            "success": False,
            "tool": "odoo_preview_write",
            "error": "Unsupported operation. Use 'create', 'write', or 'call'.",
        }

    if operation == "write" and not input.record_ids:
        return {
            "success": False,
            "tool": "odoo_preview_write",
            "error": "record_ids are required for write operations.",
        }

    if operation == "call" and not (input.method and input.method.strip()):
        return {
            "success": False,
            "tool": "odoo_preview_write",
            "error": "method is required for call operations.",
        }

    payload = {
        "model": input.model,
        "operation": operation,
        "record_ids": input.record_ids,
        "values": input.values,
        "method": input.method,
        "args": input.args,
        "kwargs": input.kwargs,
    }
    return {
        "success": True,
        "tool": "odoo_preview_write",
        "payload": payload,
        "next": "Run odoo_validate_write with the same payload.",
    }


@mcp.tool(
    name="odoo_validate_write",
    description="Dry-run step 2: validate a mutation draft with SafetyGuard and live metadata checks where applicable, then issue a short-lived single-use approval token for explicit user approval in conversation; does not execute writes.",
    annotations={"title": "Validate Write", "readOnlyHint": True, "destructiveHint": False},
)
async def odoo_validate_write(input: OdooValidateWriteInput, ctx: Context) -> dict[str, Any] | str:
    """Tool: validate staged write payload and issue an approval token without execution."""
    # Step 2: syntactic operation validation.
    operation = input.operation.strip().lower()
    if operation not in {"create", "write", "call"}:
        return {
            "success": False,
            "tool": "odoo_validate_write",
            "error": "Unsupported operation. Use 'create', 'write', or 'call'.",
        }

    if operation == "write" and not input.record_ids:
        return {
            "success": False,
            "tool": "odoo_validate_write",
            "error": "record_ids are required for write operations.",
        }

    if operation == "call" and not (input.method and input.method.strip()):
        return {
            "success": False,
            "tool": "odoo_validate_write",
            "error": "method is required for call operations.",
        }

    # Apply outbound communication safety policy before any metadata checks.
    guard = SafetyGuard()
    try:
        guard.validate_write(
            input.model,
            input.method.strip() if operation == "call" and input.method else operation,
            input.kwargs if operation == "call" else input.values,
        )
    except SafetyViolation as exc:
        return {
            "success": False,
            "tool": "odoo_validate_write",
            "error": str(exc),
            "metadata_used": {"live_odoo": False},
        }

    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo

    metadata_used: dict[str, Any] = {"live_odoo": False}
    if operation in {"create", "write"}:
        # Live metadata is required so approval is based on current Odoo schema, not assumptions.
        field_meta = await odoo.fields_get(model=input.model, attributes=["string", "type", "required", "readonly"])
        if not field_meta:
            return {
                "success": False,
                "tool": "odoo_validate_write",
                "error": "fields_get returned empty metadata; refusing approval.",
                "metadata_used": {"live_odoo": False},
            }

        # Unknown fields are rejected to prevent drift and typo-based writes.
        unknown_fields = sorted(set(input.values.keys()) - set(field_meta.keys()))
        if unknown_fields:
            return {
                "success": False,
                "tool": "odoo_validate_write",
                "error": f"Unknown fields for model {input.model}: {', '.join(unknown_fields)}",
                "metadata_used": {"live_odoo": True},
            }
        metadata_used = {
            "live_odoo": True,
            "field_count": len(field_meta),
        }

    payload = {
        "model": input.model,
        "operation": operation,
        "record_ids": input.record_ids,
        "values": input.values,
        "method": input.method,
        "args": input.args,
        "kwargs": input.kwargs,
    }
    # Register short-lived single-use approval token bound to exact validated payload.
    approval = _approval_store.register(payload)
    _validated_payloads[approval.token] = payload
    return {
        "success": True,
        "tool": "odoo_validate_write",
        "approval": {
            "token": approval.token,
            "expires_at": approval.expires_at,
            "requires_confirm": True,
        },
        "metadata_used": metadata_used,
        "next": "Run odoo_execute_approved_write with approval_token and confirm=true.",
    }


@mcp.tool(
    name="odoo_execute_approved_write",
    description="Step 3 (execution): perform approved create/write/call only after explicit user approval and only when confirm=true, token is valid and unused, and ODOO_MCP_ENABLE_WRITES=1; otherwise fail closed.",
    annotations={"title": "Execute Approved Write", "readOnlyHint": False, "destructiveHint": True},
)
async def odoo_execute_approved_write(input: OdooExecuteApprovedWriteInput, ctx: Context) -> dict[str, Any] | str:
    """Tool: execute a previously validated write under strict runtime gates."""
    # Step 3 gate A: explicit confirmation required at execution time.
    if not input.confirm:
        return {
            "success": False,
            "tool": "odoo_execute_approved_write",
            "error": "confirm must be true.",
        }

    # Step 3 gate B: runtime env gate required for any mutating execution.
    if not _truthy_env("ODOO_MCP_ENABLE_WRITES"):
        return {
            "success": False,
            "tool": "odoo_execute_approved_write",
            "error": "Write execution is disabled. Set ODOO_MCP_ENABLE_WRITES=1.",
        }

    odoo = _odoo(ctx)
    if isinstance(odoo, str):
        return odoo

    # Lookup the payload bound to this token during validation.
    token = input.approval_token
    payload = _validated_payloads.get(token)
    if payload is None:
        return {
            "success": False,
            "tool": "odoo_execute_approved_write",
            "error": "Unknown approval token. Run odoo_validate_write first.",
        }

    # Step 3 gate C: token must be valid, unexpired, unused, and payload-matching.
    try:
        _approval_store.consume(token, payload)
    except Exception:
        return {
            "success": False,
            "tool": "odoo_execute_approved_write",
            "error": "Approval token invalid, expired, already used, or does not match payload.",
        }
    # Drop payload binding after token use to preserve single-use semantics.
    _validated_payloads.pop(token, None)

    # Only validated operations are executable, with operation-specific execution path.
    operation = payload["operation"]
    if operation == "create":
        created_id = await odoo.create(payload["model"], payload["values"])
        return {
            "success": True,
            "tool": "odoo_execute_approved_write",
            "operation": operation,
            "model": payload["model"],
            "created_id": created_id,
        }

    if operation == "write":
        ok = await odoo.write(payload["model"], payload["record_ids"], payload["values"])
        return {
            "success": True,
            "tool": "odoo_execute_approved_write",
            "operation": operation,
            "model": payload["model"],
            "record_ids": payload["record_ids"],
            "ok": ok,
        }

    if operation == "call":
        result = await odoo._execute(
            payload["model"],
            payload.get("method", ""),
            *(payload.get("args") or []),
            **(payload.get("kwargs") or {}),
        )
        return {
            "success": True,
            "tool": "odoo_execute_approved_write",
            "operation": operation,
            "model": payload["model"],
            "method": payload.get("method"),
            "result": result,
        }

    return {
        "success": False,
        "tool": "odoo_execute_approved_write",
        "error": f"Unsupported operation in approved payload: {operation}",
    }


# ── Credential Setup Tool (Claude Cowork per-user onboarding) ──


class OdooSetupCredentialsInput(BaseModel):
    """Input schema for user credential setup."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., description="Odoo URL, e.g. https://my.odoo.com")
    db: str = Field(..., description="Odoo database name")
    username: str = Field(..., description="Your Odoo login email")
    api_key: str = Field(..., description="Your Odoo API key (Settings > Users > API Keys tab)")


@mcp.tool(
    name="odoo_setup_credentials",
    description=(
        "Save your personal Odoo credentials so Odoo tools can connect on your behalf. "
        "Run this once. Credentials are stored in your user home directory (~/.config/odoo-mcp/) "
        "and are only accessible to you. To generate an API key: go to Odoo Settings > "
        "Users > your profile > API Keys tab > New API Key."
    ),
    annotations={"title": "Set Up Odoo Credentials", "readOnlyHint": False, "destructiveHint": False},
)
async def odoo_setup_credentials(input: OdooSetupCredentialsInput) -> str:
    """Tool: write per-user Odoo credentials to ~/.config/odoo-mcp/credentials.json.

    Validates the credentials against Odoo before storing them.
    Does not require an existing authenticated session.
    """
    import re

    # Basic input validation
    if not re.match(r"^https?://", input.url):
        return "Error: URL must start with https:// (e.g. https://my.odoo.com)"
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
        "write_execution_enabled": _truthy_env("ODOO_MCP_ENABLE_WRITES"),
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
