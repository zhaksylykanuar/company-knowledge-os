#!/usr/bin/env python
"""Report no-marker persisted attention candidates without creating delivery artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, not_, select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.digest import (  # noqa: E402
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
    SYNTHETIC_PERSISTED_ATTENTION_SOURCE_OBJECT_PREFIX,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import report_manual_pilot_status as pilot_status_script  # noqa: E402


class NoMarkerCandidateInputError(ValueError):
    pass


class NoMarkerCandidateBlockedError(RuntimeError):
    pass


class NoMarkerCandidateRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NoMarkerCandidateQuery:
    start_at: datetime
    end_at: datetime
    activity_start_at: datetime | None = None
    activity_end_at: datetime | None = None
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT
    debug_evidence: bool = False
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise NoMarkerCandidateInputError(str(exc)) from exc


def _clean_limit(value: int) -> int:
    if not isinstance(value, int):
        raise NoMarkerCandidateInputError("limit must be an integer")
    if value < 1 or value > MAX_DIGEST_ENTRY_LIMIT:
        raise NoMarkerCandidateInputError(
            f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}"
        )
    return value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-at",
        required=True,
        help="Timezone-aware ISO start for the persisted attention window.",
    )
    parser.add_argument(
        "--end-at",
        required=True,
        help="Timezone-aware ISO end for the persisted attention window.",
    )
    parser.add_argument(
        "--activity-start-at",
        help="Optional timezone-aware ISO start for linked source/activity rows.",
    )
    parser.add_argument(
        "--activity-end-at",
        help="Optional timezone-aware ISO end for linked source/activity rows.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_DIGEST_ENTRY_LIMIT,
        help=f"Maximum visible items per section, 1-{MAX_DIGEST_ENTRY_LIMIT}.",
    )
    parser.add_argument(
        "--debug-evidence",
        action="store_true",
        help="Use existing digest debug-evidence semantics for hash computation only.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> NoMarkerCandidateQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise NoMarkerCandidateInputError("end_at must be after start_at")

    activity_start_at = None
    activity_end_at = None
    if args.activity_start_at is not None or args.activity_end_at is not None:
        if args.activity_start_at is None or args.activity_end_at is None:
            raise NoMarkerCandidateInputError(
                "activity_start_at and activity_end_at must be supplied together"
            )
        activity_start_at = _parse_datetime(
            args.activity_start_at,
            field_name="activity_start_at",
        )
        activity_end_at = _parse_datetime(
            args.activity_end_at,
            field_name="activity_end_at",
        )
        if activity_end_at <= activity_start_at:
            raise NoMarkerCandidateInputError(
                "activity_end_at must be after activity_start_at"
            )

    return NoMarkerCandidateQuery(
        start_at=start_at,
        end_at=end_at,
        activity_start_at=activity_start_at,
        activity_end_at=activity_end_at,
        limit=_clean_limit(args.limit),
        debug_evidence=bool(args.debug_evidence),
        output_format=args.format,
    )


def _safe_int(value: Any) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _safe_count_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): _safe_int(count)
        for key, count in sorted(value.items())
        if isinstance(key, str)
    }


def _synthetic_marker_clause(record_class: Any) -> Any:
    return (
        (record_class.source == "internal")
        & record_class.source_object_id.like(
            f"{SYNTHETIC_PERSISTED_ATTENTION_SOURCE_OBJECT_PREFIX}%"
        )
    )


def _marker_status(*, synthetic_count: int, no_marker_count: int, total: int) -> str:
    if total < 1:
        return "unknown"
    if synthetic_count > 0 and no_marker_count > 0:
        return "mixed"
    if synthetic_count > 0:
        return "synthetic_local_dev_detected"
    return "no_synthetic_marker_detected"


async def _marker_counts(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
) -> dict[str, Any]:
    from app.db.attention_models import AttentionTriageResultRecord

    filters = (
        AttentionTriageResultRecord.created_at >= start_at,
        AttentionTriageResultRecord.created_at < end_at,
    )
    visible_filters = (*filters, AttentionTriageResultRecord.show_in_digest.is_(True))
    synthetic_clause = _synthetic_marker_clause(AttentionTriageResultRecord)
    total = _safe_int(
        await session.scalar(
            select(func.count()).select_from(AttentionTriageResultRecord).where(*filters)
        )
    )
    visible = _safe_int(
        await session.scalar(
            select(func.count())
            .select_from(AttentionTriageResultRecord)
            .where(*visible_filters)
        )
    )
    synthetic = _safe_int(
        await session.scalar(
            select(func.count())
            .select_from(AttentionTriageResultRecord)
            .where(*filters, synthetic_clause)
        )
    )
    synthetic_visible = _safe_int(
        await session.scalar(
            select(func.count())
            .select_from(AttentionTriageResultRecord)
            .where(*visible_filters, synthetic_clause)
        )
    )
    no_marker = max(total - synthetic, 0)
    synthetic_hidden = max(synthetic - synthetic_visible, 0)
    return {
        "total": total,
        "visible": visible,
        "synthetic_marker_count": synthetic,
        "synthetic_visible_count": synthetic_visible,
        "synthetic_hidden_count": synthetic_hidden,
        "no_marker_count": no_marker,
        "no_marker_visible_count": max(visible - synthetic_visible, 0),
        "other_marker_count": 0,
    }


def _candidate_summary(
    *,
    digest: Mapping[str, Any],
    draft_preview: Mapping[str, Any],
) -> dict[str, Any]:
    safe_summary = pilot_status_script._safe_digest_summary(digest)
    metadata = (
        safe_summary.get("metadata")
        if isinstance(safe_summary.get("metadata"), Mapping)
        else {}
    )
    return {
        "total": safe_summary["total"],
        "visible": safe_summary["visible"],
        "hidden": safe_summary["hidden"],
        "shown": safe_summary["shown"],
        "truncated": metadata.get("truncated") is True,
        "by_source": safe_summary["by_source"],
        "by_attention_class": safe_summary["by_attention_class"],
        "by_priority": safe_summary["by_priority"],
        "hidden_low_priority_count": safe_summary["hidden_low_priority_count"],
        "text_sha256": draft_preview.get("text_sha256"),
        "char_count": draft_preview.get("char_count"),
        "chunk_count": draft_preview.get("chunk_count"),
    }


async def _timestamp_reconciliation(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
    activity_start_at: datetime | None,
    activity_end_at: datetime | None,
    no_marker_attention_results_in_persisted_window_count: int,
) -> dict[str, Any]:
    if activity_start_at is None or activity_end_at is None:
        return {
            "activity_window_supplied": False,
            "linkage_available": False,
            "no_marker_attention_results_in_persisted_window_count": (
                no_marker_attention_results_in_persisted_window_count
            ),
            "linked_no_marker_normalized_activity_in_activity_window_count": 0,
            "linked_no_marker_source_events_in_activity_window_count": 0,
            "no_marker_attention_results_linked_to_activity_window_count": 0,
            "no_marker_attention_results_in_persisted_window_linked_to_activity_window_count": 0,
            "no_marker_attention_results_write_time_outside_activity_window_count": 0,
            "no_marker_normalized_items_in_activity_window_with_attention_result_count": 0,
            "timestamp_mismatch_detected": False,
        }

    from app.db.attention_models import AttentionTriageResultRecord
    from app.db.event_models import NormalizedActivityItemRecord, SourceEvent

    activity_time = func.coalesce(
        NormalizedActivityItemRecord.activity_created_at,
        NormalizedActivityItemRecord.created_at,
    )
    normalized_rows = (
        await session.execute(
            select(
                NormalizedActivityItemRecord.activity_item_id,
                NormalizedActivityItemRecord.source_event_id,
            )
            .where(activity_time >= activity_start_at, activity_time < activity_end_at)
            .order_by(NormalizedActivityItemRecord.id)
        )
    ).all()
    normalized_by_activity_id = {
        row.activity_item_id: row.source_event_id
        for row in normalized_rows
        if isinstance(row.activity_item_id, str) and row.activity_item_id
    }

    linked_attention_rows = []
    if normalized_by_activity_id:
        linked_attention_rows = list(
            (
                await session.scalars(
                    select(AttentionTriageResultRecord)
                    .where(
                        AttentionTriageResultRecord.activity_item_id.in_(
                            sorted(normalized_by_activity_id)
                        )
                    )
                    .where(AttentionTriageResultRecord.activity_item_id.is_not(None))
                    .where(
                        not_(
                            _synthetic_marker_clause(
                                AttentionTriageResultRecord
                            )
                        )
                    )
                    .order_by(AttentionTriageResultRecord.id)
                )
            ).all()
        )

    linked_activity_ids = {
        row.activity_item_id
        for row in linked_attention_rows
        if isinstance(row.activity_item_id, str) and row.activity_item_id
    }
    linked_source_event_ids = {
        normalized_by_activity_id[activity_item_id]
        for activity_item_id in linked_activity_ids
        if isinstance(normalized_by_activity_id.get(activity_item_id), str)
    }
    linked_source_count = 0
    if linked_source_event_ids:
        source_time = func.coalesce(SourceEvent.source_event_ts, SourceEvent.created_at)
        linked_source_count = _safe_int(
            await session.scalar(
                select(func.count())
                .select_from(SourceEvent)
                .where(SourceEvent.source_event_id.in_(linked_source_event_ids))
                .where(source_time >= activity_start_at, source_time < activity_end_at)
            )
        )

    linked_attention_count = len(linked_attention_rows)
    linked_attention_in_persisted_window_count = sum(
        1
        for row in linked_attention_rows
        if row.created_at >= start_at and row.created_at < end_at
    )
    outside_activity_window_count = sum(
        1
        for row in linked_attention_rows
        if row.created_at < activity_start_at or row.created_at >= activity_end_at
    )
    return {
        "activity_window_supplied": True,
        "linkage_available": True,
        "no_marker_attention_results_in_persisted_window_count": (
            no_marker_attention_results_in_persisted_window_count
        ),
        "linked_no_marker_normalized_activity_in_activity_window_count": (
            len(linked_activity_ids)
        ),
        "linked_no_marker_source_events_in_activity_window_count": linked_source_count,
        "no_marker_attention_results_linked_to_activity_window_count": (
            linked_attention_count
        ),
        "no_marker_attention_results_in_persisted_window_linked_to_activity_window_count": (
            linked_attention_in_persisted_window_count
        ),
        "no_marker_attention_results_write_time_outside_activity_window_count": (
            outside_activity_window_count
        ),
        "no_marker_normalized_items_in_activity_window_with_attention_result_count": (
            len(linked_activity_ids)
        ),
        "timestamp_mismatch_detected": outside_activity_window_count > 0,
    }


def _draft_has_successful_delivery(draft: Mapping[str, Any]) -> bool:
    summary = draft.get("delivery_results_summary")
    if not isinstance(summary, Mapping):
        return False
    return _safe_int(summary.get("successful_count")) > 0


def _candidate_lifecycle_status(
    *,
    visible_count: int,
    matching_hash_has_successful_delivery_result: bool,
    candidate_has_matching_draft_hash: bool,
    prior_successful_delivery_for_different_digest_hash: bool,
) -> str:
    if visible_count < 1:
        return "candidate_has_no_visible_items"
    if matching_hash_has_successful_delivery_result:
        return "candidate_already_successfully_sent"
    if candidate_has_matching_draft_hash:
        return "candidate_has_matching_draft_without_successful_delivery"
    if prior_successful_delivery_for_different_digest_hash:
        return "prior_successful_delivery_for_different_digest_hash"
    return "candidate_unsent_no_matching_draft"


def _candidate_lifecycle_reconciliation(
    *,
    candidate_text_sha256: str | None,
    candidate_visible_count: int,
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    matching_drafts = [
        draft for draft in drafts if draft.get("text_sha256") == candidate_text_sha256
    ]
    matching_ids = [
        str(draft.get("delivery_draft_id"))
        for draft in matching_drafts
        if isinstance(draft.get("delivery_draft_id"), str)
    ]
    successful_drafts = [draft for draft in drafts if _draft_has_successful_delivery(draft)]
    matching_success = any(_draft_has_successful_delivery(draft) for draft in matching_drafts)
    prior_different_success = any(
        draft.get("text_sha256") != candidate_text_sha256
        for draft in successful_drafts
    )
    candidate_has_matching_hash = bool(matching_drafts)
    return {
        "associated_window_draft_count": len(drafts),
        "candidate_text_sha256": candidate_text_sha256,
        "candidate_has_matching_draft_hash": candidate_has_matching_hash,
        "matching_hash_delivery_draft_ids": matching_ids,
        "matching_hash_has_successful_delivery_result": matching_success,
        "any_window_successful_delivery_result": bool(successful_drafts),
        "prior_successful_delivery_for_different_digest_hash": (
            prior_different_success
        ),
        "candidate_lifecycle_status": _candidate_lifecycle_status(
            visible_count=candidate_visible_count,
            matching_hash_has_successful_delivery_result=matching_success,
            candidate_has_matching_draft_hash=candidate_has_matching_hash,
            prior_successful_delivery_for_different_digest_hash=(
                prior_different_success
            ),
        ),
        "drafts": drafts,
    }


def _warnings(
    *,
    marker_summary: Mapping[str, Any],
    timestamp_reconciliation: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if marker_summary.get("mixed_source_window") is True:
        warnings.append("mixed_synthetic_and_no_marker_attention_results")
    if _safe_int(candidate.get("visible")) < 1:
        warnings.append("no_no_marker_visible_candidates")
    if timestamp_reconciliation.get("activity_window_supplied") is not True:
        warnings.append("activity_window_not_supplied")
    if timestamp_reconciliation.get("timestamp_mismatch_detected") is True:
        warnings.append("timestamp_mismatch_detected")
    if lifecycle.get("prior_successful_delivery_for_different_digest_hash") is True:
        warnings.append("prior_successful_delivery_for_different_digest_hash")
    if lifecycle.get("matching_hash_has_successful_delivery_result") is True:
        warnings.append("candidate_already_successfully_sent")
    return warnings


def _recommended_next_action(
    *,
    candidate: Mapping[str, Any],
    timestamp_reconciliation: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
) -> str:
    if _safe_int(candidate.get("visible")) < 1:
        return "choose_window_with_no_marker_visible_candidates"
    if lifecycle.get("matching_hash_has_successful_delivery_result") is True:
        return "do_not_resend_same_digest_content"
    if timestamp_reconciliation.get("timestamp_mismatch_detected") is True:
        return "review_no_marker_timestamp_linkage_before_draft_prepare"
    if timestamp_reconciliation.get("linkage_available") is not True:
        return "inspect_linkage_limitations_before_draft_prepare"
    return "prepare_no_marker_draft_after_review"


def _limitations(*, activity_window_supplied: bool) -> list[str]:
    notes = [
        "no_marker_candidate_report_is_count_only_not_company_facts",
        "marker_filter_selects_rows_without_detected_synthetic_local_dev_marker",
        "no_marker_is_not_proof_of_production_truth",
        "candidate_digest_hash_computed_without_returning_digest_body",
        "hidden_low_priority_items_remain_count_only",
        "draft_lifecycle_is_hash_aware_for_no_marker_candidate_content",
        "delivery_execution_remains_separately_gated",
    ]
    if not activity_window_supplied:
        notes.append("activity_window_not_supplied_linkage_counts_limited")
    return notes


def _safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "local_operator_command": True,
        "db_write_scope": "none",
        "source_events_created": False,
        "normalized_activity_created": False,
        "attention_results_created": False,
        "approval_created": False,
        "rejection_created": False,
        "delivery_draft_created": False,
        "delivery_intention_created": False,
        "telegram_plan_created": False,
        "preflight_created": False,
        "execution_gate_created": False,
        "delivery_result_created": False,
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "telegram_invoked": False,
        "slack_invoked": False,
        "scheduler_invoked": False,
        "delivery_worker_invoked": False,
        "outbox_record_created": False,
        "api_clients_invoked": False,
        "connectors_invoked": False,
        "live_api_calls": False,
        "openai_invoked": False,
        "stored_digest_text_included": False,
        "chunk_text_included": False,
        "credential_values_exposed": False,
        "raw_content_exposed": False,
        "item_details_included": False,
        "evidence_refs_included": False,
        "raw_storage_touched": False,
        "obsidian_touched": False,
        "production_mode": False,
        "report_is_source_of_truth": False,
        "draft_is_source_of_truth": False,
        "intention_is_source_of_truth": False,
        "delivery_result_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _safety_metadata(),
    }


async def build_no_marker_persisted_attention_candidate_report(
    query: NoMarkerCandidateQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    settings_override: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.db.base import AsyncSessionLocal
    from app.services.digest import build_persisted_attention_digest_read_model
    from app.services.digest_delivery_drafts import (
        build_persisted_attention_digest_delivery_draft,
        list_persisted_digest_delivery_drafts_for_window,
        sanitize_persisted_attention_digest_for_delivery_draft,
    )
    from app.services.digest_rendering import render_persisted_attention_digest_text

    try:
        prepare_script._assert_local_environment(
            settings=settings_override or settings,
            environ=environ if environ is not None else os.environ,
        )
    except prepare_script.PrepareBlockedError as exc:
        raise NoMarkerCandidateBlockedError(str(exc)) from exc

    session_factory = session_factory or AsyncSessionLocal
    try:
        async with session_factory() as session:
            candidate_digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                limit_per_section=query.limit,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
            safe_candidate_digest = (
                sanitize_persisted_attention_digest_for_delivery_draft(
                    candidate_digest,
                    debug_evidence=query.debug_evidence,
                )
            )
            rendered_text = render_persisted_attention_digest_text(
                safe_candidate_digest,
                debug_evidence=query.debug_evidence,
            )
            draft_preview = build_persisted_attention_digest_delivery_draft(
                digest=safe_candidate_digest,
                rendered_text=rendered_text,
                start_at=query.start_at,
                end_at=query.end_at,
                limit=query.limit,
                debug_evidence=query.debug_evidence,
            )
            candidate = _candidate_summary(
                digest=candidate_digest,
                draft_preview=draft_preview,
            )
            marker_counts = await _marker_counts(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
            )
            timestamp_reconciliation = await _timestamp_reconciliation(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                activity_start_at=query.activity_start_at,
                activity_end_at=query.activity_end_at,
                no_marker_attention_results_in_persisted_window_count=_safe_int(
                    marker_counts.get("no_marker_count")
                ),
            )
            matching_drafts = await list_persisted_digest_delivery_drafts_for_window(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                limit=query.limit,
                debug_evidence=query.debug_evidence,
            )
            draft_summaries = [
                await pilot_status_script._draft_lifecycle_summary(
                    session,
                    draft=draft,
                )
                for draft in matching_drafts
            ]
    except (
        NoMarkerCandidateInputError,
        NoMarkerCandidateBlockedError,
        NoMarkerCandidateRuntimeError,
    ):
        raise
    except ValueError as exc:
        raise NoMarkerCandidateInputError(str(exc)) from exc
    except Exception as exc:
        raise NoMarkerCandidateRuntimeError(
            "no-marker persisted attention candidate report blocked; database, schema, or configuration is unavailable"
        ) from exc

    lifecycle = _candidate_lifecycle_reconciliation(
        candidate_text_sha256=str(candidate.get("text_sha256") or ""),
        candidate_visible_count=_safe_int(candidate.get("visible")),
        drafts=draft_summaries,
    )
    marker_summary = {
        "no_marker_count": _safe_int(marker_counts.get("no_marker_count")),
        "synthetic_marker_count": _safe_int(
            marker_counts.get("synthetic_marker_count")
        ),
        "mixed_source_window": _safe_int(marker_counts.get("no_marker_count")) > 0
        and _safe_int(marker_counts.get("synthetic_marker_count")) > 0,
        "synthetic_status": _marker_status(
            synthetic_count=_safe_int(marker_counts.get("synthetic_marker_count")),
            no_marker_count=_safe_int(marker_counts.get("no_marker_count")),
            total=_safe_int(marker_counts.get("total")),
        ),
        "no_marker_not_production_truth": True,
    }
    excluded_markers = {
        "synthetic_marker_count": _safe_int(
            marker_counts.get("synthetic_marker_count")
        ),
        "synthetic_visible_count": _safe_int(
            marker_counts.get("synthetic_visible_count")
        ),
        "synthetic_hidden_count": _safe_int(
            marker_counts.get("synthetic_hidden_count")
        ),
        "other_marker_count": _safe_int(marker_counts.get("other_marker_count")),
    }
    warnings = _warnings(
        marker_summary=marker_summary,
        timestamp_reconciliation=timestamp_reconciliation,
        lifecycle=lifecycle,
        candidate=candidate,
    )
    return {
        "status": "no_marker_persisted_attention_candidates",
        "start_at": query.start_at.isoformat(),
        "end_at": query.end_at.isoformat(),
        "activity_start_at": (
            query.activity_start_at.isoformat()
            if query.activity_start_at is not None
            else None
        ),
        "activity_end_at": (
            query.activity_end_at.isoformat()
            if query.activity_end_at is not None
            else None
        ),
        "limit": query.limit,
        "debug_evidence": query.debug_evidence,
        "marker_filter": PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
        "no_marker_candidate": candidate,
        "excluded_markers": excluded_markers,
        "marker_summary": marker_summary,
        "timestamp_reconciliation": timestamp_reconciliation,
        "candidate_lifecycle_reconciliation": lifecycle,
        "recommended_next_action": _recommended_next_action(
            candidate=candidate,
            timestamp_reconciliation=timestamp_reconciliation,
            lifecycle=lifecycle,
        ),
        "warnings": warnings,
        "limitations": _limitations(
            activity_window_supplied=query.activity_start_at is not None
            and query.activity_end_at is not None,
        ),
        "safety": _safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    candidate = (
        report.get("no_marker_candidate")
        if isinstance(report.get("no_marker_candidate"), Mapping)
        else {}
    )
    excluded = (
        report.get("excluded_markers")
        if isinstance(report.get("excluded_markers"), Mapping)
        else {}
    )
    marker = (
        report.get("marker_summary")
        if isinstance(report.get("marker_summary"), Mapping)
        else {}
    )
    timestamp = (
        report.get("timestamp_reconciliation")
        if isinstance(report.get("timestamp_reconciliation"), Mapping)
        else {}
    )
    lifecycle = (
        report.get("candidate_lifecycle_reconciliation")
        if isinstance(report.get("candidate_lifecycle_reconciliation"), Mapping)
        else {}
    )
    safety = report.get("safety") if isinstance(report.get("safety"), Mapping) else {}
    lines = [
        "No-marker persisted attention candidates (read-only)",
        f"Window start: {report.get('start_at')}",
        f"Window end: {report.get('end_at')}",
        f"Activity window start: {report.get('activity_start_at')}",
        f"Activity window end: {report.get('activity_end_at')}",
        f"Limit: {report.get('limit')}",
        f"Debug evidence: {report.get('debug_evidence')}",
        f"Marker filter: {report.get('marker_filter')}",
        f"Candidate total: {candidate.get('total')}",
        f"Candidate visible: {candidate.get('visible')}",
        f"Candidate hidden: {candidate.get('hidden')}",
        f"Candidate shown: {candidate.get('shown')}",
        f"Candidate truncated: {candidate.get('truncated')}",
        f"Candidate text SHA-256: {candidate.get('text_sha256')}",
        f"Candidate char count: {candidate.get('char_count')}",
        f"Candidate chunk count: {candidate.get('chunk_count')}",
        f"Excluded synthetic marker count: {excluded.get('synthetic_marker_count')}",
        f"Excluded synthetic visible count: {excluded.get('synthetic_visible_count')}",
        f"Synthetic status: {marker.get('synthetic_status')}",
        f"No-marker count: {marker.get('no_marker_count')}",
        "No-marker is production truth: False",
        f"Timestamp mismatch detected: {timestamp.get('timestamp_mismatch_detected')}",
        (
            "No-marker attention linked to activity window: "
            f"{timestamp.get('no_marker_attention_results_linked_to_activity_window_count')}"
        ),
        (
            "No-marker attention outside activity window: "
            f"{timestamp.get('no_marker_attention_results_write_time_outside_activity_window_count')}"
        ),
        (
            "Candidate has matching draft hash: "
            f"{lifecycle.get('candidate_has_matching_draft_hash')}"
        ),
        (
            "Matching hash has successful delivery: "
            f"{lifecycle.get('matching_hash_has_successful_delivery_result')}"
        ),
        (
            "Prior success for different hash: "
            f"{lifecycle.get('prior_successful_delivery_for_different_digest_hash')}"
        ),
        f"Candidate lifecycle status: {lifecycle.get('candidate_lifecycle_status')}",
        f"Recommended next action: {report.get('recommended_next_action')}",
        f"Warnings: {report.get('warnings')}",
        "",
        f"Provider free: {safety.get('provider_free')}",
        f"Read only: {safety.get('read_only')}",
        f"DB write scope: {safety.get('db_write_scope')}",
        f"Delivery draft created: {safety.get('delivery_draft_created')}",
        f"Delivery intention created: {safety.get('delivery_intention_created')}",
        f"Delivery result created: {safety.get('delivery_result_created')}",
        f"Delivery invoked: {safety.get('delivery_invoked')}",
        f"Telegram invoked: {safety.get('telegram_invoked')}",
        f"Scheduler invoked: {safety.get('scheduler_invoked')}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        report = asyncio.run(
            build_no_marker_persisted_attention_candidate_report(query)
        )
    except NoMarkerCandidateInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except NoMarkerCandidateBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except NoMarkerCandidateRuntimeError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="runtime_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    if query.output_format == "json":
        _print_json(report)
    else:
        print(format_text_report(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
