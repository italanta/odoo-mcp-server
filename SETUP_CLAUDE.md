# Claude Desktop Setup (Fastest Path)

This is the quickest way to run this Odoo MCP server in Claude Desktop on macOS.

## 1) Add MCP Server to Claude Desktop

Open this file:

`~/Library/Application Support/Claude/claude_desktop_config.json`

If it does not exist, create it.

Use this config:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "uvx",
      "args": [
        "--from",
        "https://github.com/italanta/odoo-mcp-server",
        "odoo-mcp-server"
      ]
    }
  }
}
```

Why this is easiest:
- No manual clone required
- No virtual environment required
- Always launches from the published GitHub source

## 2) Restart Claude Desktop

Completely quit and reopen Claude Desktop after saving the config.

## 3) Set Credentials in Claude

In Claude chat, say:

`Set up my Odoo credentials`

Provide:
- Odoo URL (example: `https://my.odoo.com`)
- Database name
- Odoo login email
- Odoo API key

Credentials are saved per user at:

`~/.config/odoo-mcp/credentials.json`

## 4) Verify It Works

Ask Claude:

- `Ping Odoo`
- `Show my Odoo runtime info`

If setup is correct, Claude should call tools such as `odoo_ping` and return your user profile.

## Troubleshooting

- If Claude says credentials are missing:
  - Run `Set up my Odoo credentials` again.
- If authentication fails:
  - Re-check URL, database, email, and API key.
- If tools do not appear:
  - Re-open Claude Desktop and confirm JSON syntax is valid.

## Alternative: Local Development Install

If you are actively developing this repository, use a local install instead of `uvx`:

```bash
cd /Users/jenterosseel/Documents/GitHub/odoo-mcp-server
pip install -e .
```

Then set Claude config to:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "odoo-mcp-server"
    }
  }
}
```
