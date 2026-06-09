from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.connectors import jira
from app.services.external_connector_config import JIRA_ENV_KEYS
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.provider_execution_guard import (
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ACK_REQUIRED,
)
from scripts import check_external_connectors_readonly as smoke
from scripts import check_jira_readonly_inventory as inventory

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_jira_readonly_inventory.py"


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://jira-inventory.invalid/path",
        "operator" + "@" + "jira-inventory.invalid",
        "bot_token inventory value",
        "a" * 64,
        "postgres" + "://jira-inventory.invalid/db",
        "provider_payload inventory body",
        "source_object_id inventory body",
        "rendered_digest_text inventory body",
        "grouped_preview_text inventory body",
        "chunk_text inventory body",
        "PROJECT" + "-123",
        "ISSUE" + "-456",
        "issue title inventory body",
    )


def _assert_inventory_output_safe(value: dict[str, Any]) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized
    assert inspect_operator_output(value).safe is True
    assert value["contract_validation"]["validation_status"] == "pass"


def _configured_jira_env() -> dict[str, str]:
    return dict.fromkeys(JIRA_ENV_KEYS, "configured_value")


def _env_file(tmp_path: Path) -> Path:
    env_file = tmp_path / "connectors.env"
    env_file.write_text(
        "\n".join(f"{key}=configured_value" for key in JIRA_ENV_KEYS) + "\n",
        encoding="utf-8",
    )
    return env_file


def test_jira_inventory_default_mode_makes_no_live_call() -> None:
    transport_called = False

    def forbidden_transport(request: jira.JiraConnectorRequest) -> list[dict[str, Any]]:
        nonlocal transport_called
        transport_called = True
        return [{"accessible": True}]

    result = inventory.run_jira_readonly_inventory(
        compare_portfolio=True,
        jira_live_transport=forbidden_transport,
        environ=_configured_jira_env(),
    )

    assert result["status"] == "pass"
    assert result["reason_code"] == "requires_acknowledgement"
    assert result["provider_calls"] == "none"
    assert result["no_provider_calls"] is True
    assert result["jira"]["inventory_status"] == "configured_not_executed"
    assert result["jira"]["failure_class"] == "requires_acknowledgement"
    assert result["portfolio_mapping"]["mapping_status"] == "planned_not_verified"
    assert transport_called is False
    _assert_inventory_output_safe(result)


def test_jira_inventory_live_mode_requires_ack_before_transport_call() -> None:
    transport_called = False

    def forbidden_transport(request: jira.JiraConnectorRequest) -> list[dict[str, Any]]:
        nonlocal transport_called
        transport_called = True
        return [{"accessible": True}]

    result = inventory.run_jira_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk="wrong_ack",
        jira_live_transport=forbidden_transport,
        environ=_configured_jira_env(),
    )

    assert result["status"] == "fail"
    assert result["provider_calls"] == "none"
    assert result["jira"]["failure_class"] == PROVIDER_EXECUTION_ACK_REQUIRED
    assert transport_called is False
    _assert_inventory_output_safe(result)


def test_jira_inventory_synthetic_mode_reports_safe_counts() -> None:
    result = inventory.run_jira_readonly_inventory(
        synthetic=True,
        compare_portfolio=True,
    )

    assert result["status"] == "pass"
    assert result["provider_calls"] == "synthetic"
    assert result["no_provider_calls"] is True
    assert result["jira"]["inventory_status"] == "synthetic_verified"
    assert result["jira"]["project_count"] == 3
    assert result["jira"]["project_count_class"] == "nonzero_count"
    assert result["jira"]["issue_count_class"] == "nonzero_count"
    assert result["portfolio_mapping"]["mapping_status"] == "synthetic_verified"
    assert result["portfolio_mapping"]["mapped_area_count_class"] == (
        "matches_portfolio_area_count"
    )
    _assert_inventory_output_safe(result)


