#!/usr/bin/env python
"""List GitHub org repositories read-only and suggest graph mapping (A4).

Live read-only call to ``/orgs/{org}/repos`` using FOS_GITHUB_READONLY_TOKEN.
Each repository name is run through the A2 alias resolution to suggest a
knowledge-graph project. No writes anywhere. The human types the
live-readonly acknowledgement phrase.
"""

from __future__ import annotations

import argparse
import asyncio
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
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402

RepoFetcher = Callable[[str, Mapping[str, str]], bytes]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live-readonly-apis", action="store_true")
    parser.add_argument(
        "--acknowledge-live-readonly-risk",
        help=f'Must be exactly "{LIVE_PROVIDER_EXECUTION_ACK}".',
    )
    parser.add_argument(
        "--org",
        help="GitHub organization login. Default: FOS_GITHUB_TARGET_ORG from env.",
    )
    parser.add_argument("--max-results", type=int, default=100)
    return parser.parse_args(argv)


def _default_fetcher(url: str, headers: Mapping[str, str]) -> bytes:
    api_request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(api_request, timeout=15) as response:
        return response.read(2_000_000)


def fetch_github_org_repos(
    environ: Mapping[str, str],
    *,
    org: str,
    max_results: int = 100,
    fetcher: RepoFetcher | None = None,
) -> list[dict[str, Any]]:
    """Return [{name, archived, pushed_at}] for the organization (read-only)."""

    token = environ.get("FOS_GITHUB_READONLY_TOKEN", "")
    if not token.strip():
        raise ValueError("FOS_GITHUB_READONLY_TOKEN is not configured")
    bounded = min(max(int(max_results), 1), 100)

    url = (
        "https://api.github.com/orgs/"
        + urllib.parse.quote(org.strip(), safe="")
        + f"/repos?per_page={bounded}&type=all&sort=pushed"
    )
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "company-knowledge-os-readonly-inventory",
    }
    body = (fetcher or _default_fetcher)(url, headers)
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("github org repos response is not a list")

    repos: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            repos.append(
                {
                    "name": name,
                    "archived": item.get("archived") is True,
                    "pushed_at": (
                        item.get("pushed_at")
                        if isinstance(item.get("pushed_at"), str)
                        else None
                    ),
                }
            )
    return repos


async def suggest_repo_mapping(
    repos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Suggest a graph project per repository via A2 alias resolution."""

    from app.db.base import AsyncSessionLocal
    from app.services.entity_resolution import (
        ENTITY_TYPE_PROJECT,
        resolve_entities_in_text,
    )

    suggestions: list[dict[str, Any]] = []
    async with AsyncSessionLocal() as session:
        for repo in repos:
            try:
                resolved = await resolve_entities_in_text(
                    session,
                    str(repo["name"]),
                    entity_type=ENTITY_TYPE_PROJECT,
                )
            except Exception:
                resolved = []
            suggestions.append(
                {
                    "repo": repo["name"],
                    "archived": repo.get("archived", False),
                    "pushed_at": repo.get("pushed_at"),
                    "suggested_entity_id": resolved[0].entity_id if resolved else None,
                    "suggested_entity_name": (
                        resolved[0].canonical_name if resolved else None
                    ),
                }
            )
    return suggestions


def format_repo_report(org: str, suggestions: list[dict[str, Any]]) -> str:
    lines = [
        f"GitHub org repos (read-only, {org}) -> graph mapping suggestions",
        "",
    ]
    if not suggestions:
        lines.append("(no repositories visible to this token)")
    for item in suggestions:
        flags = " [archived]" if item["archived"] else ""
        pushed = f" pushed {item['pushed_at'][:10]}" if item.get("pushed_at") else ""
        if item["suggested_entity_id"]:
            suggestion = f"-> {item['suggested_entity_id']} ({item['suggested_entity_name']})"
        else:
            suggestion = "-> no graph match (add alias or skip)"
        lines.append(f"  {item['repo'][:40]:<40}{flags}{pushed}  {suggestion}")
    lines.extend(
        [
            "",
            "Next step: confirm which repos belong to which project; the A4 sync",
            "slice will persist the mapping and sync commits/PRs for mapped repos.",
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
            "Error: live read-only GitHub call requires --allow-live-readonly-apis",
            file=sys.stderr,
        )
        return 2
    if args.acknowledge_live_readonly_risk != LIVE_PROVIDER_EXECUTION_ACK:
        print("Error: live readonly acknowledgement phrase did not match", file=sys.stderr)
        return 2

    environment = load_local_connector_environment(environ=os.environ).environment
    org = (args.org or environment.get("FOS_GITHUB_TARGET_ORG", "")).strip()
    if not org:
        print(
            "Error: pass --org or set FOS_GITHUB_TARGET_ORG in .env",
            file=sys.stderr,
        )
        return 2

    try:
        repos = fetch_github_org_repos(
            environment, org=org, max_results=args.max_results
        )
    except Exception as exc:
        print(f"Error: github repo listing failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    suggestions = asyncio.run(suggest_repo_mapping(repos))
    print(format_repo_report(org, suggestions), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
