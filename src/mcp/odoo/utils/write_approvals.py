"""In-memory approval token store for staged write execution.

Inspired by tuanle96/mcp-odoo's preview/validate/execute model.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class ApprovalRecord:
    token: str
    payload_hash: str
    created_at: float
    expires_at: float
    consumed: bool = False


def payload_hash(payload: dict[str, Any]) -> str:
    # Canonicalize payload representation before hashing so ordering does not matter.
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ApprovalStore:
    """Stores short-lived, single-use approvals in server memory."""

    def __init__(self, ttl_seconds: int = 600):
        self._ttl_seconds = ttl_seconds
        self._records: dict[str, ApprovalRecord] = {}

    def register(self, payload: dict[str, Any]) -> ApprovalRecord:
        # Register a token tied to a specific payload hash and expiry window.
        now = time.time()
        token = secrets.token_urlsafe(24)
        record = ApprovalRecord(
            token=token,
            payload_hash=payload_hash(payload),
            created_at=now,
            expires_at=now + self._ttl_seconds,
            consumed=False,
        )
        self._records[token] = record
        return record

    def consume(self, token: str, payload: dict[str, Any]) -> ApprovalRecord:
        # Consume is fail-closed: unknown/used/expired/mismatched tokens are rejected.
        now = time.time()
        record = self._records.get(token)
        if not record:
            raise ValueError("Unknown approval token.")
        if record.consumed:
            raise ValueError("Approval token already used.")
        if now > record.expires_at:
            raise ValueError("Approval token expired.")
        if record.payload_hash != payload_hash(payload):
            raise ValueError("Approval token does not match this payload.")

        # Mark consumed to enforce one-time execution.
        record.consumed = True
        return record
