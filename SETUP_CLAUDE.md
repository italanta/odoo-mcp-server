# Claude Desktop Setup (macOS and Windows)

This guide is split into two complete tracks so you can follow only your platform.

## Do I Need Python?

Short answer: not always on your own laptop, but yes somewhere.

- Claude Desktop on your Mac/PC: Yes. The MCP server runs locally, so a local runtime is required (Python directly, or `uv`/`uvx` which manages it for you).
- Claude Cowork managed environment: Usually not on your personal machine. But the environment running the MCP server still needs Python available.

Claude Cowork does not remove the Python requirement entirely. It shifts where Python must exist.

## macOS Track

### 1) Install Python (3.11+)

Option A (official installer):
- Download from: `https://www.python.org/downloads/macos/`
- Run the installer, then restart Terminal.

Option B (Homebrew):

```bash
brew install python
```

Verify:

```bash
python3 --version
```

### 2) Add MCP Server to Claude Desktop

Open:

`~/Library/Application Support/Claude/claude_desktop_config.json`

If it does not exist, create it.

Use:

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

### 3) Restart Claude Desktop

Completely quit and reopen Claude Desktop.

### 4) Set Credentials in Claude

In Claude chat, say:

`Set up my Odoo credentials`

Provide:
- Odoo URL (example: `https://my.odoo.com`)
- Database name
- Odoo login email
- Odoo API key

Credentials are saved per user at:

`~/.config/my-odoo/credentials.json`

### 5) Verify

Ask Claude:
- `Ping Odoo`
- `Show my Odoo runtime info`

## Windows (Microsoft) Track

### 1) Install Python (3.11+)

Option A (official installer):
- Download from: `https://www.python.org/downloads/windows/`
- Run installer and enable `Add Python to PATH`.

Option B (winget):

```powershell
winget install -e --id Python.Python.3.12
```

Verify (PowerShell):

```powershell
python --version
```

### 2) Add MCP Server to Claude Desktop

Open:

`%AppData%\Claude\claude_desktop_config.json`

If it does not exist, create it.

Use:

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

### 3) Restart Claude Desktop

Completely quit and reopen Claude Desktop.

### 4) Set Credentials in Claude

In Claude chat, say:

`Set up my Odoo credentials`

Provide:
- Odoo URL
- Database name
- Odoo login email
- Odoo API key

Credentials are saved in the user profile used by the MCP process.

### 5) Verify

Ask Claude:
- `Ping Odoo`
- `Show my Odoo runtime info`

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
