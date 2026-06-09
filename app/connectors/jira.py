from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.integrations.source_registry import validate_source_event_contract
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.provider_execution_guard import require_live_provider_execution_ack

JIRA_PROVIDER = "jira"
LIVE_EXECUTION_MODE = "live"
SYNTHETIC_EXECUTION_MODE = "synthetic"
RAW_EVENT_SCHEMA_VERSION = "external_connector_raw_event.v1"

JIRA_ISSUE_EVENTS_BOUNDARY = "jira_issue_events"
JIRA_PROJECT_ISSUE_EVENTS_BOUNDARY = "jira_project_issue_events"
JIRA_READONLY_INVENTORY_BOUNDARY = "jira_readonly_inventory"

JIRA_CONNECTOR_TRANSPORT_MISSING = "jira_connector_transport_missing"
JIRA_CONNECTOR_MODE_UNSUPPORTED = "jira_connector_mode_unsupported"
JIRA_RAW_EVENT_CONTRACT_INVALID = "jira_raw_event_contract_invalid"
JIRA_INVENTORY_RESPONSE_CONTRACT_INVALID = "jira_inventory_response_contract_invalid"

COUNT_NOT_OBSERVED = "not_observed"
COUNT_ZERO = "zero_count"
COUNT_NONZERO = "nonzero_count"
INVENTORY_RESPONSE_CONTRACT_PASS = "pass"
PROVIDER_PAYLOAD_VISIBILITY_SUPPRESSED = "suppressed"


@dataclass(frozen=True)
class JiraConnectorRequest:
    provider_key: str
    operation: str
    source_object_type: str
    event_type: str
    execution_mode: str


JiraTransport = Callable[
    [JiraConnectorRequest],
    Iterable[Mapping[str, Any]],
]


class JiraConnectorError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def connector_diagnostics() -> dict[str, Any]:
    diagnostics = {
        "provider_key": JIRA_PROVIDER,
        "connector_status": "present/guarded/synthetic_ready",
        "live_calls": "default_denied",
        "source_of_truth_role": "raw_event_source_only",
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "provider_payload_in_diagnostics": False,
    }
    if inspect_operator_output(diagnostics).safe is not True:
        raise JiraConnectorError(JIRA_RAW_EVENT_CONTRACT_INVALID)
    return diagnostics


