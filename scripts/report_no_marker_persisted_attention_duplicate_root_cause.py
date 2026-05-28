#!/usr/bin/env python
"""Explain no-marker duplicate-looking digest clusters with safe linkage counts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
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
from scripts import report_no_marker_persisted_attention_digest_quality as quality_script  # noqa: E402


DEFAULT_CLUSTER_THRESHOLD = quality_script.DEFAULT_CLUSTER_THRESHOLD
MAX_CLUSTER_THRESHOLD = quality_script.MAX_CLUSTER_THRESHOLD


class NoMarkerDuplicateRootCauseInputError(ValueError):
    pass


class NoMarkerDuplicateRootCauseBlockedError(RuntimeError):
    pass


class NoMarkerDuplicateRootCauseRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NoMarkerDuplicateRootCauseQuery:
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
        raise NoMarkerDuplicateRootCauseInputError(str(exc)) from exc


def _clean_limit(value: int) -> int:
    if not isinstance(value, int):
        raise NoMarkerDuplicateRootCauseInputError("limit must be an integer")
    if value < 1 or value > MAX_DIGEST_ENTRY_LIMIT:
        raise NoMarkerDuplicateRootCauseInputError(
            f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}"
        )
    return value


def _clean_cluster_threshold(value: int) -> int:
    if not isinstance(value, int):
        raise NoMarkerDuplicateRootCauseInputError(
            "cluster_threshold must be an integer"
        )
    if value < 2 or value > MAX_CLUSTER_THRESHOLD:
        raise NoMarkerDuplicateRootCauseInputError(
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


def _query_from_args(args: argparse.Namespace) -> NoMarkerDuplicateRootCauseQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise NoMarkerDuplicateRootCauseInputError("end_at must be after start_at")

    activity_start_at = None
    activity_end_at = None
    if args.activity_start_at is not None or args.activity_end_at is not None:
        if args.activity_start_at is None or args.activity_end_at is None:
            raise NoMarkerDuplicateRootCauseInputError(
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
            raise NoMarkerDuplicateRootCauseInputError(
                "activity_end_at must be after activity_start_at"
            )

    return NoMarkerDuplicateRootCauseQuery(
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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return value
    return []


def _safe_count_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): _safe_int(count)
        for key, count in sorted(value.items())
        if isinstance(key, str)
    }


def _safe_candidate(report: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _mapping(report.get("candidate"))
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
    lifecycle = _mapping(report.get("lifecycle"))
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


def _quality_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    duplicate_quality = _mapping(report.get("duplicate_quality"))
    return {
        "duplicate_like_item_count": _safe_int(
            duplicate_quality.get("duplicate_like_item_count")
        ),
        "duplicate_like_ratio": duplicate_quality.get("duplicate_like_ratio", 0.0),
        "duplicate_cluster_count": _safe_int(
            duplicate_quality.get("duplicate_cluster_count")
        ),
        "largest_cluster_size": _safe_int(
            duplicate_quality.get("largest_cluster_size")
        ),
        "high_duplicate_risk": duplicate_quality.get("high_duplicate_risk") is True,
        "possible_origin_from_quality_report": duplicate_quality.get(
            "possible_origin",
            "unknown",
        ),
    }


def _bucket_value(item: Mapping[str, Any], field_name: str) -> str | None:
    value = item.get(field_name)
    if isinstance(value, str) and value:
        return quality_script._internal_fingerprint((field_name, value))
    return None


def _source_object_key(item: Mapping[str, Any]) -> Sequence[Any]:
    source_object = (
        item.get("source_object_id")
        or item.get("activity_source_object_id")
        or item.get("attention_source_object_id")
    )
    return (
        item.get("source") or item.get("activity_source") or item.get("source_system"),
        item.get("source_object_type"),
        quality_script._canonical_text(source_object),
    )


def _source_event_key(item: Mapping[str, Any]) -> Sequence[Any]:
    return (
        item.get("source_system"),
        item.get("source_object_type"),
        item.get("event_type"),
        item.get("source_event_bucket"),
    )


def _normalized_activity_key(item: Mapping[str, Any]) -> Sequence[Any]:
    return (
        item.get("activity_source"),
        item.get("activity_type"),
        item.get("normalized_activity_bucket"),
    )


def _attention_result_exact_key(item: Mapping[str, Any]) -> Sequence[Any]:
    return (
        item.get("source"),
        item.get("attention_result_bucket"),
    )


def _bucket_counts(
    items: Sequence[Mapping[str, Any]],
    *,
    field_name: str,
) -> tuple[int, int, dict[str, int]]:
    counts: dict[str, int] = {}
    for item in items:
        bucket = item.get(field_name)
        if isinstance(bucket, str) and bucket:
            counts[bucket] = counts.get(bucket, 0) + 1
    return len(counts), max(counts.values(), default=0), counts


def _distinct_count(items: Sequence[Mapping[str, Any]], field_name: str) -> int:
    return len(
        {
            item.get(field_name)
            for item in items
            if isinstance(item.get(field_name), str) and item.get(field_name)
        }
    )


def _fanout_max(
    items: Sequence[Mapping[str, Any]],
    *,
    parent_field: str,
    child_field: str,
) -> int:
    grouped: dict[str, set[str]] = {}
    for item in items:
        parent = item.get(parent_field)
        child = item.get(child_field)
        if not isinstance(parent, str) or not parent:
            continue
        if not isinstance(child, str) or not child:
            continue
        grouped.setdefault(parent, set()).add(child)
    return max((len(children) for children in grouped.values()), default=0)


def _rendered_shape_collision(
    items: Sequence[Mapping[str, Any]],
    *,
    distinct_field: str,
    threshold: int,
) -> bool:
    grouped: dict[str, set[str]] = {}
    for item in items:
        shape = quality_script._internal_fingerprint(quality_script._rendered_shape_key(item))
        distinct_value = item.get(distinct_field)
        if not isinstance(distinct_value, str) or not distinct_value:
            continue
        grouped.setdefault(shape, set()).add(distinct_value)
    return any(len(values) >= threshold for values in grouped.values())


def _rendered_shape_source_object_distribution(
    items: Sequence[Mapping[str, Any]],
    *,
    threshold: int,
) -> dict[str, int]:
    grouped: dict[str, set[str]] = {}
    for item in items:
        shape = quality_script._internal_fingerprint(quality_script._rendered_shape_key(item))
        bucket = item.get("source_object_bucket")
        if not isinstance(bucket, str) or not bucket:
            continue
        grouped.setdefault(shape, set()).add(bucket)
    repeated_shapes = [
        len(buckets) for buckets in grouped.values() if len(buckets) >= threshold
    ]
    return {
        "max_distinct_source_object_buckets": max(repeated_shapes, default=0),
        "multi_source_object_rendered_shape_count": sum(
            1 for count in repeated_shapes if count > 1
        ),
        "single_source_object_rendered_shape_count": sum(
            1 for count in repeated_shapes if count == 1
        ),
    }


async def _load_root_cause_items(
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

    items: list[dict[str, Any]] = []
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

        item = {
            "source": record.source,
            "attention_class": result.attention_class,
            "priority": result.priority,
            "show_in_digest": result.show_in_digest,
            "title": (
                activity.title
                if activity is not None and isinstance(activity.title, str)
                else f"{record.source} activity"
            ),
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
                source_event.source_object_type if source_event is not None else None
            ),
            "source_object_id": (
                source_event.source_object_id if source_event is not None else None
            ),
            "event_type": source_event.event_type if source_event is not None else None,
            "attention_source_object_id": record.source_object_id,
            "attention_result_bucket": _bucket_value(
                {"triage_result_id": record.triage_result_id},
                "triage_result_id",
            ),
            "normalized_activity_bucket": _bucket_value(
                {"activity_item_id": activity.activity_item_id}
                if activity is not None
                else {},
                "activity_item_id",
            ),
            "source_event_bucket": _bucket_value(
                {"source_event_id": source_event.source_event_id}
                if source_event is not None
                else {},
                "source_event_id",
            ),
        }
        item["source_object_bucket"] = quality_script._internal_fingerprint(
            _source_object_key(item)
        )
        items.append(item)

    limitations = []
    if missing_activity_count:
        limitations.append("some_attention_results_lack_normalized_activity_linkage")
    if missing_source_event_count:
        limitations.append("some_normalized_activity_rows_lack_source_event_linkage")
    if not source_event_ids:
        limitations.append("source_event_linkage_unavailable_for_root_cause_analysis")
    return items, limitations


def _root_cause_clusters(
    items: Sequence[Mapping[str, Any]],
    *,
    threshold: int,
) -> dict[str, dict[str, Any]]:
    return {
        "source_object": quality_script._cluster_report(
            [
                item
                for item in items
                if isinstance(item.get("source_object_bucket"), str)
            ],
            key_func=lambda item: (item.get("source_object_bucket"),),
            enum_fields=("source", "activity_source", "source_system", "source_object_type"),
            threshold=threshold,
        ),
        "source_event": quality_script._cluster_report(
            [item for item in items if isinstance(item.get("source_event_bucket"), str)],
            key_func=_source_event_key,
            enum_fields=("source_system", "source_object_type", "event_type"),
            threshold=threshold,
        ),
        "normalized_activity": quality_script._cluster_report(
            [
                item
                for item in items
                if isinstance(item.get("normalized_activity_bucket"), str)
            ],
            key_func=_normalized_activity_key,
            enum_fields=("activity_source", "activity_type"),
            threshold=threshold,
        ),
        "attention_result": quality_script._cluster_report(
            [
                item
                for item in items
                if isinstance(item.get("attention_result_bucket"), str)
            ],
            key_func=quality_script._attention_result_key,
            enum_fields=("source", "attention_class", "priority"),
            threshold=threshold,
        ),
        "rendered_shape": quality_script._cluster_report(
            items,
            key_func=quality_script._rendered_shape_key,
            enum_fields=("source", "attention_class", "priority"),
            threshold=threshold,
        ),
    }


def _reason_codes(
    *,
    metrics: Mapping[str, Any],
    quality_summary: Mapping[str, Any],
    limitations: Sequence[str],
) -> list[str]:
    reasons: list[str] = []
    if _safe_int(metrics.get("candidate_visible_count")) < 1:
        reasons.append("no_no_marker_visible_candidates")
    if quality_summary.get("high_duplicate_risk") is True:
        reasons.append("high_duplicate_risk_from_quality_report")
    if metrics.get("single_source_object_bucket_covers_candidate") is True:
        reasons.append("single_source_object_bucket_covers_candidate")
    if metrics.get("source_event_bucket_covers_candidate") is True:
        reasons.append("single_source_event_bucket_covers_candidate")
    if metrics.get("source_event_to_normalized_activity_fanout_detected") is True:
        reasons.append("source_event_to_normalized_activity_fanout_detected")
    if metrics.get("normalized_activity_to_attention_result_fanout_detected") is True:
        reasons.append("normalized_activity_to_attention_result_fanout_detected")
    if metrics.get("rendered_shape_collision_across_distinct_source_objects") is True:
        reasons.append("rendered_shape_collision_across_distinct_source_objects")
    if (
        metrics.get("rendered_shape_collision_across_distinct_normalized_items")
        is True
    ):
        reasons.append("rendered_shape_collision_across_distinct_normalized_items")
    if limitations:
        reasons.append("linkage_limitations_present")
    return reasons


def _classify_root_cause(
    *,
    metrics: Mapping[str, Any],
    quality_summary: Mapping[str, Any],
    limitations: Sequence[str],
) -> tuple[str, str]:
    visible_count = _safe_int(metrics.get("candidate_visible_count"))
    if visible_count < 1:
        return "unknown", "unknown"
    if _safe_int(metrics.get("linkage_missing_count")) >= visible_count:
        return "insufficient_linkage", "low"

    signals: list[tuple[str, str]] = []
    attention_fanout = (
        metrics.get("normalized_activity_to_attention_result_fanout_detected") is True
    )
    normalization_fanout = (
        metrics.get("source_event_to_normalized_activity_fanout_detected") is True
    )
    if attention_fanout:
        signals.append(("attention_result_fanout", "high"))
    if normalization_fanout:
        signals.append(("normalization_fanout", "high"))
    if (
        not attention_fanout
        and not normalization_fanout
        and metrics.get("source_event_bucket_covers_candidate") is True
    ):
        signals.append(("source_event_repeated", "high"))
    elif (
        not attention_fanout
        and not normalization_fanout
        and metrics.get("single_source_object_bucket_covers_candidate") is True
    ):
        signals.append(("source_object_repeated", "high"))
    if metrics.get("rendered_shape_collision_across_distinct_source_objects") is True:
        signals.append(("rendered_shape_collision", "medium"))

    distinct_origins = {origin for origin, _confidence in signals}
    if len(distinct_origins) > 1:
        return "mixed", "medium"
    if signals:
        return signals[0]
    if quality_summary.get("high_duplicate_risk") is True:
        return "unknown", "low"
    if limitations:
        return "insufficient_linkage", "low"
    return "unknown", "unknown"


def _root_cause_summary(
    *,
    items: Sequence[Mapping[str, Any]],
    clusters: Mapping[str, Mapping[str, Any]],
    quality_summary: Mapping[str, Any],
    limitations: Sequence[str],
    threshold: int,
) -> dict[str, Any]:
    candidate_visible_count = len(items)
    (
        source_object_bucket_count,
        largest_source_object_bucket_size,
        _source_object_counts,
    ) = _bucket_counts(items, field_name="source_object_bucket")
    (
        source_event_bucket_count,
        largest_source_event_bucket_size,
        _source_event_counts,
    ) = _bucket_counts(items, field_name="source_event_bucket")
    (
        normalized_activity_bucket_count,
        largest_normalized_activity_bucket_size,
        _normalized_counts,
    ) = _bucket_counts(items, field_name="normalized_activity_bucket")
    (
        attention_result_bucket_count,
        largest_attention_result_bucket_size,
        _attention_counts,
    ) = _bucket_counts(items, field_name="attention_result_bucket")
    rendered_shape_bucket_count = _safe_int(
        _mapping(clusters.get("rendered_shape")).get("cluster_count")
    )
    largest_rendered_shape_bucket_size = _safe_int(
        _mapping(clusters.get("rendered_shape")).get("largest_cluster_size")
    )
    source_event_to_normalized_max = _fanout_max(
        items,
        parent_field="source_event_bucket",
        child_field="normalized_activity_bucket",
    )
    normalized_to_attention_max = _fanout_max(
        items,
        parent_field="normalized_activity_bucket",
        child_field="attention_result_bucket",
    )
    linkage_missing_count = sum(
        1
        for item in items
        if not isinstance(item.get("source_object_bucket"), str)
        or not isinstance(item.get("source_event_bucket"), str)
        or not isinstance(item.get("normalized_activity_bucket"), str)
    )
    rendered_distribution = _rendered_shape_source_object_distribution(
        items,
        threshold=threshold,
    )
    metrics = {
        "candidate_visible_count": candidate_visible_count,
        "source_object_bucket_count": source_object_bucket_count,
        "largest_source_object_bucket_size": largest_source_object_bucket_size,
        "single_source_object_bucket_covers_candidate": (
            candidate_visible_count > 0
            and source_object_bucket_count == 1
            and largest_source_object_bucket_size == candidate_visible_count
        ),
        "distinct_source_object_buckets_per_rendered_shape": rendered_distribution,
        "source_event_bucket_count": source_event_bucket_count,
        "largest_source_event_bucket_size": largest_source_event_bucket_size,
        "source_event_bucket_covers_candidate": (
            candidate_visible_count > 0
            and source_event_bucket_count == 1
            and largest_source_event_bucket_size == candidate_visible_count
        ),
        "source_event_to_normalized_activity_fanout_detected": (
            source_event_to_normalized_max > 1
        ),
        "source_event_to_normalized_activity_max_fanout": (
            source_event_to_normalized_max
        ),
        "normalized_activity_to_source_event_many_to_one_detected": (
            source_event_to_normalized_max > 1
        ),
        "normalized_activity_bucket_count": normalized_activity_bucket_count,
        "largest_normalized_activity_bucket_size": (
            largest_normalized_activity_bucket_size
        ),
        "normalized_activity_to_attention_result_fanout_detected": (
            normalized_to_attention_max > 1
        ),
        "normalized_activity_to_attention_result_max_fanout": (
            normalized_to_attention_max
        ),
        "attention_result_to_normalized_activity_many_to_one_detected": (
            normalized_to_attention_max > 1
        ),
        "attention_result_bucket_count": attention_result_bucket_count,
        "largest_attention_result_bucket_size": largest_attention_result_bucket_size,
        "attention_result_field_shape_cluster_count": _safe_int(
            _mapping(clusters.get("attention_result")).get("duplicate_cluster_count")
        ),
        "rendered_shape_bucket_count": rendered_shape_bucket_count,
        "largest_rendered_shape_bucket_size": largest_rendered_shape_bucket_size,
        "rendered_shape_collision_across_distinct_source_objects": (
            _rendered_shape_collision(
                items,
                distinct_field="source_object_bucket",
                threshold=threshold,
            )
        ),
        "rendered_shape_collision_across_distinct_normalized_items": (
            _rendered_shape_collision(
                items,
                distinct_field="normalized_activity_bucket",
                threshold=threshold,
            )
        ),
        "linkage_missing_count": linkage_missing_count,
    }
    likely_origin, confidence = _classify_root_cause(
        metrics=metrics,
        quality_summary=quality_summary,
        limitations=limitations,
    )
    return {
        "likely_origin": likely_origin,
        "confidence": confidence,
        "reason_codes": _reason_codes(
            metrics=metrics,
            quality_summary=quality_summary,
            limitations=limitations,
        ),
        **metrics,
    }


def _warnings(
    *,
    quality_report: Mapping[str, Any],
    root_cause: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    limitations: Sequence[str],
) -> list[str]:
    warnings = [
        str(warning)
        for warning in _sequence(quality_report.get("warnings"))
        if isinstance(warning, str)
    ]
    if root_cause.get("likely_origin") in {"mixed", "unknown"}:
        warnings.append("duplicate_root_cause_requires_review")
    if root_cause.get("likely_origin") == "insufficient_linkage":
        warnings.append("duplicate_root_cause_has_insufficient_linkage")
    if lifecycle.get("matching_hash_has_successful_delivery_result") is True:
        warnings.append("candidate_already_successfully_sent")
    if limitations:
        warnings.append("root_cause_linkage_limitations_present")
    warnings.append("duplicate_looking_not_semantic_duplicate")
    return sorted(set(warnings))


def _recommended_next_action(
    *,
    candidate: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    root_cause: Mapping[str, Any],
) -> str:
    if _safe_int(candidate.get("visible")) < 1:
        return "choose_window_with_no_marker_visible_candidates"
    if lifecycle.get("matching_hash_has_successful_delivery_result") is True:
        return "do_not_resend_same_digest_content"

    likely_origin = root_cause.get("likely_origin")
    if likely_origin in {"source_object_repeated", "source_event_repeated"}:
        return "inspect_source_event_ingestion_duplicates"
    if likely_origin == "normalization_fanout":
        return "inspect_normalization_fanout_before_dedupe"
    if likely_origin == "attention_result_fanout":
        return "inspect_attention_result_fanout_before_dedupe"
    if likely_origin == "rendered_shape_collision":
        return "consider_renderer_grouping_after_review"
    if likely_origin == "insufficient_linkage":
        return "inspect_linkage_limitations_before_another_send"
    if likely_origin == "mixed":
        return "review_duplicate_root_cause_before_dedupe"
    return "continue_no_marker_manual_pilot_review"


def _limitations(
    *,
    activity_window_supplied: bool,
    quality_limitations: Sequence[str],
    root_limitations: Sequence[str],
) -> list[str]:
    notes = [
        "duplicate_root_cause_report_is_count_only_not_company_facts",
        "marker_filter_selects_rows_without_detected_synthetic_local_dev_marker",
        "no_marker_is_not_proof_of_production_truth",
        "duplicate_looking_does_not_prove_semantic_duplicate",
        "root_cause_diagnosis_is_conservative_and_may_be_heuristic",
        "raw_linkage_values_and_fingerprints_are_not_returned",
        "cluster_ids_are_opaque_report_labels_not_database_identifiers",
        "candidate_digest_hash_computed_without_returning_digest_body",
        "hidden_low_priority_items_remain_count_only",
        "delivery_execution_remains_separately_gated",
    ]
    if not activity_window_supplied:
        notes.append("activity_window_not_supplied_linkage_counts_limited")
    notes.extend(str(note) for note in quality_limitations if isinstance(note, str))
    notes.extend(str(note) for note in root_limitations if isinstance(note, str))
    return list(dict.fromkeys(notes))


def _safety_metadata() -> dict[str, Any]:
    safety = dict(quality_script._safety_metadata())
    safety["source_object_ids_exposed"] = False
    safety["raw_fingerprints_exposed"] = False
    return safety


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _safety_metadata(),
    }


async def build_no_marker_persisted_attention_duplicate_root_cause_report(
    query: NoMarkerDuplicateRootCauseQuery,
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
        raise NoMarkerDuplicateRootCauseBlockedError(str(exc)) from exc

    quality_query = quality_script.NoMarkerDigestQualityQuery(
        start_at=query.start_at,
        end_at=query.end_at,
        activity_start_at=query.activity_start_at,
        activity_end_at=query.activity_end_at,
        limit=query.limit,
        debug_evidence=query.debug_evidence,
        cluster_threshold=query.cluster_threshold,
        output_format="json",
    )
    try:
        quality_report = (
            await quality_script.build_no_marker_persisted_attention_digest_quality_report(
                quality_query,
                session_factory=session_factory,
                settings_override=settings_override,
                environ=environ,
            )
        )
    except quality_script.NoMarkerDigestQualityInputError as exc:
        raise NoMarkerDuplicateRootCauseInputError(str(exc)) from exc
    except quality_script.NoMarkerDigestQualityBlockedError as exc:
        raise NoMarkerDuplicateRootCauseBlockedError(str(exc)) from exc
    except quality_script.NoMarkerDigestQualityRuntimeError as exc:
        raise NoMarkerDuplicateRootCauseRuntimeError(str(exc)) from exc

    session_factory = session_factory or AsyncSessionLocal
    try:
        async with session_factory() as session:
            root_items, root_limitations = await _load_root_cause_items(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                settings_override=settings_override,
            )
    except (NoMarkerDuplicateRootCauseInputError, NoMarkerDuplicateRootCauseBlockedError):
        raise
    except ValueError as exc:
        raise NoMarkerDuplicateRootCauseInputError(str(exc)) from exc
    except Exception as exc:
        raise NoMarkerDuplicateRootCauseRuntimeError(
            "no-marker duplicate root-cause report blocked; database, schema, or configuration is unavailable"
        ) from exc

    candidate = _safe_candidate(quality_report)
    quality_summary = _quality_summary(quality_report)
    lifecycle = _safe_lifecycle(quality_report)
    clusters = _root_cause_clusters(
        root_items,
        threshold=query.cluster_threshold,
    )
    quality_limitations = [
        str(note)
        for note in _sequence(quality_report.get("limitations"))
        if isinstance(note, str)
    ]
    root_cause = _root_cause_summary(
        items=root_items,
        clusters=clusters,
        quality_summary=quality_summary,
        limitations=root_limitations,
        threshold=query.cluster_threshold,
    )
    limitations = _limitations(
        activity_window_supplied=query.activity_start_at is not None
        and query.activity_end_at is not None,
        quality_limitations=quality_limitations,
        root_limitations=root_limitations,
    )
    warnings = _warnings(
        quality_report=quality_report,
        root_cause=root_cause,
        lifecycle=lifecycle,
        limitations=root_limitations,
    )
    return {
        "status": "no_marker_persisted_attention_duplicate_root_cause",
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
        "quality_summary": quality_summary,
        "root_cause": root_cause,
        "clusters": clusters,
        "lifecycle": lifecycle,
        "recommended_next_action": _recommended_next_action(
            candidate=candidate,
            lifecycle=lifecycle,
            root_cause=root_cause,
        ),
        "warnings": warnings,
        "limitations": limitations,
        "safety": _safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    candidate = _mapping(report.get("candidate"))
    quality_summary = _mapping(report.get("quality_summary"))
    root_cause = _mapping(report.get("root_cause"))
    lifecycle = _mapping(report.get("lifecycle"))
    safety = _mapping(report.get("safety"))
    lines = [
        "No-marker duplicate root-cause linkage report (read-only)",
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
        f"Candidate text SHA-256: {candidate.get('text_sha256')}",
        (
            "Duplicate-like item count: "
            f"{quality_summary.get('duplicate_like_item_count')}"
        ),
        f"Duplicate-like ratio: {quality_summary.get('duplicate_like_ratio')}",
        f"High duplicate risk: {quality_summary.get('high_duplicate_risk')}",
        f"Likely origin: {root_cause.get('likely_origin')}",
        f"Confidence: {root_cause.get('confidence')}",
        (
            "Source object buckets: "
            f"{root_cause.get('source_object_bucket_count')}"
        ),
        (
            "Largest source object bucket: "
            f"{root_cause.get('largest_source_object_bucket_size')}"
        ),
        (
            "Source event to normalized fanout: "
            f"{root_cause.get('source_event_to_normalized_activity_fanout_detected')}"
        ),
        (
            "Normalized to attention fanout: "
            f"{root_cause.get('normalized_activity_to_attention_result_fanout_detected')}"
        ),
        (
            "Rendered collision across source objects: "
            f"{root_cause.get('rendered_shape_collision_across_distinct_source_objects')}"
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
            build_no_marker_persisted_attention_duplicate_root_cause_report(query)
        )
    except NoMarkerDuplicateRootCauseInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except NoMarkerDuplicateRootCauseBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except NoMarkerDuplicateRootCauseRuntimeError as exc:
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
