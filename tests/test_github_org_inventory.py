from __future__ import annotations

import json
from typing import Any

import pytest

from app.connectors import github
from app.services.external_connector_config import GITHUB_ENV_KEYS
from app.services.github_org_inventory import (
    GitHubOrgInventoryLiveError,
    github_org_inventory_readiness_summary,
    run_github_org_readonly_inventory,
)
from app.services.guarded_execution_contracts import (
    validate_github_org_readonly_inventory_contract,
)
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.provider_execution_guard import (
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ACK_REQUIRED,
)
from app.services.repository_portfolio import repository_portfolio_catalog


def _configured_github_env() -> dict[str, str]:
    return dict.fromkeys(GITHUB_ENV_KEYS, "configured_value")


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://github-org-inventory.invalid/path",
        "operator" + "@" + "github-org-inventory.invalid",
        "bot_token github org inventory value",
        "a" * 64,
        "postgres" + "://github-org-inventory.invalid/db",
        "provider_payload github org inventory body",
        "source_object_id github org inventory body",
        "repo name github org inventory body",
        "owner name github org inventory body",
        "PR" + "-123",
        "issue title github org inventory body",
    )


def _assert_inventory_output_safe(value: dict[str, Any]) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized
    for entry in repository_portfolio_catalog():
        assert entry["repo_key"] not in serialized
    assert inspect_operator_output(value).safe is True
    validation = validate_github_org_readonly_inventory_contract(value)
    assert validation.passed is True
    assert validation.as_dict()["validation_status"] == "pass"


def test_github_org_inventory_default_mode_makes_no_live_call() -> None:
    transport_called = False

    def forbidden_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal transport_called
        transport_called = True
        return [{"repo_key": "synthetic_repo"}]

    result = run_github_org_readonly_inventory(
        compare_portfolio=True,
        github_live_transport=forbidden_transport,
        environ=_configured_github_env(),
    )

    assert result["status"] == "pass"
    assert result["reason_code"] == "requires_acknowledgement"
    assert result["provider_calls"] == "none"
    assert result["no_provider_calls"] is True
    assert result["github"]["config_status"] == "configured"
    assert result["github"]["target_org_key"] == "qtwin-io"
    assert result["github"]["target_owner_class"] == "github_organization"
    assert result["github"]["org_inventory_status"] == "configured_not_executed"
    assert result["github"]["org_repo_count_class"] == "not_observed"
    assert result["github"]["seed_repo_count"] == 19
    assert result["github"]["expected_migration_count"] == 19
    assert result["github"]["write_operations"] == "disabled"
    assert result["github"]["repo_transfer_operations"] == "disabled"
    assert result["github"]["repo_edit_operations"] == "disabled"
    assert result["migration_readiness"]["next_action_class"] == (
        "run_gated_github_org_inventory"
    )
    assert transport_called is False
    _assert_inventory_output_safe(result)


def test_github_org_inventory_live_mode_requires_ack_before_transport_call() -> None:
    transport_called = False

    def forbidden_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal transport_called
        transport_called = True
        return [{"repo_key": "synthetic_repo"}]

    result = run_github_org_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk="wrong_ack",
        github_live_transport=forbidden_transport,
        environ=_configured_github_env(),
    )

    assert result["status"] == "fail"
    assert result["reason_code"] == PROVIDER_EXECUTION_ACK_REQUIRED
    assert result["provider_calls"] == "none"
    assert result["github"]["failure_class"] == PROVIDER_EXECUTION_ACK_REQUIRED
    assert transport_called is False
    _assert_inventory_output_safe(result)


