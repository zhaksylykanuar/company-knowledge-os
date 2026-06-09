from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
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


def _configured_jira_env(*, site: str | None = None) -> dict[str, str]:
    configured = _configured_env()
    configured["FOS_JIRA_READONLY_SITE"] = site or ("https" + "://jira.invalid")
    configured["FOS_JIRA_READONLY_USER"] = "configured_value"
    configured["FOS_JIRA_READONLY_TOKEN"] = "configured_value"
    return configured


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
    assert result["providers"]["github"]["portfolio_compare_scope"] == (
        "seed_portfolio_counts_only"
    )
    assert result["providers"]["github"]["github_target_owner_class"] == (
        "github_organization"
    )
    assert result["providers"]["github"]["github_target_org_key"] == "qtwin-io"
    assert result["providers"]["github"]["github_org_live_inventory_status"] == (
        "gated_not_verified"
    )
    assert result["providers"]["github"]["github_write_operations"] == "disabled"
    assert result["providers"]["github"]["github_repo_transfer_operations"] == (
        "disabled"
    )
    assert result["providers"]["github"]["github_repo_edit_operations"] == "disabled"
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
    assert github_result["portfolio_compare_scope"] == "seed_portfolio_counts_only"
    assert github_result["github_org_migration_status"] == (
        "manual_org_migration_planned"
    )
    assert github_result["github_org_live_inventory_status"] == "gated_not_verified"
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


def test_jira_live_readonly_success_reports_safe_adapter_diagnostics() -> None:
    jira_called = 0
    request_seen: jira.JiraConnectorRequest | None = None

    def mocked_jira(request: jira.JiraConnectorRequest) -> list[dict[str, str]]:
        nonlocal jira_called, request_seen
        jira_called += 1
        request_seen = request
        return [_payload(), _payload()]

    result = smoke.run_connector_readonly_smoke(
        provider="jira",
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        jira_live_transport=mocked_jira,
        environ=_configured_jira_env(),
    )

    jira_result = result["providers"]["jira"]
    assert result["status"] == "pass"
    assert result["provider_calls"] == "live_readonly_attempted"
    assert jira_called == 1
    assert request_seen is not None
    assert request_seen.operation == "fetch_project_issue_events"
    assert jira_result["live_readonly_status"] == "pass"
    assert jira_result["live_failure_class"] is None
    assert jira_result["auth_status_class"] == "jira_auth_accepted"
    assert jira_result["transport_status_class"] == "jira_transport_pass"
    assert jira_result["response_contract_status"] == "pass"
    assert jira_result["provider_payload_visibility"] == "suppressed"
    assert jira_result["project_count"] == 2
    _assert_smoke_output_safe(result)


def test_jira_live_readonly_invalid_site_config_is_sanitized(
    monkeypatch: Any,
) -> None:
    urlopen_called = False

    def forbidden_urlopen(*args: Any, **kwargs: Any) -> object:
        nonlocal urlopen_called
        urlopen_called = True
        raise AssertionError("urlopen should not be called")

    monkeypatch.setattr(smoke.urllib.request, "urlopen", forbidden_urlopen)

    result = smoke.run_connector_readonly_smoke(
        provider="jira",
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        environ=_configured_jira_env(site="not a valid site"),
    )

    jira_result = result["providers"]["jira"]
    assert result["status"] == "fail"
    assert result["provider_calls"] == "live_readonly_attempted"
    assert jira_result["live_readonly_status"] == "fail"
    assert jira_result["provider_reason_code"] == "jira_site_config_invalid"
    assert jira_result["live_failure_class"] == "jira_site_config_invalid"
    assert jira_result["transport_status_class"] == "jira_transport_not_started"
    assert urlopen_called is False
    _assert_smoke_output_safe(result)


def test_jira_live_readonly_normalizes_site_before_safe_readonly_request(
    monkeypatch: Any,
) -> None:
    urlopen_called = 0

    class SafeResponse:
        def __enter__(self) -> SafeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            return b'{"values":[{},{}]}'

    def fake_urlopen(request: object, timeout: int) -> SafeResponse:
        nonlocal urlopen_called
        urlopen_called += 1
        assert timeout == 10
        return SafeResponse()

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)

    result = smoke.run_connector_readonly_smoke(
        provider="jira",
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        environ=_configured_jira_env(site="jira.invalid"),
    )

    jira_result = result["providers"]["jira"]
    assert result["status"] == "pass"
    assert urlopen_called == 1
    assert jira_result["live_readonly_status"] == "pass"
    assert jira_result["project_count"] == 2
    _assert_smoke_output_safe(result)


