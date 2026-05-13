import pytest

from src.mcp.odoo import server


class TestCheckForUpdate:
    @pytest.mark.asyncio
    async def test_check_for_update_returns_upgrade_hint(self, monkeypatch):
        def fake_check(repo, timeout):
            return {
                "repo": repo,
                "local_version": "0.1.0",
                "latest_version": "v0.2.0",
                "latest_url": "https://github.com/italanta/odoo-mcp-server/releases/tag/v0.2.0",
                "source": "release",
                "update_available": True,
            }

        monkeypatch.setattr(server, "check_for_update", fake_check)
        monkeypatch.setattr(server, "default_repo", lambda: "italanta/odoo-mcp-server")

        result = await server.odoo_check_for_update(server.OdooCheckForUpdateInput())

        assert result["ok"] is True
        assert result["update_available"] is True
        assert result["latest_version"] == "v0.2.0"
        assert "pip" in " ".join(result["suggested_upgrade_command"])


class TestApplySelfUpdate:
    @pytest.mark.asyncio
    async def test_apply_requires_confirm(self):
        result = await server.odoo_apply_self_update(
            server.OdooApplySelfUpdateInput(confirm=False)
        )

        assert result["ok"] is False
        assert "confirm" in result["error"]

    @pytest.mark.asyncio
    async def test_apply_respects_env_gate(self, monkeypatch):
        monkeypatch.delenv("ODOO_MCP_ENABLE_SELF_UPDATE", raising=False)

        result = await server.odoo_apply_self_update(
            server.OdooApplySelfUpdateInput(confirm=True)
        )

        assert result["ok"] is False
        assert "disabled" in result["error"]

    @pytest.mark.asyncio
    async def test_apply_runs_update_when_enabled(self, monkeypatch):
        monkeypatch.setenv("ODOO_MCP_ENABLE_SELF_UPDATE", "1")
        monkeypatch.setattr(server, "default_repo", lambda: "italanta/odoo-mcp-server")
        monkeypatch.setattr(
            server,
            "fetch_latest_release_or_tag",
            lambda repo, timeout: {
                "version": "v0.2.0",
                "url": "https://github.com/italanta/odoo-mcp-server/releases/tag/v0.2.0",
                "source": "release",
            },
        )
        monkeypatch.setattr(
            server,
            "apply_self_update",
            lambda repo, ref, timeout: {
                "ok": True,
                "command": ["python", "-m", "pip", "install", "--upgrade", "dummy"],
                "returncode": 0,
                "stdout_tail": "ok",
                "stderr_tail": "",
            },
        )

        result = await server.odoo_apply_self_update(
            server.OdooApplySelfUpdateInput(confirm=True)
        )

        assert result["ok"] is True
        assert result["restart_required"] is True
        assert result["ref"] == "v0.2.0"
