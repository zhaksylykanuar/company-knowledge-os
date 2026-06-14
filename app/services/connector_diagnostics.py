"""Connector diagnostics read model.

Founder-facing, read-only diagnostics for every source/connector. It reports
*readiness* (configured / missing / never tested), the names (never values) of
missing environment variables, what actions are safe to run, the most recent
test/sync results, and an explicit security policy.

Hard rules:
- No secret values. Only environment-variable *names* and masked statuses.
- Source state is derived from real run history; a source is never reported as
  ``connected`` purely because env vars are present — only a successful run sets
  ``last_success_at``.
- This layer never calls an external provider.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services.secret_patterns import assert_no_secret_values
from app.services.source_connectors import (
    REAL_CLIENT_SOURCES,
    ReadOnlyConnectorClient,
    _INTERNAL_SOURCES,
    NoopSourceConnector,
)
from app.services.source_control import (
    SOURCE_DEFINITIONS,
    connector_setup_status,
)

SECURITY_POLICY = {
    "read_only": True,
    "secrets_exposed_to_browser": False,
    "external_writes_allowed": False,
}

CONNECTOR_DOCS = "docs/source-connectors.md"
RESTART_CMD = "uv run python scripts/start_local.py"
RUN_SOURCE_REQUESTS_CMD = (
    'uv run python scripts/run_source_requests.py --confirm-run "RUN SOURCE REQUESTS"'
)
RUN_EVIDENCE_CMD = (
    'uv run python scripts/run_evidence_pipeline.py --confirm-run "RUN EVIDENCE PIPELINE"'
)
SYNC_OBSIDIAN_CMD = (
    'uv run python scripts/sync_obsidian_vault.py --confirm-run "SYNC OBSIDIAN VAULT"'
)
PILOT_CMD = (
    'uv run python scripts/run_local_connector_pilot.py '
    '--confirm-run "RUN LOCAL CONNECTOR PILOT"'
)
RESTART_REQUIRED_HINT = (
    "Restart the backend after changing environment variables: " + RESTART_CMD
)

SETUP_STEPS: dict[str, list[str]] = {
    "jira": [
        "Set JIRA_BASE_URL to your Atlassian site URL (backend env).",
        "Set JIRA_EMAIL to the read-only account email (backend env).",
        "Set JIRA_API_TOKEN as a read-only API token (backend env only).",
        "Restart the backend, then run Test connection.",
    ],
    "github": [
        "Set GITHUB_TOKEN to a read-only token (backend env only).",
        "Restart the backend, then run Test connection.",
    ],
    "gmail": [
        "Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET (backend env).",
        "Complete the Gmail OAuth token file, or rely on already-ingested "
        "local email records.",
        "Restart the backend, then run Test connection.",
    ],
    "meetings": [
        "Provide a local meetings/calendar source, or rely on already-ingested "
        "local meeting documents.",
    ],
    "manual_inputs": ["No setup required; backed by local manual ingestion."],
    "declarations": ["No setup required; backed by the local database."],
    "generated_evidence": ["No setup required; produced by internal agents."],
    "share_packs": ["No setup required; produced by curated outputs."],
}

# Result fields that are safe to surface (no raw payloads, no secret values).
_SAFE_RESULT_KEYS = ("status", "reason", "mode", "external_side_effect")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _adapter_type(
    source_type: str,
    *,
    enabled: bool,
    has_injected_client: bool,
    has_local_data: bool,
) -> str:
    if source_type in _INTERNAL_SOURCES:
        return "internal"
    if has_injected_client:
        return "fake"
    if source_type in REAL_CLIENT_SOURCES:
        return "real" if enabled else "real-disabled"
    if source_type == "gmail":
        return "local_only" if has_local_data else "noop"
    return "noop"


def _real_execution(source_type: str, *, enabled: bool) -> str:
    if source_type in REAL_CLIENT_SOURCES:
        return "enabled" if enabled else "disabled"
    if source_type == "gmail":
        return "local_only"
    if source_type in _INTERNAL_SOURCES:
        return "internal"
    return "not_applicable"


def _connector_state(
    *, state: SourceControlState | None, setup_status: str, configured: bool
) -> str:
    # Lifecycle, derived from real run history — never "connected" from env
    # presence alone (only a successful run sets last_success_at).
    if state and state.paused:
        return "paused"
    if state and state.last_success_at:
        return "connected"
    if configured:
        return "never_tested"
    if setup_status in {"missing", "partial"}:
        return "missing_config"
    return "no_data"


def _result_view(row: SourceRunRequest | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = row.result_summary if isinstance(row.result_summary, dict) else {}
    sanitized = result.get("sanitized_summary")
    mode = sanitized.get("mode") if isinstance(sanitized, dict) else None
    view: dict[str, Any] = {
        "request_id": row.request_id,
        "run_id": row.run_id,
        "action_type": row.action_type,
        "status": row.status,
        "result_status": result.get("status"),
        "mode": mode,
        "requested_at": _iso(row.requested_at),
        "finished_at": _iso(row.finished_at),
        "external_side_effect": bool(row.external_side_effect),
    }
    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        view["warnings"] = [str(item) for item in warnings][:10]
    missing = sanitized.get("missing_env_vars") if isinstance(sanitized, dict) else None
    if isinstance(missing, list) and missing:
        view["missing_env_vars"] = [str(item) for item in missing]
    return view


def _latest_for_action(
    rows: list[SourceRunRequest], action_type: str
) -> SourceRunRequest | None:
    for row in rows:
        if row.action_type == action_type and (row.finished_at or row.started_at):
            return row
    return None


def _action_result_status(rows: list[SourceRunRequest], action_type: str) -> str | None:
    for row in rows:
        if row.action_type == action_type and (row.finished_at or row.started_at):
            result = row.result_summary if isinstance(row.result_summary, dict) else {}
            return str(result.get("status") or row.status)
    return None


def _has_pending(rows: list[SourceRunRequest], *action_types: str) -> bool:
    wanted = set(action_types)
    return any(
        row.action_type in wanted and row.status in {"requested", "accepted"}
        for row in rows
    )


def _has_running(rows: list[SourceRunRequest]) -> bool:
    return any(row.status == "running" for row in rows)


def _pipeline_state(
    *,
    configured: bool,
    real_capable: bool,
    real_enabled: bool,
    state: SourceControlState | None,
    rows: list[SourceRunRequest],
    events_ingested: int,
) -> str:
    if state and state.paused:
        return "paused"
    if not configured:
        return "missing_config"
    if real_capable and not real_enabled:
        return "real_disabled"
    if _has_running(rows):
        return "running"
    if _has_pending(rows, "test"):
        return "test_requested"
    if _has_pending(rows, "sync", "backfill"):
        return "sync_requested"
    has_success = bool(state and state.last_success_at)
    sync_status = _action_result_status(rows, "sync")
    test_status = _action_result_status(rows, "test")
    if not has_success:
        if sync_status == "failed":
            return "sync_failed"
        if test_status == "failed":
            return "test_failed"
        if sync_status == "skipped" or test_status == "skipped":
            return "degraded"
        return "never_tested"
    if sync_status == "succeeded" or (state and state.last_sync_at):
        return "sync_succeeded" if events_ingested else "synced_no_events"
    if test_status == "succeeded":
        return "test_succeeded"
    return "connected"


def _runbook(
    pipeline_state: str,
    *,
    missing_env_vars: list[str],
    events_ingested: int,
) -> dict[str, Any]:
    if pipeline_state == "missing_config":
        return {
            "stage": "configure_env",
            "next_action": "Add the missing backend env vars (names below) and "
            "restart the backend.",
            "next_command": RESTART_CMD,
            "blockers": ["missing_config"],
            "blocking_env_vars": list(missing_env_vars),
        }
    if pipeline_state == "real_disabled":
        return {
            "stage": "enable_real_connectors",
            "next_action": "Set FOUNDEROS_ENABLE_REAL_CONNECTORS=true and restart to "
            "run real read-only sync (or keep disabled for a dry run).",
            "next_command": "FOUNDEROS_ENABLE_REAL_CONNECTORS=true  # then "
            + RESTART_CMD,
            "blockers": ["real_connectors_disabled"],
        }
    if pipeline_state == "paused":
        return {
            "stage": "resume",
            "next_action": "Resume the source to allow sync/backfill.",
            "next_command": None,
            "blockers": ["paused"],
        }
    if pipeline_state in {"test_requested", "sync_requested"}:
        return {
            "stage": "run_operator",
            "next_action": "Run the operator script to execute the queued request.",
            "next_command": RUN_SOURCE_REQUESTS_CMD,
            "blockers": ["request_queued"],
        }
    if pipeline_state == "running":
        return {
            "stage": "running",
            "next_action": "A run is in progress — check back for the result.",
            "next_command": None,
            "blockers": ["running"],
        }
    if pipeline_state in {"test_failed", "sync_failed"}:
        return {
            "stage": "inspect_failure",
            "next_action": "Open the failed run detail, fix configuration, then retry "
            "with a new request.",
            "next_command": RUN_SOURCE_REQUESTS_CMD,
            "blockers": [pipeline_state],
        }
    if pipeline_state == "never_tested":
        return {
            "stage": "test_connection",
            "next_action": "Click Test connection, then run the operator script.",
            "next_command": RUN_SOURCE_REQUESTS_CMD,
            "blockers": [],
        }
    if pipeline_state == "test_succeeded":
        return {
            "stage": "sync",
            "next_action": "Click Sync now, then run the operator script.",
            "next_command": RUN_SOURCE_REQUESTS_CMD,
            "blockers": [],
        }
    if pipeline_state == "synced_no_events":
        return {
            "stage": "check_source_scope",
            "next_action": "Sync succeeded but no events were ingested. Check the "
            "source scope or run Backfill.",
            "next_command": RUN_SOURCE_REQUESTS_CMD,
            "blockers": ["no_events"],
        }
    if pipeline_state in {"sync_succeeded", "connected"}:
        if events_ingested:
            return {
                "stage": "process_evidence",
                "next_action": "Process new evidence into the graph, then sync Obsidian.",
                "next_command": RUN_EVIDENCE_CMD,
                "blockers": [],
            }
        return {
            "stage": "monitor",
            "next_action": "Connected. Sync periodically to keep evidence fresh.",
            "next_command": RUN_SOURCE_REQUESTS_CMD,
            "blockers": [],
        }
    if pipeline_state == "degraded":
        return {
            "stage": "inspect",
            "next_action": "Last run was skipped or degraded — review the run detail.",
            "next_command": None,
            "blockers": ["degraded"],
        }
    return {
        "stage": "review",
        "next_action": "Review connector diagnostics.",
        "next_command": None,
        "blockers": [],
    }


def _pilot_next_steps(
    connectors: list[dict[str, Any]], *, real_enabled: bool
) -> list[str]:
    steps: list[str] = []
    has_external = any(
        c["source_type"] in REAL_CLIENT_SOURCES for c in connectors
    )
    if has_external and not real_enabled:
        steps.append(
            "Real connector execution is disabled. Internal/local sources still "
            "run; set FOUNDEROS_ENABLE_REAL_CONNECTORS=true to pilot Jira/GitHub "
            "read-only sync."
        )
    missing = [c["source_type"] for c in connectors if c["pipeline_state"] == "missing_config"]
    if missing:
        steps.append("Add missing env (names only) for: " + ", ".join(missing) + ".")
    queued = [
        c["source_type"]
        for c in connectors
        if c["pipeline_state"] in {"test_requested", "sync_requested"}
    ]
    if queued:
        steps.append("Run the operator script to execute queued requests: " + RUN_SOURCE_REQUESTS_CMD)
    needs_test = [c["source_type"] for c in connectors if c["pipeline_state"] == "never_tested"]
    if needs_test:
        steps.append("Test connection for: " + ", ".join(needs_test) + ".")
    if any(
        c["pipeline_state"] in {"sync_succeeded", "connected"}
        and c.get("events_ingested")
        for c in connectors
    ):
        steps.append("Process evidence into the graph: " + RUN_EVIDENCE_CMD)
        steps.append("Sync the Obsidian vault: " + SYNC_OBSIDIAN_CMD)
    if not steps:
        steps.append(
            "All connectors are configured and current. Sync periodically to keep "
            "evidence fresh."
        )
    return steps


def _latest_error(
    rows: list[SourceRunRequest], state: SourceControlState | None
) -> dict[str, Any] | None:
    for row in rows:
        error = row.error_summary if isinstance(row.error_summary, dict) else {}
        if error:
            return {
                "request_id": row.request_id,
                "action_type": row.action_type,
                "error_type": str(error.get("error_type") or "error"),
                "message": str(error.get("message") or error.get("error") or "error"),
                "at": _iso(state.last_error_at) if state else _iso(row.finished_at),
            }
    return None


async def build_connector_diagnostics(
    session: AsyncSession,
    *,
    clients: dict[str, ReadOnlyConnectorClient] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    safe_now = now or _now()
    client_map = clients or {}
    real_enabled = bool(getattr(settings, "enable_real_connectors", False))
    states = {
        row.source_type: row
        for row in (await session.execute(select(SourceControlState))).scalars()
    }
    recent_requests = (
        await session.execute(
            select(SourceRunRequest)
            .order_by(SourceRunRequest.created_at.desc(), SourceRunRequest.id.desc())
            .limit(200)
        )
    ).scalars().all()
    by_source: dict[str, list[SourceRunRequest]] = {}
    for row in recent_requests:
        by_source.setdefault(row.source_type, []).append(row)

    event_rows = (
        await session.execute(
            select(SourceEvent.source_system, func.count(SourceEvent.id)).group_by(
                SourceEvent.source_system
            )
        )
    ).all()
    events_by_system = {str(system): int(count or 0) for system, count in event_rows}
    normalized_rows = (
        await session.execute(
            select(
                NormalizedActivityItemRecord.source,
                func.count(NormalizedActivityItemRecord.id),
            ).group_by(NormalizedActivityItemRecord.source)
        )
    ).all()
    normalized_by_source = {
        str(source): int(count or 0) for source, count in normalized_rows
    }

    connectors: list[dict[str, Any]] = []
    by_state: dict[str, int] = {}
    by_pipeline: dict[str, int] = {}
    for definition in SOURCE_DEFINITIONS:
        source_type = definition.source_type
        has_client = source_type in client_map
        connector = NoopSourceConnector(
            source_type, session=session, client=client_map.get(source_type)
        )
        readiness = await connector.readiness()
        setup_status = connector_setup_status(source_type)
        state = states.get(source_type)
        source_rows = by_source.get(source_type, [])
        has_local_data = "local_email_records" in readiness.warnings
        events_ingested = sum(
            events_by_system.get(system, 0) for system in definition.event_systems
        )
        normalized_events = sum(
            normalized_by_source.get(source, 0)
            for source in definition.normalized_sources
        )
        connector_state = _connector_state(
            state=state,
            setup_status=setup_status,
            configured=readiness.configured,
        )
        pipeline_state = _pipeline_state(
            configured=readiness.configured,
            real_capable=source_type in REAL_CLIENT_SOURCES,
            real_enabled=real_enabled,
            state=state,
            rows=source_rows,
            events_ingested=events_ingested,
        )
        by_state[connector_state] = by_state.get(connector_state, 0) + 1
        by_pipeline[pipeline_state] = by_pipeline.get(pipeline_state, 0) + 1
        connectors.append(
            {
                "source_type": source_type,
                "label": definition.label,
                "internal": source_type in _INTERNAL_SOURCES,
                "adapter_type": _adapter_type(
                    source_type,
                    enabled=real_enabled,
                    has_injected_client=has_client,
                    has_local_data=has_local_data,
                ),
                "real_execution": _real_execution(source_type, enabled=real_enabled),
                "pipeline_state": pipeline_state,
                "runbook": _runbook(
                    pipeline_state,
                    missing_env_vars=list(readiness.missing_env_vars),
                    events_ingested=events_ingested,
                ),
                "real_execution_enabled": real_enabled
                if source_type in REAL_CLIENT_SOURCES
                else None,
                "readiness": setup_status,
                "configured": readiness.configured,
                "connector_state": connector_state,
                "missing_env_vars": list(readiness.missing_env_vars),
                "masked_config_status": list(readiness.masked_config_status),
                "can_test": readiness.can_test,
                "can_sync": readiness.can_sync,
                "can_backfill": readiness.can_backfill,
                "events_ingested": events_ingested,
                "normalized_events": normalized_events,
                "paused": bool(state.paused) if state else False,
                "last_test_at": _iso(state.last_action_at)
                if state and state.last_action == "test"
                else None,
                "last_success_at": _iso(state.last_success_at) if state else None,
                "last_error_at": _iso(state.last_error_at) if state else None,
                "last_test_result": _result_view(_latest_for_action(source_rows, "test")),
                "last_sync_result": _result_view(_latest_for_action(source_rows, "sync")),
                "last_error_sanitized": _latest_error(source_rows, state),
                "docs_link": CONNECTOR_DOCS,
                "setup_steps": list(SETUP_STEPS.get(source_type, [])),
                "restart_required_hint": RESTART_REQUIRED_HINT,
                "security_policy": dict(SECURITY_POLICY),
                "warnings": list(readiness.warnings),
            }
        )

    next_steps = _pilot_next_steps(connectors, real_enabled=real_enabled)
    result = {
        "generated_at": safe_now.isoformat(),
        "real_execution_enabled": real_enabled,
        "security_policy": dict(SECURITY_POLICY),
        "connectors": connectors,
        "pilot": {
            "real_execution_enabled": real_enabled,
            "by_pipeline_state": by_pipeline,
            "commands": {
                "pilot": PILOT_CMD,
                "operator_run": RUN_SOURCE_REQUESTS_CMD,
                "evidence_pipeline": RUN_EVIDENCE_CMD,
                "sync_obsidian": SYNC_OBSIDIAN_CMD,
                "restart": RESTART_CMD,
            },
            "next_steps": next_steps,
        },
        "summary": {
            "total": len(connectors),
            "real_execution_enabled": real_enabled,
            "configured": sum(1 for c in connectors if c["configured"]),
            "missing_config": sum(
                1 for c in connectors if c["connector_state"] == "missing_config"
            ),
            "never_tested": sum(
                1 for c in connectors if c["connector_state"] == "never_tested"
            ),
            "connected": sum(
                1 for c in connectors if c["connector_state"] == "connected"
            ),
            "by_connector_state": by_state,
        },
    }
    # Defense in depth: never emit a secret value, only names/statuses.
    assert_no_secret_values(result)
    return result