def search_issue_events(
    *,
    transport: JiraTransport | None = None,
    execution_mode: str = LIVE_EXECUTION_MODE,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> list[dict[str, Any]]:
    return _fetch_raw_events(
        operation="search_issue_events",
        boundary=JIRA_ISSUE_EVENTS_BOUNDARY,
        source_object_type="issue",
        event_type="jira.issue.updated",
        transport=transport,
        execution_mode=execution_mode,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )


def fetch_project_issue_events(
    *,
    transport: JiraTransport | None = None,
    execution_mode: str = LIVE_EXECUTION_MODE,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> list[dict[str, Any]]:
    return _fetch_raw_events(
        operation="fetch_project_issue_events",
        boundary=JIRA_PROJECT_ISSUE_EVENTS_BOUNDARY,
        source_object_type="issue",
        event_type="jira.issue.created",
        transport=transport,
        execution_mode=execution_mode,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )


def fetch_readonly_inventory_summary(
    *,
    transport: JiraTransport | None = None,
    execution_mode: str = LIVE_EXECUTION_MODE,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
    max_results: int = 50,
) -> dict[str, Any]:
    _require_execution_mode(
        boundary=JIRA_READONLY_INVENTORY_BOUNDARY,
        execution_mode=execution_mode,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )
    if transport is None:
        raise JiraConnectorError(JIRA_CONNECTOR_TRANSPORT_MISSING)

    request = JiraConnectorRequest(
        provider_key=JIRA_PROVIDER,
        operation="fetch_readonly_inventory_summary",
        source_object_type="project",
        event_type="jira.inventory.observed",
        execution_mode=execution_mode,
    )
    payloads = list(transport(request))
    if any(not isinstance(payload, Mapping) for payload in payloads):
        raise JiraConnectorError(JIRA_INVENTORY_RESPONSE_CONTRACT_INVALID)

    bounded_payloads = payloads[: _safe_max_results(max_results)]
    project_count = len(bounded_payloads)
    accessible_count = sum(
        1 for payload in bounded_payloads if payload.get("accessible", True) is True
    )
    inaccessible_count = sum(
        1 for payload in bounded_payloads if payload.get("accessible") is False
    )
    permission_limited_count = sum(
        1 for payload in bounded_payloads if payload.get("permission_limited") is True
    )
    issue_count_observed = any(
        isinstance(payload.get("issue_count"), int) and payload.get("issue_count", 0) >= 0
        for payload in bounded_payloads
    )
    issue_count_total = sum(
        int(payload.get("issue_count", 0))
        for payload in bounded_payloads
        if isinstance(payload.get("issue_count"), int) and payload.get("issue_count", 0) >= 0
    )
    summary = {
        "provider_key": JIRA_PROVIDER,
        "project_count": project_count,
        "project_count_class": _zero_nonzero_count_class(project_count),
        "accessible_project_count_class": _zero_nonzero_count_class(accessible_count),
        "inaccessible_project_count_class": _zero_nonzero_count_class(inaccessible_count),
        "permission_limited_count_class": _zero_nonzero_count_class(
            permission_limited_count
        ),
        "issue_count_class": _zero_nonzero_count_class(issue_count_total)
        if issue_count_observed
        else COUNT_NOT_OBSERVED,
        "response_contract_status": INVENTORY_RESPONSE_CONTRACT_PASS,
        "provider_payload_visibility": PROVIDER_PAYLOAD_VISIBILITY_SUPPRESSED,
        "max_results_class": "bounded",
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
    }
    if inspect_operator_output(summary).safe is not True:
        raise JiraConnectorError(JIRA_INVENTORY_RESPONSE_CONTRACT_INVALID)
    return summary


def build_raw_event_envelope(
    *,
    source_object_type: str,
    event_type: str,
    payload: Mapping[str, Any],
    source_object_id: str,
    idempotency_key: str,
    raw_object_ref: str,
) -> dict[str, Any]:
    if validate_source_event_contract(
        source_system=JIRA_PROVIDER,
        source_object_type=source_object_type,
        event_type=event_type,
        payload=dict(payload),
    ):
        raise JiraConnectorError(JIRA_RAW_EVENT_CONTRACT_INVALID)
    return {
        "schema_version": RAW_EVENT_SCHEMA_VERSION,
        "source_system": JIRA_PROVIDER,
        "source_object_type": source_object_type,
        "event_type": event_type,
        "source_object_id": source_object_id,
        "idempotency_key": idempotency_key,
        "raw_object_ref": raw_object_ref,
        "payload": dict(payload),
        "connector_boundary": "raw_event_source_only",
        "interpreted_truth": False,
    }


def _fetch_raw_events(
    *,
    operation: str,
    boundary: str,
    source_object_type: str,
    event_type: str,
    transport: JiraTransport | None,
    execution_mode: str,
    allow_live_provider_execution: bool,
    provider_execution_ack: str | None,
) -> list[dict[str, Any]]:
    _require_execution_mode(
        boundary=boundary,
        execution_mode=execution_mode,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )
    if transport is None:
        raise JiraConnectorError(JIRA_CONNECTOR_TRANSPORT_MISSING)

    request = JiraConnectorRequest(
        provider_key=JIRA_PROVIDER,
        operation=operation,
        source_object_type=source_object_type,
        event_type=event_type,
        execution_mode=execution_mode,
    )
    return [
        build_raw_event_envelope(
            source_object_type=source_object_type,
            event_type=event_type,
            payload=payload,
            source_object_id=f"{operation}_{index}",
            idempotency_key=f"{event_type}_{index}",
            raw_object_ref=f"{JIRA_PROVIDER}_{operation}_{index}",
        )
        for index, payload in enumerate(transport(request), start=1)
    ]


def _require_execution_mode(
    *,
    boundary: str,
    execution_mode: str,
    allow_live_provider_execution: bool,
    provider_execution_ack: str | None,
) -> None:
    if execution_mode == LIVE_EXECUTION_MODE:
        require_live_provider_execution_ack(
            provider=JIRA_PROVIDER,
            boundary=boundary,
            allow_live_provider_execution=allow_live_provider_execution,
            provider_execution_ack=provider_execution_ack,
        )
        return
    if execution_mode == SYNTHETIC_EXECUTION_MODE:
        return
    raise JiraConnectorError(JIRA_CONNECTOR_MODE_UNSUPPORTED)


def _safe_max_results(value: int) -> int:
    if not isinstance(value, int):
        return 50
    return min(max(value, 1), 100)


def _zero_nonzero_count_class(count: int) -> str:
    return COUNT_ZERO if count == 0 else COUNT_NONZERO
