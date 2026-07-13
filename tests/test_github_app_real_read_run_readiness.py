"""Offline unit tests for GitHub App real-read-run readiness.

These tests are pure and offline: no database, no network, no GitHub provider
calls. They pin the deterministic readiness contract used to gate the first
human-approved real read run and assert that no secret values leak into the
readiness payload.
"""

from __future__ import annotations

import json

from app.core.config import Settings
from app.services.github_connection_service import (
    GITHUB_APP_CONNECTION_METHOD,
    GITHUB_APP_REAL_READ_RUN_BLOCKED,
    GITHUB_APP_REAL_READ_RUN_READY,
    github_app_real_read_run_readiness,
)


def _configured_settings() -> Settings:
    return Settings(
        github_app_id="12345",
        github_app_slug="founderos-test",
        github_app_private_key=None,
        github_app_private_key_path="/secrets/github-app.pem",
    )


def _unconfigured_settings() -> Settings:
    return Settings(
        github_app_id=None,
        github_app_slug=None,
        github_app_private_key=None,
        github_app_private_key_path=None,
    )


def _connection_status(*, recorded: bool, connected: bool) -> dict:
    if not recorded:
        return {
            "has_connection_record": False,
            "connection_method": None,
            "status": None,
        }
    return {
        "has_connection_record": True,
        "connection_method": GITHUB_APP_CONNECTION_METHOD,
        "status": "connected" if connected else "error",
    }


def test_readiness_reports_ready_when_env_connection_and_repos_present() -> None:
    readiness = github_app_real_read_run_readiness(
        connection_status=_connection_status(recorded=True, connected=True),
        local_repository_count=25,
        config=_configured_settings(),
    )

    assert readiness["status"] == GITHUB_APP_REAL_READ_RUN_READY
    assert readiness["ready"] is True
    assert readiness["blockers"] == []
    assert readiness["requires_human_approval"] is True
    assert readiness["provider_read_started"] is False
    assert readiness["provider_writes_enabled"] is False


def test_readiness_lists_all_blockers_when_nothing_is_ready() -> None:
    readiness = github_app_real_read_run_readiness(
        connection_status=_connection_status(recorded=False, connected=False),
        local_repository_count=0,
        config=_unconfigured_settings(),
    )

    assert readiness["status"] == GITHUB_APP_REAL_READ_RUN_BLOCKED
    assert readiness["ready"] is False
    assert "github_app_env_incomplete" in readiness["blockers"]
    assert "github_app_installation_connection_missing" in readiness["blockers"]
    assert "local_repository_surface_empty" in readiness["blockers"]


def test_readiness_flags_recorded_but_disconnected_installation() -> None:
    readiness = github_app_real_read_run_readiness(
        connection_status=_connection_status(recorded=True, connected=False),
        local_repository_count=25,
        config=_configured_settings(),
    )

    assert readiness["status"] == GITHUB_APP_REAL_READ_RUN_BLOCKED
    assert "github_app_installation_connection_not_connected" in readiness["blockers"]
    assert "github_app_installation_connection_missing" not in readiness["blockers"]


def test_readiness_flags_missing_local_repository_surface() -> None:
    readiness = github_app_real_read_run_readiness(
        connection_status=_connection_status(recorded=True, connected=True),
        local_repository_count=0,
        config=_configured_settings(),
    )

    assert readiness["status"] == GITHUB_APP_REAL_READ_RUN_BLOCKED
    assert readiness["blockers"] == ["local_repository_surface_empty"]
    assert "explicit target" in readiness["next_step"]


def test_readiness_payload_contains_no_secret_values() -> None:
    readiness = github_app_real_read_run_readiness(
        connection_status=_connection_status(recorded=True, connected=True),
        local_repository_count=25,
        config=_configured_settings(),
    )

    blob = json.dumps(readiness)
    # Neither the configured app id nor the private-key path may leak as a value.
    assert "12345" not in blob
    assert "/secrets/github-app.pem" not in blob
