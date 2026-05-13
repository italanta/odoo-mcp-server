# 🚀 Odoo MCP Server — GitHub Setup Guide

Your standalone Odoo MCP repository is ready at `/Users/jenterosseel/Documents/GitHub/odoo-mcp-server/`.

## Step 1: Initialize Git

```bash
cd /Users/jenterosseel/Documents/GitHub/odoo-mcp-server
git init
git add .
git commit -m "Initial commit: Standalone Odoo MCP server

- Includes sales, projects domain tools
- Safety guard for outbound communication blocker
- Full test suite with safety validation"
```

## Step 2: Create GitHub Repository

1. Go to [https://github.com/new](https://github.com/new)
2. **Owner**: `italanta` (or your preferred org)
3. **Repository name**: `odoo-mcp-server`
4. **Description**: `Odoo MCP Server — Claude MCP tools for Odoo CRM, projects, and domain tools`
5. **Visibility**: Private (or Public if you want community contributions)
6. **Initialize with**: None (we already have files)
7. Click **Create repository**

## Step 3: Add Remote and Push

```bash
cd /Users/jenterosseel/Documents/GitHub/odoo-mcp-server

# Add GitHub as remote
git remote add origin https://github.com/italanta/odoo-mcp-server.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

## Step 4: Verify & Configure

- [ ] Verify repo is at `https://github.com/italanta/odoo-mcp-server`
- [ ] Check that all files are present (src/, pyproject.toml, README.md, etc.)
- [ ] (Optional) Set up branch protection rules: Require PR reviews before merge
- [ ] (Optional) Add CI/CD: Add GitHub Actions for running tests

## Step 5: Usage from This Repo

### Option A: Direct Installation from GitHub

Users can now install with:

```bash
pip install git+https://github.com/italanta/odoo-mcp-server
```

### Option B: PyPI Release (Future)

When ready for public release:

```bash
# Build distribution
python -m build

# Upload to PyPI (requires credentials)
twine upload dist/*
```

Then users can install with:

```bash
pip install odoo-mcp-server
```

## Odoo MCP Server

The core Odoo MCP server is now a standalone package:
- **Repository**: https://github.com/italanta/odoo-mcp-server
- **Install**: `pip install git+https://github.com/italanta/odoo-mcp-server`
```

## File Structure Summary

```
odoo-mcp-server/
├── src/
│   ├── core/
│   │   └── credentials.py          ← Per-user credential management
│   └── mcp/
│       └── odoo/
│           ├── server.py            ← Main MCP server & generic tools
│           ├── README.md            ← Architecture & design docs
│           ├── utils/
│           │   ├── client.py        ← Async Odoo XML-RPC client
│           │   └── safety.py        ← SafetyGuard: outbound blocker
│           ├── tools/
│           │   ├── sales.py         ← CRM tools (8 tools)
│           │   ├── projects.py      ← Project tools (6 tools)
│           │   └── _shared.py       ← Shared types
│           └── tests/
│               └── test_safety.py   ← Critical safety tests
├── pyproject.toml                   ← Package metadata & dependencies
├── README.md                        ← Public-facing documentation
├── LICENSE                          ← Proprietary license
├── .gitignore                       ← Git exclusions
└── SETUP_GUIDE.md                   ← This file
```

## Key Files for Deployment

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package name, version, dependencies, entry point |
| `src/mcp/odoo/server.py` | Main MCP server (entry point: `odoo-mcp-server`) |
| `src/mcp/odoo/utils/safety.py` | **CRITICAL**: Outbound communication blocker |
| `src/mcp/odoo/tests/test_safety.py` | **CRITICAL**: Safety validation tests |
| `README.md` | Installation, setup, usage documentation |
| `LICENSE` | Proprietary license terms |

## Testing Before Release

Always run safety tests before any commit or release:

```bash
cd /Users/my-user/Documents/GitHub/odoo-mcp-server

# Install dev dependencies
pip install -e ".[dev]"

# Run critical safety tests
pytest src/mcp/odoo/tests/test_safety.py -v

# Run all tests
pytest tests/ src/mcp/odoo/tests/ -v
``` 

## Common Commands

```bash
# Clone the repo
git clone https://github.com/italanta/odoo-mcp-server
cd odoo-mcp-server

# Set up for development
pip install -e ".[dev]"

# Run tests
pytest src/mcp/odoo/tests/test_safety.py -v

# Install in Claude Desktop
# (follow README.md Setup instructions)
```

## Support

Questions about deployment?
- Check the main [README.md](README.md) for usage docs
- See [src/mcp/odoo/README.md](src/mcp/odoo/README.md) for architecture details
- Review [src/mcp/odoo/utils/safety.py](src/mcp/odoo/utils/safety.py) for safety guarantees
