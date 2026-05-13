import pytest

from src.mcp.odoo import server
from src.mcp.odoo.utils.write_approvals import ApprovalStore


class FakeOdooClient:
    def __init__(self):
        self.created = []
        self.written = []
        self.executed = []

    async def fields_get(self, model, attributes=None):
        return {
            "name": {"string": "Name", "type": "char", "required": False, "readonly": False},
            "stage_id": {"string": "Stage", "type": "many2one", "required": False, "readonly": False},
        }

    async def create(self, model, values):
        self.created.append((model, values))
        return 101

    async def write(self, model, record_ids, values):
        self.written.append((model, record_ids, values))
        return True

    async def _execute(self, model, method, *args, **kwargs):
        self.executed.append((model, method, list(args), kwargs))
        return {"ok": True, "model": model, "method": method}


class FakeRequestContext:
    def __init__(self, lifespan_context):
        self.lifespan_context = lifespan_context


class FakeContext:
    def __init__(self, lifespan_context):
        self.request_context = FakeRequestContext(lifespan_context)


@pytest.fixture
def isolated_governance(monkeypatch):
    monkeypatch.setattr(server, "_approval_store", ApprovalStore(ttl_seconds=600))
    monkeypatch.setattr(server, "_validated_payloads", {})


@pytest.fixture
def fake_ctx():
    fake_odoo = FakeOdooClient()
    ctx = FakeContext(server.AppContext(odoo=fake_odoo, auth_error=None))
    return ctx, fake_odoo


class TestPreviewWrite:
    @pytest.mark.asyncio
    async def test_preview_rejects_call_without_method(self):
        result = await server.odoo_preview_write(
            server.OdooPreviewWriteInput(model="crm.lead", operation="call")
        )

        assert result["success"] is False
        assert "method is required" in result["error"]


class TestValidateWrite:
    @pytest.mark.asyncio
    async def test_validate_rejects_unknown_field(self, isolated_governance, fake_ctx):
        ctx, _ = fake_ctx
        result = await server.odoo_validate_write(
            server.OdooValidateWriteInput(
                model="crm.lead",
                operation="write",
                record_ids=[1],
                values={"unknown_field": "x"},
            ),
            ctx,
        )

        assert result["success"] is False
        assert "Unknown fields" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_note_call_returns_token(self, isolated_governance, fake_ctx):
        ctx, _ = fake_ctx
        result = await server.odoo_validate_write(
            server.OdooValidateWriteInput(
                model="crm.lead",
                operation="call",
                method="message_post",
                args=[1],
                kwargs={"body": "hello", "message_type": "comment", "subtype_id": 2},
            ),
            ctx,
        )

        assert result["success"] is True
        assert result["approval"]["token"]
        assert result["metadata_used"] == {"live_odoo": False}


class TestExecuteApprovedWrite:
    @pytest.mark.asyncio
    async def test_execute_fails_closed_when_env_disabled(self, isolated_governance, fake_ctx, monkeypatch):
        ctx, _ = fake_ctx
        monkeypatch.delenv("ODOO_MCP_ENABLE_WRITES", raising=False)
        validate = await server.odoo_validate_write(
            server.OdooValidateWriteInput(
                model="crm.lead",
                operation="call",
                method="message_post",
                args=[1],
                kwargs={"body": "hello", "message_type": "comment", "subtype_id": 2},
            ),
            ctx,
        )

        result = await server.odoo_execute_approved_write(
            server.OdooExecuteApprovedWriteInput(
                approval_token=validate["approval"]["token"],
                confirm=True,
            ),
            ctx,
        )

        assert result["success"] is False
        assert "disabled" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_runs_approved_call(self, isolated_governance, fake_ctx, monkeypatch):
        ctx, fake_odoo = fake_ctx
        monkeypatch.setenv("ODOO_MCP_ENABLE_WRITES", "1")
        validate = await server.odoo_validate_write(
            server.OdooValidateWriteInput(
                model="crm.lead",
                operation="call",
                method="message_post",
                args=[42],
                kwargs={"body": "hello", "message_type": "comment", "subtype_id": 2},
            ),
            ctx,
        )

        result = await server.odoo_execute_approved_write(
            server.OdooExecuteApprovedWriteInput(
                approval_token=validate["approval"]["token"],
                confirm=True,
            ),
            ctx,
        )

        assert result["success"] is True
        assert result["operation"] == "call"
        assert fake_odoo.executed == [
            (
                "crm.lead",
                "message_post",
                [42],
                {"body": "hello", "message_type": "comment", "subtype_id": 2},
            )
        ]
