#!/usr/bin/env python
"""Sync PRs and commits of mapped repos into source events (A4, read GitHub only).

Live read-only GitHub calls per mapped repository; PRs and commits become
connector payloads persisted through the existing ingestion boundary,
idempotent by PR state+updated / commit sha. Jira issue keys are extracted
from titles, branches and commit messages into payload ``jira_keys``.

Example:
  uv run python scripts/sync_github_activity.py \\
    --allow-live-readonly-apis \\
    --acknowledge-live-readonly-risk "ALLOW LIVE PROVIDER EXECUTION" \\
    --confirm-sync "SYNC GITHUB ACTIVITY"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
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
from scripts.sync_jira_issues import ingest_issue_payloads  # noqa: E402

Fetcher = Callable[[str, Mapping[str, str]], bytes]

CONFIRM_SYNC_PHRASE = "SYNC GITHUB ACTIVITY"
JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")

PR_STATE_EVENT_TYPES = {
    "open": "github.pull_request.synchronized",
    "merged": "github.pull_request.merged",
    "closed": "github.pull_request.closed",
}


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
    parser.add_argument("--max-results", type=int, default=50)
    return parser.parse_args(argv)


def _default_fetcher(url: str, headers: Mapping[str, str]) -> bytes:
    api_request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(api_request, timeout=15) as response:
        return response.read(5_000_000)


def _github_get(
    environ: Mapping[str, str],
    path: str,
    *,
    fetcher: Fetcher | None = None,
) -> Any:
    import urllib.error

    token = environ.get("FOS_GITHUB_READONLY_TOKEN", "")
    if not token.strip():
        raise ValueError("FOS_GITHUB_READONLY_TOKEN is not configured")
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "company-knowledge-os-readonly-sync",
    }
    try:
        body = (fetcher or _default_fetcher)(
            "https://api.github.com" + path, headers
        )
    except urllib.error.HTTPError as exc:
        hints = {
            401: "token invalid or expired",
            403: "token lacks permission or rate limited",
            404: "repo not found or token lacks repo access (fine-grained scopes)",
            409: "repository is empty",
        }
        hint = hints.get(exc.code, "unexpected status")
        raise RuntimeError(
            f"HTTP {exc.code} on {path.split('?')[0]} ({hint})"
        ) from None
    return json.loads(body.decode("utf-8"))


def extract_jira_keys(*texts: Any) -> list[str]:
    keys: list[str] = []
    for text in texts:
        if isinstance(text, str):
            keys.extend(JIRA_KEY_RE.findall(text))
    return sorted(set(keys))


def build_pr_connector_payload(
    pr: Mapping[str, Any],
    *,
    org: str,
    repo: str,
) -> dict[str, Any] | None:
    number = pr.get("number")
    if not isinstance(number, int):
        return None
    merged = bool(pr.get("merged_at"))
    state = "merged" if merged else str(pr.get("state") or "open")
    updated = str(pr.get("updated_at") or "unknown")
    title = str(pr.get("title") or f"PR #{number}")
    branch = (
        pr.get("head", {}).get("ref") if isinstance(pr.get("head"), Mapping) else None
    )
    author = (
        pr.get("user", {}).get("login") if isinstance(pr.get("user"), Mapping) else None
    )
    jira_keys = extract_jira_keys(title, branch, pr.get("body"))

    return {
        "source_system": "github",
        "source_object_type": "pull_request",
        "source_object_id": f"{org}/{repo}/pull/{number}",
        "event_type": PR_STATE_EVENT_TYPES.get(state, PR_STATE_EVENT_TYPES["open"]),
        "idempotency_key": f"github-{repo}-pr-{number}-{state}-{updated}",
        "raw_object_ref": f"raw://github/{org}/{repo}/pulls/{number}/{updated}.json",
        "payload": {
            "source_object_type": "pull_request",
            "title": f"PR #{number}: {title}",
            "summary": f"state={state}; updated={updated}",
            "actor_external_id": author or "unknown",
            "source_url": str(
                pr.get("html_url")
                or f"https://github.com/{org}/{repo}/pull/{number}"
            ),
            "repo": f"{org}/{repo}",
            "state": state,
            "merged": merged,
            "branch": branch,
            "updated": updated,
            "review_requested": bool(pr.get("requested_reviewers")),
            "jira_keys": jira_keys,
        },
    }


def build_commit_connector_payload(
    commit: Mapping[str, Any],
    *,
    org: str,
    repo: str,
) -> dict[str, Any] | None:
    sha = commit.get("sha")
    if not isinstance(sha, str) or not sha:
        return None
    inner = commit.get("commit") if isinstance(commit.get("commit"), Mapping) else {}
    message = str(inner.get("message") or "")
    first_line = message.splitlines()[0] if message else sha[:12]
    author_data = inner.get("author") if isinstance(inner.get("author"), Mapping) else {}
    authored_at = str(author_data.get("date") or "unknown")
    author = str(author_data.get("name") or "unknown")
    jira_keys = extract_jira_keys(message)

    return {
        "source_system": "github",
        "source_object_type": "commit",
        "source_object_id": f"{org}/{repo}@{sha[:12]}",
        "event_type": "github.commit.pushed",
        "idempotency_key": f"github-{repo}-commit-{sha}",
        "raw_object_ref": f"raw://github/{org}/{repo}/commits/{sha}.json",
        "payload": {
            "source_object_type": "commit",
            "title": first_line[:200],
            "summary": f"sha={sha[:12]}; authored={authored_at}",
            "actor_external_id": author,
            "source_url": str(
                commit.get("html_url")
                or f"https://github.com/{org}/{repo}/commit/{sha}"
            ),
            "repo": f"{org}/{repo}",
            "sha": sha,
            "authored_at": authored_at,
            "jira_keys": jira_keys,
        },
    }


def fetch_repo_activity(
    environ: Mapping[str, str],
    *,
    org: str,
    repo: str,
    max_results: int = 50,
    fetcher: Fetcher | None = None,
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    bounded = min(max(int(max_results), 1), 100)
    quoted_org = urllib.parse.quote(org, safe="")
    quoted_repo = urllib.parse.quote(repo, safe="")
    prs = _github_get(
        environ,
        f"/repos/{quoted_org}/{quoted_repo}/pulls"
        f"?state=all&sort=updated&direction=desc&per_page={bounded}",
        fetcher=fetcher,
    )
    commits = _github_get(
        environ,
        f"/repos/{quoted_org}/{quoted_repo}/commits?per_page={bounded}",
        fetcher=fetcher,
    )
    prs_list = prs if isinstance(prs, list) else []
    commits_list = commits if isinstance(commits, list) else []
    return (
        [p for p in prs_list if isinstance(p, Mapping)],
        [c for c in commits_list if isinstance(c, Mapping)],
    )


async def _run(args: argparse.Namespace) -> int:
    from app.db.base import AsyncSessionLocal
    from app.services.github_graph_mapping import all_mapped_repos

    environment = load_local_connector_environment(environ=os.environ).environment

    async with AsyncSessionLocal() as session:
        repos = await all_mapped_repos(session)
    if not repos:
        print("Error: no mapped repos; run map_github_repos.py first", file=sys.stderr)
        return 1

    total_new = 0
    total_known = 0
    for item in repos:
        org, repo = item["org"], item["repo"]
        prs, commits = fetch_repo_activity(
            environment, org=org, repo=repo, max_results=args.max_results
        )
        payloads = [
            p
            for pr in prs
            if (p := build_pr_connector_payload(pr, org=org, repo=repo)) is not None
        ] + [
            p
            for commit in commits
            if (p := build_commit_connector_payload(commit, org=org, repo=repo))
            is not None
        ]
        counts = await ingest_issue_payloads(payloads)
        total_new += counts["source_events_created"]
        total_known += counts["already_present"]
        print(
            f"{org}/{repo}: prs={len(prs)} commits={len(commits)} "
            f"new={counts['source_events_created']} known={counts['already_present']}"
        )

    print(f"sync done: new={total_new} known={total_known}")
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
                "Error: live read-only GitHub call requires --allow-live-readonly-apis",
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
        detail = str(exc) or type(exc).__name__
        print(f"Error: github sync failed: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
