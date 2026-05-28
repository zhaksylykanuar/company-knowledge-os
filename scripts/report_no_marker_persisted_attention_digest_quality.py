#!/usr/bin/env python
"""Report no-marker persisted attention digest duplicate/noise quality safely."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import not_, select

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


DEFAULT_CLUSTER_THRESHOLD = 2
MAX_CLUSTER_THRESHOLD = 50
TOP_CLUSTER_LIMIT = 5
_INTERNAL_FINGERPRINT_NAMESPACE = "fos088-no-marker-digest-quality-v1"


class NoMarkerDigestQualityInputError(ValueError):
    pass


class NoMarkerDigestQualityBlockedError(RuntimeError):
    pass


class NoMarkerDigestQualityRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NoMarkerDigestQualityQuery:
    start_at: datetime
    end_at: datetime
    activity_start_at: datetime | None = None
    activity_end_at: datetime | None = None
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT
    debug_evidence: bool = False
    cluster_threshold: int = DEFAULT_CLUSTER_THRESHOLD
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise NoMarkerDigestQualityInputError(str(exc)) from exc


def _clean_limit(value: int) -> int:
    if not isinstance(value, int):
        raise NoMarkerDigestQualityInputError("limit must be an integer")
    if value < 1 or value > MAX_DIGEST_ENTRY_LIMIT:
        raise NoMarkerDigestQualityInputError(
            f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}"
        )
    return value


def _clean_cluster_threshold(value: int) -> int:
    if not isinstance(value, int):
        raise NoMarkerDigestQualityInputError("cluster_threshold must be an integer")
    if value < 2 or value > MAX_CLUSTER_THRESHOLD:
        raise NoMarkerDigestQualityInputError(
            f"cluster_threshold must be between 2 and {MAX_CLUSTER_THRESHOLD}"
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
        "--cluster-threshold",
        type=int,
        default=DEFAULT_CLUSTER_THRESHOLD,
        help=(
            "Minimum repeated item count for a duplicate-looking cluster, "
            f"2-{MAX_CLUSTER_THRESHOLD}."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> NoMarkerDigestQualityQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise NoMarkerDigestQualityInputError("end_at must be after start_at")

    activity_start_at = None
    activity_end_at = None
    if args.activity_start_at is not None or args.activity_end_at is not None:
        if args.activity_start_at is None or args.activity_end_at is None:
            raise NoMarkerDigestQualityInputError(
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
            raise NoMarkerDigestQualityInputError(
                "activity_end_at must be after activity_start_at"
            )

    return NoMarkerDigestQualityQuery(
        start_at=start_at,
        end_at=end_at,
        activity_start_at=activity_start_at,
        activity_end_at=activity_end_at,
        limit=_clean_limit(args.limit),
        debug_evidence=bool(args.debug_evidence),
        cluster_threshold=_clean_cluster_threshold(args.cluster_threshold),
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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return value
    return []


def _canonical_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.casefold().strip().split())


def _internal_fingerprint(parts: Sequence[Any]) -> str:
    payload = json.dumps(
        {
            "namespace": _INTERNAL_FINGERPRINT_NAMESPACE,
            "parts": list(parts),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _counter_for(items: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in items:
        value = item.get(field_name)
        if isinstance(value, str) and value:
            counter[value] += 1
    return dict(sorted(counter.items()))


def _safe_enum_summary(
    items: Sequence[Mapping[str, Any]],
    *,
    fields: Sequence[str],
) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for field_name in fields:
        counts = _counter_for(items, field_name)
        if counts:
            summary[f"by_{field_name}"] = counts
    return summary


def _cluster_report(
    items: Sequence[Mapping[str, Any]],
    *,
    key_func: Callable[[Mapping[str, Any]], Sequence[Any]],
    enum_fields: Sequence[str],
    threshold: int,
) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        groups[_internal_fingerprint(key_func(item))].append(item)

    sorted_groups = sorted(
        groups.items(),
        key=lambda pair: (-len(pair[1]), pair[0]),
    )
    duplicate_groups = [
        (fingerprint, grouped_items)
        for fingerprint, grouped_items in sorted_groups
        if len(grouped_items) >= threshold
    ]
    top_clusters = [
        {
            "cluster_id": f"cluster_{index:03d}",
            "count": len(grouped_items),
            "safe_enum_summary": _safe_enum_summary(
                grouped_items,
                fields=enum_fields,
            ),
        }
        for index, (_fingerprint, grouped_items) in enumerate(
            duplicate_groups[:TOP_CLUSTER_LIMIT],
            start=1,
        )
    ]
    return {
        "cluster_count": len(groups),
        "duplicate_cluster_count": len(duplicate_groups),
        "duplicate_item_count": sum(len(group) for _fingerprint, group in duplicate_groups),
        "largest_cluster_size": max((len(group) for group in groups.values()), default=0),
        "top_clusters": top_clusters,
    }


def _rendered_shape_key(item: Mapping[str, Any]) -> Sequence[Any]:
    return (
        item.get("source"),
        item.get("attention_class"),
        item.get("priority"),
        _canonical_text(item.get("title")),
        _canonical_text(item.get("safe_summary")),
        _canonical_text(item.get("recommended_action")),
    )


def _attention_result_key(item: Mapping[str, Any]) -> Sequence[Any]:
    return (
        item.get("source"),
        item.get("attention_class"),
        item.get("priority"),
        item.get("show_in_digest"),
        _canonical_text(item.get("reason")),
        _canonical_text(item.get("recommended_action")),
    )


def _normalized_activity_key(item: Mapping[str, Any]) -> Sequence[Any]:
    return (
        item.get("activity_source"),
        item.get("activity_type"),
        _canonical_text(item.get("activity_title")),
        _canonical_text(item.get("activity_safe_summary")),
    )


def _source_event_linkage_key(item: Mapping[str, Any]) -> Sequence[Any]:
    return (
        item.get("source_system"),
        item.get("source_object_type"),
        _canonical_text(item.get("source_object_id")),
        item.get("event_type"),
    )


def _possible_origin(*, layer_reports: Mapping[str, Mapping[str, Any]]) -> str:
    duplicate_layers = [
        layer_name
        for layer_name, report in layer_reports.items()
        if _safe_int(report.get("duplicate_cluster_count")) > 0
    ]
    if not duplicate_layers:
        return "unknown"
    if len(duplicate_layers) > 1:
        return "mixed"
    return {
        "rendered_shape": "rendered_shape",
        "attention_result": "attention_result",
        "normalized_activity": "normalized_activity",
        "source_event_linkage": "source_event",
    }.get(duplicate_layers[0], "unknown")


def _duplicate_quality(
    *,
    candidate_visible_count: int,
    rendered_shape_report: Mapping[str, Any],
    layer_reports: Mapping[str, Mapping[str, Any]],
    threshold: int,
) -> dict[str, Any]:
    duplicate_like_item_count = _safe_int(
        rendered_shape_report.get("duplicate_item_count")
    )
    duplicate_like_ratio = (
        round(duplicate_like_item_count / candidate_visible_count, 4)
        if candidate_visible_count > 0
        else 0.0
    )
    largest_cluster_size = _safe_int(rendered_shape_report.get("largest_cluster_size"))
    return {
        "candidate_visible_count": candidate_visible_count,
        "duplicate_like_item_count": duplicate_like_item_count,
        "duplicate_like_ratio": duplicate_like_ratio,
        "duplicate_cluster_count": _safe_int(
            rendered_shape_report.get("duplicate_cluster_count")
        ),
        "largest_cluster_size": largest_cluster_size,
        "high_duplicate_risk": (
            candidate_visible_count > 0
            and (
                duplicate_like_ratio >= 0.25
                or largest_cluster_size >= threshold
            )
        ),
        "possible_origin": _possible_origin(layer_reports=layer_reports),
    }


async def _load_no_marker_visible_quality_items(
    session: Any,
    *,
    start_at: datetime,
    end_at: datetime,
    settings_override: Any | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    from app.core.config import settings
    from app.db.attention_models import AttentionTriageResultRecord
    from app.db.event_models import SourceEvent
    from app.services.attention_triage import apply_attention_confidence_policy
    from app.services.digest import (
        _attention_result_from_record,
        _linked_normalized_activity_rows,
        _persisted_attention_group_key,
        _persisted_attention_synthetic_marker_clause,
    )

    effective_settings = settings_override or settings
    records = list(
        (
            await session.scalars(
                select(AttentionTriageResultRecord)
                .where(AttentionTriageResultRecord.created_at >= start_at)
                .where(AttentionTriageResultRecord.created_at < end_at)
                .where(not_(_persisted_attention_synthetic_marker_clause()))
                .order_by(AttentionTriageResultRecord.id)
            )
        ).all()
    )
    linked_activities = await _linked_normalized_activity_rows(session, records)
    source_event_ids = sorted(
        {
            activity.source_event_id
            for activity in linked_activities.values()
            if isinstance(activity.source_event_id, str) and activity.source_event_id
        }
    )
    source_events_by_id = {}
    if source_event_ids:
        source_rows = list(
            (
                await session.scalars(
                    select(SourceEvent).where(
                        SourceEvent.source_event_id.in_(source_event_ids)
                    )
                )
            ).all()
        )
        source_events_by_id = {row.source_event_id: row for row in source_rows}

    quality_items: list[dict[str, Any]] = []
    missing_activity_count = 0
    missing_source_event_count = 0
    for record in records:
        raw_result = _attention_result_from_record(record)
        result = apply_attention_confidence_policy(
            raw_result,
            min_confidence_to_hide=getattr(
                effective_settings,
                "attention_triage_min_confidence_to_hide",
                settings.attention_triage_min_confidence_to_hide,
            ),
            review_threshold=getattr(
                effective_settings,
                "attention_triage_review_threshold",
                settings.attention_triage_review_threshold,
            ),
        )
        if _persisted_attention_group_key(result) is None:
            continue

        activity = (
            linked_activities.get(record.activity_item_id)
            if record.activity_item_id is not None
            else None
        )
        if record.activity_item_id is not None and activity is None:
            missing_activity_count += 1
        source_event = None
        if activity is not None and isinstance(activity.source_event_id, str):
            source_event = source_events_by_id.get(activity.source_event_id)
            if source_event is None:
                missing_source_event_count += 1

        title = (
            activity.title
            if activity is not None and isinstance(activity.title, str)
            else f"{record.source} activity"
        )
        quality_items.append(
            {
                "source": record.source,
                "attention_class": result.attention_class,
                "priority": result.priority,
                "show_in_digest": result.show_in_digest,
                "title": title,
                "safe_summary": (
                    activity.safe_summary
                    if activity is not None and isinstance(activity.safe_summary, str)
                    else None
                ),
                "reason": result.reason,
                "recommended_action": result.recommended_action,
                "activity_source": activity.source if activity is not None else None,
                "activity_type": activity.activity_type if activity is not None else None,
                "activity_title": activity.title if activity is not None else None,
                "activity_safe_summary": (
                    activity.safe_summary if activity is not None else None
                ),
                "activity_source_object_id": (
                    activity.source_object_id if activity is not None else None
                ),
                "source_system": (
                    source_event.source_system if source_event is not None else None
                ),
                "source_object_type": (
                    source_event.source_object_type
                    if source_event is not None
                    else None
                ),
                "source_object_id": (
                    source_event.source_object_id if source_event is not None else None
                ),
                "event_type": (
                    source_event.event_type if source_event is not None else None
                ),
            }
        )

    limitations = []
    if missing_activity_count:
        limitations.append("some_attention_results_lack_normalized_activity_linkage")
    if missing_source_event_count:
        limitations.append("some_normalized_activity_rows_lack_source_event_linkage")
    if not source_event_ids:
        limitations.append("source_event_linkage_unavailable_for_quality_clusters")
    return quality_items, limitations


def _cluster_layers(
    quality_items: Sequence[Mapping[str, Any]],
    *,
    threshold: int,
) -> dict[str, dict[str, Any]]:
    return {
        "rendered_shape": _cluster_report(
            quality_items,
            key_func=_rendered_shape_key,
            enum_fields=("source", "attention_class", "priority"),
            threshold=threshold,
        ),
        "attention_result": _cluster_report(
            quality_items,
            key_func=_attention_result_key,
            enum_fields=("source", "attention_class", "priority"),
            threshold=threshold,
        ),
        "normalized_activity": _cluster_report(
            [
                item
                for item in quality_items
                if item.get("activity_source") is not None
                or item.get("activity_type") is not None
            ],
            key_func=_normalized_activity_key,
            enum_fields=("activity_source", "activity_type"),
            threshold=threshold,
        ),
        "source_event_linkage": _cluster_report(
            [
                item
                for item in quality_items
                if item.get("source_system") is not None
                or item.get("source_object_type") is not None
                or item.get("event_type") is not None
            ],
            key_func=_source_event_linkage_key,
            enum_fields=("source_system", "source_object_type", "event_type"),
            threshold=threshold,
        ),
    }


def _safe_candidate(report: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _mapping(report.get("no_marker_candidate"))
    return {
        "total": _safe_int(candidate.get("total")),
        "visible": _safe_int(candidate.get("visible")),
        "hidden": _safe_int(candidate.get("hidden")),
        "shown": _safe_int(candidate.get("shown")),
        "truncated": candidate.get("truncated") is True,
        "by_source": _safe_count_mapping(candidate.get("by_source")),
        "by_attention_class": _safe_count_mapping(candidate.get("by_attention_class")),
        "by_priority": _safe_count_mapping(candidate.get("by_priority")),
        "text_sha256": candidate.get("text_sha256"),
        "char_count": candidate.get("char_count"),
        "chunk_count": candidate.get("chunk_count"),
    }


def _safe_lifecycle(report: Mapping[str, Any]) -> dict[str, Any]:
    lifecycle = _mapping(report.get("candidate_lifecycle_reconciliation"))
    return {
        "candidate_text_sha256": lifecycle.get("candidate_text_sha256"),
        "candidate_has_matching_draft_hash": (
            lifecycle.get("candidate_has_matching_draft_hash") is True
        ),
        "matching_hash_has_successful_delivery_result": (
            lifecycle.get("matching_hash_has_successful_delivery_result") is True
        ),
        "any_window_successful_delivery_result": (
            lifecycle.get("any_window_successful_delivery_result") is True
        ),
        "prior_successful_delivery_for_different_digest_hash": (
            lifecycle.get("prior_successful_delivery_for_different_digest_hash") is True
        ),
        "candidate_lifecycle_status": lifecycle.get("candidate_lifecycle_status"),
    }


def _warnings(
    *,
    candidate_report: Mapping[str, Any],
    duplicate_quality: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    limitations: Sequence[str],
) -> list[str]:
    warnings = [
        str(warning)
        for warning in _sequence(candidate_report.get("warnings"))
        if isinstance(warning, str)
    ]
    if _safe_int(duplicate_quality.get("candidate_visible_count")) < 1:
        warnings.append("no_no_marker_visible_candidates")
    if duplicate_quality.get("high_duplicate_risk") is True:
        warnings.append("duplicate_noise_risk_detected")
    if lifecycle.get("matching_hash_has_successful_delivery_result") is True:
        warnings.append("candidate_already_successfully_sent")
    if limitations:
        warnings.append("quality_linkage_limitations_present")
    warnings.append("duplicate_looking_not_semantic_duplicate")
    return sorted(set(warnings))


def _recommended_next_action(
    *,
    candidate: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    duplicate_quality: Mapping[str, Any],
    limitations: Sequence[str],
) -> str:
    if _safe_int(candidate.get("visible")) < 1:
        return "choose_window_with_no_marker_visible_candidates"
    if lifecycle.get("matching_hash_has_successful_delivery_result") is True:
        return "do_not_resend_same_digest_content"
    if limitations:
        return "inspect_linkage_limitations_before_another_send"
    if duplicate_quality.get("high_duplicate_risk") is True:
        return "review_duplicate_noise_before_another_send"
    return "continue_no_marker_manual_pilot_review"


def _limitations(
    *,
    cluster_threshold: int,
    activity_window_supplied: bool,
    quality_limitations: Sequence[str],
) -> list[str]:
    notes = [
        "duplicate_quality_report_is_count_only_not_company_facts",
        "marker_filter_selects_rows_without_detected_synthetic_local_dev_marker",
        "no_marker_is_not_proof_of_production_truth",
        "duplicate_looking_does_not_prove_semantic_duplicate",
        "raw_duplicate_field_values_are_not_returned",
        "cluster_ids_are_opaque_report_labels_not_database_identifiers",
        f"clusters_require_at_least_{cluster_threshold}_items",
        "candidate_digest_hash_computed_without_returning_digest_body",
        "hidden_low_priority_items_remain_count_only",
        "delivery_execution_remains_separately_gated",
    ]
    if not activity_window_supplied:
        notes.append("activity_window_not_supplied_linkage_counts_limited")
    notes.extend(str(note) for note in quality_limitations if isinstance(note, str))
    return list(dict.fromkeys(notes))


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


async def build_no_marker_persisted_attention_digest_quality_report(
    query: NoMarkerDigestQualityQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    settings_override: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.db.base import AsyncSessionLocal

    try:
        prepare_script._assert_local_environment(
            settings=settings_override or settings,
            environ=environ if environ is not None else os.environ,
        )
    except prepare_script.PrepareBlockedError as exc:
        raise NoMarkerDigestQualityBlockedError(str(exc)) from exc

    candidate_query = no_marker_script.NoMarkerCandidateQuery(
        start_at=query.start_at,
        end_at=query.end_at,
        activity_start_at=query.activity_start_at,
        activity_end_at=query.activity_end_at,
        limit=query.limit,
        debug_evidence=query.debug_evidence,
        output_format="json",
    )
    try:
        candidate_report = (
            await no_marker_script.build_no_marker_persisted_attention_candidate_report(
                candidate_query,
                session_factory=session_factory,
                settings_override=settings_override,
                environ=environ,
            )
        )
    except no_marker_script.NoMarkerCandidateInputError as exc:
        raise NoMarkerDigestQualityInputError(str(exc)) from exc
    except no_marker_script.NoMarkerCandidateBlockedError as exc:
        raise NoMarkerDigestQualityBlockedError(str(exc)) from exc
    except no_marker_script.NoMarkerCandidateRuntimeError as exc:
        raise NoMarkerDigestQualityRuntimeError(str(exc)) from exc

    session_factory = session_factory or AsyncSessionLocal
    try:
        async with session_factory() as session:
            quality_items, quality_limitations = (
                await _load_no_marker_visible_quality_items(
                    session,
                    start_at=query.start_at,
                    end_at=query.end_at,
                    settings_override=settings_override,
                )
            )
    except (NoMarkerDigestQualityInputError, NoMarkerDigestQualityBlockedError):
        raise
    except ValueError as exc:
        raise NoMarkerDigestQualityInputError(str(exc)) from exc
    except Exception as exc:
        raise NoMarkerDigestQualityRuntimeError(
            "no-marker persisted attention digest quality report blocked; database, schema, or configuration is unavailable"
        ) from exc

    candidate = _safe_candidate(candidate_report)
    lifecycle = _safe_lifecycle(candidate_report)
    layer_reports = _cluster_layers(
        quality_items,
        threshold=query.cluster_threshold,
    )
    duplicate_quality = _duplicate_quality(
        candidate_visible_count=len(quality_items),
        rendered_shape_report=layer_reports["rendered_shape"],
        layer_reports=layer_reports,
        threshold=query.cluster_threshold,
    )
    limitations = _limitations(
        cluster_threshold=query.cluster_threshold,
        activity_window_supplied=query.activity_start_at is not None
        and query.activity_end_at is not None,
        quality_limitations=quality_limitations,
    )
    warnings = _warnings(
        candidate_report=candidate_report,
        duplicate_quality=duplicate_quality,
        lifecycle=lifecycle,
        limitations=quality_limitations,
    )
    return {
        "status": "no_marker_persisted_attention_digest_quality",
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
        "cluster_threshold": query.cluster_threshold,
        "marker_filter": PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
        "no_marker_not_production_truth": True,
        "candidate": candidate,
        "excluded_markers": _mapping(candidate_report.get("excluded_markers")),
        "duplicate_quality": duplicate_quality,
        "clusters": layer_reports,
        "lifecycle": lifecycle,
        "recommended_next_action": _recommended_next_action(
            candidate=candidate,
            lifecycle=lifecycle,
            duplicate_quality=duplicate_quality,
            limitations=quality_limitations,
        ),
        "warnings": warnings,
        "limitations": limitations,
        "safety": _safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    candidate = _mapping(report.get("candidate"))
    duplicate_quality = _mapping(report.get("duplicate_quality"))
    lifecycle = _mapping(report.get("lifecycle"))
    safety = _mapping(report.get("safety"))
    clusters = _mapping(report.get("clusters"))
    rendered = _mapping(clusters.get("rendered_shape"))
    attention = _mapping(clusters.get("attention_result"))
    normalized = _mapping(clusters.get("normalized_activity"))
    source_event = _mapping(clusters.get("source_event_linkage"))
    lines = [
        "No-marker persisted attention digest quality (read-only)",
        f"Window start: {report.get('start_at')}",
        f"Window end: {report.get('end_at')}",
        f"Activity window start: {report.get('activity_start_at')}",
        f"Activity window end: {report.get('activity_end_at')}",
        f"Limit: {report.get('limit')}",
        f"Debug evidence: {report.get('debug_evidence')}",
        f"Cluster threshold: {report.get('cluster_threshold')}",
        f"Marker filter: {report.get('marker_filter')}",
        "No-marker is production truth: False",
        f"Candidate visible: {candidate.get('visible')}",
        f"Candidate hidden: {candidate.get('hidden')}",
        f"Candidate shown: {candidate.get('shown')}",
        f"Candidate truncated: {candidate.get('truncated')}",
        f"Candidate text SHA-256: {candidate.get('text_sha256')}",
        f"Candidate char count: {candidate.get('char_count')}",
        f"Candidate chunk count: {candidate.get('chunk_count')}",
        (
            "Duplicate-like item count: "
            f"{duplicate_quality.get('duplicate_like_item_count')}"
        ),
        f"Duplicate-like ratio: {duplicate_quality.get('duplicate_like_ratio')}",
        f"Duplicate cluster count: {duplicate_quality.get('duplicate_cluster_count')}",
        f"Largest cluster size: {duplicate_quality.get('largest_cluster_size')}",
        f"High duplicate risk: {duplicate_quality.get('high_duplicate_risk')}",
        f"Possible origin: {duplicate_quality.get('possible_origin')}",
        (
            "Rendered-shape duplicate clusters: "
            f"{rendered.get('duplicate_cluster_count')}"
        ),
        (
            "Attention-result duplicate clusters: "
            f"{attention.get('duplicate_cluster_count')}"
        ),
        (
            "Normalized-activity duplicate clusters: "
            f"{normalized.get('duplicate_cluster_count')}"
        ),
        (
            "Source-event linkage duplicate clusters: "
            f"{source_event.get('duplicate_cluster_count')}"
        ),
        (
            "Matching hash has successful delivery: "
            f"{lifecycle.get('matching_hash_has_successful_delivery_result')}"
        ),
        f"Candidate lifecycle status: {lifecycle.get('candidate_lifecycle_status')}",
        f"Recommended next action: {report.get('recommended_next_action')}",
        f"Warnings: {report.get('warnings')}",
        "Duplicate-looking is semantic duplicate: False",
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
            build_no_marker_persisted_attention_digest_quality_report(query)
        )
    except NoMarkerDigestQualityInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except NoMarkerDigestQualityBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except NoMarkerDigestQualityRuntimeError as exc:
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
