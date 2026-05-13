"""Shared update helpers for CLI scripts and MCP runtime tools.

The project stays local-first: these helpers only inspect public GitHub metadata
and run a local package manager command when explicitly requested.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    import certifi
except Exception:  # pragma: no cover - optional dependency fallback.
    certifi = None


DEFAULT_REPO = "italanta/odoo-mcp-server"


def default_repo() -> str:
    """Return configured update source repository.

    Allows controlled override for forks while keeping a safe canonical default.
    """
    return os.environ.get("ODOO_MCP_UPDATE_REPO", "").strip() or DEFAULT_REPO


def normalize_version(value: str) -> tuple[int, int, int]:
    """Normalize semantic-ish version text to integer tuple for simple comparison."""
    numbers = [int(part) for part in re.findall(r"\d+", value)]
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers[:3])


def read_local_version(package_name: str = "odoo-mcp-server") -> str:
    """Read currently installed package version, falling back to unknown marker."""
    try:
        return metadata.version(package_name)
    except Exception:
        return "0.0.0"


def _ssl_context() -> ssl.SSLContext:
    # Prefer certifi for consistent trust behavior across macOS/Windows Python
    # distributions, but fall back to OS CA store if certifi is unavailable.
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def _request_json(url: str, timeout: int) -> dict | list:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "odoo-mcp-server-update-manager",
        },
    )
    with urlopen(request, timeout=timeout, context=_ssl_context()) as response:  # nosec B310 - controlled HTTPS URL.
        return json.loads(response.read().decode("utf-8"))


def fetch_latest_release_or_tag(repo: str, timeout: int) -> dict[str, str]:
    """Return latest release metadata, falling back to latest tag if needed."""
    release_url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        payload = _request_json(release_url, timeout=timeout)
        return {
            "version": str(payload.get("tag_name") or payload.get("name") or "0.0.0"),
            "url": str(payload.get("html_url") or f"https://github.com/{repo}/releases"),
            "source": "release",
        }
    except HTTPError as exc:
        if exc.code != 404:
            raise

    tags_url = f"https://api.github.com/repos/{repo}/tags"
    payload = _request_json(tags_url, timeout=timeout)
    if isinstance(payload, list) and payload:
        first = payload[0] or {}
        name = str(first.get("name") or "")
        if name:
            return {
                "version": name,
                "url": f"https://github.com/{repo}/tags",
                "source": "tag",
            }

    raise RuntimeError(f"No published releases or tags found for repository: {repo}")


def check_for_update(repo: str, timeout: int, package_name: str = "odoo-mcp-server") -> dict[str, object]:
    """Compare local installed version with latest remote release/tag."""
    local_version = read_local_version(package_name=package_name)
    latest = fetch_latest_release_or_tag(repo=repo, timeout=timeout)
    latest_version = str(latest["version"])
    update_available = normalize_version(latest_version) > normalize_version(local_version)
    return {
        "repo": repo,
        "local_version": local_version,
        "latest_version": latest_version,
        "latest_url": str(latest["url"]),
        "source": str(latest["source"]),
        "update_available": update_available,
    }


def build_upgrade_command(repo: str, ref: str) -> list[str]:
    """Construct a local pip-based upgrade command pinned to a git ref/tag."""
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        f"git+https://github.com/{repo}.git@{ref}",
    ]


def apply_self_update(repo: str, ref: str, timeout: int = 300) -> dict[str, object]:
    """Execute local package update and return process result for MCP response."""
    command = build_upgrade_command(repo=repo, ref=ref)
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "ok": completed.returncode == 0,
        "command": command,
        "returncode": completed.returncode,
        # Return tails to keep tool responses compact while still debuggable.
        "stdout_tail": "\n".join(completed.stdout.splitlines()[-40:]),
        "stderr_tail": "\n".join(completed.stderr.splitlines()[-40:]),
    }


def repo_from_pyproject(pyproject_path: Path) -> str | None:
    """Best-effort repository extraction from pyproject metadata for local script UX."""
    if not pyproject_path.exists():
        return None
    try:
        import tomllib

        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    repo_url = str((data.get("project") or {}).get("repository") or "")
    match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"
