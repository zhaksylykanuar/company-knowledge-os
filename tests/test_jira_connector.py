from __future__ import annotations

import json

import pytest

from app.connectors import jira
from app.integrations.payload_mapper import map_connector_payload_to_ingested_event
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.provider_execution_guard import (
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ACK_REQUIRED,
    PROVIDER_EXECUTION_DEFAULT_DENIED,
    ProviderExecutionBlockedError,
)


def _payload(title: str = "synthetic_title") -> dict[str, str]:
    return {
        "title": title,
        "source_url": "synthetic_source_location",
    }


def test_jira_live_execution_default_denies_before_transport_call() -> None:
    transport_called = False

    def forbidden_transport(request: jira.JiraConnectorRequest) -> list[dict[str, str]]:
        nonlocal transport_called
        transport_called = True
        return [_payload()]

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        jira.search_issue_events(transport=forbidden_transport)

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED
    assert transport_called is False


def test_jira_live_execution_requires_exact_ack_before_transport_call() -> None:
    transport_called = False

    def forbidden_transport(request: jira.JiraConnectorRequest) -> list[dict[str, str]]:
        nonlocal transport_called
        transport_called = True
        return [_payload()]

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        jira.fetch_project_issue_events(
            transport=forbidden_transport,
            allow_live_provider_execution=True,
            provider_execution_ack="wrong_ack",
        )

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_ACK_REQUIRED
    assert transport_called is False


def test_jira_synthetic_issue_search_returns_raw_event_source_envelope() -> None:
    request_seen: jira.JiraConnectorRequest | None = None

    def synthetic_transport(request: jira.JiraConnectorRequest) -> list[dict[str, str]]:
        nonlocal request_seen
        request_seen = request
        return [_payload()]

    events = jira.search_issue_events(
        transport=synthetic_transport,
        execution_mode=jira.SYNTHETIC_EXECUTION_MODE,
    )

    assert request_seen is not None
    assert request_seen.provider_key == "jira"
    assert request_seen.execution_mode == jira.SYNTHETIC_EXECUTION_MODE
    assert len(events) == 1
    assert events[0]["source_system"] == "jira"
    assert events[0]["source_object_type"] == "issue"
    assert events[0]["event_type"] == "jira.issue.updated"
    assert events[0]["connector_boundary"] == "raw_event_source_only"
    assert events[0]["interpreted_truth"] is False
    mapped = map_connector_payload_to_ingested_event(events[0])
    assert mapped.source_system == "jira"
    assert mapped.event_type == "jira.issue.updated"


def test_jira_synthetic_project_issue_fetch_returns_raw_event_source_envelope() -> None:
    events = jira.fetch_project_issue_events(
        transport=lambda request: [_payload()],
        execution_mode=jira.SYNTHETIC_EXECUTION_MODE,
    )

    assert events[0]["source_system"] == "jira"
    assert events[0]["source_object_type"] == "issue"
    assert events[0]["event_type"] == "jira.issue.created"
    assert events[0]["interpreted_truth"] is False


