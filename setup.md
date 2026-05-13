# Setup

This document is the single setup source of truth for this repository.

## Supported Hosting Options

This package is built for exactly two hosting models.

1. Personal agent hosting (local): Claude Desktop, ClawdBot, Hermes.
2. Org-wide hosting on Claude Cowork via plugin from your own fork.

## Hosted MCP Server

Do not host this as a central multi-user MCP server.

Reason: Odoo uses private API keys. A shared central MCP host would store private user or org tokens in one place, increasing credential exposure and blast radius.

This package is intentionally local-first and plugin-scoped for safer credential boundaries.

## Option 1: Personal Agent Hosting (Local)

Use this mode for individual users running MCP locally in their own agent harness.

Supported harnesses:

- Claude Desktop
- ClawdBot
- Hermes

### Install

Primary download links:

- https://github.com/italanta/odoo-mcp-server/releases
- Rolling prerelease (latest-main): https://github.com/italanta/odoo-mcp-server/releases/tag/latest-main
- Repository source: https://github.com/italanta/odoo-mcp-server

Release assets to use:

- odoo-mcp-server-<version>-bundle.zip (single download bundle)
- odoo-mcp-server-<version>-bundle.zip.sha256 (checksum)
- odoo-mcp-server*.mcpb (Claude Desktop extension bundle)
- dist/client-configs/claude_desktop_config.odoo.json
- dist/client-configs/openclaw_mcp_servers.json
- dist/client-configs/hermes_mcp_servers.yaml

### Method 1A: Claude Desktop (personal local install)

1. Open Releases: https://github.com/italanta/odoo-mcp-server/releases
2. Download either:
- odoo-mcp-server-<version>-bundle.zip, or
- odoo-mcp-server*.mcpb directly.
3. Install the .mcpb in Claude Desktop Extensions.
4. Claude Extensions install docs: https://claude.com/docs/connectors/building/mcpb
5. Install methods supported by Claude Desktop:
- Double-click the .mcpb file, or
- Drag and drop the .mcpb into Claude Desktop, or
- Open Settings -> Extensions -> Advanced settings -> Install Extension.
6. Restart Claude Desktop.
7. In chat, run: Set up my Odoo credentials.
8. Verify with: odoo_runtime_info and odoo_ping.

Fallback manual config:

1. Extract dist/client-configs/claude_desktop_config.odoo.json from the bundle.
2. Merge it into your local Claude Desktop MCP config.

### Method 1B: ClawdBot (personal local install)

1. Open Releases: https://github.com/italanta/odoo-mcp-server/releases
2. Download odoo-mcp-server-<version>-bundle.zip.
3. Extract dist/client-configs/openclaw_mcp_servers.json.
4. Import or merge this file into your ClawdBot/OpenClaw local MCP server config.
5. Reload MCP servers in ClawdBot.
6. In chat, run: Set up my Odoo credentials, then odoo_ping.

### Method 1C: Hermes (personal local install)

1. Open Releases: https://github.com/italanta/odoo-mcp-server/releases
2. Download odoo-mcp-server-<version>-bundle.zip.
3. Extract dist/client-configs/hermes_mcp_servers.yaml.
4. Merge under mcp_servers in ~/.hermes/config.yaml.
5. Start Hermes (or run /reload-mcp if already running).
6. In chat, run: Set up my Odoo credentials, then odoo_ping.

You can also run directly from source with uvx:

- uvx --from https://github.com/italanta/odoo-mcp-server odoo-mcp-server

Install uv/uvx:

- macOS: https://docs.astral.sh/uv/getting-started/installation/
- Windows (winget package): https://github.com/astral-sh/uv

### Configure transport

- Odoo 18 and below: xmlrpc
- Odoo 19 and above: json2

If using json2, ensure API key auth is configured.

### Configure credentials

In your agent chat, run:

- Set up my Odoo credentials

Provide:

- Odoo URL
- Database name
- Login email
- Odoo API key (not password)

## Option 2: Org-wide Hosting on Claude Cowork via Plugin

Use this mode when you want a managed rollout inside Claude Cowork.

### Fork and prepare

1. Fork this repository into your org or private namespace:
- https://github.com/italanta/odoo-mcp-server/fork
2. Keep plugin metadata aligned with your fork:
- https://github.com/italanta/odoo-mcp-server/blob/main/.claude-plugin/plugin.json
3. Push your fork updates to main.

### Import into Claude Cowork

Claude Cowork plugin usage docs:

- https://support.claude.com/en/articles/13837440-use-plugins-in-claude-cowork

1. Open Claude Cowork admin/plugin import flow.
2. Choose repo/plugin import.
3. Provide your fork repository URL (example: https://github.com/<your-org>/odoo-mcp-server).
4. Confirm plugin manifest detection.
5. Install and enable for the target workspace/users.

### Post-import validation

1. Restart or reload plugin context in Claude Cowork.
2. Run odoo_runtime_info.
3. Run odoo_ping.
4. Run staged write flow checks before enabling real write execution.

## Update and self-update behavior

- Release updates are published as versioned assets and a rolling latest-main prerelease.
- MCP-native check: odoo_check_for_update.
- MCP-native apply: odoo_apply_self_update.
- Self-update execution requires ODOO_MCP_ENABLE_SELF_UPDATE=1 and explicit confirm=true.

## Safety reminder

- Keep Odoo credentials scoped to user/plugin runtime.
- Do not centralize raw Odoo API tokens in shared infrastructure unless your security team explicitly accepts that risk and controls.
