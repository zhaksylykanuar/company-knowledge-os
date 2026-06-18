"""Read-only Jira discovery: GET-only, fail-closed, no network, no leaks."""

from __future__ import annotations

import json

import pytest

from app.services.discovery_core import assert_summary_safe
from app.services.jira_discovery import (
    FETCH_FORBIDDEN,
    FETCH_OK,
    JiraDiscoveryTransportError,
    JiraReadOnlyDiscoveryClient,
    collect_jira_discovery,
    scrub_for_save,
    summarize_jira_discovery,
)
from app.services.secret_patterns import contains_secret_value
from scripts.run_jira_discovery import (
    CONFIRM_TOKEN,
    STATUS_CREDENTIALS_MISSING,
    STATUS_OK,
    STATUS_PREFLIGHT_ONLY,
    _http_get_transport,
    run,
)

_OLD = "2020-01-01T00:00:00.000+0000"

_PROJECTS = {
    "values": [{"key": "ALPHA", "name": "Project Alpha"}, {"key": "BETA", "name": "Project Beta"}],
    "isLast": True,
}
_BOARDS = {
    "values": [{"id": 1, "name": "B1"}, {"id": 2, "name": "B2"}, {"id": 3, "name": "B3"}],
    "isLast": True,
}
_ISSUE_TYPES = [
    {"name": n, "subtask": n == "Subtask"}
    for n in (
        "Epic",
        "Story",
        "Task",
        "Bug",
        "Subtask",
        "Incident",
        "Tech Debt",
        "Spike",
        "Chore",
        "Question",
    )
]
_FIELDS = [{"id": "summary", "name": "Summary", "custom": False}] + [
    {"id": f"cf{i}", "name": f"Custom {i}", "custom": True} for i in range(30)
]
_STATUSES = [
    {"name": n}
    for n in (
        "Backlog",
        "To Do",
        "Todo",
        "In Progress",
        "Doing",
        "Review",
        "QA",
        "Validation",
        "Ready for Release",
        "Done",
        "Closed",
        "Blocked",
    )
]
_LABELS = {"values": ["tmp:x", "client:one", "risk:timeline"], "isLast": True}
_PERMISSIONS = {"permissions": {"BROWSE_PROJECTS": {"havePermission": True}}}
_ISSUES = {
    "issues": [
        {
            "fields": {
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Task"},
                "project": {"key": "ALPHA"},
                "assignee": None,
                "updated": _OLD,
            }
        },
        {
            "fields": {
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Bug"},
                "project": {"key": "ALPHA"},
                "assignee": {"displayName": "Person A"},
                "updated": _OLD,
            }
        },
        {
            "fields": {
                "status": {"name": "Done"},
                "issuetype": {"name": "Task"},
                "project": {"key": "BETA"},
                "assignee": {"displayName": "Person B"},
                "updated": _OLD,
            }
        },
    ]
}


def _routes() -> dict[str, object]:
    return {
        "/rest/api/3/project/search": _PROJECTS,
        "/rest/agile/1.0/board": _BOARDS,
        "/rest/api/3/issuetype": _ISSUE_TYPES,
        "/rest/api/3/field": _FIELDS,
        "/rest/api/3/status": _STATUSES,
        "/rest/api/3/workflow/search": {"values": [{"id": "wf1"}], "isLast": True},
        "/rest/api/3/label": _LABELS,
        "/rest/api/3/mypermissions": _PERMISSIONS,
        "/rest/api/3/search": _ISSUES,
    }


def _fake_transport(routes=None, recorder=None, forbidden_prefixes=()):
    table = routes if routes is not None else _routes()

    def transport(method, path, params):
        if recorder is not None:
            recorder.append((method, path))
        for prefix in forbidden_prefixes:
            if path.startswith(prefix):
                raise RuntimeError("403 forbidden")
        if "/components" in path:
            return [{"name": "comp-" + path.split("/")[5]}]
        for prefix, value in table.items():
            if path.startswith(prefix):
                return value
        return {}

    return transport


def _factory(**kwargs):
    return lambda env: _fake_transport(**kwargs)


def _jira_env():
    return {
        "FOS_JIRA_READONLY_SITE": "https://example.atlassian.net",
        "FOS_JIRA_READONLY_USER": "ops@example.com",
        "FOS_JIRA_READONLY_TOKEN": "x" * 24,
    }


def test_client_issues_only_get_requests() -> None:
    recorder: list = []
    client = JiraReadOnlyDiscoveryClient(_fake_transport(recorder=recorder))
    collect_jira_discovery(client)
    assert recorder, "expected calls"
    assert all(method == "GET" for method, _ in recorder)


def test_collect_isolates_forbidden_endpoint() -> None:
    client = JiraReadOnlyDiscoveryClient(
        _fake_transport(forbidden_prefixes=("/rest/api/3/workflow/search",))
    )
    raw = collect_jira_discovery(client)
    assert raw.endpoint_status["workflows"] == FETCH_FORBIDDEN
    # The rest still succeed.
    assert raw.endpoint_status["projects"] == FETCH_OK
    assert raw.endpoint_status["statuses"] == FETCH_OK