def test_github_org_inventory_synthetic_mode_reports_safe_counts() -> None:
    result = run_github_org_readonly_inventory(
        synthetic=True,
        compare_portfolio=True,
        environ={},
        use_connector_env_file=False,
    )

    assert result["status"] == "pass"
    assert result["reason_code"] == "github_org_readonly_inventory_passed"
    assert result["provider_calls"] == "synthetic"
    assert result["no_provider_calls"] is True
    assert result["github"]["org_inventory_status"] == "synthetic_verified"
    assert result["github"]["org_repo_count_class"] == "nonzero_count"
    assert result["github"]["matched_count_class"] == "nonzero_count"
    assert result["github"]["missing_count_class"] == "nonzero_count"
    assert result["github"]["extra_count_class"] == "zero_count"
    assert result["github"]["provider_payload_visibility"] == "suppressed"
    assert result["migration_readiness"]["migration_status_class"] == (
        "manual_org_migration_planned"
    )
    assert result["migration_readiness"]["target_org_current_status_class"] == (
        "one_repo_reported_by_operator"
    )
    assert result["migration_readiness"]["next_action_class"] == (
        "review_manual_org_migration_status"
    )
    _assert_inventory_output_safe(result)


def test_github_org_inventory_mocked_live_readonly_calls_transport_once() -> None:
    seed_key = str(repository_portfolio_catalog()[0]["repo_key"])
    call_count = 0
    request_seen: github.GitHubConnectorRequest | None = None

    def mocked_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal call_count, request_seen
        call_count += 1
        request_seen = request
        return [{"repo_key": seed_key}, {"repo_key": "synthetic_extra_repo"}]

    result = run_github_org_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        compare_portfolio=True,
        github_live_transport=mocked_transport,
        environ=_configured_github_env(),
    )

    assert result["status"] == "pass"
    assert result["provider_calls"] == "live_readonly_attempted"
    assert result["no_provider_calls"] is False
    assert call_count == 1
    assert request_seen is not None
    assert request_seen.provider_key == "github"
    assert request_seen.operation == "fetch_org_repository_inventory_summary"
    assert request_seen.source_object_type == "repository"
    assert result["github"]["org_inventory_status"] == "live_readonly_verified"
    assert result["github"]["live_readonly_status"] == "pass"
    assert result["github"]["live_failure_class"] is None
    assert result["github"]["auth_status_class"] == "pass"
    assert result["github"]["permission_status_class"] == "pass"
    assert result["github"]["transport_status_class"] == "pass"
    assert result["github"]["response_contract_status"] == "pass"
    assert result["github"]["org_visibility_status_class"] == (
        "github_org_inventory_visible"
    )
    assert result["github"]["org_repo_count_class"] == "nonzero_count"
    assert result["github"]["matched_count_class"] == "nonzero_count"
    assert result["github"]["missing_count_class"] == "nonzero_count"
    assert result["github"]["extra_count_class"] == "nonzero_count"
    assert result["migration_readiness"]["live_inventory_status_class"] == (
        "live_readonly_verified"
    )
    _assert_inventory_output_safe(result)


@pytest.mark.parametrize(
    ("failure_class", "expected_auth", "expected_permission"),
    [
        ("github_auth_failed", "github_auth_failed", "not_checked"),
        ("github_permission_denied", "pass", "github_permission_denied"),
        (
            "github_org_not_found_or_no_access",
            "pass",
            "github_org_not_found_or_no_access",
        ),
        ("github_rate_limited", "pass", "pass"),
        ("github_server_error", "pass", "pass"),
    ],
)
def test_github_org_inventory_live_failure_maps_to_safe_class(
    failure_class: str,
    expected_auth: str,
    expected_permission: str,
) -> None:
    def failing_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        raise GitHubOrgInventoryLiveError(failure_class)

    result = run_github_org_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        github_live_transport=failing_transport,
        environ=_configured_github_env(),
    )

    assert result["status"] == "fail"
    assert result["reason_code"] == failure_class
    assert result["provider_calls"] == "live_readonly_attempted"
    assert result["github"]["live_readonly_status"] == "fail"
    assert result["github"]["failure_class"] == failure_class
    assert result["github"]["live_failure_class"] == failure_class
    assert result["github"]["auth_status_class"] == expected_auth
    assert result["github"]["permission_status_class"] == expected_permission
    assert result["github"]["provider_payload_visibility"] == "suppressed"
    _assert_inventory_output_safe(result)


