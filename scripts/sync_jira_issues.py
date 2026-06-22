#!/usr/bin/env python
"""Jira sync compatibility helper.

The production path is Source Control requests via
``scripts/run_source_requests.py``. Running this script records a sanitized
Source Control ``sync`` request for Jira; it does not call Jira or persist
provider payloads directly. The pure fetch/map/ingest helper functions remain
for connector-adapter tests and migration work.

Example:
  uv run python scripts/sync_jira_issues.py \\
    --confirm-sync "SYNC JIRA ISSUES" \\
    --request-key "jira-sync-manual-YYYYMMDD"
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import check_external_connectors_readonly as smoke  # noqa: E402

IssueFetcher = Callable[[str, Mapping[str, str]], bytes]

CONFIRM_SYNC_PHRASE = "SYNC JIRA ISSUES"
ISSUE_FIELDS = "summary,status,assignee,updated,created,duedate,priority,issuetype"
LEGACY_SCRIPT_NAME = "scripts/sync_jira_issues.py"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-live-readonly-apis",
        action="store_true",
        help="Compatibility flag recorded as metadata only; this script no longer calls Jira.",
    )
    parser.add_argument(
        "--acknowledge-live-readonly-risk",
        help="Compatibility acknowledgement; only whether it was supplied is recorded.",
    )
    parser.add_argument(
        "--confirm-sync",
        required=True,
        help=f'Must be exactly "{CONFIRM_SYNC_PHRASE}".',
    )
    parser.add_argument(
        "--jira-key",
        action="append",
        help="Jira project key to request (repeatable). Values are recorded as scope names.",
    )
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--request-key", help="Optional Source Control idempotency key.")
    parser.add_argument(
        "--requested-by",
        default="legacy_jira_sync_script",
        help="Safe actor label for the Source Control request.",
    )
    return parser.parse_args(argv)


def _default_fetcher(url: str, headers: Mapping[str, str]) -> bytes:
    api_request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(api_request, timeout=15) as response:
        return response.read(5_000_000)


def fetch_jira_issues(
    environ: Mapping[str, str],
    *,
    jira_key: str,
    max_results: int = 50,
    fetcher: IssueFetcher | None = None,
) -> tuple[str, list[Mapping[str, Any]]]:
    """Return (site, issues) from a read-only Jira search for one project."""

    site = smoke._normalize_jira_site_config(environ.get("FOS_JIRA_READONLY_SITE", ""))
    user = environ["FOS_JIRA_READONLY_USER"]
    api_key = environ["FOS_JIRA_READONLY_TOKEN"]
    bounded = min(max(int(max_results), 1), 100)

    query = urllib.parse.urlencode(
        {
            "jql": f"project = {jira_key} ORDER BY updated DESC",
            "maxResults": str(bounded),
            "fields": ISSUE_FIELDS,
        }
    )
    url = f"{site}/rest/api/3/search/jql?{query}"
    auth_value = base64.b64encode(f"{user}:{api_key}".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": "Basic " + auth_value,
        "Accept": "application/json",
    }
    body = (fetcher or _default_fetcher)(url, headers)
    data = json.loads(body.decode("utf-8"))
    issues = data.get("issues", []) if isinstance(data, Mapping) else []
    if not isinstance(issues, list):
        raise ValueError("jira issue search response is not a list")
    return site, [issue for issue in issues if isinstance(issue, Mapping)]


def _field(issue: Mapping[str, Any], *path: str) -> str | None:
    value: Any = issue
    for part in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value if isinstance(value, str) and value else None


def build_issue_connector_payload(
    issue: Mapping[str, Any],
    *,
    site: str,
    jira_project_key: str,
) -> dict[str, Any] | None:
    """Map a Jira search issue into the connector-ingestion payload contract."""

    issue_key = issue.get("key")
    if not isinstance(issue_key, str) or not issue_key:
        return None
    updated = _field(issue, "fields", "updated") or "unknown"
    summary = _field(issue, "fields", "summary") or issue_key
    status = _field(issue, "fields", "status", "name")
    assignee = _field(issue, "fields", "assignee", "displayName")
    parts = [p for p in (
        f"status={status}" if status else None,
        f"assignee={assignee}" if assignee else None,
        f"updated={updated}",
    ) if p]

    return {
        "source_system": "jira",
        "source_object_type": "issue",
        "source_object_id": issue_key,
        "event_type": "jira.issue.updated",
        "idempotency_key": f"jira-{issue_key.lower()}-updated-{updated}",
        "raw_object_ref": f"raw://jira/issues/{issue_key}/{updated}.json",
        "payload": {
            "source_object_type": "issue",
            "title": f"[{issue_key}] {summary}",
            "summary": "; ".join(parts),
            "actor_external_id": assignee or "unassigned",
            "source_url": f"{site}/browse/{issue_key}",
            "jira_project_key": jira_project_key,
            "status": status,
            "updated": updated,
            "duedate": _field(issue, "fields", "duedate"),
            "priority": _field(issue, "fields", "priority", "name"),
            "issuetype": _field(issue, "fields", "issuetype", "name"),
        },
    }


async def ingest_issue_payloads(
    payloads: list[dict[str, Any]],
) -> dict[str, int]:
    """Persist payloads through the ingestion boundary, idempotently."""

    from app.db.base import AsyncSessionLocal
    from app.integrations.connector_ingestion import (
        ingest_connector_payload_to_source_event,
    )

    created = 0
    seen = 0
    async with AsyncSessionLocal() as session:
        for payload in payloads:
            result = await ingest_connector_payload_to_source_event(session, payload)
            if result.source_event_created:
                created += 1
            else:
                seen += 1
        await session.commit()
    return {"source_events_created": created, "already_present": seen}


def _requested_jira_keys(args: argparse.Namespace) -> list[str]:
    return sorted({key.strip().upper() for key in (args.jira_key or []) if key.strip()})


async def _run(args: argparse.Namespace) -> int:
    from app.db.base import AsyncSessionLocal
    from app.services.source_control import ACTION_SYNC, request_source_action

    keys = _requested_jira_keys(args)
    request_key = args.request_key or "legacy-jira-sync"
    input_payload = {
        "legacy_script": LEGACY_SCRIPT_NAME,
        "max_results": max(1, min(int(args.max_results), 100)),
        "requested_jira_keys": keys,
        "requested_jira_key_count": len(keys),
        "uses_configured_scope": not bool(keys),
        "live_readonly_requested": bool(args.allow_live_readonly_apis),
        "live_readonly_ack_supplied": args.acknowledge_live_readonly_risk is not None,
    }
    async with AsyncSessionLocal() as session:
        request = await request_source_action(
            session,
            source_type="jira",
            action_type=ACTION_SYNC,
            request_key=request_key,
            requested_by=args.requested_by,
            input_payload=input_payload,
        )
        await session.commit()
    print(json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if args.confirm_sync != CONFIRM_SYNC_PHRASE:
            print("Error: confirm_sync phrase did not match", file=sys.stderr)
            return 2
        return asyncio.run(_run(args))
    except Exception as exc:
        print(
            f"Error: jira sync request failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
