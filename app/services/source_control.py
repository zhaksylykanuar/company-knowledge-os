"""Source Control Center read model and safe action requests.

This layer never calls external connectors. It summarizes what the database
already knows, reports masked connector readiness, and records requested
test/sync/backfill/pause/resume actions with audit/idempotency.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.agent_models import AgentProposal, AgentRunLog, DataAvailability
from app.db.declaration_models import FounderDeclaration
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import AuditLog, IngestedEvent
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.share_pack_models import SharePack
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.db.source_models import SourceDocument
from app.services.browser_config import sanitize_for_logs
from app.services.source_run_receipts import build_source_run_receipt

ACTION_BACKFILL = "backfill"
ACTION_PAUSE = "pause"
ACTION_PREVIEW_SYNC = "preview_sync"
ACTION_RESUME = "resume"
ACTION_SYNC = "sync"
ACTION_TEST = "test"
SOURCE_ACTIONS = (
    ACTION_TEST,
    ACTION_PREVIEW_SYNC,
    ACTION_SYNC,
    ACTION_BACKFILL,
    ACTION_PAUSE,
    ACTION_RESUME,
)

STATUS_CONNECTED = "connected"
STATUS_DEGRADED = "degraded"
STATUS_DISABLED = "disabled"
STATUS_DISCONNECTED = "disconnected"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class SourceDefinition:
    source_type: str
    label: str
    event_systems: tuple[str, ...] = ()
    normalized_sources: tuple[str, ...] = ()
    metric_prefixes: tuple[str, ...] = ()
    setup_groups: tuple[str, ...] = ()
    virtual: bool = False


SOURCE_DEFINITIONS: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        "jira",
        "Jira",
        event_systems=("jira",),
        normalized_sources=("jira",),
        metric_prefixes=("jira.",),
        setup_groups=("jira",),
    ),
    SourceDefinition(
        "github",
        "GitHub",
        event_systems=("github",),
        normalized_sources=("github",),
        setup_groups=("github",),
    ),
    SourceDefinition(
        "gmail",
        "Gmail / Email",
        event_systems=("gmail",),
        normalized_sources=("gmail",),
        setup_groups=("gmail",),
    ),
    SourceDefinition(
        "meetings",
        "Meetings",
        event_systems=("calendar", "meeting", "meetings", "drive"),
        normalized_sources=("calendar", "meeting", "meetings", "drive"),
        setup_groups=("meetings",),
    ),
    SourceDefinition("declarations", "Declarations", virtual=True),
    SourceDefinition(
        "manual_inputs",
        "Manual inputs",
        event_systems=("manual",),
        normalized_sources=("manual",),
        setup_groups=("manual_inputs",),
        virtual=True,
    ),
    SourceDefinition(
        "generated_evidence",
        "Generated evidence",
        setup_groups=("generated_evidence",),
        virtual=True,
    ),
    SourceDefinition(
        "share_packs",
        "Share packs / curated outputs",
        setup_groups=("share_packs",),
        virtual=True,
    ),
)

SOURCE_BY_TYPE = {definition.source_type: definition for definition in SOURCE_DEFINITIONS}
_FAILED_EVENT_STATUSES = {"error", "failed", "normalization_failed"}
_PENDING_REQUEST_STATUSES = {"requested", "accepted"}


def known_source_types() -> tuple[str, ...]:
    return tuple(SOURCE_BY_TYPE)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _configured(*names: str, attrs: tuple[str, ...] = ()) -> bool:
    for attr in attrs:
        value = getattr(settings, attr, None)
        if isinstance(value, str) and value.strip():
            return True
    return any(bool(os.getenv(name)) for name in names)


def _setup_item(name: str, *, configured: bool, secret: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "status": "masked" if secret and configured else ("configured" if configured else "missing"),
        "secret": secret,
    }


def _connector_setup() -> dict[str, list[dict[str, Any]]]:
    return {
        "jira": [
            _setup_item("JIRA_BASE_URL", configured=_configured("JIRA_BASE_URL", attrs=("jira_base_url",))),
            _setup_item("JIRA_EMAIL", configured=_configured("JIRA_EMAIL", attrs=("jira_email",))),
            _setup_item(
                "JIRA_API_TOKEN",
                configured=_configured("JIRA_API_TOKEN", attrs=("jira_api_token",)),
                secret=True,
            ),
        ],
        "github": [
            _setup_item(
                "GITHUB_TOKEN",
                configured=_configured("GITHUB_TOKEN", "FOS_GITHUB_READONLY_TOKEN"),
                secret=True,
            )
        ],
        "gmail": [
            _setup_item(
                "GMAIL_CLIENT_ID",
                configured=_configured("GMAIL_CLIENT_ID", "FOS_GMAIL_READONLY_CLIENT_ID"),
            ),
            _setup_item(
                "GMAIL_CLIENT_SECRET",
                configured=_configured(
                    "GMAIL_CLIENT_SECRET",
                    "FOS_GMAIL_READONLY_CLIENT_SECRET",
                ),
                secret=True,
            ),
            _setup_item(
                "OAuth token",
                configured=_configured("GOOGLE_GMAIL_TOKEN_FILE", attrs=("google_gmail_token_file",)),
                secret=True,
            ),
        ],
        "meetings": [
            _setup_item(
                "MEETINGS_SOURCE",
                configured=_configured("MEETINGS_SOURCE", "GOOGLE_CALENDAR_TOKEN_FILE"),
            )
        ],
        "manual_inputs": [_setup_item("Manual ingestion", configured=True)],
        "generated_evidence": [_setup_item("Internal agents", configured=True)],
        "share_packs": [_setup_item("Curated outputs", configured=True)],
    }


def _setup_for(definition: SourceDefinition) -> list[dict[str, Any]]:
    groups = _connector_setup()
    items: list[dict[str, Any]] = []
    for group in definition.setup_groups:
        items.extend(groups.get(group, []))
    return items


def connector_setup_for_source(source_type: str) -> list[dict[str, Any]]:
    definition = SOURCE_BY_TYPE.get(source_type)
    if definition is None:
        raise ValueError(f"unknown source: {source_type}")
    return _setup_for(definition)


def _setup_status(items: list[dict[str, Any]]) -> str:
    if not items:
        return "not_required"
    if all(item["status"] in {"configured", "masked"} for item in items):
        return "ready"
    if any(item["status"] in {"configured", "masked"} for item in items):
        return "partial"
    return "missing"


def connector_setup_status(source_type: str) -> str:
    return _setup_status(connector_setup_for_source(source_type))


def _visibility_policy() -> dict[str, Any]:
    return {
        "founder": "full sanitized event metadata; raw_object_ref allowed",
        "team": "working sanitized fields only; raw refs hidden",
        "investor": "source events hidden",
    }


def _redaction_policy() -> dict[str, Any]:
    return {
        "raw_bodies": "never returned",
        "external_tokens": "never returned",
        "connection_status": "configured/missing/masked only",
    }


def _safe_actions(definition: SourceDefinition) -> list[dict[str, Any]]:
    actions = [
        ("test", "Test connection"),
        ("preview_sync", "Preview sync"),
        ("sync", "Sync now"),
        ("backfill", "Backfill"),
        ("pause", "Pause source"),
        ("resume", "Resume source"),
        ("events", "View events"),
        ("errors", "View errors"),
        ("evidence", "Open evidence explorer"),
    ]
    return [
        {
            "action": action,
            "label": label,
            "safe_mode": action in SOURCE_ACTIONS,
            "external_side_effect": False,
            "requires_confirmation": action in {ACTION_BACKFILL, ACTION_PAUSE},
        }
        for action, label in actions
    ]


async def _group_counts(
    session: AsyncSession,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, int]]:
    event_rows = (
        await session.execute(
            select(
                SourceEvent.source_system,
                func.count(SourceEvent.id),
                func.max(SourceEvent.created_at),
                func.max(SourceEvent.source_event_ts),
            ).group_by(SourceEvent.source_system)
        )
    ).all()
    events = {
        str(source): {
            "count": int(count or 0),
            "last_received_at": last.isoformat() if last else None,
            "last_source_event_at": last_source.isoformat() if last_source else None,
        }
        for source, count, last, last_source in event_rows
    }
    normalized_rows = (
        await session.execute(
            select(
                NormalizedActivityItemRecord.source,
                func.count(NormalizedActivityItemRecord.id),
                func.max(NormalizedActivityItemRecord.created_at),
            ).group_by(NormalizedActivityItemRecord.source)
        )
    ).all()
    normalized = {
        str(source): {
            "count": int(count or 0),
            "last_normalized_at": last.isoformat() if last else None,
        }
        for source, count, last in normalized_rows
    }
    failed_rows = (
        await session.execute(
            select(IngestedEvent.source_system, func.count(IngestedEvent.id))
            .where(IngestedEvent.status.in_(_FAILED_EVENT_STATUSES))
            .group_by(IngestedEvent.source_system)
        )
    ).all()
    failed = {str(source): int(count or 0) for source, count in failed_rows}
    return events, normalized, failed


async def _virtual_counts(session: AsyncSession) -> dict[str, dict[str, Any]]:
    declarations_count = await session.scalar(
        select(func.count(FounderDeclaration.id))
    )
    declarations_last = await session.scalar(
        select(func.max(FounderDeclaration.updated_at))
    )
    manual_documents = await session.scalar(
        select(func.count(SourceDocument.id)).where(SourceDocument.source_system == "manual")
    )
    findings_count = await session.scalar(select(func.count(SecondOpinionFinding.id)))
    findings_last = await session.scalar(select(func.max(SecondOpinionFinding.updated_at)))
    proposals_count = await session.scalar(select(func.count(AgentProposal.id)))
    packs_count = await session.scalar(select(func.count(SharePack.id)))
    packs_last = await session.scalar(select(func.max(SharePack.updated_at)))
    return {
        "declarations": {
            "events_ingested": int(declarations_count or 0),
            "last_sync_at": declarations_last.isoformat() if declarations_last else None,
            "last_success_at": declarations_last.isoformat() if declarations_last else None,
        },
        "manual_inputs": {"events_ingested": int(manual_documents or 0)},
        "generated_evidence": {
            "findings_generated": int(findings_count or 0),
            "proposals_generated": int(proposals_count or 0),
            "last_sync_at": findings_last.isoformat() if findings_last else None,
            "last_success_at": findings_last.isoformat() if findings_last else None,
        },
        "share_packs": {
            "proposals_generated": int(packs_count or 0),
            "last_sync_at": packs_last.isoformat() if packs_last else None,
            "last_success_at": packs_last.isoformat() if packs_last else None,
        },
    }


async def _findings_for_source(session: AsyncSession, definition: SourceDefinition) -> int:
    if definition.source_type == "generated_evidence":
        return int(await session.scalar(select(func.count(SecondOpinionFinding.id))) or 0)
    if not definition.event_systems:
        return 0
    total = 0
    for source in definition.event_systems:
        total += int(
            await session.scalar(
                select(func.count(SecondOpinionFinding.id)).where(
                    cast(SecondOpinionFinding.evidence_refs, Text).like(f"%{source}%")
                )
            )
            or 0
        )
    return total


async def _proposals_for_source(session: AsyncSession, definition: SourceDefinition) -> int:
    if definition.source_type == "generated_evidence":
        return int(await session.scalar(select(func.count(AgentProposal.id))) or 0)
    if definition.source_type == "share_packs":
        return int(await session.scalar(select(func.count(SharePack.id))) or 0)
    if not definition.event_systems:
        return 0
    total = 0
    for source in definition.event_systems:
        total += int(
            await session.scalar(
                select(func.count(AgentProposal.id)).where(
                    cast(AgentProposal.evidence_refs, Text).like(f"%{source}%")
                )
            )
            or 0
        )
    return total


def _runs_for_source(
    runs: list[AgentRunLog],
    definition: SourceDefinition,
) -> list[AgentRunLog]:
    tokens = {definition.source_type, *definition.event_systems, *definition.normalized_sources}
    matched: list[AgentRunLog] = []
    for run in runs:
        haystack = f"{run.agent} {run.input_watermark or ''} {run.details or {}}".casefold()
        if any(token and token.casefold() in haystack for token in tokens):
            matched.append(run)
    return matched


def _pipeline_summary_for_request(row: SourceRunRequest) -> dict[str, Any]:
    result = row.result_summary if isinstance(row.result_summary, dict) else {}
    pipeline = result.get("evidence_pipeline") if isinstance(result, dict) else None
    return pipeline if isinstance(pipeline, dict) else {}


def _pipeline_totals(rows: list[SourceRunRequest]) -> dict[str, int]:
    totals = {
        "graph_updates": 0,
        "graph_nodes_created": 0,
        "graph_nodes_updated": 0,
        "graph_edges_created": 0,
        "graph_edges_updated": 0,
        "findings_generated": 0,
        "proposals_generated": 0,
        "data_quality_issues": 0,
    }
    for row in rows:
        pipeline = _pipeline_summary_for_request(row)
        totals["graph_nodes_created"] += int(pipeline.get("graph_nodes_created") or 0)
        totals["graph_nodes_updated"] += int(pipeline.get("graph_nodes_updated") or 0)
        totals["graph_edges_created"] += int(pipeline.get("graph_edges_created") or 0)
        totals["graph_edges_updated"] += int(pipeline.get("graph_edges_updated") or 0)
        totals["findings_generated"] += int(pipeline.get("findings_created") or 0)
        totals["proposals_generated"] += int(pipeline.get("proposals_created") or 0)
        totals["data_quality_issues"] += int(
            pipeline.get("data_quality_issues_created") or 0
        )
    totals["graph_updates"] = (
        totals["graph_nodes_created"]
        + totals["graph_nodes_updated"]
        + totals["graph_edges_created"]
        + totals["graph_edges_updated"]
    )
    return totals


def _availability_for_source(
    rows: list[DataAvailability],
    definition: SourceDefinition,
) -> dict[str, Any]:
    relevant = [
        row
        for row in rows
        if any(row.metric_key.startswith(prefix) for prefix in definition.metric_prefixes)
    ]
    if not relevant and definition.source_type in {"github", "gmail", "manual_inputs"}:
        relevant = [row for row in rows if row.metric_key == "activity.events"]
    if not relevant:
        return {
            "status": "no_data",
            "message": "No availability series for this source yet.",
            "series": [],
        }
    order = {"no_data": 0, "stale": 1, "insufficient": 2, "collecting": 3, "ready": 4}
    worst = min(relevant, key=lambda row: order.get(row.status, -1))
    return {
        "status": worst.status,
        "message": worst.message,
        "series": [
            {
                "metric_key": row.metric_key,
                "scope": row.scope,
                "status": row.status,
                "points_count": row.points_count,
                "last_point_at": row.last_point_at,
            }
            for row in relevant[:12]
        ],
    }


def _source_status(
    *,
    state: SourceControlState | None,
    setup_status: str,
    evidence_count: int,
    failed_runs: int,
    failed_events: int,
    availability_status: str,
) -> str:
    if state and state.paused:
        return STATUS_DISABLED
    if failed_runs or failed_events:
        return STATUS_ERROR
    if availability_status == "stale":
        return STATUS_DEGRADED
    if setup_status == "missing" and evidence_count == 0:
        return STATUS_DISCONNECTED
    if setup_status == "partial" and evidence_count == 0:
        return STATUS_DEGRADED
    if evidence_count > 0:
        return STATUS_CONNECTED
    return STATUS_DISCONNECTED


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def build_source_health(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    safe_now = now or _utcnow()
    events, normalized, failed_events = await _group_counts(session)
    virtual = await _virtual_counts(session)
    states = {
        row.source_type: row
        for row in (
            await session.execute(select(SourceControlState))
        ).scalars()
    }
    availability_rows = (
        await session.execute(select(DataAvailability).order_by(DataAvailability.updated_at.desc()))
    ).scalars().all()
    runs = (
        await session.execute(
            select(AgentRunLog).order_by(AgentRunLog.created_at.desc()).limit(200)
        )
    ).scalars().all()
    pending_rows = (
        await session.execute(
            select(
                SourceRunRequest.source_type,
                func.count(SourceRunRequest.id),
            )
            .where(SourceRunRequest.status.in_(_PENDING_REQUEST_STATUSES))
            .group_by(SourceRunRequest.source_type)
        )
    ).all()
    pending_by_source = {str(source): int(count or 0) for source, count in pending_rows}
    recent_requests = (
        await session.execute(
            select(SourceRunRequest)
            .order_by(SourceRunRequest.created_at.desc(), SourceRunRequest.id.desc())
            .limit(80)
        )
    ).scalars().all()
    requests_by_source: dict[str, list[SourceRunRequest]] = {}
    for request in recent_requests:
        requests_by_source.setdefault(request.source_type, []).append(request)

    sources: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    readiness_counts: Counter[str] = Counter()
    degraded: list[str] = []
    total_events = 0
    total_normalized = 0
    total_graph_updates = 0
    pending_total = 0
    failed_recent_runs = 0
    normalization_errors = 0
    paused_sources = 0
    last_successful_sync: str | None = None

    for definition in SOURCE_DEFINITIONS:
        setup = _setup_for(definition)
        setup_status = _setup_status(setup)
        readiness_counts[setup_status] += 1
        ev_count = sum(events.get(source, {}).get("count", 0) for source in definition.event_systems)
        norm_count = sum(
            normalized.get(source, {}).get("count", 0)
            for source in definition.normalized_sources
        )
        last_sync = next(
            (
                events[source]["last_received_at"]
                for source in definition.event_systems
                if events.get(source, {}).get("last_received_at")
            ),
            None,
        )
        last_success = next(
            (
                normalized[source]["last_normalized_at"]
                for source in definition.normalized_sources
                if normalized.get(source, {}).get("last_normalized_at")
            ),
            last_sync,
        )
        v = virtual.get(definition.source_type, {})
        ev_count += int(v.get("events_ingested") or 0)
        last_sync = str(v.get("last_sync_at") or last_sync or "") or None
        last_success = str(v.get("last_success_at") or last_success or "") or None
        related_runs = _runs_for_source(runs, definition)
        latest_agent_run = related_runs[0] if related_runs else None
        failed_run_count = sum(1 for run in related_runs if run.errors)
        failed_event_count = sum(failed_events.get(source, 0) for source in definition.event_systems)
        availability = _availability_for_source(availability_rows, definition)
        findings_count = await _findings_for_source(session, definition)
        proposals_count = await _proposals_for_source(session, definition)
        proposals_count += int(v.get("proposals_generated") or 0)
        findings_count += int(v.get("findings_generated") or 0)
        evidence_count = ev_count + norm_count + findings_count + proposals_count
        state = states.get(definition.source_type)
        source_requests = requests_by_source.get(definition.source_type, [])
        pipeline_totals = _pipeline_totals(source_requests)
        evidence_count += pipeline_totals["graph_updates"]
        latest_request = source_requests[0] if source_requests else None
        latest_source_run = next(
            (request for request in source_requests if request.started_at or request.run_id),
            latest_request,
        )
        failed_recent_runs += sum(1 for request in source_requests if request.status == "failed")
        for request in source_requests:
            result = request.result_summary if isinstance(request.result_summary, dict) else {}
            sanitized = result.get("sanitized_summary") if isinstance(result, dict) else {}
            ingestion = sanitized.get("ingestion") if isinstance(sanitized, dict) else {}
            if isinstance(ingestion, dict):
                normalization_errors += int(ingestion.get("normalization_errors") or 0)
        if state and state.paused:
            paused_sources += 1
        state_success = _iso(state.last_success_at) if state and state.last_success_at else None
        if state_success and (last_successful_sync is None or state_success > last_successful_sync):
            last_successful_sync = state_success
        status = _source_status(
            state=state,
            setup_status=setup_status,
            evidence_count=evidence_count,
            failed_runs=failed_run_count,
            failed_events=failed_event_count,
            availability_status=str(availability["status"]),
        )
        if status in {STATUS_DEGRADED, STATUS_ERROR, STATUS_DISABLED}:
            degraded.append(definition.label)
        pending = pending_by_source.get(definition.source_type, 0)
        total_events += ev_count
        total_normalized += norm_count
        total_graph_updates += pipeline_totals["graph_updates"]
        pending_total += pending
        status_counts[status] += 1
        sources.append(
            {
                "source_type": definition.source_type,
                "label": definition.label,
                "status": status,
                "control_state": {
                    "paused": bool(state.paused) if state else False,
                    "last_action": state.last_action if state else None,
                    "last_action_at": _iso(state.last_action_at) if state else None,
                    "last_action_by": state.last_action_by if state else None,
                    "last_sync_at": _iso(state.last_sync_at) if state else None,
                    "last_success_at": _iso(state.last_success_at) if state else None,
                    "last_error_at": _iso(state.last_error_at) if state else None,
                    "latest_run_id": state.latest_run_id if state else None,
                },
                "connector_state": (
                    "paused"
                    if state and state.paused
                    else "connected"
                    if state and state.last_success_at
                    else "never_tested"
                    if setup_status in {"ready", "partial"}
                    else "missing_config"
                    if setup_status == "missing"
                    else "no_data"
                ),
                "last_sync_at": _iso(state.last_sync_at) if state and state.last_sync_at else last_sync,
                "last_success_at": _iso(state.last_success_at)
                if state and state.last_success_at
                else last_success,
                "last_error_at": _iso(state.last_error_at)
                if state and state.last_error_at
                else (_iso(latest_agent_run.run_finished_at) if latest_agent_run and latest_agent_run.errors else None),
                "input_watermark": state.input_watermark
                if state and state.input_watermark
                else (latest_agent_run.input_watermark if latest_agent_run else None),
                "events_ingested": ev_count,
                "normalized_events": norm_count,
                "graph_updates": pipeline_totals["graph_updates"],
                "graph_nodes_created": pipeline_totals["graph_nodes_created"],
                "graph_nodes_updated": pipeline_totals["graph_nodes_updated"],
                "graph_edges_created": pipeline_totals["graph_edges_created"],
                "graph_edges_updated": pipeline_totals["graph_edges_updated"],
                "data_quality_issues": pipeline_totals["data_quality_issues"],
                "findings_generated": findings_count,
                "proposals_generated": proposals_count,
                "failed_runs": failed_run_count,
                "failed_events": failed_event_count,
                "pending_requests": pending,
                "queue_status": {
                    "pending": pending,
                    "running": sum(1 for request in source_requests if request.status == "running"),
                    "failed": sum(1 for request in source_requests if request.status == "failed"),
                    "succeeded": sum(1 for request in source_requests if request.status == "succeeded"),
                    "skipped": sum(1 for request in source_requests if request.status == "skipped"),
                    "blocked": sum(1 for request in source_requests if request.status == "blocked"),
                },
                "latest_request": _request_model(latest_request) if latest_request else None,
                "latest_run": _request_model(latest_source_run) if latest_source_run else None,
                "data_availability": availability,
                "visibility_policy": _visibility_policy(),
                "redaction_policy": _redaction_policy(),
                "safe_actions": _safe_actions(definition),
                "connector_readiness": {
                    "status": setup_status,
                    "setup": setup,
                    "restart_backend_after_env_change": True,
                    "docs": "docs/dev-env.md",
                },
                "masked_connection": {
                    "status": setup_status,
                    "secrets": "masked_or_missing",
                },
                "warnings": [
                    warning
                    for warning in (
                        "source_paused" if state and state.paused else None,
                        "failed_events_present" if failed_event_count else None,
                        "failed_runs_present" if failed_run_count else None,
                        "data_stale" if availability["status"] == "stale" else None,
                    )
                    if warning
                ],
            }
        )

    return {
        "generated_at": safe_now.isoformat(),
        "sources": sources,
        "summary": {
            "total_sources": len(sources),
            "by_status": dict(status_counts),
            "by_readiness": dict(readiness_counts),
            "events_ingested": total_events,
            "normalized_events": total_normalized,
            "graph_updates": total_graph_updates,
            "pending_requests": pending_total,
            "failed_recent_runs": failed_recent_runs,
            "normalization_errors": normalization_errors,
            "paused_sources": paused_sources,
            "missing_config_sources": readiness_counts.get("missing", 0)
            + readiness_counts.get("partial", 0),
            "last_successful_sync": last_successful_sync,
            "degraded_sources": degraded,
            "sources_needing_attention": len(degraded),
        },
        "pending_requests": [
            _request_model(row)
            for row in recent_requests
            if row.status in _PENDING_REQUEST_STATUSES
        ][:20],
        "recent_runs": [
            _request_model(row)
            for row in recent_requests
            if row.started_at or row.finished_at or row.run_id
        ][:20],
        "setup_checklist": [
            {
                "source_type": item["source_type"],
                "label": item["label"],
                "status": item["connector_readiness"]["status"],
                "setup": item["connector_readiness"]["setup"],
            }
            for item in sources
        ],
    }


def _request_model(row: SourceRunRequest, *, idempotent: bool = False) -> dict[str, Any]:
    return {
        "request_id": row.request_id,
        "run_id": row.run_id,
        "correlation_id": row.correlation_id,
        "source_type": row.source_type,
        "action_type": row.action_type,
        "status": row.status,
        "request_key": row.request_key,
        "requested_by": row.requested_by,
        "approved_by": row.approved_by,
        "requested_at": _iso(row.requested_at),
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "input_snapshot": row.input_snapshot,
        "result_summary": row.result_summary,
        "error_summary": row.error_summary,
        "external_side_effect": row.external_side_effect,
        "retry_count": row.retry_count,
        "idempotency_key": row.idempotency_key,
        "audit_log_id": row.audit_log_id,
        "source_state_before": row.source_state_before,
        "source_state_after": row.source_state_after,
        "receipt": build_source_run_receipt(row),
        "idempotent": idempotent,
    }


async def _get_or_create_state(
    session: AsyncSession,
    *,
    source_type: str,
) -> SourceControlState:
    row = await session.scalar(
        select(SourceControlState).where(SourceControlState.source_type == source_type)
    )
    if row is not None:
        return row
    row = SourceControlState(source_type=source_type, status=STATUS_DISCONNECTED)
    session.add(row)
    await session.flush()
    return row


async def request_source_action(
    session: AsyncSession,
    *,
    source_type: str,
    action_type: str,
    request_key: str | None,
    requested_by: str = "founder",
    input_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if source_type not in SOURCE_BY_TYPE:
        raise ValueError(f"unknown source: {source_type}")
    if action_type not in SOURCE_ACTIONS:
        raise ValueError(f"unknown source action: {action_type}")

    clean_request_key = (request_key or f"{source_type}:{action_type}:manual").strip()
    existing = await session.scalar(
        select(SourceRunRequest)
        .where(SourceRunRequest.source_type == source_type)
        .where(SourceRunRequest.action_type == action_type)
        .where(SourceRunRequest.request_key == clean_request_key)
    )
    if existing is not None:
        return _request_model(existing, idempotent=True)

    state = await _get_or_create_state(session, source_type=source_type)
    now = _utcnow()
    setup = _setup_for(SOURCE_BY_TYPE[source_type])
    setup_status = _setup_status(setup)
    blocked = bool(state.paused and action_type in {ACTION_SYNC, ACTION_BACKFILL})
    status = "skipped" if blocked else ("accepted" if action_type in {ACTION_PAUSE, ACTION_RESUME} else "requested")
    if action_type == ACTION_PAUSE:
        state.paused = True
        state.status = STATUS_DISABLED
    elif action_type == ACTION_RESUME:
        state.paused = False
        state.status = STATUS_DISCONNECTED

    request_id = f"src_req_{uuid4().hex}"
    snapshot = {
        "source_type": source_type,
        "action_type": action_type,
        "connector_readiness": setup_status,
        "external_side_effect": False,
        "input": sanitize_for_logs(dict(input_payload or {})),
    }
    result_summary = {
        "mode": "request_only",
        "external_side_effect": False,
        "queued": status in {"requested", "accepted"},
        "blocked": blocked,
        "reason": "source_paused" if blocked else "recorded_for_review",
    }
    audit = AuditLog(
        event_type="source_action_requested",
        actor=requested_by,
        correlation_id=request_id,
        trace_id=request_id,
        before_ref=f"source:{source_type}",
        after_ref=f"source_run_request:{request_id}",
        payload={
            "source_type": source_type,
            "action_type": action_type,
            "status": status,
            "request_key": clean_request_key,
            "external_side_effect": False,
        },
    )
    session.add(audit)
    await session.flush()
    row = SourceRunRequest(
        request_id=request_id,
        source_type=source_type,
        action_type=action_type,
        status=status,
        request_key=clean_request_key,
        correlation_id=request_id,
        idempotency_key=f"{source_type}:{action_type}:{clean_request_key}",
        requested_by=requested_by,
        requested_at=now,
        input_snapshot=snapshot,
        result_summary=result_summary,
        error_summary={},
        external_side_effect=False,
        audit_log_id=audit.id,
    )
    session.add(row)
    state.last_action = action_type
    state.last_action_at = now
    state.last_action_by = requested_by
    state.last_request_key = clean_request_key
    state.config_status = {"status": setup_status, "setup": setup}
    await session.flush()
    return _request_model(row)


async def list_source_run_requests(
    session: AsyncSession,
    *,
    source_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = select(SourceRunRequest).order_by(
        SourceRunRequest.created_at.desc(), SourceRunRequest.id.desc()
    )
    if source_type is not None:
        query = query.where(SourceRunRequest.source_type == source_type)
    if status is not None:
        query = query.where(SourceRunRequest.status == status)
    rows = (await session.execute(query.limit(limit))).scalars()
    return [_request_model(row) for row in rows]


async def get_source_run_receipt(
    session: AsyncSession,
    *,
    request_id: str,
) -> dict[str, Any] | None:
    row = await session.scalar(
        select(SourceRunRequest).where(SourceRunRequest.request_id == request_id)
    )
    if row is None:
        return None
    return {
        "run": _request_model(row),
        "receipt": build_source_run_receipt(row),
    }


async def request_source_retry(
    session: AsyncSession,
    *,
    source_type: str,
    request_id: str,
    request_key: str | None,
    requested_by: str = "founder",
) -> dict[str, Any]:
    if source_type not in SOURCE_BY_TYPE:
        raise ValueError(f"unknown source: {source_type}")
    original = await session.scalar(
        select(SourceRunRequest).where(SourceRunRequest.request_id == request_id)
    )
    if original is None or original.source_type != source_type:
        raise ValueError("source run request not found")
    if original.status == "succeeded":
        raise ValueError("completed source run cannot be retried")
    retry_number = int(original.retry_count or 0) + 1
    retry_key = (
        request_key
        or f"{original.request_key}:retry:{retry_number}"
    ).strip()
    existing = await session.scalar(
        select(SourceRunRequest)
        .where(SourceRunRequest.source_type == source_type)
        .where(SourceRunRequest.action_type == original.action_type)
        .where(SourceRunRequest.request_key == retry_key)
    )
    if existing is not None:
        return _request_model(existing, idempotent=True)

    original.retry_count = retry_number
    retry = await request_source_action(
        session,
        source_type=source_type,
        action_type=original.action_type,
        request_key=retry_key,
        requested_by=requested_by,
        input_payload={
            "retry_of": original.request_id,
            "retry_count": retry_number,
            "original_scope_snapshot": (
                build_source_run_receipt(original).get("scope_snapshot") or {}
            ),
        },
    )
    row = await session.scalar(
        select(SourceRunRequest).where(SourceRunRequest.request_id == retry["request_id"])
    )
    if row is not None:
        row.retry_count = retry_number
        row.result_summary = sanitize_for_logs(
            {
                **(row.result_summary if isinstance(row.result_summary, dict) else {}),
                "retry_of": original.request_id,
                "retry_count": retry_number,
                "external_side_effect": False,
            }
        )
        return _request_model(row)
    return retry
