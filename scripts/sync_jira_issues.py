#!/usr/bin/env python
"""Sync Jira issues of mapped projects into source events (A3, read Jira only).

Live read-only Jira search per mapped project key; each issue becomes a
connector payload persisted through the existing raw-event-first ingestion
boundary (IngestedEvent -> SourceEvent), idempotent by issue+updated
timestamp. Writes only ingestion rows; never mutates Jira.

Example:
  uv run python scripts/sync_jira_issues.py \\
    --allow-live-readonly-apis \\
    --acknowledge-live-readonly-risk "ALLOW LIVE PROVIDER EXECUTION" \\
    --confirm-sync "SYNC JIRA ISSUES"
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.local_connector_env import (  # noqa: E402
    load_local_connector_environment,
)
from app.services.provider_execution_guard import (  # noqa: E402
    LIVE_PROVIDER_EXECUTION_ACK,
)
from scripts import check_external_connectors_readonly as smoke  # noqa: E402
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402

IssueFetcher = Callable[[str, Mapping[str, str]], bytes]

CONFIRM_SYNC_PHRASE = "SYNC JIRA ISSUES"
ISSUE_FIELDS = "summary,status,assignee,updated,created,duedate,priority,issuetype"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live-readonly-apis", action="store_true")
    parser.add_argument(
        "--acknowledge-live-readonly-risk",
        help=f'Must be exactly "{LIVE_PROVIDER_EXECUTION_ACK}".',
    )
    parser.add_argument(
        "--confirm-sync",
        required=True,
        help=f'Must be exactly "{CONFIRM_SYNC_PHRASE}".',
    )
    parser.add_argument(
        "--jira-key",
        action="append",
        help="Jira project key to sync (repeatable). Default: all mapped keys.",
    )
    parser.add_argument("--max-results", type=int, default=50)
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


async def _run(args: argparse.Namespace) -> int:
    from app.db.base import AsyncSessionLocal
    from app.services.jira_graph_mapping import all_mapped_jira_keys

    environment = load_local_connector_environment(environ=os.environ).environment

    if args.jira_key:
        keys = [key.strip().upper() for key in args.jira_key if key.strip()]
    else:
        async with AsyncSessionLocal() as session:
            keys = sorted((await all_mapped_jira_keys(session)))
    if not keys:
        print("Error: no mapped jira keys; run map_jira_projects.py first", file=sys.stderr)
        return 1

    total = {"source_events_created": 0, "already_present": 0}
    for key in keys:
        site, issues = fetch_jira_issues(
            environment,
            jira_key=key,
            max_results=args.max_results,
        )
        payloads = [
            payload
            for issue in issues
            if (
                payload := build_issue_connector_payload(
                    issue, site=site, jira_project_key=key
                )
            )
            is not None
        ]
        counts = await ingest_issue_payloads(payloads)
        total["source_events_created"] += counts["source_events_created"]
        total["already_present"] += counts["already_present"]
        print(
            f"{key}: issues={len(payloads)} "
            f"new_source_events={counts['source_events_created']} "
            f"already_present={counts['already_present']}"
        )

    print(
        "sync done: "
        f"new={total['source_events_created']} known={total['already_present']}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    from app.core.config import settings

    try:
        args = _parse_args(argv)
        if args.confirm_sync != CONFIRM_SYNC_PHRASE:
            print("Error: confirm_sync phrase did not match", file=sys.stderr)
            return 2
        if not args.allow_live_readonly_apis:
            print(
                "Error: live read-only Jira call requires --allow-live-readonly-apis",
                file=sys.stderr,
            )
            return 2
        if args.acknowledge_live_readonly_risk != LIVE_PROVIDER_EXECUTION_ACK:
            print(
                "Error: live readonly acknowledgement phrase did not match",
                file=sys.stderr,
            )
            return 2
        prepare_script._assert_local_environment(
            settings=settings,
            environ=os.environ,
        )
        return asyncio.run(_run(args))
    except prepare_script.PrepareBlockedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: jira sync failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
