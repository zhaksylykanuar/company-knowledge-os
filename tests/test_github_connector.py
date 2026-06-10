from __future__ import annotations

import json

import pytest

from app.connectors import github
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


def test_github_live_execution_default_denies_before_transport_call() -> None:
    transport_called = False

    def forbidden_transport(request: github.GitHubConnectorRequest) -> list[dict[str, str]]:
        nonlocal transport_called
        transport_called = True
        return [_payload()]

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        github.fetch_issue_events(transport=forbidden_transport)

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED
    assert transport_called is False


def test_github_live_execution_requires_exact_ack_before_transport_call() -> None:
    transport_called = False

    def forbidden_transport(request: github.GitHubConnectorRequest) -> list[dict[str, str]]:
        nonlocal transport_called
        transport_called = True
        return [_payload()]

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        github.fetch_pull_request_events(
            transport=forbidden_transport,
            allow_live_provider_execution=True,
            provider_execution_ack="wrong_ack",
        )

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_ACK_REQUIRED
    assert transport_called is False


def test_github_synthetic_issue_fetch_returns_raw_event_source_envelope() -> None:
    request_seen: github.GitHubConnectorRequest | None = None

    def synthetic_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal request_seen
        request_seen = request
        return [_payload()]

    events = github.fetch_issue_events(
        transport=synthetic_transport,
        execution_mode=github.SYNTHETIC_EXECUTION_MODE,
    )

    assert request_seen is not None
    assert request_seen.provider_key == "github"
    assert request_seen.execution_mode == github.SYNTHETIC_EXECUTION_MODE
    assert len(events) == 1
    assert events[0]["source_system"] == "github"
    assert events[0]["source_object_type"] == "issue"
    assert events[0]["event_type"] == "github.issue.opened"
    assert events[0]["connector_boundary"] == "raw_event_source_only"
    assert events[0]["interpreted_truth"] is False
    mapped = map_connector_payload_to_ingested_event(events[0])
    assert mapped.source_system == "github"
    assert mapped.event_type == "github.issue.opened"


def test_github_synthetic_pull_request_fetch_returns_raw_event_source_envelope() -> None:
    events = github.fetch_pull_request_events(
        transport=lambda request: [_payload()],
        execution_mode=github.SYNTHETIC_EXECUTION_MODE,
    )

    assert events[0]["source_system"] == "github"
    assert events[0]["source_object_type"] == "pull_request"
    assert events[0]["event_type"] == "github.pull_request.opened"
    assert events[0]["interpreted_truth"] is False


def test_github_synthetic_repository_fetch_returns_raw_event_source_envelope() -> None:
    events = github.list_repository_events(
        transport=lambda request: [_payload()],
        execution_mode=github.SYNTHETIC_EXECUTION_MODE,
    )

    assert events[0]["source_system"] == "github"
    assert events[0]["source_object_type"] == "commit"
    assert events[0]["event_type"] == "github.commit.pushed"
    assert events[0]["interpreted_truth"] is False


def test_github_raw_event_contract_rejects_invalid_synthetic_payload() -> None:
    with pytest.raises(github.GitHubConnectorError) as exc_info:
        github.fetch_issue_events(
            transport=lambda request: [{"title": ""}],
            execution_mode=github.SYNTHETIC_EXECUTION_MODE,
        )

    assert exc_info.value.reason_code == github.GITHUB_RAW_EVENT_CONTRACT_INVALID


def test_github_connector_diagnostics_are_sanitized_and_json_serializable() -> None:
    diagnostics = github.connector_diagnostics()

    assert diagnostics["provider_key"] == "github"
    assert diagnostics["live_calls"] == "default_denied"
    assert diagnostics["source_of_truth_role"] == "raw_event_source_only"
    assert diagnostics["provider_payload_in_diagnostics"] is False
    json.dumps(diagnostics, sort_keys=True)
    assert inspect_operator_output(diagnostics).safe is True


def test_github_org_inventory_default_denies_before_transport_call() -> None:
    transport_called = False

    def forbidden_transport(request: github.GitHubConnectorRequest) -> list[dict[str, str]]:
        nonlocal transport_called
        transport_called = True
        return [{"repo_key": "synthetic_repo"}]

    with pytest.raises(ProviderExecutionBlockedError) as exc_info:
        github.fetch_org_repository_inventory_summary(
            transport=forbidden_transport,
            seed_repository_keys=("seed_repo",),
        )

    assert exc_info.value.reason_code == PROVIDER_EXECUTION_DEFAULT_DENIED
    assert transport_called is False


def test_github_org_inventory_synthetic_summary_uses_counts_only() -> None:
    summary = github.fetch_org_repository_inventory_summary(
        transport=lambda request: [{"repo_key": "seed_repo"}],
        execution_mode=github.SYNTHETIC_EXECUTION_MODE,
        seed_repository_keys=("seed_repo", "missing_repo"),
    )

    assert summary == {
        "target_org_repo_count_class": "nonzero_count",
        "matched_seed_count_class": "nonzero_count",
        "missing_seed_count_class": "nonzero_count",
        "extra_org_count_class": "zero_count",
        "provider_payload_visibility": "suppressed",
        "no_send": True,
        "no_source_of_truth_mutation": True,
    }
    assert "seed_repo" not in json.dumps(summary, sort_keys=True)
    assert inspect_operator_output(summary).safe is True


def test_github_org_inventory_rejects_malformed_payload_shape() -> None:
    with pytest.raises(github.GitHubConnectorError) as exc_info:
        github.fetch_org_repository_inventory_summary(
            transport=lambda request: ["not-a-repository-payload"],
            execution_mode=github.SYNTHETIC_EXECUTION_MODE,
            seed_repository_keys=("seed_repo",),
        )

    assert exc_info.value.reason_code == "github_response_malformed"


def test_github_org_inventory_rejects_response_contract_mismatch() -> None:
    with pytest.raises(github.GitHubConnectorError) as exc_info:
        github.fetch_org_repository_inventory_summary(
            transport=lambda request: [{"repo_key": ""}],
            execution_mode=github.SYNTHETIC_EXECUTION_MODE,
            seed_repository_keys=("seed_repo",),
        )

    assert exc_info.value.reason_code == "github_response_contract_mismatch"


def test_github_org_inventory_mocked_live_readonly_calls_transport_once() -> None:
    call_count = 0
    request_seen: github.GitHubConnectorRequest | None = None

    def mocked_transport(
        request: github.GitHubConnectorRequest,
    ) -> list[dict[str, str]]:
        nonlocal call_count, request_seen
        call_count += 1
        request_seen = request
        return [{"repo_key": "seed_repo"}, {"repo_key": "extra_repo"}]

    summary = github.fetch_org_repository_inventory_summary(
        transport=mocked_transport,
        execution_mode=github.LIVE_EXECUTION_MODE,
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
        seed_repository_keys=("seed_repo", "missing_repo"),
    )

    assert call_count == 1
    assert request_seen is not None
    assert request_seen.operation == "fetch_org_repository_inventory_summary"
    assert summary["target_org_repo_count_class"] == "nonzero_count"
    assert summary["matched_seed_count_class"] == "nonzero_count"
    assert summary["missing_seed_count_class"] == "nonzero_count"
    assert summary["extra_org_count_class"] == "nonzero_count"
    assert "seed_repo" not in json.dumps(summary, sort_keys=True)
    assert inspect_operator_output(summary).safe is True
