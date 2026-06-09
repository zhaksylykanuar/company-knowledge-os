from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.integrations.source_registry import validate_source_event_contract
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.provider_execution_guard import require_live_provider_execution_ack

GITHUB_PROVIDER = "github"
LIVE_EXECUTION_MODE = "live"
SYNTHETIC_EXECUTION_MODE = "synthetic"
RAW_EVENT_SCHEMA_VERSION = "external_connector_raw_event.v1"

GITHUB_REPOSITORY_EVENTS_BOUNDARY = "github_repository_events"
GITHUB_ISSUE_EVENTS_BOUNDARY = "github_issue_events"
GITHUB_PULL_REQUEST_EVENTS_BOUNDARY = "github_pull_request_events"
GITHUB_ORG_REPOSITORY_INVENTORY_BOUNDARY = "github_org_repository_inventory"

GITHUB_CONNECTOR_TRANSPORT_MISSING = "github_connector_transport_missing"
GITHUB_CONNECTOR_MODE_UNSUPPORTED = "github_connector_mode_unsupported"
GITHUB_RAW_EVENT_CONTRACT_INVALID = "github_raw_event_contract_invalid"
GITHUB_ORG_INVENTORY_CONTRACT_INVALID = "github_org_inventory_contract_invalid"

COUNT_ZERO = "zero_count"
COUNT_NONZERO = "nonzero_count"
COUNT_NOT_OBSERVED = "not_observed"
PAYLOAD_VISIBILITY_SUPPRESSED = "suppressed"


@dataclass(frozen=True)
class GitHubConnectorRequest:
    provider_key: str
    operation: str
    source_object_type: str
    event_type: str
    execution_mode: str


GitHubTransport = Callable[
    [GitHubConnectorRequest],
    Iterable[Mapping[str, Any]],
]


class GitHubConnectorError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def connector_diagnostics() -> dict[str, Any]:
    diagnostics = {
        "provider_key": GITHUB_PROVIDER,
        "connector_status": "present/guarded/synthetic_ready",
        "live_calls": "default_denied",
        "source_of_truth_role": "raw_event_source_only",
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "provider_payload_in_diagnostics": False,
    }
    if inspect_operator_output(diagnostics).safe is not True:
        raise GitHubConnectorError(GITHUB_RAW_EVENT_CONTRACT_INVALID)
    return diagnostics


def list_repository_events(
    *,
    transport: GitHubTransport | None = None,
    execution_mode: str = LIVE_EXECUTION_MODE,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> list[dict[str, Any]]:
    return _fetch_raw_events(
        operation="list_repository_events",
        boundary=GITHUB_REPOSITORY_EVENTS_BOUNDARY,
        source_object_type="commit",
        event_type="github.commit.pushed",
        transport=transport,
        execution_mode=execution_mode,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )


def fetch_issue_events(
    *,
    transport: GitHubTransport | None = None,
    execution_mode: str = LIVE_EXECUTION_MODE,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> list[dict[str, Any]]:
    return _fetch_raw_events(
        operation="fetch_issue_events",
        boundary=GITHUB_ISSUE_EVENTS_BOUNDARY,
        source_object_type="issue",
        event_type="github.issue.opened",
        transport=transport,
        execution_mode=execution_mode,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )


def fetch_pull_request_events(
    *,
    transport: GitHubTransport | None = None,
    execution_mode: str = LIVE_EXECUTION_MODE,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> list[dict[str, Any]]:
    return _fetch_raw_events(
        operation="fetch_pull_request_events",
        boundary=GITHUB_PULL_REQUEST_EVENTS_BOUNDARY,
        source_object_type="pull_request",
        event_type="github.pull_request.opened",
        transport=transport,
        execution_mode=execution_mode,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )


def fetch_org_repository_inventory_summary(
    *,
    transport: GitHubTransport | None = None,
    execution_mode: str = LIVE_EXECUTION_MODE,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
    seed_repository_keys: Iterable[str] = (),
    max_results: int = 50,
) -> dict[str, Any]:
    _require_execution_mode(
        boundary=GITHUB_ORG_REPOSITORY_INVENTORY_BOUNDARY,
        execution_mode=execution_mode,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )
    if transport is None:
        raise GitHubConnectorError(GITHUB_CONNECTOR_TRANSPORT_MISSING)

    request = GitHubConnectorRequest(
        provider_key=GITHUB_PROVIDER,
        operation="fetch_org_repository_inventory_summary",
        source_object_type="repository",
        event_type="github.repository.inventory_observed",
        execution_mode=execution_mode,
    )
    observed_repo_keys = _repo_keys_from_payloads(transport(request), max_results)
    seed_repo_keys = {key for key in seed_repository_keys if key}
    matched_count = len(seed_repo_keys & observed_repo_keys)
    missing_count = len(seed_repo_keys - observed_repo_keys)
    extra_count = len(observed_repo_keys - seed_repo_keys)
    summary = {
        "target_org_repo_count_class": _zero_nonzero_count_class(
            len(observed_repo_keys)
        ),
        "matched_seed_count_class": _zero_nonzero_count_class(matched_count),
        "missing_seed_count_class": _zero_nonzero_count_class(missing_count),
        "extra_org_count_class": _zero_nonzero_count_class(extra_count),
        "provider_payload_visibility": PAYLOAD_VISIBILITY_SUPPRESSED,
        "no_send": True,
        "no_source_of_truth_mutation": True,
    }
    if inspect_operator_output(summary).safe is not True:
        raise GitHubConnectorError(GITHUB_ORG_INVENTORY_CONTRACT_INVALID)
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
        source_system=GITHUB_PROVIDER,
        source_object_type=source_object_type,
        event_type=event_type,
        payload=dict(payload),
    ):
        raise GitHubConnectorError(GITHUB_RAW_EVENT_CONTRACT_INVALID)
    return {
        "schema_version": RAW_EVENT_SCHEMA_VERSION,
        "source_system": GITHUB_PROVIDER,
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
    transport: GitHubTransport | None,
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
        raise GitHubConnectorError(GITHUB_CONNECTOR_TRANSPORT_MISSING)

    request = GitHubConnectorRequest(
        provider_key=GITHUB_PROVIDER,
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
            raw_object_ref=f"{GITHUB_PROVIDER}_{operation}_{index}",
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
            provider=GITHUB_PROVIDER,
            boundary=boundary,
            allow_live_provider_execution=allow_live_provider_execution,
            provider_execution_ack=provider_execution_ack,
        )
        return
    if execution_mode == SYNTHETIC_EXECUTION_MODE:
        return
    raise GitHubConnectorError(GITHUB_CONNECTOR_MODE_UNSUPPORTED)


def _repo_keys_from_payloads(
    payloads: Iterable[Mapping[str, Any]],
    max_results: int,
) -> set[str]:
    repo_keys: set[str] = set()
    bounded_max = max(0, min(max_results, 100))
    for index, payload in enumerate(payloads, start=1):
        if index > bounded_max:
            break
        repo_key = payload.get("repo_key")
        if isinstance(repo_key, str) and repo_key:
            repo_keys.add(repo_key)
    return repo_keys


def _zero_nonzero_count_class(count: int) -> str:
    return COUNT_ZERO if count == 0 else COUNT_NONZERO
