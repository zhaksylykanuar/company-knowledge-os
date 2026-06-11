from __future__ import annotations

import json
from collections.abc import Mapping

from scripts.list_jira_projects_readonly import (
    fetch_jira_projects,
    format_mapping_report,
    suggest_graph_mapping,
)
from tests.test_entity_resolution import _seed

ENVIRON = {
    "FOS_JIRA_READONLY_SITE": "example-team.atlassian.net",
    "FOS_JIRA_READONLY_USER": "reader@example.invalid",
    "FOS_JIRA_READONLY_TOKEN": "test-token-not-real",
}


def _fake_fetcher(payload: object):
    calls: list[tuple[str, Mapping[str, str]]] = []

    def fetcher(url: str, headers: Mapping[str, str]) -> bytes:
        calls.append((url, headers))
        return json.dumps(payload).encode("utf-8")

    fetcher.calls = calls  # type: ignore[attr-defined]
    return fetcher


def test_fetch_parses_keys_and_names_and_bounds_results() -> None:
    fetcher = _fake_fetcher(
        {
            "values": [
                {"key": "SSAP", "name": "SSAP Delivery"},
                {"key": "QTW", "name": "qTwin Platform"},
                {"key": "OPS", "name": "Internal Ops"},
                {"name": "broken row without key"},
            ]
        }
    )

    projects = fetch_jira_projects(ENVIRON, max_results=500, fetcher=fetcher)

    assert projects == [
        {"key": "SSAP", "name": "SSAP Delivery"},
        {"key": "QTW", "name": "qTwin Platform"},
        {"key": "OPS", "name": "Internal Ops"},
    ]
    url, headers = fetcher.calls[0]  # type: ignore[attr-defined]
    assert "maxResults=100" in url  # bounded
    assert "project/search" in url
    assert headers["Authorization"].startswith("Basic ")


async def test_suggestions_use_graph_aliases() -> None:
    await _seed()

    suggestions = await suggest_graph_mapping(
        [
            {"key": "SSAP", "name": "SSAP Delivery"},
            {"key": "QTW", "name": "qTwin Platform"},
            {"key": "OPS", "name": "Internal Ops"},
        ]
    )

    by_key = {item["jira_key"]: item for item in suggestions}
    assert by_key["SSAP"]["suggested_entity_id"] == "project:ssap"
    assert by_key["QTW"]["suggested_entity_id"] == "project:qtwin"
    assert by_key["OPS"]["suggested_entity_id"] is None

    report = format_mapping_report(suggestions)
    assert "SSAP" in report
    assert "project:ssap" in report
    assert "no graph match" in report
    assert "test-token-not-real" not in report


def test_empty_project_list_renders_safe_report() -> None:
    report = format_mapping_report([])
    assert "no projects visible" in report
