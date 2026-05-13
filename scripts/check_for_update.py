#!/usr/bin/env python3
"""Check whether a newer GitHub release is available for this project.

This helper is intentionally dependency-free so users can run it in a fresh
local environment before deciding to upgrade their MCP client assets.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

# When this script is executed directly, Python's import base is scripts/.
# Add repository root so shared runtime modules under src/ are importable.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mcp.odoo.utils.update_manager import check_for_update, default_repo, repo_from_pyproject


def _parse_repo_arg() -> str:
    parser = argparse.ArgumentParser(
        description="Compare local odoo-mcp-server version with the latest GitHub release."
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="GitHub repo in owner/name format (auto-detected when omitted)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="HTTP timeout in seconds for the GitHub API call",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Return exit code 0 for both up-to-date and update-available outcomes",
    )
    args = parser.parse_args()
    repo = args.repo or repo_from_pyproject(PYPROJECT) or default_repo()
    return repo, args.timeout, args.ci


def main() -> int:
    repo, timeout, ci_mode = _parse_repo_arg()
    try:
        result = check_for_update(repo=repo, timeout=timeout)
    except HTTPError as exc:
        print(f"GitHub API returned HTTP {exc.code}: {exc.reason}")
        return 2
    except URLError as exc:
        print(f"Could not reach GitHub releases API: {exc}")
        print("Tip: rerun later or pass --repo owner/name if the configured source is wrong.")
        return 2
    except Exception as exc:
        print(str(exc))
        return 2

    print(f"Repository: {result['repo']}")
    print(f"Local version: {result['local_version']}")
    print(f"Latest release: {result['latest_version']}")
    print(f"Release page: {result['latest_url']}")

    if bool(result["update_available"]):
        print()
        print("Update available.")
        print("Download the newest release bundle zip and re-apply client assets if needed.")
        print(f"Open: {result['latest_url']}")
        if ci_mode:
            return 0
        return 1

    print()
    print("You are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
