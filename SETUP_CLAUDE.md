# Claude Desktop Setup (Local-Only)

This setup assumes the MCP server runs on each user's local machine.

## Quick Start: Install by Passing the Repo

If your Claude environment supports plugin/repo install, this repository includes:

- `.claude-plugin/plugin.json`

Use that flow first. After install:

1. Fully restart Claude Desktop.
2. Run `Set up my Odoo credentials`.
3. Run `Show my Odoo runtime info`.

## Transport Rule (Required)

Set `ODOO_TRANSPORT` by Odoo version:

- Odoo 18 and below: `xmlrpc`
- Odoo 19 and above: `json2`

If you use `json2`, also provide an API key (`ODOO_API_KEY` or stored credentials).

## macOS Manual Setup (Fallback)

### 1) Install uv/uvx

Option A (Homebrew):

```bash
brew install uv
```

Option B (official installer):

- https://docs.astral.sh/uv/getting-started/installation/

Verify:

```bash
uvx --version
```

### 2) Configure Claude Desktop

Open:

`~/Library/Application Support/Claude/claude_desktop_config.json`

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
      ],
      "env": {
        "ODOO_TRANSPORT": "xmlrpc"
      }
    }
  }
}
```

For Odoo 19+, set `ODOO_TRANSPORT` to `json2`.

If Claude cannot find `uvx`, use its absolute path:

```bash
which uvx
```

Then set `command` to that full path.

### 3) Restart and verify

1. Fully quit and reopen Claude Desktop.
2. Run `Set up my Odoo credentials`.
3. Provide:
- Odoo URL
- Database name
- Odoo login email
- Odoo API key (not password)
4. Run `Ping Odoo` and `Show my Odoo runtime info`.

## Windows Manual Setup (Fallback)

### 1) Install uv/uvx

```powershell
winget install -e --id astral-sh.uv
```

Verify:

```powershell
uvx --version
Get-Command uvx | Select-Object -ExpandProperty Source
```

### 2) Create or open Claude config

```powershell
$configDir = Join-Path $env:APPDATA "Claude"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$configPath = Join-Path $configDir "claude_desktop_config.json"
if (-not (Test-Path $configPath)) { "{}" | Set-Content -Path $configPath -Encoding UTF8 }
notepad $configPath
```

### 3) Use absolute uvx path (most reliable)

Use the `Get-Command uvx` output as `command`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "C:\\absolute\\path\\to\\uvx.exe",
      "args": [
        "--from",
        "https://github.com/italanta/odoo-mcp-server",
        "odoo-mcp-server"
      ],
      "env": {
        "ODOO_TRANSPORT": "xmlrpc"
      }
    }
  }
}
```

For Odoo 19+, set `ODOO_TRANSPORT` to `json2`.

### 4) Restart and verify

1. Fully quit and reopen Claude Desktop.
2. Run `Set up my Odoo credentials`.
3. Provide:
- Odoo URL
- Database name
- Odoo login email
- Odoo API key (not password)
4. Run `Ping Odoo` and `Show my Odoo runtime info`.

## Troubleshooting

- `uvx` works in terminal but not Claude:
  - Use absolute `uvx` path in config `command`.
- Tools do not appear:
  - Validate JSON syntax and fully restart Claude Desktop.
- Auth fails:
  - Re-check URL, DB, email, API key, and transport version rule.
- Prompt asks for password:
  - Use API key only.

## Local Development Install

If developing this repository locally:

macOS:

```bash
cd /Users/jenterosseel/Documents/GitHub/odoo-mcp-server
pip install -e .
```

Windows:

```powershell
cd C:\Users\<your-user>\Documents\GitHub\odoo-mcp-server
py -m pip install -e .
```
