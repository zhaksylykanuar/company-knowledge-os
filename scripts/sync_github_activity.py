#!/usr/bin/env python
"""GitHub activity sync compatibility helper.

The production direction is Source Control requests via
``scripts/run_source_requests.py``. Running this script records a sanitized
Source Control ``sync`` request for GitHub; it does not call GitHub or persist
provider payloads directly. The pure fetch/map helpers remain for
connector-adapter tests and migration work. Jira issue keys are extracted from
titles, branches and commit messages into payload ``jira_keys``.

Example:
  uv run python scripts/sync_github_activity.py \\
    --confirm-sync "SYNC GITHUB ACTIVITY" \\
    --request-key "github-sync-manual-YYYYMMDD"
"""

from __future__ import annotations

import argparse
import asyncio
import json
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

Fetcher = Callable[[str, Mapping[str, str]], bytes]

CONFIRM_SYNC_PHRASE = "SYNC GITHUB ACTIVITY"
LEGACY_SCRIPT_NAME = "scripts/sync_github_activity.py"
JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")

PR_STATE_EVENT_TYPES = {
    "open": "github.pull_request.synchronized",
    "merged": "github.pull_request.merged",
    "closed": "github.pull_request.closed",
}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-live-readonly-apis",
        action="store_true",
        help="Compatibility flag recorded as metadata only; this script no longer calls GitHub.",
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
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--request-key", help="Optional Source Control idempotency key.")
    parser.add_argument(
        "--requested-by",
        default="legacy_github_sync_script",
        help="Safe actor label for the Source Control request.",
    )
    return parser.parse_args(argv)


MAX_RESPONSE_BYTES = 5_000_000
_READ_CHUNK_BYTES = 65_536


def _read_response_body(response: Any, *, max_bytes: int = MAX_RESPONSE_BYTES) -> bytes:
    # A single read(amt) may return fewer bytes than available on the socket,
    # truncating large GitHub responses; read to EOF with a total-size cap.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(_READ_CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise RuntimeError(
                f"GitHub API response exceeds {max_bytes} bytes; "
                "lower --max-results"
            )
        chunks.append(chunk)


def _default_fetcher(url: str, headers: Mapping[str, str]) -> bytes:
    api_request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(api_request, timeout=15) as response:
        return _read_response_body(response)


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
    from app.services.source_control import ACTION_SYNC, request_source_action

    request_key = args.request_key or "legacy-github-sync"
    input_payload = {
        "legacy_script": LEGACY_SCRIPT_NAME,
        "max_results": max(1, min(int(args.max_results), 100)),
        "uses_configured_scope": True,
        "live_readonly_requested": bool(args.allow_live_readonly_apis),
        "live_readonly_ack_supplied": args.acknowledge_live_readonly_risk is not None,
    }
    async with AsyncSessionLocal() as session:
        request = await request_source_action(
            session,
            source_type="github",
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
        detail = str(exc) or type(exc).__name__
        print(f"Error: github sync request failed: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
