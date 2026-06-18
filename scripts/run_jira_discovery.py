#!/usr/bin/env python
"""Read-only Jira discovery runner.

GET-only. Writes the full export to ``.local/discovery/jira/<timestamp>/`` and
prints only a sanitized, numeric summary. Live calls require
``--confirm-run "RUN JIRA DISCOVERY"``; without it (or without credentials) the
runner does a credential preflight only and makes no network call.

    uv run python scripts/run_jira_discovery.py --confirm-run "RUN JIRA DISCOVERY"
"""

from __future__ import annotations

import argparse
import base64
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
    SOURCE_JIRA,
    assert_summary_safe,
    credential_preflight,
    load_discovery_environment,
    run_dir,
    write_run_artifact,
    write_run_text,
)
from app.services.jira_discovery import (  # noqa: E402
    GET,
    EP_BOARDS,
    EP_COMPONENTS,
    EP_FIELDS,
    EP_ISSUE_TYPES,
    EP_ISSUES,
    EP_LABELS,
    EP_PERMISSIONS,
    EP_PROJECTS,
    EP_STATUSES,
    EP_WORKFLOWS,
    JiraDiscoveryTransportError,
    JiraReadOnlyDiscoveryClient,
    collect_jira_discovery,
    render_current_jira_audit,
    scrub_for_save,
    summarize_jira_discovery,
)
from app.services.secret_patterns import contains_secret_value  # noqa: E402

CONFIRM_TOKEN = "RUN JIRA DISCOVERY"
STATUS_OK = "ok"
STATUS_PREFLIGHT_ONLY = "preflight_only"
STATUS_CREDENTIALS_MISSING = "credentials_missing"
REPORT_KIND = "jira_discovery_run"


def _normalize_site(site: str) -> str:
    site = site.strip().rstrip("/")
    if not site:
        return ""
    if not site.startswith(("http://", "https://")):
        site = "https://" + site
    return site


def _http_get_transport(env: Mapping[str, str], *, timeout: float = 20.0):
    """Build a GET-only httpx transport. Any non-GET method is refused."""

    import httpx

    site = _normalize_site(env.get("FOS_JIRA_READONLY_SITE", ""))
    user = env.get("FOS_JIRA_READONLY_USER", "")
    token = env.get("FOS_JIRA_READONLY_TOKEN", "")
    auth = base64.b64encode(f"{user}:{token}".encode("utf-8")).decode("ascii")
    headers = {"Authorization": "Basic " + auth, "Accept": "application/json"}

    def transport(method: str, path: str, params: Mapping[str, Any]) -> Any:
        if method != GET:
            raise JiraDiscoveryTransportError("non_get_method_blocked")
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(site + path, headers=headers, params=dict(params))
            resp.raise_for_status()
            return resp.json()

    return transport


def _raw_items(raw) -> list[tuple[str, Any]]:
    return [
        (EP_PROJECTS, raw.projects),
        (EP_BOARDS, raw.boards),
        (EP_ISSUE_TYPES, raw.issue_types),
        (EP_FIELDS, raw.fields),
        (EP_STATUSES, raw.statuses),
        (EP_WORKFLOWS, raw.workflows),
        (EP_LABELS, raw.labels),
        (EP_COMPONENTS, raw.components),
        (EP_PERMISSIONS, raw.permissions),
        (EP_ISSUES, raw.issues),
    ]


def _stdout_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Numeric/class-only view safe for stdout — no project/issue names."""

    issue = summary.get("issue_summary", {})
    return {
        "counts": summary.get("counts", {}),
        "endpoint_status": summary.get("endpoint_status", {}),
        "issue_summary_numeric": {
            "stale_issue_count": issue.get("stale_issue_count", 0),
            "unassigned_issue_count": issue.get("unassigned_issue_count", 0),
            "distinct_status_count": len(issue.get("status_distribution", {})),
            "distinct_type_count": len(issue.get("type_distribution", {})),
            "distinct_project_count": len(issue.get("project_usage", {})),
        },
        "mess_indicators": summary.get("mess_indicators", {}),
    }


def run(
    *,
    confirm_run: str | None,
    root: Path,
    environ: Mapping[str, str],
    page_cap: int = 20,
    max_issues: int = 500,
    timestamp: str | None = None,
    transport_factory: Any = None,
) -> dict[str, Any]:
    env = load_discovery_environment(root=root, base_environ=environ)
    pre = credential_preflight(SOURCE_JIRA, env)
    base: dict[str, Any] = {
        "report_kind": REPORT_KIND,
        "confirmed": confirm_run == CONFIRM_TOKEN,
        "credentials": pre.as_dict(),
    }

    if confirm_run != CONFIRM_TOKEN:
        base["status"] = STATUS_PREFLIGHT_ONLY
        base["note"] = 'pass --confirm-run "RUN JIRA DISCOVERY" to make read-only GET calls'
        return assert_summary_safe(base)

    if not pre.ready:
        base["status"] = STATUS_CREDENTIALS_MISSING
        return assert_summary_safe(base)

    factory = transport_factory or _http_get_transport
    client = JiraReadOnlyDiscoveryClient(factory(env), page_cap=page_cap)
    raw = collect_jira_discovery(client)
    raw.issues = raw.issues[:max_issues]
    summary = summarize_jira_discovery(raw)

    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = run_dir(SOURCE_JIRA, root=root, timestamp=stamp)

    artifacts = [
        write_run_artifact(
            root=root,
            run_directory=directory,
            name=label,
            records=records,
            subdir="raw",
            scrub=scrub_for_save,
        ).as_dict()
        for label, records in _raw_items(raw)
    ]
    artifacts.append(
        write_run_artifact(
            root=root,
            run_directory=directory,
            name="summary",
            records=summary,
            scrub=scrub_for_save,
        ).as_dict()
    )
    audit_md = render_current_jira_audit(summary)
    if contains_secret_value(audit_md):
        audit_md = "# Current Jira Audit\n\nWithheld: secret-shaped content detected.\n"
    artifacts.append(
        write_run_text(
            root=root, run_directory=directory, name="current-jira-audit", text=audit_md
        ).as_dict()
    )

    result = {
        "report_kind": REPORT_KIND,
        "status": STATUS_OK,
        "confirmed": True,
        "credentials": pre.as_dict(),
        "run_dir": _safe_run_dir(directory, root),
        **_stdout_summary(summary),
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
    parser.add_argument("--page-cap", type=int, default=20)
    parser.add_argument("--max-issues", type=int, default=500)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run(
        confirm_run=args.confirm_run,
        root=REPO_ROOT,
        environ=dict(os.environ),
        page_cap=args.page_cap,
        max_issues=args.max_issues,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {STATUS_OK, STATUS_PREFLIGHT_ONLY} else 2


if __name__ == "__main__":
    raise SystemExit(main())
