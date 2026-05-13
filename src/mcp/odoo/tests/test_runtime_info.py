import pytest

from src.mcp.odoo import server


class TestRuntimeInfo:
    @pytest.mark.asyncio
    async def test_runtime_info_reports_json2_configuration(self, monkeypatch):
        monkeypatch.setenv("ODOO_TRANSPORT", "json2")
        monkeypatch.setenv("ODOO_API_KEY", "secret")

        info = await server.odoo_runtime_info()

        assert info["odoo_transport"] == "json2"
        assert info["json2_api_key_configured"] is True
        assert info["transport_compatibility_hints"]

    @pytest.mark.asyncio
    async def test_runtime_info_defaults_to_xmlrpc(self, monkeypatch):
        monkeypatch.delenv("ODOO_TRANSPORT", raising=False)
        monkeypatch.delenv("ODOO_API_KEY", raising=False)

        info = await server.odoo_runtime_info()

        assert info["odoo_transport"] == "xmlrpc"
        assert info["json2_api_key_configured"] is False