def test_jira_live_readonly_fetch_calls_transport_once_with_ack() -> None:
    transport_call_count = 0
    request_seen: jira.JiraConnectorRequest | None = None

    def live_readonly_transport(
        request: jira.JiraConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal transport_call_count, request_seen
        transport_call_count += 1
        request_seen = request
        return [_payload()]

    events = jira.fetch_project_issue_events(
        transport=live_readonly_transport,
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
    )

    assert transport_call_count == 1
    assert request_seen is not None
    assert request_seen.provider_key == "jira"
    assert request_seen.operation == "fetch_project_issue_events"
    assert request_seen.execution_mode == jira.LIVE_EXECUTION_MODE
    assert len(events) == 1
    assert events[0]["connector_boundary"] == "raw_event_source_only"
    assert events[0]["interpreted_truth"] is False


def test_jira_readonly_inventory_default_denies_before_transport_call() -> None:
    transport_called = False

    def forbidden_transport(request: jira.JiraConnectorRequest) -> list[dict[str, int]]:
        nonlocal transport_called
        transport_called = True
        return [{"issue_count": 1}]

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        jira.fetch_readonly_inventory_summary(transport=forbidden_transport)

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED
    assert transport_called is False


def test_jira_readonly_inventory_synthetic_summary_counts_only() -> None:
    request_seen: jira.JiraConnectorRequest | None = None

    def synthetic_transport(request: jira.JiraConnectorRequest) -> list[dict[str, int | bool]]:
        nonlocal request_seen
        request_seen = request
        return [
            {"accessible": True, "issue_count": 2},
            {"accessible": False, "permission_limited": True},
        ]

    summary = jira.fetch_readonly_inventory_summary(
        transport=synthetic_transport,
        execution_mode=jira.SYNTHETIC_EXECUTION_MODE,
    )

    assert request_seen is not None
    assert request_seen.operation == "fetch_readonly_inventory_summary"
    assert request_seen.execution_mode == jira.SYNTHETIC_EXECUTION_MODE
    assert summary["project_count"] == 2
    assert summary["project_inventory_status"] == "permission_limited"
    assert summary["project_count_class"] == "nonzero_count"
    assert summary["accessible_project_count_class"] == "nonzero_count"
    assert summary["inaccessible_project_count_class"] == "nonzero_count"
    assert summary["permission_limited_count_class"] == "nonzero_count"
    assert summary["issue_inventory_status"] == "permission_limited"
    assert summary["issue_count_class"] == "nonzero_count"
    assert summary["access_diagnostic_class"] == (
        "jira_project_inventory_permission_limited"
    )
    assert summary["provider_payload_visibility"] == "suppressed"
    assert inspect_operator_output(summary).safe is True


def test_jira_readonly_inventory_zero_projects_has_specific_diagnostic() -> None:
    summary = jira.fetch_readonly_inventory_summary(
        transport=lambda request: [],
        execution_mode=jira.SYNTHETIC_EXECUTION_MODE,
    )

    assert summary["project_count"] == 0
    assert summary["project_inventory_status"] == "empty"
    assert summary["project_count_class"] == "zero_count"
    assert summary["issue_inventory_status"] == "not_observed"
    assert summary["issue_count_class"] == "not_observed"
    assert summary["access_diagnostic_class"] == "jira_project_inventory_empty"
    assert inspect_operator_output(summary).safe is True


def test_jira_readonly_inventory_access_zero_has_specific_diagnostic() -> None:
    summary = jira.fetch_readonly_inventory_summary(
        transport=lambda request: [{"accessible": False}],
        execution_mode=jira.SYNTHETIC_EXECUTION_MODE,
    )

    assert summary["project_inventory_status"] == "access_zero"
    assert summary["accessible_project_count_class"] == "zero_count"
    assert summary["inaccessible_project_count_class"] == "nonzero_count"
    assert summary["access_diagnostic_class"] == "jira_project_access_zero"
    assert inspect_operator_output(summary).safe is True


def test_jira_readonly_inventory_rejects_malformed_transport_payload() -> None:
    with pytest.raises(jira.JiraConnectorError) as exc_info:
        jira.fetch_readonly_inventory_summary(
            transport=lambda request: ["not-a-mapping"],
            execution_mode=jira.SYNTHETIC_EXECUTION_MODE,
        )

    assert exc_info.value.reason_code == jira.JIRA_INVENTORY_RESPONSE_CONTRACT_INVALID


def test_jira_raw_event_contract_rejects_invalid_synthetic_payload() -> None:
    with pytest.raises(jira.JiraConnectorError) as exc_info:
        jira.search_issue_events(
            transport=lambda request: [{"title": ""}],
            execution_mode=jira.SYNTHETIC_EXECUTION_MODE,
        )

    assert exc_info.value.reason_code == jira.JIRA_RAW_EVENT_CONTRACT_INVALID


def test_jira_connector_diagnostics_are_sanitized_and_json_serializable() -> None:
    diagnostics = jira.connector_diagnostics()

    assert diagnostics["provider_key"] == "jira"
    assert diagnostics["live_calls"] == "default_denied"
    assert diagnostics["source_of_truth_role"] == "raw_event_source_only"
    assert diagnostics["provider_payload_in_diagnostics"] is False
    json.dumps(diagnostics, sort_keys=True)
    assert inspect_operator_output(diagnostics).safe is True
