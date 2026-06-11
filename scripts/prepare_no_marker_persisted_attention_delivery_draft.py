#!/usr/bin/env python
"""Prepare an inert delivery draft from no-marker persisted attention candidates."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.digest import (  # noqa: E402
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import report_no_marker_persisted_attention_candidates as no_marker_script  # noqa: E402

CONFIRM_PREPARE_PHRASE = "PREPARE NO-MARKER DIGEST DRAFT"
ACTOR = "operator_no_marker_persisted_attention_prepare"


class NoMarkerDraftPrepareInputError(ValueError):
    pass


class NoMarkerDraftPrepareBlockedError(RuntimeError):
    pass


class NoMarkerDraftPrepareRuntimeError(RuntimeError):
    pass


DIGEST_STYLE_STANDARD = "standard"
DIGEST_STYLE_FOUNDER_V2 = "founder_v2"
DIGEST_STYLE_CHOICES = (DIGEST_STYLE_STANDARD, DIGEST_STYLE_FOUNDER_V2)


@dataclass(frozen=True)
class NoMarkerDraftPrepareQuery:
    start_at: datetime
    end_at: datetime
    confirm_prepare: str
    activity_start_at: datetime | None = None
    activity_end_at: datetime | None = None
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT
    debug_evidence: bool = False
    digest_style: str = DIGEST_STYLE_STANDARD
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise NoMarkerDraftPrepareInputError(str(exc)) from exc


def _clean_limit(value: int) -> int:
    if not isinstance(value, int):
        raise NoMarkerDraftPrepareInputError("limit must be an integer")
    if value < 1 or value > MAX_DIGEST_ENTRY_LIMIT:
        raise NoMarkerDraftPrepareInputError(
            f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}"
        )
    return value


def _clean_confirm(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NoMarkerDraftPrepareInputError("confirm_prepare must not be empty")
    cleaned = value.strip()
    if cleaned != CONFIRM_PREPARE_PHRASE:
        raise NoMarkerDraftPrepareInputError("confirm_prepare phrase did not match")
    return cleaned


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
        "--confirm-prepare",
        required=True,
        help=f'Must be exactly "{CONFIRM_PREPARE_PHRASE}".',
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
        help="Use existing persisted digest debug-evidence semantics for storage.",
    )
    parser.add_argument(
        "--digest-style",
        choices=DIGEST_STYLE_CHOICES,
        default=DIGEST_STYLE_STANDARD,
        help="Draft body style: standard renderer or founder digest v2.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> NoMarkerDraftPrepareQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise NoMarkerDraftPrepareInputError("end_at must be after start_at")

    activity_start_at = None
    activity_end_at = None
    if args.activity_start_at is not None or args.activity_end_at is not None:
        if args.activity_start_at is None or args.activity_end_at is None:
            raise NoMarkerDraftPrepareInputError(
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
            raise NoMarkerDraftPrepareInputError(
                "activity_end_at must be after activity_start_at"
            )

    return NoMarkerDraftPrepareQuery(
        start_at=start_at,
        end_at=end_at,
        confirm_prepare=_clean_confirm(args.confirm_prepare),
        activity_start_at=activity_start_at,
        activity_end_at=activity_end_at,
        limit=_clean_limit(args.limit),
        debug_evidence=bool(args.debug_evidence),
        digest_style=str(args.digest_style),
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


def _candidate_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    candidate = (
        report.get("no_marker_candidate")
        if isinstance(report.get("no_marker_candidate"), Mapping)
        else {}
    )
    return {
        "total": _safe_int(candidate.get("total")),
        "visible": _safe_int(candidate.get("visible")),
        "hidden": _safe_int(candidate.get("hidden")),
        "shown": _safe_int(candidate.get("shown")),
        "truncated": candidate.get("truncated") is True,
        "by_source": _safe_count_mapping(candidate.get("by_source")),
        "by_attention_class": _safe_count_mapping(
            candidate.get("by_attention_class")
        ),
        "by_priority": _safe_count_mapping(candidate.get("by_priority")),
        "hidden_low_priority_count": _safe_int(
            candidate.get("hidden_low_priority_count")
        ),
        "text_sha256": candidate.get("text_sha256"),
        "char_count": _safe_int(candidate.get("char_count")),
        "chunk_count": _safe_int(candidate.get("chunk_count")),
    }


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _excluded_markers_from_report(report: Mapping[str, Any]) -> dict[str, int]:
    excluded = _safe_mapping(report.get("excluded_markers"))
    return {
        "synthetic_marker_count": _safe_int(excluded.get("synthetic_marker_count")),
        "synthetic_visible_count": _safe_int(excluded.get("synthetic_visible_count")),
        "synthetic_hidden_count": _safe_int(excluded.get("synthetic_hidden_count")),
        "other_marker_count": _safe_int(excluded.get("other_marker_count")),
    }


def _timestamp_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    timestamp = _safe_mapping(report.get("timestamp_reconciliation"))
    return {
        "activity_window_supplied": timestamp.get("activity_window_supplied") is True,
        "linkage_available": timestamp.get("linkage_available") is True,
        "no_marker_attention_results_in_persisted_window_count": _safe_int(
            timestamp.get("no_marker_attention_results_in_persisted_window_count")
        ),
        "linked_no_marker_normalized_activity_in_activity_window_count": _safe_int(
            timestamp.get(
                "linked_no_marker_normalized_activity_in_activity_window_count"
            )
        ),
        "linked_no_marker_source_events_in_activity_window_count": _safe_int(
            timestamp.get("linked_no_marker_source_events_in_activity_window_count")
        ),
        "no_marker_attention_results_linked_to_activity_window_count": _safe_int(
            timestamp.get(
                "no_marker_attention_results_linked_to_activity_window_count"
            )
        ),
        "no_marker_attention_results_in_persisted_window_linked_to_activity_window_count": (
            _safe_int(
                timestamp.get(
                    "no_marker_attention_results_in_persisted_window_linked_to_activity_window_count"
                )
            )
        ),
        "no_marker_attention_results_write_time_outside_activity_window_count": (
            _safe_int(
                timestamp.get(
                    "no_marker_attention_results_write_time_outside_activity_window_count"
                )
            )
        ),
        "no_marker_normalized_items_in_activity_window_with_attention_result_count": (
            _safe_int(
                timestamp.get(
                    "no_marker_normalized_items_in_activity_window_with_attention_result_count"
                )
            )
        ),
        "timestamp_mismatch_detected": (
            timestamp.get("timestamp_mismatch_detected") is True
        ),
    }


def _safe_lifecycle_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    lifecycle = _safe_mapping(report.get("candidate_lifecycle_reconciliation"))
    matching_ids = lifecycle.get("matching_hash_delivery_draft_ids")
    safe_matching_ids = (
        [str(value) for value in matching_ids if isinstance(value, str)]
        if isinstance(matching_ids, list)
        else []
    )
    return {
        "candidate_text_sha256": lifecycle.get("candidate_text_sha256"),
        "candidate_has_matching_draft_hash": (
            lifecycle.get("candidate_has_matching_draft_hash") is True
        ),
        "matching_hash_delivery_draft_ids": safe_matching_ids,
        "matching_hash_has_successful_delivery_result": (
            lifecycle.get("matching_hash_has_successful_delivery_result") is True
        ),
        "any_window_successful_delivery_result": (
            lifecycle.get("any_window_successful_delivery_result") is True
        ),
        "prior_successful_delivery_for_different_digest_hash": (
            lifecycle.get("prior_successful_delivery_for_different_digest_hash")
            is True
        ),
        "candidate_lifecycle_status": lifecycle.get("candidate_lifecycle_status"),
    }


def _warnings_from_report(report: Mapping[str, Any]) -> list[str]:
    warnings = report.get("warnings")
    if not isinstance(warnings, list):
        return []
    return sorted(str(warning) for warning in warnings if isinstance(warning, str))


def _post_prepare_lifecycle(
    *,
    delivery_draft_id: str,
    candidate_text_sha256: str | None,
    preflight_lifecycle: Mapping[str, Any],
    draft_usage_status: Mapping[str, Any],
) -> dict[str, Any]:
    results_summary = _safe_mapping(draft_usage_status.get("delivery_results_summary"))
    matching_hash_success = _safe_int(results_summary.get("successful_count")) > 0
    prior_different_success = (
        preflight_lifecycle.get(
            "prior_successful_delivery_for_different_digest_hash"
        )
        is True
    )
    return {
        "candidate_text_sha256": candidate_text_sha256,
        "candidate_has_matching_draft_hash": True,
        "matching_hash_delivery_draft_ids": [delivery_draft_id],
        "matching_hash_has_successful_delivery_result": matching_hash_success,
        "any_window_successful_delivery_result": (
            matching_hash_success
            or preflight_lifecycle.get("any_window_successful_delivery_result")
            is True
        ),
        "prior_successful_delivery_for_different_digest_hash": (
            prior_different_success
        ),
        "candidate_lifecycle_status": (
            "candidate_already_successfully_sent"
            if matching_hash_success
            else "candidate_has_matching_draft_without_successful_delivery"
        ),
    }


def _activity_window_metadata(query: NoMarkerDraftPrepareQuery) -> dict[str, Any] | None:
    if query.activity_start_at is None or query.activity_end_at is None:
        return None
    return {
        "start_at": query.activity_start_at.isoformat(),
        "end_at": query.activity_end_at.isoformat(),
    }


def _enrich_no_marker_draft(
    draft: Mapping[str, Any],
    *,
    query: NoMarkerDraftPrepareQuery,
    candidate: Mapping[str, Any],
    excluded_markers: Mapping[str, Any],
    marker_summary: Mapping[str, Any],
    timestamp_reconciliation: Mapping[str, Any],
    preflight_lifecycle: Mapping[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    enriched = dict(draft)
    digest = _safe_mapping(enriched.get("digest"))
    metadata = _safe_mapping(digest.get("metadata"))
    metadata.update(
        {
            "marker_filter": PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            "filtered_digest": True,
            "filter_scope": "no_marker_persisted_attention_candidate",
            "no_marker_not_production_truth": True,
            "digest_style": query.digest_style,
            "activity_window": _activity_window_metadata(query),
            "candidate_text_sha256": candidate.get("text_sha256"),
            "excluded_markers": dict(excluded_markers),
            "timestamp_mismatch_detected": (
                timestamp_reconciliation.get("timestamp_mismatch_detected") is True
            ),
            "prior_successful_delivery_for_different_digest_hash": (
                preflight_lifecycle.get(
                    "prior_successful_delivery_for_different_digest_hash"
                )
                is True
            ),
            "warnings": list(warnings),
        }
    )
    digest["metadata"] = metadata
    enriched["digest"] = digest

    source_of_truth = _safe_mapping(enriched.get("source_of_truth"))
    source_of_truth.update(
        {
            "delivery_draft_scope": "no_marker_persisted_attention_candidate",
            "marker_filter": PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            "filtered_digest": True,
            "synthetic_local_dev_excluded": True,
            "no_marker_not_production_truth": True,
            "counts_are_operational_metadata": True,
            "candidate_text_sha256": candidate.get("text_sha256"),
            "candidate_counts": {
                "total": _safe_int(candidate.get("total")),
                "visible": _safe_int(candidate.get("visible")),
                "hidden": _safe_int(candidate.get("hidden")),
                "shown": _safe_int(candidate.get("shown")),
            },
            "excluded_markers": dict(excluded_markers),
            "marker_summary": dict(marker_summary),
            "activity_window": _activity_window_metadata(query),
            "timestamp_mismatch_detected": (
                timestamp_reconciliation.get("timestamp_mismatch_detected") is True
            ),
            "warnings": list(warnings),
        }
    )
    enriched["source_of_truth"] = source_of_truth

    safety = _safe_mapping(enriched.get("safety"))
    safety.update(
        {
            "local_dev_only": True,
            "marker_filter": PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            "synthetic_local_dev_excluded": True,
            "no_marker_not_production_truth": True,
            "approval_required": True,
            "approval_created": False,
            "delivery_intention_created": False,
            "delivery_result_created": False,
            "telegram_invoked": False,
            "slack_invoked": False,
            "openai_invoked": False,
            "item_details_included_in_output": False,
            "evidence_refs_included_in_output": False,
        }
    )
    enriched["safety"] = safety
    return enriched


def _safe_delivery_results_summary(value: Any) -> dict[str, int]:
    summary = _safe_mapping(value)
    return {
        "count": _safe_int(summary.get("count")),
        "successful_count": _safe_int(summary.get("successful_count")),
        "failed_count": _safe_int(summary.get("failed_count")),
        "partial_count": _safe_int(summary.get("partial_count")),
        "skipped_count": _safe_int(summary.get("skipped_count")),
    }


def _safety_metadata(*, delivery_draft_record_created: bool) -> dict[str, Any]:
    return {
        "provider_free": True,
        "local_dev_only": True,
        "local_operator_command": True,
        "db_write_scope": (
            "delivery_draft_audit_log_only"
            if delivery_draft_record_created
            else "none"
        ),
        "source_events_created": False,
        "normalized_activity_created": False,
        "attention_results_created": False,
        "approval_created": False,
        "rejection_created": False,
        "delivery_draft_created": delivery_draft_record_created,
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
        "draft_is_source_of_truth": False,
        "intention_is_source_of_truth": False,
        "delivery_result_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _base_result(
    *,
    status: str,
    prepared: bool,
    query: NoMarkerDraftPrepareQuery,
    candidate: Mapping[str, Any],
    excluded_markers: Mapping[str, Any],
    timestamp_reconciliation: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    warnings: list[str],
    delivery_draft_id: str | None,
    delivery_draft_record_created: bool,
    recommended_next_action: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "prepared": prepared,
        "marker_filter": PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
        "no_marker_not_production_truth": True,
        "delivery_draft_id": delivery_draft_id,
        "delivery_draft_record_created": delivery_draft_record_created,
        "delivery_draft_created": delivery_draft_record_created,
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
        "digest_type": "persisted_attention",
        "channel": "telegram",
        "candidate": dict(candidate),
        "excluded_markers": dict(excluded_markers),
        "timestamp_reconciliation": dict(timestamp_reconciliation),
        "lifecycle": dict(lifecycle),
        "warnings": list(warnings),
        "recommended_next_action": recommended_next_action,
        "next_steps": (
            prepare_script._next_step_commands(delivery_draft_id)
            if delivery_draft_id
            else {}
        ),
        "safety": _safety_metadata(
            delivery_draft_record_created=delivery_draft_record_created,
        ),
    }


def _not_prepared_result(
    *,
    query: NoMarkerDraftPrepareQuery,
    candidate: Mapping[str, Any],
    excluded_markers: Mapping[str, Any],
    timestamp_reconciliation: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    warnings: list[str],
    delivery_draft_id: str | None = None,
    recommended_next_action: str,
) -> dict[str, Any]:
    return _base_result(
        status="no_marker_delivery_draft_not_prepared",
        prepared=False,
        query=query,
        candidate=candidate,
        excluded_markers=excluded_markers,
        timestamp_reconciliation=timestamp_reconciliation,
        lifecycle=lifecycle,
        warnings=warnings,
        delivery_draft_id=delivery_draft_id,
        delivery_draft_record_created=False,
        recommended_next_action=recommended_next_action,
    )


async def prepare_no_marker_persisted_attention_delivery_draft(
    query: NoMarkerDraftPrepareQuery,
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
        get_delivery_draft_send_status,
        get_persisted_digest_delivery_draft,
        persist_digest_delivery_draft,
        sanitize_persisted_attention_digest_for_delivery_draft,
    )
    from app.services.digest_rendering import render_persisted_attention_digest_text
    from app.services.founder_digest_rendering import (
        render_founder_attention_digest_text,
    )

    try:
        prepare_script._assert_local_environment(
            settings=settings_override or settings,
            environ=environ if environ is not None else os.environ,
        )
    except prepare_script.PrepareBlockedError as exc:
        raise NoMarkerDraftPrepareBlockedError(str(exc)) from exc

    if query.confirm_prepare != CONFIRM_PREPARE_PHRASE:
        raise NoMarkerDraftPrepareInputError("confirm_prepare phrase did not match")

    session_factory = session_factory or AsyncSessionLocal
    report_query = no_marker_script.NoMarkerCandidateQuery(
        start_at=query.start_at,
        end_at=query.end_at,
        activity_start_at=query.activity_start_at,
        activity_end_at=query.activity_end_at,
        limit=query.limit,
        debug_evidence=query.debug_evidence,
        output_format="json",
    )
    try:
        report = await no_marker_script.build_no_marker_persisted_attention_candidate_report(
            report_query,
            session_factory=session_factory,
            settings_override=settings_override,
            environ=environ,
        )
    except no_marker_script.NoMarkerCandidateInputError as exc:
        raise NoMarkerDraftPrepareInputError(str(exc)) from exc
    except no_marker_script.NoMarkerCandidateBlockedError as exc:
        raise NoMarkerDraftPrepareBlockedError(str(exc)) from exc
    except no_marker_script.NoMarkerCandidateRuntimeError as exc:
        raise NoMarkerDraftPrepareRuntimeError(str(exc)) from exc

    candidate = _candidate_from_report(report)
    excluded_markers = _excluded_markers_from_report(report)
    timestamp_reconciliation = _timestamp_from_report(report)
    preflight_lifecycle = _safe_lifecycle_from_report(report)
    warnings = _warnings_from_report(report)
    marker_summary = _safe_mapping(report.get("marker_summary"))

    if _safe_int(candidate.get("visible")) < 1:
        return _not_prepared_result(
            query=query,
            candidate=candidate,
            excluded_markers=excluded_markers,
            timestamp_reconciliation=timestamp_reconciliation,
            lifecycle=preflight_lifecycle,
            warnings=warnings,
            recommended_next_action="choose_window_with_no_marker_visible_candidates",
        )

    if preflight_lifecycle.get("matching_hash_has_successful_delivery_result") is True:
        matching_ids = preflight_lifecycle.get("matching_hash_delivery_draft_ids")
        delivery_draft_id = (
            matching_ids[0]
            if isinstance(matching_ids, list) and matching_ids
            else None
        )
        if "candidate_already_successfully_sent" not in warnings:
            warnings.append("candidate_already_successfully_sent")
        return _base_result(
            status="no_marker_delivery_draft_already_sent",
            prepared=False,
            query=query,
            candidate=candidate,
            excluded_markers=excluded_markers,
            timestamp_reconciliation=timestamp_reconciliation,
            lifecycle=preflight_lifecycle,
            warnings=sorted(warnings),
            delivery_draft_id=delivery_draft_id,
            delivery_draft_record_created=False,
            recommended_next_action="do_not_resend_same_digest_content",
        )

    try:
        async with session_factory() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                limit_per_section=query.limit,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
            safe_digest = sanitize_persisted_attention_digest_for_delivery_draft(
                digest,
                debug_evidence=query.debug_evidence,
            )
            if query.digest_style == DIGEST_STYLE_FOUNDER_V2:
                rendered_text = render_founder_attention_digest_text(
                    safe_digest,
                    generated_at=datetime.now(timezone.utc),
                )
            else:
                rendered_text = render_persisted_attention_digest_text(
                    safe_digest,
                    debug_evidence=query.debug_evidence,
                )
            draft = build_persisted_attention_digest_delivery_draft(
                digest=safe_digest,
                rendered_text=rendered_text,
                start_at=query.start_at,
                end_at=query.end_at,
                limit=query.limit,
                debug_evidence=query.debug_evidence,
            )
            if (
                query.digest_style == DIGEST_STYLE_STANDARD
                and draft.get("text_sha256") != candidate.get("text_sha256")
            ):
                raise NoMarkerDraftPrepareRuntimeError(
                    "no-marker candidate hash changed before draft persistence"
                )
            draft = _enrich_no_marker_draft(
                draft,
                query=query,
                candidate=candidate,
                excluded_markers=excluded_markers,
                marker_summary=marker_summary,
                timestamp_reconciliation=timestamp_reconciliation,
                preflight_lifecycle=preflight_lifecycle,
                warnings=warnings,
            )
            delivery_draft_id = str(draft.get("delivery_draft_id", ""))
            existing = await get_persisted_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            persisted = await persist_digest_delivery_draft(
                session,
                draft=draft,
                actor=ACTOR,
            )
            delivery_draft_record_created = existing is None
            if delivery_draft_record_created:
                await session.commit()

            draft_usage_status = await get_delivery_draft_send_status(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if draft_usage_status is None:
                raise NoMarkerDraftPrepareRuntimeError(
                    "prepared no-marker delivery draft status was not found"
                )
    except (
        NoMarkerDraftPrepareInputError,
        NoMarkerDraftPrepareBlockedError,
        NoMarkerDraftPrepareRuntimeError,
    ):
        raise
    except ValueError as exc:
        raise NoMarkerDraftPrepareInputError(str(exc)) from exc
    except Exception as exc:
        raise NoMarkerDraftPrepareRuntimeError(
            "no-marker delivery draft preparation blocked; database, schema, or configuration is unavailable"
        ) from exc

    lifecycle = _post_prepare_lifecycle(
        delivery_draft_id=delivery_draft_id,
        candidate_text_sha256=str(candidate.get("text_sha256") or ""),
        preflight_lifecycle=preflight_lifecycle,
        draft_usage_status=draft_usage_status,
    )
    if lifecycle.get("prior_successful_delivery_for_different_digest_hash") is True:
        if "prior_successful_delivery_for_different_digest_hash" not in warnings:
            warnings.append("prior_successful_delivery_for_different_digest_hash")
    if timestamp_reconciliation.get("timestamp_mismatch_detected") is True:
        if "timestamp_mismatch_detected" not in warnings:
            warnings.append("timestamp_mismatch_detected")

    result = _base_result(
        status="no_marker_delivery_draft_prepared",
        prepared=True,
        query=query,
        candidate=candidate,
        excluded_markers=excluded_markers,
        timestamp_reconciliation=timestamp_reconciliation,
        lifecycle=lifecycle,
        warnings=sorted(warnings),
        delivery_draft_id=str(persisted.get("delivery_draft_id")),
        delivery_draft_record_created=delivery_draft_record_created,
        recommended_next_action=(
            "do_not_resend_same_digest_content"
            if lifecycle.get("matching_hash_has_successful_delivery_result") is True
            else "approve_delivery_draft"
        ),
    )
    result.update(
        {
            "text_sha256": persisted.get("text_sha256"),
            "char_count": persisted.get("char_count"),
            "chunk_count": persisted.get("chunk_count"),
            "persisted": bool(persisted.get("persisted")),
            "existing": not delivery_draft_record_created,
            "idempotent": not delivery_draft_record_created,
            "delivery_results_summary": _safe_delivery_results_summary(
                draft_usage_status.get("delivery_results_summary")
            ),
            "associated_delivery_intention_count": _safe_int(
                draft_usage_status.get("associated_delivery_intention_count")
            ),
            "stale_or_already_sent_warning": bool(
                draft_usage_status.get("stale_or_already_sent_warning")
            ),
            "draft_usage_blocker": draft_usage_status.get("blocker"),
        }
    )
    return result


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "prepared": False,
        "error_code": error_code,
        "message": message,
        "safety": _safety_metadata(delivery_draft_record_created=False),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_prepare(result: Mapping[str, Any]) -> str:
    if result.get("status") == "blocked":
        return f"No-marker delivery draft preparation blocked: {result.get('message')}\n"

    candidate = _safe_mapping(result.get("candidate"))
    excluded = _safe_mapping(result.get("excluded_markers"))
    timestamp = _safe_mapping(result.get("timestamp_reconciliation"))
    lifecycle = _safe_mapping(result.get("lifecycle"))
    safety = _safe_mapping(result.get("safety"))
    next_steps = _safe_mapping(result.get("next_steps"))
    lines = [
        "No-marker persisted attention delivery draft",
        f"Status: {result.get('status')}",
        f"Prepared: {result.get('prepared')}",
        f"Delivery draft ID: {result.get('delivery_draft_id')}",
        f"Delivery draft record created: {result.get('delivery_draft_record_created')}",
        f"Existing/idempotent: {result.get('idempotent')}",
        f"Marker filter: {result.get('marker_filter')}",
        "No-marker is production truth: False",
        f"Window start: {result.get('start_at')}",
        f"Window end: {result.get('end_at')}",
        f"Activity window start: {result.get('activity_start_at')}",
        f"Activity window end: {result.get('activity_end_at')}",
        f"Limit: {result.get('limit')}",
        f"Debug evidence: {result.get('debug_evidence')}",
        f"Candidate visible: {candidate.get('visible')}",
        f"Candidate hidden: {candidate.get('hidden')}",
        f"Candidate shown: {candidate.get('shown')}",
        f"Candidate text SHA-256: {candidate.get('text_sha256')}",
        f"Candidate char count: {candidate.get('char_count')}",
        f"Candidate chunk count: {candidate.get('chunk_count')}",
        f"Excluded synthetic marker count: {excluded.get('synthetic_marker_count')}",
        f"Excluded synthetic visible count: {excluded.get('synthetic_visible_count')}",
        f"Timestamp mismatch detected: {timestamp.get('timestamp_mismatch_detected')}",
        (
            "Prior success for different hash: "
            f"{lifecycle.get('prior_successful_delivery_for_different_digest_hash')}"
        ),
        (
            "Matching hash successful delivery: "
            f"{lifecycle.get('matching_hash_has_successful_delivery_result')}"
        ),
        f"Candidate lifecycle status: {lifecycle.get('candidate_lifecycle_status')}",
        f"Recommended next action: {result.get('recommended_next_action')}",
        f"Warnings: {result.get('warnings')}",
        "",
        "Next steps (human approval remains separate):",
        f"Approve draft: {next_steps.get('approve_draft')}",
        f"Check readiness: {next_steps.get('check_readiness')}",
        f"Create delivery intention: {next_steps.get('create_delivery_intention')}",
        f"Review delivery intention: {next_steps.get('review_delivery_intention')}",
        f"Check send status: {next_steps.get('check_send_status')}",
        f"Check execution gate: {next_steps.get('check_execution_gate')}",
        "Bounded test send, DO NOT RUN UNTIL CHECKS PASS: "
        f"{next_steps.get('bounded_test_send_do_not_run_until_checks_pass')}",
        "",
        f"DB write scope: {safety.get('db_write_scope')}",
        f"Approval created: {safety.get('approval_created')}",
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
        result = asyncio.run(
            prepare_no_marker_persisted_attention_delivery_draft(query)
        )
    except NoMarkerDraftPrepareInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except NoMarkerDraftPrepareBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="prepare_blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except NoMarkerDraftPrepareRuntimeError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="runtime_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    if query.output_format == "json":
        _print_json(result)
    else:
        print(format_text_prepare(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
