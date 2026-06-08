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

JIRA_CONNECTOR_TRANSPORT_MISSING = "jira_connector_transport_missing"
JIRA_CONNECTOR_MODE_UNSUPPORTED = "jira_connector_mode_unsupported"
JIRA_RAW_EVENT_CONTRACT_INVALID = "jira_raw_event_contract_invalid"


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