def test_jira_live_readonly_http_failures_map_to_safe_classes(
    monkeypatch: Any,
) -> None:
    cases = {
        401: "jira_auth_failed",
        403: "jira_permission_denied",
        404: "jira_not_found_or_wrong_site",
        429: "jira_rate_limited",
        500: "jira_server_error",
    }

    for status_code, expected_class in cases.items():

        def fake_urlopen(request: object, timeout: int) -> object:
            raise urllib.error.HTTPError(
                url="safe_endpoint",
                code=status_code,
                msg="safe",
                hdrs=None,
                fp=None,
            )

        monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)

        result = smoke.run_connector_readonly_smoke(
            provider="jira",
            allow_live_readonly_apis=True,
            acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
            environ=_configured_jira_env(),
        )

        jira_result = result["providers"]["jira"]
        assert result["status"] == "fail"
        assert jira_result["provider_reason_code"] == expected_class
        assert jira_result["live_failure_class"] == expected_class
        assert jira_result["transport_status_class"] == "jira_transport_http_error"
        _assert_smoke_output_safe(result)


def test_jira_live_readonly_timeout_and_transport_errors_are_sanitized(
    monkeypatch: Any,
) -> None:
    for raised, expected_class in (
        (TimeoutError(), "jira_timeout"),
        (urllib.error.URLError("safe_transport_failure"), "jira_transport_error"),
    ):

        def fake_urlopen(request: object, timeout: int) -> object:
            raise raised

        monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)

        result = smoke.run_connector_readonly_smoke(
            provider="jira",
            allow_live_readonly_apis=True,
            acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
            environ=_configured_jira_env(),
        )

        jira_result = result["providers"]["jira"]
        assert result["status"] == "fail"
        assert jira_result["provider_reason_code"] == expected_class
        assert jira_result["live_failure_class"] == expected_class
        _assert_smoke_output_safe(result)


def test_jira_live_readonly_malformed_response_is_sanitized(
    monkeypatch: Any,
) -> None:
    class MalformedResponse:
        def __enter__(self) -> MalformedResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            return b"{not-json"

    monkeypatch.setattr(
        smoke.urllib.request,
        "urlopen",
        lambda request, timeout: MalformedResponse(),
    )

    result = smoke.run_connector_readonly_smoke(
        provider="jira",
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        environ=_configured_jira_env(),
    )

    jira_result = result["providers"]["jira"]
    assert result["status"] == "fail"
    assert jira_result["provider_reason_code"] == "jira_response_malformed"
    assert jira_result["live_failure_class"] == "jira_response_malformed"
    assert jira_result["response_contract_status"] == "jira_response_malformed"
    _assert_smoke_output_safe(result)


def test_jira_live_readonly_response_contract_mismatch_is_sanitized(
    monkeypatch: Any,
) -> None:
    class ContractMismatchResponse:
        def __enter__(self) -> ContractMismatchResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            return b'{"values":["not-an-object"]}'

    monkeypatch.setattr(
        smoke.urllib.request,
        "urlopen",
        lambda request, timeout: ContractMismatchResponse(),
    )

    result = smoke.run_connector_readonly_smoke(
        provider="jira",
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        environ=_configured_jira_env(),
    )

    jira_result = result["providers"]["jira"]
    assert result["status"] == "fail"
    assert jira_result["provider_reason_code"] == "jira_response_contract_mismatch"
    assert jira_result["live_failure_class"] == "jira_response_contract_mismatch"
    assert jira_result["response_contract_status"] == "jira_response_contract_mismatch"
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
            "--no-connector-env-file",
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
            "--no-connector-env-file",
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


def test_connector_smoke_cli_uses_synthetic_env_file_for_config_status(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "connectors.env"
    env_file.write_text(
        "\n".join(
            [f"{key}=configured_value" for key in (*GITHUB_ENV_KEYS, *JIRA_ENV_KEYS)]
        )
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--provider",
            "all",
            "--compare-portfolio",
            "--json",
            "--connector-env-file",
            str(env_file),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={},
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["provider_calls"] == "none"
    assert payload["diagnostics"]["connector_env_file"]["env_file_status"] == "loaded"
    assert payload["diagnostics"]["connector_env_file"]["loaded_allowed_key_count"] == (
        len(GITHUB_ENV_KEYS) + len(JIRA_ENV_KEYS)
    )
    assert payload["providers"]["github"]["live_readonly_status"] == "not_run"
    assert payload["providers"]["jira"]["live_readonly_status"] == "not_run"
    assert "configured_value" not in completed.stdout
    _assert_smoke_output_safe(payload)


def test_connector_smoke_live_readonly_uses_env_file_but_remains_ack_gated(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "connectors.env"
    env_file.write_text(
        "\n".join(
            [f"{key}={_unsafe_values()[0]}" for key in (*GITHUB_ENV_KEYS, *JIRA_ENV_KEYS)]
        )
        + "\n",
        encoding="utf-8",
    )

    result = smoke.run_connector_readonly_smoke(
        provider="all",
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk="wrong_ack",
        compare_portfolio=True,
        environ={},
        connector_env_file=env_file,
        use_connector_env_file=True,
    )

    assert result["status"] == "fail"
    assert result["provider_calls"] == "none"
    assert result["providers"]["github"]["provider_reason_code"] == (
        PROVIDER_EXECUTION_ACK_REQUIRED
    )
    assert result["providers"]["jira"]["provider_reason_code"] == (
        PROVIDER_EXECUTION_ACK_REQUIRED
    )
    assert _unsafe_values()[0] not in json.dumps(result, sort_keys=True)
    _assert_smoke_output_safe(result)
