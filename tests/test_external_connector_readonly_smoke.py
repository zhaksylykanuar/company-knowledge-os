from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.connectors import github, jira
from app.services.external_connector_config import GITHUB_ENV_KEYS, JIRA_ENV_KEYS
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.provider_execution_guard import (
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ACK_REQUIRED,
)
from scripts import check_external_connectors_readonly as smoke

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_external_connectors_readonly.py"


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://smoke.invalid/path",
        "operator" + "@" + "smoke.invalid",
        "bot_token smoke value",
        "a" * 64,
        "postgres" + "://smoke.invalid/db",
        "provider_payload smoke body",
        "source_object_id smoke body",
        "rendered_digest_text smoke body",
        "grouped_preview_text smoke body",
        "chunk_text smoke body",
        "item_title smoke body",
        "raw_smoke_json smoke body",
        "PROJECT" + "-123",
        "PR" + "-456",
    )


def _assert_no_raw_unsafe_values(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized


def _assert_smoke_output_safe(value: dict[str, Any]) -> None:
    assert inspect_operator_output(value).safe is True
    assert value["contract_validation"]["validation_status"] == "pass"
    _assert_no_raw_unsafe_values(value)


def _configured_env() -> dict[str, str]:
    return {
        **dict.fromkeys(GITHUB_ENV_KEYS, "configured_value"),
        **dict.fromkeys(JIRA_ENV_KEYS, "configured_value"),
    }


def _payload(**extra: Any) -> dict[str, Any]:
    return {
        "title": "synthetic_connector_event",
        "source_url": "synthetic_source_location",
        **extra,
    }


def test_connector_smoke_default_mode_makes_no_live_calls() -> None:
    github_called = False
    jira_called = False

    def forbidden_github(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal github_called
        github_called = True
        return [_payload()]

    def forbidden_jira(request: jira.JiraConnectorRequest) -> list[dict[str, str]]:
        nonlocal jira_called
        jira_called = True
        return [_payload()]

    result = smoke.run_connector_readonly_smoke(
        provider="all",
        compare_portfolio=True,
        github_live_transport=forbidden_github,
        jira_live_transport=forbidden_jira,
        environ=_configured_env(),
    )

    assert result["status"] == "pass"
    assert result["reason_code"] == "requires_acknowledgement"
    assert result["provider_calls"] == "none"
    assert result["no_provider_calls"] is True
    assert result["providers"]["github"]["default_denied"] == "pass"
    assert result["providers"]["jira"]["default_denied"] == "pass"
    assert result["providers"]["github"]["live_readonly_status"] == "not_run"
    assert result["providers"]["jira"]["live_readonly_status"] == "not_run"
    assert result["providers"]["github"]["portfolio_expected_count"] == 19
    assert github_called is False
    assert jira_called is False
    _assert_smoke_output_safe(result)


def test_connector_smoke_live_mode_requires_exact_ack_before_transport_call() -> None:
    github_called = False
    jira_called = False

    def forbidden_github(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal github_called
        github_called = True
        return [_payload()]

    def forbidden_jira(request: jira.JiraConnectorRequest) -> list[dict[str, str]]:
        nonlocal jira_called
        jira_called = True
        return [_payload()]

    result = smoke.run_connector_readonly_smoke(
        provider="all",
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk="wrong_ack",
        compare_portfolio=True,
        github_live_transport=forbidden_github,
        jira_live_transport=forbidden_jira,
        environ=_configured_env(),
    )

    assert result["status"] == "fail"
    assert result["provider_calls"] == "none"
    assert result["providers"]["github"]["provider_reason_code"] == (
        PROVIDER_EXECUTION_ACK_REQUIRED
    )
    assert result["providers"]["jira"]["provider_reason_code"] == (
        PROVIDER_EXECUTION_ACK_REQUIRED
    )
    assert github_called is False
    assert jira_called is False
    _assert_smoke_output_safe(result)


def test_connector_smoke_synthetic_mode_reports_counts_only() -> None:
    result = smoke.run_connector_readonly_smoke(
        provider="all",
        synthetic=True,
        compare_portfolio=True,
    )

    github_result = result["providers"]["github"]
    jira_result = result["providers"]["jira"]
    assert result["status"] == "pass"
    assert result["provider_calls"] == "synthetic"
    assert result["no_provider_calls"] is True
    assert github_result["synthetic_status"] == "pass"
    assert github_result["portfolio_expected_count"] == 19
    assert github_result["live_inventory_count_class"] == "matches_expected_count"
    assert github_result["matched_count"] == 19
    assert github_result["missing_count"] == 0
    assert github_result["extra_count"] == 0
    assert jira_result["synthetic_status"] == "pass"
    assert jira_result["mapping_status"] == "synthetic_verified"
    assert jira_result["project_count_class"] == "nonzero_count"
    _assert_smoke_output_safe(result)


def test_connector_smoke_live_readonly_not_configured_is_sanitized() -> None:
    result = smoke.run_connector_readonly_smoke(
        provider="all",
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        compare_portfolio=True,
        environ={},
    )

    assert result["status"] == "pass"
    assert result["provider_calls"] == "none"
    assert result["diagnostics"]["not_configured_count"] == 2
    assert result["providers"]["github"]["live_readonly_status"] == "not_configured"
    assert result["providers"]["jira"]["live_readonly_status"] == "not_configured"
    _assert_smoke_output_safe(result)


def test_connector_smoke_mocked_live_readonly_path_reports_safe_counts_only() -> None:
    github_called = False
    jira_called = False

    def mocked_github(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, Any]]:
        nonlocal github_called
        github_called = True
        return [
            _payload(repo_key=repo_key)
            for repo_key in smoke._portfolio_repo_keys()
        ]

    def mocked_jira(request: jira.JiraConnectorRequest) -> list[dict[str, str]]:
        nonlocal jira_called
        jira_called = True
        return [_payload(), _payload(), _payload()]

    result = smoke.run_connector_readonly_smoke(
        provider="all",
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        compare_portfolio=True,
        github_live_transport=mocked_github,
        jira_live_transport=mocked_jira,
        environ=_configured_env(),
    )

    assert result["status"] == "pass"
    assert result["provider_calls"] == "live_readonly_attempted"
    assert result["no_provider_calls"] is False
    assert result["providers"]["github"]["live_readonly_status"] == "pass"
    assert result["providers"]["github"]["matched_count"] == 19
    assert result["providers"]["github"]["missing_count"] == 0
    assert result["providers"]["github"]["extra_count"] == 0
    assert result["providers"]["jira"]["live_readonly_status"] == "pass"
    assert result["providers"]["jira"]["mapping_status"] == "live_readonly_verified"
    assert github_called is True
    assert jira_called is True
    _assert_smoke_output_safe(result)


def test_connector_smoke_does_not_echo_unsafe_mocked_provider_data() -> None:
    unsafe_repo_key = _unsafe_values()[0]
    unsafe_text = _unsafe_values()[1]

    def unsafe_github(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, Any]]:
        return [_payload(title=unsafe_text, repo_key=unsafe_repo_key)]

    def unsafe_jira(request: jira.JiraConnectorRequest) -> list[dict[str, str]]:
        return [_payload(title=unsafe_text)]

    result = smoke.run_connector_readonly_smoke(
        provider="all",
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        compare_portfolio=True,
        github_live_transport=unsafe_github,
        jira_live_transport=unsafe_jira,
        environ=_configured_env(),
    )

    assert result["status"] == "pass"
    assert result["providers"]["github"]["extra_count"] == 1
    assert result["providers"]["github"]["missing_count"] == 19
    assert result["providers"]["jira"]["project_count"] == 1
    _assert_smoke_output_safe(result)


def test_connector_smoke_cli_outputs_strict_json_in_synthetic_mode() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--provider",
            "all",
            "--synthetic",
            "--compare-portfolio",
            "--json",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["report_kind"] == "external_connector_readonly_smoke"
    assert payload["provider_calls"] == "synthetic"
    assert payload["providers"]["github"]["portfolio_expected_count"] == 19
    _assert_smoke_output_safe(payload)


def test_connector_smoke_cli_outputs_strict_json_in_default_no_live_mode() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--provider",
            "all",
            "--compare-portfolio",
            "--json",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["report_kind"] == "external_connector_readonly_smoke"
    assert payload["provider_calls"] == "none"
    assert payload["providers"]["github"]["default_denied"] == "pass"
    assert payload["providers"]["jira"]["default_denied"] == "pass"
    _assert_smoke_output_safe(payload)
