import pytest
import json

from src.mcp.odoo import server


class FakeRequestContext:
    def __init__(self, lifespan_context):
        self.lifespan_context = lifespan_context


class FakeContext:
    def __init__(self, lifespan_context):
        self.request_context = FakeRequestContext(lifespan_context)


class TestRuntimeInfo:
    @pytest.mark.asyncio
    async def test_runtime_info_reports_json2_configuration(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ODOO_TRANSPORT", "json2")
        monkeypatch.setenv("ODOO_API_KEY", "secret")
        monkeypatch.setattr(server, "CONFIG_PATH", tmp_path / "credentials.json")

        info = await server.odoo_runtime_info()

        assert info["odoo_transport"] == "json2"
        assert info["json2_env_api_key_configured"] is True
        assert info["json2_stored_api_key_configured"] is False
        assert info["json2_api_key_available"] is True
        assert info["transport_compatibility_hints"]

    @pytest.mark.asyncio
    async def test_runtime_info_defaults_to_xmlrpc(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ODOO_TRANSPORT", raising=False)
        monkeypatch.delenv("ODOO_API_KEY", raising=False)
        monkeypatch.setattr(server, "CONFIG_PATH", tmp_path / "credentials.json")

        info = await server.odoo_runtime_info()

        assert info["odoo_transport"] == "xmlrpc"
        assert info["json2_api_key_available"] is False

    @pytest.mark.asyncio
    async def test_runtime_info_reports_stored_api_key(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ODOO_TRANSPORT", "json2")
        monkeypatch.delenv("ODOO_API_KEY", raising=False)
        monkeypatch.setattr(server, "CONFIG_PATH", tmp_path / "credentials.json")
        server.CONFIG_PATH.write_text(json.dumps({"api_key": "stored-secret"}))

        info = await server.odoo_runtime_info()

        assert info["json2_env_api_key_configured"] is False
        assert info["json2_stored_api_key_configured"] is True
        assert info["json2_api_key_available"] is True

    @pytest.mark.asyncio
    async def test_setup_credentials_refreshes_current_session(self, monkeypatch, tmp_path):
        monkeypatch.setattr(server, "store_odoo_credentials_file", lambda **_: None)

        class FakeClient:
            def __init__(self, credentials=None):
                self.credentials = credentials
                self.authenticated = False
                self.closed = False

            async def authenticate(self):
                self.authenticated = True
                return 7

            async def close(self):
                self.closed = True

        monkeypatch.setattr(server, "OdooClient", FakeClient)

        ctx = FakeContext(server.AppContext(odoo=None, auth_error="Odoo is not authenticated"))
        result = await server.odoo_setup_credentials(
            server.OdooSetupCredentialsInput(
                url="https://example.odoo.com",
                db="example",
                username="user@example.com",
                api_key="secret",
            ),
            ctx,
        )

        assert "Credentials saved" in result
        assert ctx.request_context.lifespan_context.auth_error is None
        assert ctx.request_context.lifespan_context.odoo is not None