@pytest.mark.parametrize(
    ("exception", "failure_class", "transport_status"),
    [
        (TimeoutError(), "github_timeout", "github_timeout"),
        (OSError(), "github_transport_error", "github_transport_error"),
    ],
)
def test_github_org_inventory_transport_exceptions_are_sanitized(
    exception: Exception,
    failure_class: str,
    transport_status: str,
) -> None:
    def failing_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        raise exception

    result = run_github_org_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        github_live_transport=failing_transport,
        environ=_configured_github_env(),
    )

    assert result["status"] == "fail"
    assert result["github"]["failure_class"] == failure_class
    assert result["github"]["transport_status_class"] == transport_status
    assert result["github"]["live_readonly_status"] == "fail"
    _assert_inventory_output_safe(result)


def test_github_org_inventory_empty_live_response_is_specific_safe_class() -> None:
    result = run_github_org_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        github_live_transport=lambda request: [],
        environ=_configured_github_env(),
    )

    assert result["status"] == "fail"
    assert result["reason_code"] == "github_empty_org_inventory"
    assert result["github"]["org_repo_count_class"] == "zero_count"
    assert result["github"]["failure_class"] == "github_empty_org_inventory"
    assert result["github"]["org_visibility_status_class"] == (
        "github_empty_org_inventory"
    )
    _assert_inventory_output_safe(result)


def test_github_org_inventory_malformed_response_is_specific_safe_class() -> None:
    def malformed_transport(request: github.GitHubConnectorRequest) -> list[Any]:
        return ["not-a-repository-payload"]

    result = run_github_org_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        github_live_transport=malformed_transport,
        environ=_configured_github_env(),
    )

    assert result["status"] == "fail"
    assert result["github"]["failure_class"] == "github_response_malformed"
    assert result["github"]["response_contract_status"] == "github_response_malformed"
    _assert_inventory_output_safe(result)


def test_github_org_inventory_contract_mismatch_is_specific_safe_class() -> None:
    def mismatched_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        return [{"repo_key": ""}]

    result = run_github_org_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        github_live_transport=mismatched_transport,
        environ=_configured_github_env(),
    )

    assert result["status"] == "fail"
    assert result["github"]["failure_class"] == "github_response_contract_mismatch"
    assert result["github"]["response_contract_status"] == (
        "github_response_contract_mismatch"
    )
    _assert_inventory_output_safe(result)


def test_github_org_inventory_invalid_target_org_config_blocks_before_transport() -> None:
    transport_called = False

    def forbidden_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal transport_called
        transport_called = True
        return [{"repo_key": "synthetic_repo"}]

    result = run_github_org_readonly_inventory(
        allow_live_readonly_apis=True,
        acknowledge_live_readonly_risk=LIVE_PROVIDER_EXECUTION_ACK,
        target_org="invalid org shape",
        github_live_transport=forbidden_transport,
        environ=_configured_github_env(),
    )

    assert result["status"] == "fail"
    assert result["reason_code"] == "github_org_config_invalid"
    assert result["github"]["target_org_key"] == "qtwin-io"
    assert result["github"]["failure_class"] == "github_org_config_invalid"
    assert transport_called is False
    _assert_inventory_output_safe(result)


def test_github_org_inventory_readiness_summary_is_safe() -> None:
    summary = github_org_inventory_readiness_summary()

    assert summary["github_org_inventory_cli"] == "present"
    assert summary["github_target_org_key"] == "qtwin-io"
    assert summary["github_target_owner_class"] == "github_organization"
    assert summary["github_org_live_inventory"] == "gated"
    assert summary["github_org_migration_status"] == "manual_org_migration_planned"
    assert summary["github_repo_transfer_operations"] == "disabled"
    assert summary["github_repo_edit_operations"] == "disabled"
    assert summary["github_write_operations"] == "disabled"
    assert summary["no_provider_calls"] is True
    assert inspect_operator_output(summary).safe is True
