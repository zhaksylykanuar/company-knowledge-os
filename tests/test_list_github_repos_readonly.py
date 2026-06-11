from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from scripts.list_github_repos_readonly import (
    fetch_github_org_repos,
    format_repo_report,
    suggest_repo_mapping,
)
from tests.test_entity_resolution import _seed

ENVIRON = {"FOS_GITHUB_READONLY_TOKEN": "test-token-not-real"}


def _fake_fetcher(payload: object):
    calls: list[tuple[str, Mapping[str, str]]] = []

    def fetcher(url: str, headers: Mapping[str, str]) -> bytes:
        calls.append((url, dict(headers)))
        return json.dumps(payload).encode("utf-8")

    fetcher.calls = calls  # type: ignore[attr-defined]
    return fetcher


def test_fetch_parses_repo_names_and_flags() -> None:
    fetcher = _fake_fetcher(
        [
            {"name": "repo-alpha-api", "archived": False, "pushed_at": "2026-06-10T10:00:00Z"},
            {"name": "qaztwin", "archived": True, "pushed_at": None},
            {"no_name": True},
        ]
    )

    repos = fetch_github_org_repos(
        ENVIRON, org="example-org", max_results=500, fetcher=fetcher
    )

    assert [r["name"] for r in repos] == ["repo-alpha-api", "qaztwin"]
    assert repos[1]["archived"] is True
    url, headers = fetcher.calls[0]  # type: ignore[attr-defined]
    assert "/orgs/example-org/repos" in url
    assert "per_page=100" in url
    assert headers["Authorization"].startswith("Bearer ")


def test_fetch_requires_token() -> None:
    with pytest.raises(ValueError):
        fetch_github_org_repos({}, org="example-org", fetcher=_fake_fetcher([]))


async def test_suggestions_use_graph_aliases() -> None:
    await _seed()

    suggestions = await suggest_repo_mapping(
        [
            {"name": "qaztwin", "archived": False, "pushed_at": None},
            {"name": "repo-alpha-api", "archived": False, "pushed_at": None},
        ]
    )

    by_repo = {s["repo"]: s for s in suggestions}
    assert by_repo["qaztwin"]["suggested_entity_id"] == "project:qtwin"
    assert by_repo["repo-alpha-api"]["suggested_entity_id"] is None

    report = format_repo_report("example-org", suggestions)
    assert "qaztwin" in report
    assert "project:qtwin" in report
    assert "no graph match" in report
    assert "test-token-not-real" not in report


def test_empty_repo_list_renders_safe_report() -> None:
    assert "no repositories visible" in format_repo_report("example-org", [])
