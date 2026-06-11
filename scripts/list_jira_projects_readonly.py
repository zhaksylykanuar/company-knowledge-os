#!/usr/bin/env python
"""List Jira projects read-only and suggest knowledge-graph mapping (A3).

Live read-only call to ``/rest/api/3/project/search`` using the existing
FOS_JIRA_READONLY_* configuration. For every project the script suggests a
knowledge-graph entity by running the project key and name through the A2
alias resolution. No writes: no source events, no entities, no links, no
Jira mutations. The human types the live-readonly acknowledgement phrase.
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

ProjectFetcher = Callable[[str, Mapping[str, str]], bytes]

REQUIRED_ENV_KEYS = (
    "FOS_JIRA_READONLY_SITE",
    "FOS_JIRA_READONLY_USER",
    "FOS_JIRA_READONLY_TOKEN",
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live-readonly-apis", action="store_true")
    parser.add_argument(
        "--acknowledge-live-readonly-risk",
        help=f'Must be exactly "{LIVE_PROVIDER_EXECUTION_ACK}".',
    )
    parser.add_argument("--max-results", type=int, default=50)
    return parser.parse_args(argv)


def _default_fetcher(url: str, headers: Mapping[str, str]) -> bytes:
    api_request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(api_request, timeout=10) as response:
        return response.read(1_000_000)


def fetch_jira_projects(
    environ: Mapping[str, str],
    *,
    max_results: int = 50,
    fetcher: ProjectFetcher | None = None,
) -> list[dict[str, str]]:
    """Fetch [{key, name}] from Jira project search (read-only)."""

    site = smoke._normalize_jira_site_config(environ.get("FOS_JIRA_READONLY_SITE", ""))
    user = environ["FOS_JIRA_READONLY_USER"]
    api_key = environ["FOS_JIRA_READONLY_TOKEN"]
    bounded = min(max(int(max_results), 1), 100)

    url = (
        site
        + "/rest/api/3/project/search?maxResults="
        + urllib.parse.quote(str(bounded), safe="")
    )
    auth_value = base64.b64encode(f"{user}:{api_key}".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": "Basic " + auth_value,
        "Accept": "application/json",
    }
    body = (fetcher or _default_fetcher)(url, headers)

    data = json.loads(body.decode("utf-8"))
    values = data.get("values", []) if isinstance(data, Mapping) else data
    if not isinstance(values, list):
        raise ValueError("jira project search response is not a list")

    projects: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        key = value.get("key")
        name = value.get("name")
        if isinstance(key, str) and key:
            projects.append(
                {
                    "key": key,
                    "name": name if isinstance(name, str) else "",
                }
            )
    return projects


async def suggest_graph_mapping(
    projects: list[dict[str, str]],
) -> list[dict[str, str | None]]:
    """For each Jira project suggest a graph entity via A2 alias resolution."""

    from app.db.base import AsyncSessionLocal
    from app.services.entity_resolution import (
        ENTITY_TYPE_PROJECT,
        resolve_entities_in_text,
    )

    suggestions: list[dict[str, str | None]] = []
    async with AsyncSessionLocal() as session:
        for project in projects:
            probe_text = f"{project['key']} {project['name']}"
            try:
                resolved = await resolve_entities_in_text(
                    session,
                    probe_text,
                    entity_type=ENTITY_TYPE_PROJECT,
                )
            except Exception:
                resolved = []
            suggestions.append(
                {
                    "jira_key": project["key"],
                    "jira_name": project["name"],
                    "suggested_entity_id": resolved[0].entity_id if resolved else None,
                    "suggested_entity_name": (
                        resolved[0].canonical_name if resolved else None
                    ),
                    "matched_alias": resolved[0].matched_alias if resolved else None,
                }
            )
    return suggestions


def format_mapping_report(suggestions: list[dict[str, str | None]]) -> str:
    lines = [
        "Jira projects (read-only) -> knowledge graph mapping suggestions",
        "",
    ]
    if not suggestions:
        lines.append("(no projects visible to this Jira account)")
    for item in suggestions:
        if item["suggested_entity_id"]:
            suggestion = (
                f"-> {item['suggested_entity_id']} "
                f"({item['suggested_entity_name']}, alias «{item['matched_alias']}»)"
            )
        else:
            suggestion = "-> no graph match (add alias or skip)"
        lines.append(f"  {item['jira_key']:<12} {item['jira_name'][:48]:<48} {suggestion}")
    lines.extend(
        [
            "",
            "Next step: confirm the mapping; the A3 sync slice will persist it as",
            "entity attrs + entity_links and start syncing issues for mapped",
            "projects only.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from app.core.config import settings

    try:
        args = _parse_args(argv)
        prepare_script._assert_local_environment(
            settings=settings,
            environ=os.environ,
        )
    except prepare_script.PrepareBlockedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not args.allow_live_readonly_apis:
        print(
            "Error: live read-only Jira call requires --allow-live-readonly-apis",
            file=sys.stderr,
        )
        return 2
    if args.acknowledge_live_readonly_risk != LIVE_PROVIDER_EXECUTION_ACK:
        print("Error: live readonly acknowledgement phrase did not match", file=sys.stderr)
        return 2

    environment = load_local_connector_environment(environ=os.environ).environment
    missing = [key for key in REQUIRED_ENV_KEYS if not environment.get(key, "").strip()]
    if missing:
        print(f"Error: missing Jira readonly config: {', '.join(missing)}", file=sys.stderr)
        return 1

    try:
        projects = fetch_jira_projects(environment, max_results=args.max_results)
    except Exception as exc:
        print(f"Error: jira project search failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    suggestions = asyncio.run(suggest_graph_mapping(projects))
    print(format_mapping_report(suggestions), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
