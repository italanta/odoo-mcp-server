"""Pure diagnostics helpers for Odoo MCP tools.

Inspired by patterns from tuanle96/mcp-odoo:
- classify calls without executing them
- provide issue lists and safe next actions
- keep helpers side-effect free
"""

from __future__ import annotations

import re
from typing import Any

MODEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*$")

READ_ONLY_METHODS = {
    "search",
    "search_count",
    "search_read",
    "read",
    "fields_get",
    "name_get",
    "name_search",
}

DESTRUCTIVE_METHODS = {"create", "write", "unlink"}

SIDE_EFFECT_METHOD_PATTERNS = (
    # Common Odoo workflow/action naming conventions that often trigger side effects.
    re.compile(r"^action_"),
    re.compile(r"^button_"),
    re.compile(r"(^|_)send($|_)"),
    re.compile(r"(^|_)post($|_)"),
    re.compile(r"(^|_)validate($|_)"),
)


def _method_safety(method: str) -> str:
    # Classify planned calls into broad risk buckets without executing anything.
    if method in DESTRUCTIVE_METHODS:
        return "destructive"
    if method in READ_ONLY_METHODS:
        return "read_only"
    if any(pattern.search(method) for pattern in SIDE_EFFECT_METHOD_PATTERNS):
        return "side_effect"
    return "unknown"


def diagnose_odoo_call(
    *,
    model: str,
    method: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze an Odoo model call without executing it."""
    # Normalize optional inputs so downstream checks can assume concrete containers.
    normalized_args = args or []
    normalized_kwargs = kwargs or {}

    issues: list[dict[str, str]] = []

    if not MODEL_NAME_RE.match(model):
        # Reject malformed model names early to avoid misleading diagnostics later.
        issues.append(
            {
                "severity": "error",
                "code": "invalid_model_name",
                "message": f"Model '{model}' is not a valid Odoo model name.",
                "recommendation": "Use a technical model name such as 'crm.lead' or 'project.task'.",
            }
        )

    if not method or not method.strip():
        # Method is mandatory for any meaningful call-level analysis.
        issues.append(
            {
                "severity": "error",
                "code": "missing_method",
                "message": "Method name is required.",
                "recommendation": "Provide a concrete method name such as 'search_read' or 'write'.",
            }
        )

    safety = _method_safety(method)

    if safety == "destructive":
        # State-changing methods should always be routed through staged governance.
        issues.append(
            {
                "severity": "warning",
                "code": "destructive_method",
                "message": f"Method '{method}' changes server state.",
                "recommendation": "Use preview/validation and explicit human approval before execution.",
            }
        )
    elif safety == "side_effect":
        # Side-effect calls are not always destructive, but can notify or trigger automations.
        issues.append(
            {
                "severity": "warning",
                "code": "side_effect_method",
                "message": f"Method '{method}' may trigger notifications or workflows.",
                "recommendation": "Review side effects and enforce exact allowlist before execution.",
            }
        )

    if method == "write" and len(normalized_args) < 2:
        # XML-RPC write typically expects [ids, values].
        issues.append(
            {
                "severity": "error",
                "code": "write_args_shape",
                "message": "write usually expects [ids, values] in args.",
                "recommendation": "Pass args like [[1, 2], {\"field\": \"value\"}].",
            }
        )

    if method == "create" and not normalized_args:
        # XML-RPC create typically expects values (dict or list of dicts) in args.
        issues.append(
            {
                "severity": "error",
                "code": "create_args_shape",
                "message": "create usually expects values in args.",
                "recommendation": "Pass args like [{\"name\": \"Example\"}].",
            }
        )

    # Only hard errors fail diagnostics; warnings still return success=True.
    success = not any(issue["severity"] == "error" for issue in issues)

    return {
        "success": success,
        "tool": "odoo_diagnose_call",
        "classification": {
            "safety": safety,
            "destructive_method": safety == "destructive",
            "side_effect_method": safety == "side_effect",
        },
        "issues": issues,
        "suggested_payload": {
            "model": model,
            "method": method,
            "args": normalized_args,
            "kwargs": normalized_kwargs,
        },
    }
