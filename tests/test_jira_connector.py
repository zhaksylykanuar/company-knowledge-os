from __future__ import annotations

import json

import pytest

from app.connectors import jira
from app.integrations.payload_mapper import map_connector_payload_to_ingested_event
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.provider_execution_guard import (
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