def test_jira_inventory_mocked_live_readonly_calls_transport_once() -> None:
    call_count = 0
    request_seen: jira.JiraConnectorRequest | None = None

    def mocked_transport(request: jira.JiraConnectorRequest) -> list[dict[str, Any]]:
        nonlocal call_count, request_seen
        call_count += 1
        request_seen = request
        return [{"accessible": True, "issue_count": 2}, {"accessible": True}]

    result = inventory.run_jira_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        compare_portfolio=True,
        jira_live_transport=mocked_transport,
        environ=_configured_jira_env(),
    )

    assert result["status"] == "pass"
    assert result["provider_calls"] == "live_readonly_attempted"
    assert result["no_provider_calls"] is False
    assert call_count == 1
    assert request_seen is not None
    assert request_seen.operation == "fetch_readonly_inventory_summary"
    assert result["jira"]["inventory_status"] == "live_readonly_verified"
    assert result["jira"]["project_count"] == 2
    assert result["jira"]["provider_payload_visibility"] == "suppressed"
    assert result["portfolio_mapping"]["mapping_status"] == "live_readonly_observed"
    _assert_inventory_output_safe(result)


def test_jira_inventory_live_failure_maps_to_safe_class() -> None:
    def failing_transport(request: jira.JiraConnectorRequest) -> list[dict[str, Any]]:
        raise smoke.JiraLiveReadonlySmokeError(
            smoke.JIRA_AUTH_FAILED,
            auth_status_class=smoke.JIRA_AUTH_FAILED,
            transport_status_class=smoke.JIRA_TRANSPORT_HTTP_ERROR,
        )

    result = inventory.run_jira_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        jira_live_transport=failing_transport,
        environ=_configured_jira_env(),
    )

    assert result["status"] == "fail"
    assert result["jira"]["inventory_status"] == "fail"
    assert result["jira"]["failure_class"] == "jira_auth_failed"
    assert result["jira"]["auth_status_class"] == "jira_auth_failed"
    _assert_inventory_output_safe(result)


def test_jira_inventory_malformed_mocked_response_is_safe_contract_mismatch() -> None:
    def malformed_transport(request: jira.JiraConnectorRequest) -> list[Any]:
        return ["not-a-project-payload"]

    result = inventory.run_jira_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        jira_live_transport=malformed_transport,
        environ=_configured_jira_env(),
    )

    assert result["status"] == "fail"
    assert result["jira"]["failure_class"] == "jira_response_contract_mismatch"
    assert result["jira"]["response_contract_status"] == (
        "jira_response_contract_mismatch"
    )
    _assert_inventory_output_safe(result)


def test_jira_inventory_does_not_echo_raw_provider_values() -> None:
    unsafe = _unsafe_values()

    def unsafe_transport(request: jira.JiraConnectorRequest) -> list[dict[str, Any]]:
        return [
            {
                "accessible": True,
                "issue_count": 1,
                "project_key": unsafe[10],
                "project_name": unsafe[1],
                "issue_key": unsafe[11],
                "issue_title": unsafe[12],
                "source_url": unsafe[0],
                "provider_payload": unsafe[5],
            }
        ]

    result = inventory.run_jira_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        jira_live_transport=unsafe_transport,
        environ=_configured_jira_env(),
    )

    assert result["status"] == "pass"
    assert result["jira"]["project_count"] == 1
    _assert_inventory_output_safe(result)


def test_jira_inventory_cli_outputs_strict_json_default_mode(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--json",
            "--connector-env-file",
            str(_env_file(tmp_path)),
            "--compare-portfolio",
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
    assert payload["report_kind"] == "jira_readonly_inventory"
    assert payload["provider_calls"] == "none"
    assert payload["jira"]["inventory_status"] == "configured_not_executed"
    _assert_inventory_output_safe(payload)


def test_jira_inventory_cli_outputs_strict_json_synthetic_mode(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--json",
            "--synthetic",
            "--connector-env-file",
            str(_env_file(tmp_path)),
            "--compare-portfolio",
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
    assert payload["report_kind"] == "jira_readonly_inventory"
    assert payload["provider_calls"] == "synthetic"
    assert payload["jira"]["inventory_status"] == "synthetic_verified"
    _assert_inventory_output_safe(payload)
