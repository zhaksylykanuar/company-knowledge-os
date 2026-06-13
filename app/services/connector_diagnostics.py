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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.services.secret_patterns import assert_no_secret_values
from app.services.source_connectors import (
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
RESTART_REQUIRED_HINT = (
    "Restart the backend after changing environment variables: "
    "uv run python scripts/start_local.py"
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


def _adapter_type(source_type: str, has_client: bool) -> str:
    if source_type in _INTERNAL_SOURCES:
        return "internal"
    if has_client:
        return "read_only_client"
    return "noop"


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

    connectors: list[dict[str, Any]] = []
    by_state: dict[str, int] = {}
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
        connector_state = _connector_state(
            state=state,
            setup_status=setup_status,
            configured=readiness.configured,
        )
        by_state[connector_state] = by_state.get(connector_state, 0) + 1
        connectors.append(
            {
                "source_type": source_type,
                "label": definition.label,
                "internal": source_type in _INTERNAL_SOURCES,
                "adapter_type": _adapter_type(source_type, has_client),
                "readiness": setup_status,
                "configured": readiness.configured,
                "connector_state": connector_state,
                "missing_env_vars": list(readiness.missing_env_vars),
                "masked_config_status": list(readiness.masked_config_status),
                "can_test": readiness.can_test,
                "can_sync": readiness.can_sync,
                "can_backfill": readiness.can_backfill,
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

    result = {
        "generated_at": safe_now.isoformat(),
        "security_policy": dict(SECURITY_POLICY),
        "connectors": connectors,
        "summary": {
            "total": len(connectors),
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
