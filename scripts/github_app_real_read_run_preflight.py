#!/usr/bin/env python3
"""Offline preflight for the first approved GitHub App real read run.

This check is read-only and offline. It performs no GitHub provider calls, opens
no network connection, and touches no database. It reports only presence
booleans, the concrete blocker list, and the exact next human step. It never
prints secret values, credential paths' contents, tokens, database URLs, or
installation identifiers.

The real read run itself (a scoped ``POST
.../github/connections/app-installation/sync``) remains a separate, explicitly
human-approved action; this script only tells the human whether that run is
currently executable.

Usage:
    uv run python scripts/github_app_real_read_run_preflight.py [--json]
        [--repos-file .local/repos.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.github_connection_service import (  # noqa: E402
    GITHUB_APP_CONNECTION_METHOD,
    github_app_config_status,
    github_app_real_read_run_readiness,
)

DEFAULT_REPOS_FILE = ".local/repos.json"


def _count_local_repositories(repos_file: Path) -> int:
    """Count the offline local repository surface without printing its contents."""

    if not repos_file.exists():
        return 0
    try:
        data = json.loads(repos_file.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    if isinstance(data, dict):
        candidates = data.get("repositories")
        if isinstance(candidates, list):
            return len(candidates)
        return 0
    if isinstance(data, list):
        return len(data)
    return 0


def _offline_connection_status() -> dict[str, Any]:
    """Best-effort offline connection status.

    We do not open the database here to keep the preflight fully offline. The
    installation-connection state is therefore reported as unknown/missing; the
    readiness output makes clear that recording/connecting the installation is a
    prerequisite the human confirms in-app.
    """

    return {
        "has_connection_record": False,
        "connection_method": GITHUB_APP_CONNECTION_METHOD,
        "status": None,
    }


def _build_report(repos_file: Path) -> dict[str, Any]:
    local_repository_count = _count_local_repositories(repos_file)
    connection_status = _offline_connection_status()
    readiness = github_app_real_read_run_readiness(
        connection_status=connection_status,
        local_repository_count=local_repository_count,
    )
    app_config = github_app_config_status()
    return {
        "check": "github_app_real_read_run_preflight",
        "offline": True,
        "provider_read_started": False,
        "provider_writes_enabled": False,
        "requires_human_approval": True,
        "app_env_configured": app_config["configured"],
        "app_missing_env": list(app_config["missing_env"]),
        "local_repository_count": local_repository_count,
        "installation_connection_checked_offline": False,
        "readiness": readiness,
    }


def _print_human(report: dict[str, Any]) -> None:
    readiness = report["readiness"]
    print("GitHub App real-read-run preflight (offline, read-only)")
    print(f"  status: {readiness['status']}")
    print(f"  app env configured: {report['app_env_configured']}")
    if report["app_missing_env"]:
        print(f"  missing env (names only): {', '.join(report['app_missing_env'])}")
    print(f"  local repository surface count: {report['local_repository_count']}")
    print(
        "  installation connection: not verified offline "
        "(confirm in-app before running)"
    )
    if readiness["blockers"]:
        print(f"  blockers: {', '.join(readiness['blockers'])}")
    print(f"  next step: {readiness['next_step']}")
    print("  note: this preflight never starts a provider read or write.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument(
        "--repos-file",
        default=DEFAULT_REPOS_FILE,
        help="Path to the offline local repository surface JSON file.",
    )
    args = parser.parse_args()

    report = _build_report(Path(args.repos_file))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
