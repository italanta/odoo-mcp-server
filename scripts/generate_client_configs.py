#!/usr/bin/env python3
"""Generate local MCP client config snippets from manifest.json.

Outputs are written to dist/client-configs/ and intended for release artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifest.json"
OUT_DIR = ROOT / "dist" / "client-configs"


def _load_manifest() -> dict:
    # Read the release manifest once and drive all client outputs from it.
    # This keeps Claude/Hermes/OpenClaw snippets aligned with bundle metadata.
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _normalize_server(manifest: dict) -> tuple[str, list[str], dict[str, str]]:
    # The manifest is the source of truth; normalize into plain strings so
    # downstream serialization is stable across clients and CI environments.
    mcp_cfg = manifest["server"]["mcp_config"]
    command = str(mcp_cfg.get("command", "uv"))
    args = [str(a) for a in mcp_cfg.get("args", [])]
    env = {str(k): str(v) for k, v in (mcp_cfg.get("env") or {}).items()}
    return command, args, env


def _replace_dir_tokens(value: str) -> str:
    # Replace bundle-time placeholders with the checked-out repository path so
    # generated snippets can be used immediately in local client configs.
    return value.replace("${__dirname}", str(ROOT))


def _build_local_server(name: str, command: str, args: list[str], env: dict[str, str]) -> dict:
    # Claude and OpenClaw both accept an mcpServers object keyed by server name.
    # Reuse the same shape to avoid per-client duplication bugs.
    return {
        "mcpServers": {
            name: {
                "command": _replace_dir_tokens(command),
                "args": [_replace_dir_tokens(a) for a in args],
                "env": env,
            }
        }
    }


def main() -> None:
    manifest = _load_manifest()
    server_name = manifest.get("name", "odoo-mcp-server")
    command, args, env = _normalize_server(manifest)

    # Ensure artifact output exists both locally and in CI.
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Claude Desktop JSON shape.
    claude = _build_local_server("odoo", command, args, env)
    (OUT_DIR / "claude_desktop_config.odoo.json").write_text(
        json.dumps(claude, indent=2) + "\n", encoding="utf-8"
    )

    # OpenClaw MCP config shape (JSON map of local stdio servers).
    openclaw = _build_local_server("odoo", command, args, env)
    (OUT_DIR / "openclaw_mcp_servers.json").write_text(
        json.dumps(openclaw, indent=2) + "\n", encoding="utf-8"
    )

    # Hermes YAML snippet for ~/.hermes/config.yaml mcp_servers.
    # Keep as static text to avoid adding a YAML dependency in CI.
    hermes_yaml = [
        "mcp_servers:",
        "  odoo:",
        f"    command: \"{_replace_dir_tokens(command)}\"",
        "    args:",
    ]
    for arg in args:
        hermes_yaml.append(f"      - \"{_replace_dir_tokens(arg)}\"")
    hermes_yaml.append("    env:")
    for k, v in env.items():
        hermes_yaml.append(f"      {k}: \"{v}\"")
    (OUT_DIR / "hermes_mcp_servers.yaml").write_text("\n".join(hermes_yaml) + "\n", encoding="utf-8")

    # Small metadata file for installers/release notes.
    meta = {
        "bundle_name": server_name,
        "generated_files": [
            "claude_desktop_config.odoo.json",
            "openclaw_mcp_servers.json",
            "hermes_mcp_servers.yaml",
        ],
    }
    (OUT_DIR / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
