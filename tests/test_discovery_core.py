"""Read-only discovery core: cred preflight (presence only) + safe local output."""

from __future__ import annotations

import json

import pytest

from app.services.discovery_core import (
    CRED_MISSING,
    CRED_READY,
    CRED_UNKNOWN_SOURCE,
    SOURCE_GITHUB,
    SOURCE_JIRA,
    assert_summary_safe,
    credential_preflight,
    discovery_dir,
    write_local_artifact,
)
from app.services.operator_output_sanitizer import inspect_operator_output

_JIRA_OK = {
    "FOS_JIRA_READONLY_SITE": "https://example.atlassian.net",
    "FOS_JIRA_READONLY_USER": "ops@example.com",
    "FOS_JIRA_READONLY_TOKEN": "x" * 24,
}


def test_jira_preflight_ready_when_all_present() -> None:
    pre = credential_preflight(SOURCE_JIRA, _JIRA_OK)
    assert pre.ready is True
    assert pre.reason_code == CRED_READY
    assert pre.missing_var_names == ()
    assert set(pre.present_var_names) == set(_JIRA_OK)


def test_jira_preflight_reports_exact_missing_names_without_values() -> None:
    pre = credential_preflight(
        SOURCE_JIRA, {"FOS_JIRA_READONLY_SITE": "https://example.atlassian.net"}
    )
    assert pre.ready is False
    assert pre.reason_code == CRED_MISSING
    assert pre.missing_var_names == (
        "FOS_JIRA_READONLY_USER",
        "FOS_JIRA_READONLY_TOKEN",
    )


def test_blank_value_counts_as_missing() -> None:
    env = dict(_JIRA_OK, FOS_JIRA_READONLY_TOKEN="   ")
    pre = credential_preflight(SOURCE_JIRA, env)
    assert pre.ready is False
    assert "FOS_JIRA_READONLY_TOKEN" in pre.missing_var_names


def test_github_optional_account_is_reported_when_present() -> None:
    env = {
        "FOS_GITHUB_READONLY_TOKEN": "ghp_" + "y" * 20,
        "FOS_GITHUB_TARGET_ORG": "example-org",
        "FOS_GITHUB_READONLY_ACCOUNT": "example-bot",
    }
    pre = credential_preflight(SOURCE_GITHUB, env)
    assert pre.ready is True
    assert pre.optional_present_var_names == ("FOS_GITHUB_READONLY_ACCOUNT",)


def test_unknown_source_fails_closed() -> None:
    pre = credential_preflight("slack", {})
    assert pre.ready is False
    assert pre.reason_code == CRED_UNKNOWN_SOURCE
    assert pre.required_var_names == ()


def test_preflight_as_dict_is_leak_safe() -> None:
    # Missing-var names are allowlisted by the sanitizer even though they
    # contain words like TOKEN; the summary must inspect clean.
    pre = credential_preflight(SOURCE_JIRA, {})
    summary = pre.as_dict()
    assert inspect_operator_output(summary).safe is True
    assert assert_summary_safe(summary) == summary


def test_write_local_artifact_writes_full_payload_and_returns_safe_ref(tmp_path) -> None:
    records = [
        {"key": "ALPHA", "name": "Project Alpha", "lead": "ops@example.com"},
        {"key": "BETA", "name": "Project Beta"},
    ]
    ref = write_local_artifact(
        SOURCE_JIRA, root=tmp_path, artifact_name="projects", records=records
    )
    # Full data landed locally...
    written = tmp_path / ".local" / "discovery" / "jira" / "projects.json"
    assert written.exists()
    assert json.loads(written.read_text())[0]["name"] == "Project Alpha"
    # ...and the returned ref carries only safe metadata (no payload, no hash).
    assert ref.record_count == 2
    assert ref.relative_path == ".local/discovery/jira/projects.json"
    assert inspect_operator_output(ref.as_dict()).safe is True


def test_discovery_dir_is_created_under_local_tree(tmp_path) -> None:
    directory = discovery_dir(SOURCE_GITHUB, root=tmp_path)
    assert directory == tmp_path / ".local" / "discovery" / "github"
    assert directory.is_dir()


def test_artifact_name_is_sanitized(tmp_path) -> None:
    ref = write_local_artifact(
        SOURCE_JIRA, root=tmp_path, artifact_name="../../etc/passwd", records={}
    )
    assert "/" not in ref.artifact_name
    assert ".." not in ref.artifact_name
    assert (tmp_path / ".local" / "discovery" / "jira" / f"{ref.artifact_name}.json").exists()


def test_unsafe_summary_is_rejected() -> None:
    with pytest.raises(ValueError):
        assert_summary_safe({"jira_site": "https://secret.atlassian.net/raw"})
