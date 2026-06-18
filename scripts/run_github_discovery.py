#!/usr/bin/env python
"""Read-only GitHub discovery runner.

GET-only. Writes the full export to ``.local/discovery/github/<timestamp>/`` and
prints only a sanitized, numeric summary. Live calls require
``--confirm-run "RUN GITHUB DISCOVERY"``; without it (or without credentials) the
runner does a credential preflight only and makes no network call.

    uv run python scripts/run_github_discovery.py --confirm-run "RUN GITHUB DISCOVERY"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.discovery_core import (  # noqa: E402
    SOURCE_GITHUB,
    assert_summary_safe,
    credential_preflight,
    load_discovery_environment,
    run_dir,
    write_run_artifact,
    write_run_text,
)
from app.services.github_discovery import (  # noqa: E402
    GET,
    GitHubDiscoveryTransportError,
    GitHubReadOnlyDiscoveryClient,
    collect_github_discovery,
    render_github_repo_audit,
    scrub_for_save,
    stdout_summary,
    summarize_github_discovery,
)
from app.services.secret_patterns import contains_secret_value  # noqa: E402

CONFIRM_TOKEN = "RUN GITHUB DISCOVERY"
STATUS_OK = "ok"
STATUS_PREFLIGHT_ONLY = "preflight_only"
STATUS_CREDENTIALS_MISSING = "credentials_missing"
REPORT_KIND = "github_discovery_run"
API_BASE = "https://api.github.com"


def _http_get_transport(env: Mapping[str, str], *, timeout: float = 20.0):
    """Build a GET-only httpx transport. Any non-GET method is refused."""

    import httpx

    token = env.get("FOS_GITHUB_READONLY_TOKEN", "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    def transport(method: str, path: str, params: Mapping[str, Any]) -> Any:
        if method != GET:
            raise GitHubDiscoveryTransportError("non_get_method_blocked")
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(API_BASE + path, headers=headers, params=dict(params))
            resp.raise_for_status()
            return resp.json()

    return transport


def run(
    *,
    confirm_run: str | None,
    root: Path,
    environ: Mapping[str, str],
    page_cap: int = 10,
    timestamp: str | None = None,
    transport_factory: Any = None,
) -> dict[str, Any]:
    env = load_discovery_environment(root=root, base_environ=environ)
    pre = credential_preflight(SOURCE_GITHUB, env)
    base: dict[str, Any] = {
        "report_kind": REPORT_KIND,
        "confirmed": confirm_run == CONFIRM_TOKEN,
        "credentials": pre.as_dict(),
    }

    if confirm_run != CONFIRM_TOKEN:
        base["status"] = STATUS_PREFLIGHT_ONLY
        base["note"] = 'pass --confirm-run "RUN GITHUB DISCOVERY" to make read-only GET calls'
        return assert_summary_safe(base)

    if not pre.ready:
        base["status"] = STATUS_CREDENTIALS_MISSING
        return assert_summary_safe(base)

    factory = transport_factory or _http_get_transport
    client = GitHubReadOnlyDiscoveryClient(
        factory(env), org=env.get("FOS_GITHUB_TARGET_ORG", ""), page_cap=page_cap
    )
    raw = collect_github_discovery(client)
    summary = summarize_github_discovery(raw)

    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = run_dir(SOURCE_GITHUB, root=root, timestamp=stamp)

    artifacts = [
        write_run_artifact(
            root=root,
            run_directory=directory,
            name="organization",
            records=raw.organization,
            subdir="raw",
            scrub=scrub_for_save,
        ).as_dict(),
        write_run_artifact(
            root=root,
            run_directory=directory,
            name="repos",
            records=raw.repos,
            subdir="raw",
            scrub=scrub_for_save,
        ).as_dict(),
        write_run_artifact(
            root=root,
            run_directory=directory,
            name="summary",
            records=summary,
            scrub=scrub_for_save,
        ).as_dict(),
    ]
    audit_md = render_github_repo_audit(summary)
    if contains_secret_value(audit_md):
        audit_md = "# GitHub Repo Audit\n\nWithheld: secret-shaped content detected.\n"
    artifacts.append(
        write_run_text(
            root=root, run_directory=directory, name="github-repo-audit", text=audit_md
        ).as_dict()
    )

    result = {
        "report_kind": REPORT_KIND,
        "status": STATUS_OK,
        "confirmed": True,
        "credentials": pre.as_dict(),
        "run_dir": _safe_run_dir(directory, root),
        **stdout_summary(summary),
        "artifacts": artifacts,
    }
    return assert_summary_safe(result)


def _safe_run_dir(directory: Path, root: Path) -> str:
    try:
        return str(directory.relative_to(Path(root)))
    except ValueError:
        return str(directory)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-run", default=None)
    parser.add_argument("--page-cap", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run(
        confirm_run=args.confirm_run,
        root=REPO_ROOT,
        environ=dict(os.environ),
        page_cap=args.page_cap,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {STATUS_OK, STATUS_PREFLIGHT_ONLY} else 2


if __name__ == "__main__":
    raise SystemExit(main())
