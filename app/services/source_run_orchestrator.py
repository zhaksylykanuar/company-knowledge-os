"""Safe execution layer for Source Control run requests.

The orchestrator drives local lifecycle state only. Connector adapters are
injected behind a small contract and the default adapters are noop/missing
config, so tests and operator runs do not call real providers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services.source_connectors import (
    CONNECTOR_STATUS_FAILED,
    CONNECTOR_STATUS_MISSING_CONFIG,
    CONNECTOR_STATUS_PARTIAL_SUCCEEDED,
    CONNECTOR_STATUS_SKIPPED,
    CONNECTOR_STATUS_SUCCEEDED,
    ConnectorRunResult,
    SourceConnector,
    default_connector_registry,
)
from app.services.source_ingestion import ingest_connector_events
from app.services.source_control import (
    ACTION_BACKFILL,
    ACTION_SYNC,
    ACTION_TEST,
    SOURCE_ACTIONS,
    STATUS_CONNECTED,
    STATUS_DEGRADED,
    STATUS_DISABLED,
    STATUS_DISCONNECTED,
    STATUS_ERROR,
    SOURCE_BY_TYPE,
)

REQUEST_STATUS_ACCEPTED = "accepted"
REQUEST_STATUS_BLOCKED = "blocked"
REQUEST_STATUS_FAILED = "failed"
REQUEST_STATUS_PARTIAL_SUCCEEDED = "partial_succeeded"
REQUEST_STATUS_REQUESTED = "requested"
REQUEST_STATUS_RUNNING = "running"
REQUEST_STATUS_SKIPPED = "skipped"
REQUEST_STATUS_SUCCEEDED = "succeeded"

PENDING_REQUEST_STATUSES = (REQUEST_STATUS_REQUESTED, REQUEST_STATUS_ACCEPTED)
TERMINAL_REQUEST_STATUSES = {
    REQUEST_STATUS_BLOCKED,
    REQUEST_STATUS_FAILED,
    REQUEST_STATUS_PARTIAL_SUCCEEDED,
    REQUEST_STATUS_SKIPPED,
    REQUEST_STATUS_SUCCEEDED,
}
EXECUTABLE_ACTIONS = (ACTION_TEST, ACTION_SYNC, ACTION_BACKFILL)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _state_snapshot(state: SourceControlState | None) -> dict[str, Any]:
    if state is None:
        return {}
    return {
        "source_type": state.source_type,
        "status": state.status,
        "paused": state.paused,
        "last_action": state.last_action,
        "last_action_at": _iso(state.last_action_at),
        "last_sync_at": _iso(state.last_sync_at),
        "last_success_at": _iso(state.last_success_at),
        "last_error_at": _iso(state.last_error_at),
        "input_watermark": state.input_watermark,
        "latest_run_id": state.latest_run_id,
    }


async def _get_or_create_state(
    session: AsyncSession,
    *,
    source_type: str,
) -> SourceControlState:
    state = await session.scalar(
        select(SourceControlState).where(SourceControlState.source_type == source_type)
    )
    if state is not None:
        return state
    state = SourceControlState(source_type=source_type, status=STATUS_DISCONNECTED)
    session.add(state)
    await session.flush()
    return state


def _audit(
    *,
    event_type: str,
    request: SourceRunRequest,
    payload: dict[str, Any],
) -> AuditLog:
    correlation_id = request.correlation_id or request.run_id or request.request_id
    return AuditLog(
        event_type=event_type,
        actor=request.requested_by or "founder",
        correlation_id=correlation_id,
        trace_id=correlation_id,
        before_ref=f"source:{request.source_type}",
        after_ref=f"source_run_request:{request.request_id}",
        payload=payload,
    )


def _result_summary(result: ConnectorRunResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "source_type": result.source_type,
        "action_type": result.action_type,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "input_watermark": result.input_watermark,
        "output_watermark": result.output_watermark,
        "events_seen": result.events_seen,
        "events_ingested": result.events_ingested,
        "normalized_events": result.normalized_events,
        "graph_updates": result.graph_updates,
        "findings_generated": result.findings_generated,
        "proposals_generated": result.proposals_generated,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
        "external_side_effect": result.external_side_effect,
        "sanitized_summary": dict(result.sanitized_summary),
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "requested": 0,
        "started": 0,
        "succeeded": 0,
        "partial_succeeded": 0,
        "failed": 0,
        "skipped_paused": 0,
        "skipped_missing_config": 0,
        "skipped_real_disabled": 0,
        "blocked_invalid": 0,
        "events_seen": 0,
        "events_ingested": 0,
        "duplicates_skipped": 0,
        "normalized_events": 0,
        "normalization_errors": 0,
        "failed_events": 0,
        "graph_updates": 0,
        "findings_generated": 0,
        "proposals_generated": 0,
        "unchanged": 0,
        "errors": 0,
        "run_started_at": None,
        "run_finished_at": None,
        "correlation_id": None,
        "run_id": None,
        "results": [],
    }


def _bump(summary: dict[str, Any], key: str) -> None:
    summary[key] = int(summary.get(key) or 0) + 1


def _add_count(summary: dict[str, Any], key: str, value: Any) -> None:
    summary[key] = int(summary.get(key) or 0) + int(value or 0)


def _ingestion_from_request(request: SourceRunRequest) -> dict[str, Any]:
    result = request.result_summary if isinstance(request.result_summary, dict) else {}
    sanitized = result.get("sanitized_summary") if isinstance(result, dict) else {}
    if not isinstance(sanitized, dict):
        return {}
    ingestion = sanitized.get("ingestion")
    return ingestion if isinstance(ingestion, dict) else {}


def _run_mode(request: SourceRunRequest) -> str | None:
    result = request.result_summary if isinstance(request.result_summary, dict) else {}
    sanitized = result.get("sanitized_summary") if isinstance(result, dict) else {}
    return sanitized.get("mode") if isinstance(sanitized, dict) else None


async def pending_source_requests(
    session: AsyncSession,
    *,
    limit: int = 25,
) -> list[SourceRunRequest]:
    rows = (
        await session.execute(
            select(SourceRunRequest)
            .where(SourceRunRequest.status.in_(PENDING_REQUEST_STATUSES))
            .where(SourceRunRequest.action_type.in_(EXECUTABLE_ACTIONS))
            .order_by(SourceRunRequest.created_at.asc(), SourceRunRequest.id.asc())
            .limit(limit)
        )
    ).scalars()
    return list(rows)


async def run_source_request(
    session: AsyncSession,
    *,
    request: SourceRunRequest,
    connectors: dict[str, SourceConnector] | None = None,
    run_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    safe_now = now or _now()
    registry = connectors or default_connector_registry(session=session)

    if request.status in TERMINAL_REQUEST_STATUSES:
        return {"request_id": request.request_id, "status": "unchanged"}

    if request.source_type not in SOURCE_BY_TYPE or request.action_type not in SOURCE_ACTIONS:
        state = await session.scalar(
            select(SourceControlState).where(
                SourceControlState.source_type == request.source_type
            )
        )
        request.source_state_before = _state_snapshot(state)
        request.status = REQUEST_STATUS_BLOCKED
        request.finished_at = safe_now
        request.result_summary = {
            "status": "blocked_invalid",
            "reason": "unknown_source_or_action",
            "external_side_effect": False,
        }
        request.error_summary = {"error": "unknown_source_or_action"}
        request.source_state_after = _state_snapshot(state)
        session.add(
            _audit(
                event_type="source_run_blocked",
                request=request,
                payload={
                    "status": "blocked_invalid",
                    "source_type": request.source_type,
                    "action_type": request.action_type,
                    "external_side_effect": False,
                },
            )
        )
        await session.flush()
        return {"request_id": request.request_id, "status": "blocked_invalid"}

    state = await _get_or_create_state(session, source_type=request.source_type)
    request.source_state_before = _state_snapshot(state)

    if request.action_type in {ACTION_SYNC, ACTION_BACKFILL} and (
        state.paused or state.status == STATUS_DISABLED
    ):
        request.status = REQUEST_STATUS_BLOCKED
        request.finished_at = safe_now
        request.result_summary = {
            "status": "skipped_paused",
            "reason": "source_paused",
            "external_side_effect": False,
        }
        request.error_summary = {}
        request.source_state_after = _state_snapshot(state)
        session.add(
            _audit(
                event_type="source_run_blocked",
                request=request,
                payload={
                    "status": "skipped_paused",
                    "source_type": request.source_type,
                    "action_type": request.action_type,
                    "external_side_effect": False,
                },
            )
        )
        await session.flush()
        return {"request_id": request.request_id, "status": "skipped_paused"}

    connector = registry.get(request.source_type)
    if connector is None:
        request.status = REQUEST_STATUS_BLOCKED
        request.finished_at = safe_now
        request.result_summary = {
            "status": "blocked_invalid",
            "reason": "missing_connector_adapter",
            "external_side_effect": False,
        }
        request.error_summary = {"error": "missing_connector_adapter"}
        request.source_state_after = _state_snapshot(state)
        session.add(
            _audit(
                event_type="source_run_blocked",
                request=request,
                payload={
                    "status": "blocked_invalid",
                    "source_type": request.source_type,
                    "action_type": request.action_type,
                    "external_side_effect": False,
                },
            )
        )
        await session.flush()
        return {"request_id": request.request_id, "status": "blocked_invalid"}

    active_run_id = run_id or f"src_run_{uuid4().hex}"
    request.run_id = active_run_id
    request.correlation_id = request.correlation_id or active_run_id
    request.idempotency_key = request.idempotency_key or (
        f"{request.source_type}:{request.action_type}:{request.request_key}"
    )
    request.status = REQUEST_STATUS_RUNNING
    request.started_at = safe_now
    state.latest_run_id = active_run_id
    state.last_action = request.action_type
    state.last_action_at = safe_now
    state.last_request_key = request.request_key
    session.add(
        _audit(
            event_type="source_run_started",
            request=request,
            payload={
                "run_id": active_run_id,
                "source_type": request.source_type,
                "action_type": request.action_type,
                "external_side_effect": False,
            },
        )
    )
    await session.flush()

    try:
        if request.action_type == ACTION_TEST:
            result = await connector.test_connection()
        elif request.action_type == ACTION_SYNC:
            result = await connector.sync(watermark=state.input_watermark)
        else:
            input_data = request.input_snapshot.get("input") or {}
            result = await connector.backfill(
                since=input_data.get("since"),
                until=input_data.get("until"),
                limit=input_data.get("limit"),
            )
    except Exception as exc:  # noqa: BLE001 - fail closed into persisted state.
        finished = _now()
        request.status = REQUEST_STATUS_FAILED
        request.finished_at = finished
        request.external_side_effect = False
        request.error_summary = {
            "error_type": type(exc).__name__,
            "message": "connector adapter failed",
        }
        request.result_summary = {
            "status": CONNECTOR_STATUS_FAILED,
            "source_type": request.source_type,
            "action_type": request.action_type,
            "finished_at": finished.isoformat(),
            "external_side_effect": False,
            "sanitized_summary": {"mode": "adapter_exception"},
        }
        state.status = STATUS_ERROR
        state.last_error_at = finished
        state.latest_run_id = active_run_id
        request.source_state_after = _state_snapshot(state)
        session.add(
            _audit(
                event_type="source_run_finished",
                request=request,
                payload={
                    "run_id": active_run_id,
                    "status": REQUEST_STATUS_FAILED,
                    "source_type": request.source_type,
                    "action_type": request.action_type,
                    "external_side_effect": False,
                    "error_type": type(exc).__name__,
                },
            )
        )
        await session.flush()
        return {"request_id": request.request_id, "status": REQUEST_STATUS_FAILED}

    finished = result.finished_at
    ingestion_summary: dict[str, Any] = {}
    if (
        request.action_type in {ACTION_SYNC, ACTION_BACKFILL}
        and result.status == CONNECTOR_STATUS_SUCCEEDED
        and result.events
    ):
        ingestion_summary = await ingest_connector_events(
            session,
            events=list(result.events),
            run_id=active_run_id,
            correlation_id=request.correlation_id,
            normalize=True,
        )
        result = ConnectorRunResult(
            status=(
                CONNECTOR_STATUS_PARTIAL_SUCCEEDED
                if ingestion_summary.get("failed_events")
                or ingestion_summary.get("normalization_errors")
                else result.status
            ),
            source_type=result.source_type,
            action_type=result.action_type,
            started_at=result.started_at,
            finished_at=result.finished_at,
            input_watermark=result.input_watermark,
            output_watermark=result.output_watermark,
            events_seen=int(ingestion_summary.get("events_seen") or result.events_seen),
            events_ingested=int(ingestion_summary.get("events_ingested") or 0),
            normalized_events=int(ingestion_summary.get("normalized_events") or 0),
            graph_updates=result.graph_updates,
            findings_generated=result.findings_generated,
            proposals_generated=result.proposals_generated,
            errors=list(result.errors),
            warnings=[*result.warnings, *ingestion_summary.get("warnings", [])],
            external_side_effect=result.external_side_effect,
            sanitized_summary={
                **result.sanitized_summary,
                "ingestion": ingestion_summary,
            },
            events=list(result.events),
        )
    request.finished_at = finished
    request.external_side_effect = bool(result.external_side_effect)
    request.result_summary = _result_summary(result)
    request.error_summary = {"errors": list(result.errors)} if result.errors else {}

    if result.status == CONNECTOR_STATUS_SUCCEEDED:
        request.status = REQUEST_STATUS_SUCCEEDED
        state.status = STATUS_CONNECTED
        state.last_success_at = finished
        if request.action_type == ACTION_SYNC:
            state.last_sync_at = finished
        if request.action_type == ACTION_SYNC and result.output_watermark:
            state.input_watermark = result.output_watermark
    elif result.status == CONNECTOR_STATUS_PARTIAL_SUCCEEDED:
        request.status = REQUEST_STATUS_PARTIAL_SUCCEEDED
        state.status = STATUS_DEGRADED
        state.last_success_at = finished
        state.last_error_at = finished
    elif result.status == CONNECTOR_STATUS_MISSING_CONFIG:
        request.status = REQUEST_STATUS_SKIPPED
        state.status = STATUS_DEGRADED
        state.last_error_at = finished
    elif result.status == CONNECTOR_STATUS_SKIPPED:
        request.status = REQUEST_STATUS_SKIPPED
        state.status = STATUS_DEGRADED
    else:
        request.status = REQUEST_STATUS_FAILED
        state.status = STATUS_ERROR
        state.last_error_at = finished

    state.latest_run_id = active_run_id
    request.source_state_after = _state_snapshot(state)
    session.add(
        _audit(
            event_type="source_run_finished",
            request=request,
            payload={
                "run_id": active_run_id,
                "status": request.status,
                "connector_status": result.status,
                "ingestion": ingestion_summary,
                "source_type": request.source_type,
                "action_type": request.action_type,
                "external_side_effect": result.external_side_effect,
                "warnings": list(result.warnings),
            },
        )
    )
    await session.flush()
    return {
        "request_id": request.request_id,
        "run_id": active_run_id,
        "status": request.status,
        "connector_status": result.status,
    }


async def run_source_requests(
    session: AsyncSession,
    *,
    connectors: dict[str, SourceConnector] | None = None,
    limit: int = 25,
    now: datetime | None = None,
) -> dict[str, Any]:
    started = now or _now()
    run_id = f"src_orch_{uuid4().hex}"
    summary = _empty_summary()
    summary["run_started_at"] = started.isoformat()
    summary["correlation_id"] = run_id
    summary["run_id"] = run_id
    requests = await pending_source_requests(session, limit=limit)
    summary["requested"] = len(requests)
    for request in requests:
        result = await run_source_request(
            session,
            request=request,
            connectors=connectors,
            run_id=f"{run_id}_{request.id or request.request_id}",
            now=_now(),
        )
        status = result.get("status")
        if status == "unchanged":
            _bump(summary, "unchanged")
        elif status == "skipped_paused":
            _bump(summary, "skipped_paused")
        elif status == "blocked_invalid":
            _bump(summary, "blocked_invalid")
        elif status == REQUEST_STATUS_SUCCEEDED:
            _bump(summary, "started")
            _bump(summary, "succeeded")
        elif status == REQUEST_STATUS_PARTIAL_SUCCEEDED:
            _bump(summary, "started")
            _bump(summary, "partial_succeeded")
            _bump(summary, "errors")
        elif status == REQUEST_STATUS_FAILED:
            _bump(summary, "started")
            _bump(summary, "failed")
            _bump(summary, "errors")
        elif status == REQUEST_STATUS_SKIPPED:
            _bump(summary, "started")
            if result.get("connector_status") == CONNECTOR_STATUS_MISSING_CONFIG:
                _bump(summary, "skipped_missing_config")
            elif _run_mode(request) == "real_connectors_disabled":
                _bump(summary, "skipped_real_disabled")
            else:
                _bump(summary, "unchanged")
        else:
            _bump(summary, "unchanged")
        ingestion = _ingestion_from_request(request)
        for key in (
            "events_seen",
            "events_ingested",
            "duplicates_skipped",
            "normalized_events",
            "normalization_errors",
            "failed_events",
        ):
            _add_count(summary, key, ingestion.get(key))
        summary["results"].append(result)
    summary["run_finished_at"] = _now().isoformat()
    return summary
