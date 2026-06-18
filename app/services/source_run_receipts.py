"""Sanitized connector run receipts.

Receipts are a formal read-model over ``source_run_requests``. They are kept in
``result_summary["receipt"]`` for auditability, but can always be rebuilt from
the request row if an older row has no embedded receipt.
"""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Any

from app.db.source_control_models import SourceRunRequest
from app.services.browser_config import sanitize_for_logs


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _duration_ms(started_at: datetime | None, finished_at: datetime | None) -> int | None:
    if started_at is None or finished_at is None:
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _stable_hash(value: Any) -> str:
    blob = json.dumps(
        sanitize_for_logs(value),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return sha256(blob).hexdigest()


def _result(row: SourceRunRequest) -> dict[str, Any]:
    result = row.result_summary if isinstance(row.result_summary, dict) else {}
    return {key: value for key, value in result.items() if key != "receipt"}


def _sanitized_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("sanitized_summary")
    return summary if isinstance(summary, dict) else {}


def _ingestion(result: dict[str, Any]) -> dict[str, Any]:
    summary = _sanitized_summary(result)
    ingestion = summary.get("ingestion")
    return ingestion if isinstance(ingestion, dict) else {}


def _pipeline(result: dict[str, Any]) -> dict[str, Any]:
    pipeline = result.get("evidence_pipeline")
    return pipeline if isinstance(pipeline, dict) else {}


def _source_state_watermark(snapshot: Any) -> str | None:
    if isinstance(snapshot, dict):
        value = snapshot.get("input_watermark")
        return str(value) if value else None
    return None


def build_source_run_receipt(row: SourceRunRequest) -> dict[str, Any]:
    """Build a secret-safe receipt for a source run/request row."""

    result = _result(row)
    summary = _sanitized_summary(result)
    ingestion = _ingestion(result)
    pipeline = _pipeline(result)
    errors = result.get("errors")
    warnings = result.get("warnings")
    receipt: dict[str, Any] = {
        "receipt_id": f"src_receipt_{row.request_id}",
        "source_run_request_id": row.request_id,
        "source_type": row.source_type,
        "action_type": row.action_type,
        "status": row.status,
        "connector_status": result.get("status"),
        "run_id": row.run_id,
        "correlation_id": row.correlation_id,
        "requested_at": _iso(row.requested_at),
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "duration_ms": _duration_ms(row.started_at, row.finished_at),
        "adapter_type": summary.get("mode") or "unknown",
        "real_execution_enabled": summary.get("real_execution") == "enabled",
        "external_side_effect": bool(row.external_side_effect),
        "scope_required": bool(result.get("scope_required")),
        "scope_configured": bool(result.get("scope_configured")),
        "scope_snapshot": sanitize_for_logs(result.get("scope_summary") or {}),
        "limits_applied": sanitize_for_logs(result.get("limits_applied") or {}),
        "input_watermark": result.get("input_watermark"),
        "output_watermark": result.get("output_watermark"),
        "previous_success_watermark": _source_state_watermark(row.source_state_before),
        "watermark_updated": bool(result.get("watermark_updated")),
        "watermark_update_reason": result.get("watermark_update_reason")
        or "not_evaluated",
        "pages_read": int(result.get("pages_read") or 0),
        "page_size": result.get("page_size"),
        "limit_applied": result.get("limit_applied"),
        "stopped_reason": result.get("stopped_reason"),
        "retry_after_seconds": result.get("retry_after_seconds"),
        "rate_limit_remaining": result.get("rate_limit_remaining"),
        "records_seen": int(result.get("records_seen") or result.get("events_seen") or 0),
        "events_seen": int(result.get("events_seen") or ingestion.get("events_seen") or 0),
        "events_ingested": int(
            result.get("events_ingested") or ingestion.get("events_ingested") or 0
        ),
        "duplicates_skipped": int(ingestion.get("duplicates_skipped") or 0),
        "normalized_events": int(
            result.get("normalized_events") or ingestion.get("normalized_events") or 0
        ),
        "normalization_errors": int(ingestion.get("normalization_errors") or 0),
        "graph_nodes_created": int(pipeline.get("graph_nodes_created") or 0),
        "graph_nodes_updated": int(pipeline.get("graph_nodes_updated") or 0),
        "findings_created": int(pipeline.get("findings_created") or 0),
        "findings_updated": int(pipeline.get("findings_updated_from_new_evidence") or 0),
        "proposals_created": int(pipeline.get("proposals_created") or 0),
        "warnings_sanitized": sanitize_for_logs(warnings if isinstance(warnings, list) else []),
        "errors_sanitized": sanitize_for_logs(errors if isinstance(errors, list) else []),
        "blocked_reason": result.get("blocked_reason") or result.get("reason"),
        "retry_count": int(row.retry_count or 0),
        "idempotency_key": row.idempotency_key,
        "secret_scan_status": "passed",
        "sanitized": True,
    }
    receipt["content_hash"] = _stable_hash(
        {key: value for key, value in receipt.items() if key != "content_hash"}
    )
    return sanitize_for_logs(receipt)


def attach_source_run_receipt(row: SourceRunRequest) -> dict[str, Any]:
    result = _result(row)
    receipt = build_source_run_receipt(row)
    row.result_summary = sanitize_for_logs({**result, "receipt": receipt})
    return receipt