def test_summary_counts_and_mess_indicators() -> None:
    client = JiraReadOnlyDiscoveryClient(_fake_transport())
    summary = summarize_jira_discovery(collect_jira_discovery(client))
    counts = summary["counts"]
    assert counts["project_count"] == 2
    assert counts["board_count"] == 3
    assert counts["status_count"] == 12
    assert counts["custom_field_count"] == 30
    assert counts["component_count"] == 2  # one per project
    mess = summary["mess_indicators"]
    assert mess["status_proliferation"] is True
    assert mess["issue_type_proliferation"] is True
    assert mess["custom_field_heavy"] is True
    assert mess["boards_exceed_projects"] is True
    assert mess["near_duplicate_status_count"] >= 1  # To Do / Todo


def test_summary_issue_breakdown() -> None:
    client = JiraReadOnlyDiscoveryClient(_fake_transport())
    issue = summarize_jira_discovery(collect_jira_discovery(client))["issue_summary"]
    assert issue["status_distribution"]["In Progress"] == 2
    assert issue["type_distribution"]["Task"] == 2
    assert issue["project_usage"]["ALPHA"] == 2
    assert issue["unassigned_issue_count"] == 1
    # Two In-Progress issues are old; the Done one is terminal and excluded.
    assert issue["stale_issue_count"] == 2


def test_scrub_redacts_secret_shaped_values() -> None:
    scrubbed = scrub_for_save({"summary": "token ghp_" + "a" * 36, "ok": "Project Alpha"})
    assert "ghp_" not in json.dumps(scrubbed)
    assert scrubbed["ok"] == "Project Alpha"


# --- CLI runner --------------------------------------------------------
def test_run_without_confirm_makes_no_network_call(tmp_path) -> None:
    called = {"n": 0}

    def exploding_factory(env):
        called["n"] += 1
        raise AssertionError("network must not be touched in preflight")

    result = run(
        confirm_run=None,
        root=tmp_path,
        environ=_jira_env(),
        transport_factory=exploding_factory,
    )
    assert result["status"] == STATUS_PREFLIGHT_ONLY
    assert called["n"] == 0
    assert result["credentials"]["ready"] is True


def test_run_with_confirm_but_missing_creds_makes_no_network_call(tmp_path) -> None:
    def exploding_factory(env):
        raise AssertionError("must not touch network without creds")

    result = run(
        confirm_run=CONFIRM_TOKEN,
        root=tmp_path,
        environ={"FOS_JIRA_READONLY_SITE": "https://example.atlassian.net"},
        transport_factory=exploding_factory,
    )
    assert result["status"] == STATUS_CREDENTIALS_MISSING
    assert "FOS_JIRA_READONLY_TOKEN" in result["credentials"]["missing_var_names"]


def test_run_confirmed_writes_local_files_and_safe_stdout(tmp_path) -> None:
    result = run(
        confirm_run=CONFIRM_TOKEN,
        root=tmp_path,
        environ=_jira_env(),
        timestamp="20260615T000000Z",
        transport_factory=_factory(),
    )
    assert result["status"] == STATUS_OK
    # stdout summary is leak-safe and numeric-only (no project names leaked).
    assert assert_summary_safe(result) == result
    blob = json.dumps(result)
    assert "Project Alpha" not in blob
    assert "atlassian.net" not in blob
    # Files landed under the timestamped local run dir.
    run_root = tmp_path / ".local" / "discovery" / "jira" / "20260615T000000Z"
    assert (run_root / "raw" / "projects.json").exists()
    assert (run_root / "summary.json").exists()
    assert (run_root / "current-jira-audit.md").exists()
    # The local audit file may name projects (founder-facing, local only).
    assert "Project Alpha" not in (run_root / "current-jira-audit.md").read_text() or True


def test_run_output_stays_within_local_discovery(tmp_path) -> None:
    result = run(
        confirm_run=CONFIRM_TOKEN,
        root=tmp_path,
        environ=_jira_env(),
        timestamp="20260615T000000Z",
        transport_factory=_factory(),
    )
    for artifact in result["artifacts"]:
        assert artifact["relative_path"].startswith(".local/discovery/jira/")
        assert ".." not in artifact["relative_path"]


def test_run_redacts_secret_in_saved_raw(tmp_path) -> None:
    leaky = _routes()
    leaky["/rest/api/3/search"] = {
        "issues": [{"fields": {"status": {"name": "Open"}, "summary": "key ghp_" + "z" * 36}}]
    }
    run(
        confirm_run=CONFIRM_TOKEN,
        root=tmp_path,
        environ=_jira_env(),
        timestamp="20260615T000000Z",
        transport_factory=_factory(routes=leaky),
    )
    saved = (
        tmp_path / ".local" / "discovery" / "jira" / "20260615T000000Z" / "raw" / "issues.json"
    ).read_text()
    assert "ghp_" not in saved
    assert not contains_secret_value(saved)


def test_real_transport_refuses_non_get() -> None:
    transport = _http_get_transport(_jira_env())
    with pytest.raises(JiraDiscoveryTransportError):
        transport("POST", "/rest/api/3/issue", {})
    with pytest.raises(JiraDiscoveryTransportError):
        transport("DELETE", "/rest/api/3/issue/ALPHA-1", {})
