#!/usr/bin/env python
"""Preview source-object grouping of no-marker persisted attention candidates.

This is a read-only, provider-free presentation-planning report. It shows how a
no-marker persisted attention digest *could* be grouped by source object while
preserving visible item counts. It never changes the real persisted digest read
model, renderer, delivery draft body, ``text_sha256`` lifecycle, or delivery
behavior, and it never creates drafts, approvals, intentions, results, or sends.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.digest import (  # noqa: E402
    DEFAULT_DIGEST_ENTRY_LIMIT,
    EMAIL_THREAD_GROUP_MANUAL_ACTIONS,
    EMAIL_THREAD_GROUP_REVIEW_OPTIONAL,
    EMAIL_THREAD_GROUP_WAITING_EXTERNAL_REPLY,
    EMAIL_THREAD_GROUP_WORK_ACTIONS,
    EMAIL_THREAD_GROUP_WORK_INFO,
    EMAIL_THREAD_GROUPS,
    MAX_DIGEST_ENTRY_LIMIT,
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
    PERSISTED_ATTENTION_SECTION_LABELS,
)
from app.services.telegram_delivery import (  # noqa: E402
    DEFAULT_TELEGRAM_CHUNK_SIZE,
    split_telegram_plain_text,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import (  # noqa: E402
    report_no_marker_persisted_attention_digest_quality as quality_script,
)
from scripts import (  # noqa: E402
    report_no_marker_persisted_attention_duplicate_root_cause as root_cause_script,
)


DEFAULT_CLUSTER_THRESHOLD = quality_script.DEFAULT_CLUSTER_THRESHOLD
MAX_CLUSTER_THRESHOLD = quality_script.MAX_CLUSTER_THRESHOLD
SUPPORTED_GROUP_BY = ("source_object",)
DEFAULT_GROUP_BY = "source_object"
_GROUPED_PREVIEW_NAMESPACE = "fos090-no-marker-grouped-preview-v1"

# Visible attention classes map deterministically to a digest section. This
# mirrors app.services.digest._persisted_attention_group_key for the items the
# root-cause loader already filtered to visible (group key not None).
_ATTENTION_CLASS_TO_SECTION = {
    "requires_my_attention": EMAIL_THREAD_GROUP_WORK_ACTIONS,
    "manual_action": EMAIL_THREAD_GROUP_MANUAL_ACTIONS,
    "waiting_on_external": EMAIL_THREAD_GROUP_WAITING_EXTERNAL_REPLY,
    "important_info": EMAIL_THREAD_GROUP_WORK_INFO,
    "review_optional": EMAIL_THREAD_GROUP_REVIEW_OPTIONAL,
}


class NoMarkerGroupedPreviewInputError(ValueError):
    pass


class NoMarkerGroupedPreviewBlockedError(RuntimeError):
    pass


class NoMarkerGroupedPreviewRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NoMarkerGroupedPreviewQuery:
    start_at: datetime
    end_at: datetime
    activity_start_at: datetime | None = None
    activity_end_at: datetime | None = None
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT
    debug_evidence: bool = False
    cluster_threshold: int = DEFAULT_CLUSTER_THRESHOLD
    group_by: str = DEFAULT_GROUP_BY
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        return prepare_script._parse_datetime(value, field_name=field_name)
    except prepare_script.PrepareInputError as exc:
        raise NoMarkerGroupedPreviewInputError(str(exc)) from exc


def _clean_limit(value: int) -> int:
    if not isinstance(value, int):
        raise NoMarkerGroupedPreviewInputError("limit must be an integer")
    if value < 1 or value > MAX_DIGEST_ENTRY_LIMIT:
        raise NoMarkerGroupedPreviewInputError(
            f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}"
        )
    return value


def _clean_cluster_threshold(value: int) -> int:
    if not isinstance(value, int):
        raise NoMarkerGroupedPreviewInputError("cluster_threshold must be an integer")
    if value < 2 or value > MAX_CLUSTER_THRESHOLD:
        raise NoMarkerGroupedPreviewInputError(
            f"cluster_threshold must be between 2 and {MAX_CLUSTER_THRESHOLD}"
        )
    return value


def _clean_group_by(value: str) -> str:
    if not isinstance(value, str) or value not in SUPPORTED_GROUP_BY:
        raise NoMarkerGroupedPreviewInputError(
            "group_by must be one of: " + ", ".join(SUPPORTED_GROUP_BY)
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
            "Minimum repeated item count for a duplicate-looking group, "
            f"2-{MAX_CLUSTER_THRESHOLD}."
        ),
    )
    parser.add_argument(
        "--group-by",
        default=DEFAULT_GROUP_BY,
        help="Grouping dimension. Only 'source_object' is supported in this slice.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> NoMarkerGroupedPreviewQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise NoMarkerGroupedPreviewInputError("end_at must be after start_at")

    activity_start_at = None
    activity_end_at = None
    if args.activity_start_at is not None or args.activity_end_at is not None:
        if args.activity_start_at is None or args.activity_end_at is None:
            raise NoMarkerGroupedPreviewInputError(
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
            raise NoMarkerGroupedPreviewInputError(
                "activity_end_at must be after activity_start_at"
            )

    return NoMarkerGroupedPreviewQuery(
        start_at=start_at,
        end_at=end_at,
        activity_start_at=activity_start_at,
        activity_end_at=activity_end_at,
        limit=_clean_limit(args.limit),
        debug_evidence=bool(args.debug_evidence),
        cluster_threshold=_clean_cluster_threshold(args.cluster_threshold),
        group_by=_clean_group_by(args.group_by),
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


def _candidate_summary(quality_report: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _mapping(quality_report.get("candidate"))
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


def _duplicate_quality_summary(quality_report: Mapping[str, Any]) -> dict[str, Any]:
    duplicate_quality = _mapping(quality_report.get("duplicate_quality"))
    return {
        "high_duplicate_risk": duplicate_quality.get("high_duplicate_risk") is True,
        "duplicate_like_item_count": _safe_int(
            duplicate_quality.get("duplicate_like_item_count")
        ),
        "duplicate_like_ratio": duplicate_quality.get("duplicate_like_ratio", 0.0),
        "largest_cluster_size": _safe_int(
            duplicate_quality.get("largest_cluster_size")
        ),
        "possible_origin": duplicate_quality.get("possible_origin", "unknown"),
    }


def _lifecycle_summary(quality_report: Mapping[str, Any]) -> dict[str, Any]:
    lifecycle = _mapping(quality_report.get("lifecycle"))
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


def _item_section(item: Mapping[str, Any]) -> str | None:
    attention_class = item.get("attention_class")
    if not isinstance(attention_class, str):
        return None
    return _ATTENTION_CLASS_TO_SECTION.get(attention_class)


def _rendered_shape_fingerprint(item: Mapping[str, Any]) -> str:
    return quality_script._internal_fingerprint(
        quality_script._rendered_shape_key(item)
    )


def _group_label_fingerprint(section: str, source_object_bucket: str) -> str:
    return quality_script._internal_fingerprint(
        (_GROUPED_PREVIEW_NAMESPACE, section, source_object_bucket)
    )


def _build_groups(
    items: Sequence[Mapping[str, Any]],
    *,
    threshold: int,
) -> tuple[list[dict[str, Any]], int]:
    """Group visible items by (section, source_object) preserving every item.

    Returns the deterministic group list and the count of items that could not
    be assigned a section (a linkage limitation, kept visible in counts).
    """

    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    unsectioned = 0
    for item in items:
        section = _item_section(item)
        source_object_bucket = item.get("source_object_bucket")
        if section is None or not isinstance(source_object_bucket, str):
            unsectioned += 1
            continue
        grouped.setdefault((section, source_object_bucket), []).append(item)

    ordered_keys = sorted(
        grouped,
        key=lambda key: (
            -len(grouped[key]),
            key[0],
            _group_label_fingerprint(key[0], key[1]),
        ),
    )

    group_entries: list[dict[str, Any]] = []
    for index, key in enumerate(ordered_keys, start=1):
        section, _bucket = key
        members = grouped[key]
        item_count = len(members)
        distinct_rendered_shapes = {
            _rendered_shape_fingerprint(member) for member in members
        }
        group_entries.append(
            {
                "group_id": f"group_{index:03d}",
                "item_count": item_count,
                "section": section,
                "safe_enum_summary": quality_script._safe_enum_summary(
                    members,
                    fields=("source", "attention_class", "priority", "activity_type"),
                ),
                "duplicate_risk": {
                    "source_object_repeated": item_count >= threshold,
                    "rendered_shape_repeated": (
                        item_count >= threshold and len(distinct_rendered_shapes) == 1
                    ),
                    "item_count": item_count,
                },
            }
        )
    return group_entries, unsectioned


def _section_counts(
    items: Sequence[Mapping[str, Any]],
    group_entries: Sequence[Mapping[str, Any]],
    *,
    threshold: int,
) -> dict[str, dict[str, int]]:
    ungrouped_visible: Counter[str] = Counter()
    for item in items:
        section = _item_section(item)
        if section is not None:
            ungrouped_visible[section] += 1

    grouped_entry: Counter[str] = Counter()
    grouped_item: Counter[str] = Counter()
    repeats: Counter[str] = Counter()
    for group in group_entries:
        section = str(group.get("section"))
        item_count = _safe_int(group.get("item_count"))
        grouped_entry[section] += 1
        grouped_item[section] += item_count
        if item_count >= threshold:
            repeats[section] += 1

    section_counts: dict[str, dict[str, int]] = {}
    for section in EMAIL_THREAD_GROUPS:
        section_counts[section] = {
            "ungrouped_visible_count": ungrouped_visible.get(section, 0),
            "grouped_entry_count": grouped_entry.get(section, 0),
            "grouped_item_count": grouped_item.get(section, 0),
            "groups_with_repeats_count": repeats.get(section, 0),
        }
    return section_counts


def _grouped_preview_safe_text(group_entries: Sequence[Mapping[str, Any]]) -> str:
    """Build a deterministic, count-only preview string for hashing.

    The string contains only opaque group ids, section labels, item counts, and
    safe enum summaries. It never contains titles, summaries, actions, source
    object ids, fingerprints, or any raw content. It is hashed but never printed.
    """

    if not group_entries:
        return f"{_GROUPED_PREVIEW_NAMESPACE}|empty"

    lines: list[str] = []
    for group in group_entries:
        enum_summary = json.dumps(
            group.get("safe_enum_summary", {}),
            sort_keys=True,
            separators=(",", ":"),
        )
        lines.append(
            "|".join(
                [
                    str(group.get("group_id")),
                    str(group.get("section")),
                    f"count={_safe_int(group.get('item_count'))}",
                    enum_summary,
                ]
            )
        )
    return f"{_GROUPED_PREVIEW_NAMESPACE}\n" + "\n".join(lines)


def _grouped_preview_hash_metadata(
    group_entries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    preview_text = _grouped_preview_safe_text(group_entries)
    chunks = split_telegram_plain_text(preview_text, max_chars=DEFAULT_TELEGRAM_CHUNK_SIZE)
    return {
        "grouped_preview_text_sha256": hashlib.sha256(
            preview_text.encode("utf-8")
        ).hexdigest(),
        "grouped_preview_char_count": len(preview_text),
        "grouped_preview_chunk_count": len(chunks),
    }


def _recommended_next_action(
    *,
    candidate: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    linkage_limited: bool,
    reduces_noise: bool,
) -> str:
    if _safe_int(candidate.get("visible")) < 1:
        return "choose_window_with_no_marker_visible_candidates"
    if lifecycle.get("matching_hash_has_successful_delivery_result") is True:
        return "do_not_resend_same_digest_content"
    if linkage_limited:
        return "inspect_linkage_limitations_before_grouping"
    if reduces_noise:
        return "review_grouped_preview_before_renderer_change"
    return "continue_no_marker_manual_pilot_review"


def _warnings(
    *,
    quality_report: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    linkage_limited: bool,
    reduces_noise: bool,
) -> list[str]:
    warnings = [
        str(warning)
        for warning in _sequence(quality_report.get("warnings"))
        if isinstance(warning, str)
    ]
    if lifecycle.get("matching_hash_has_successful_delivery_result") is True:
        warnings.append("candidate_already_successfully_sent")
    if linkage_limited:
        warnings.append("grouped_preview_linkage_limitations_present")
    if reduces_noise:
        warnings.append("grouped_preview_would_reduce_duplicate_noise")
    warnings.append("grouped_preview_is_presentation_planning_not_source_of_truth")
    warnings.append("duplicate_looking_not_semantic_duplicate")
    return sorted(set(warnings))


def _limitations(
    *,
    activity_window_supplied: bool,
    quality_limitations: Sequence[str],
    root_limitations: Sequence[str],
) -> list[str]:
    notes = [
        "grouped_preview_is_presentation_planning_only_not_source_of_truth_mutation",
        "grouped_preview_does_not_change_real_read_model_renderer_or_draft",
        "grouped_preview_text_sha256_is_separate_from_canonical_candidate_text_sha256",
        "canonical_candidate_text_sha256_is_unchanged",
        "grouped_preview_groups_by_source_object_for_presentation_only",
        "grouped_preview_preserves_visible_item_counts",
        "grouped_preview_hash_computed_without_returning_grouped_text",
        "duplicate_looking_does_not_prove_semantic_duplicate",
        "no_marker_is_not_proof_of_production_truth",
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
    safety["grouped_preview_text_included"] = False
    safety["grouped_preview_chunk_text_included"] = False
    return safety


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _safety_metadata(),
    }


async def build_no_marker_persisted_attention_grouped_preview_report(
    query: NoMarkerGroupedPreviewQuery,
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
        raise NoMarkerGroupedPreviewBlockedError(str(exc)) from exc

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
        raise NoMarkerGroupedPreviewInputError(str(exc)) from exc
    except quality_script.NoMarkerDigestQualityBlockedError as exc:
        raise NoMarkerGroupedPreviewBlockedError(str(exc)) from exc
    except quality_script.NoMarkerDigestQualityRuntimeError as exc:
        raise NoMarkerGroupedPreviewRuntimeError(str(exc)) from exc

    session_factory = session_factory or AsyncSessionLocal
    try:
        async with session_factory() as session:
            items, root_limitations = await root_cause_script._load_root_cause_items(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                settings_override=settings_override,
            )
    except (
        NoMarkerGroupedPreviewInputError,
        NoMarkerGroupedPreviewBlockedError,
    ):
        raise
    except ValueError as exc:
        raise NoMarkerGroupedPreviewInputError(str(exc)) from exc
    except Exception as exc:
        raise NoMarkerGroupedPreviewRuntimeError(
            "no-marker grouped preview blocked; database, schema, or configuration is unavailable"
        ) from exc

    candidate = _candidate_summary(quality_report)
    duplicate_quality = _duplicate_quality_summary(quality_report)
    lifecycle = _lifecycle_summary(quality_report)

    group_entries, unsectioned_count = _build_groups(
        items,
        threshold=query.cluster_threshold,
    )
    grouped_item_count = sum(_safe_int(g.get("item_count")) for g in group_entries)
    sectioned_visible_count = len(items) - unsectioned_count
    grouped_entry_count = len(group_entries)
    groups_with_repeats_count = sum(
        1
        for group in group_entries
        if _safe_int(group.get("item_count")) >= query.cluster_threshold
    )
    largest_group_size = max(
        (_safe_int(group.get("item_count")) for group in group_entries),
        default=0,
    )
    section_counts = _section_counts(
        items,
        group_entries,
        threshold=query.cluster_threshold,
    )
    hash_metadata = _grouped_preview_hash_metadata(group_entries)
    hash_differs = (
        hash_metadata["grouped_preview_text_sha256"] != candidate.get("text_sha256")
    )
    reduces_noise = grouped_entry_count < grouped_item_count
    linkage_limited = unsectioned_count > 0 or bool(root_limitations)

    grouped_preview = {
        "grouped_item_count": grouped_item_count,
        "grouped_entry_count": grouped_entry_count,
        "groups_with_repeats_count": groups_with_repeats_count,
        "largest_group_size": largest_group_size,
        "grouped_preview_text_sha256": hash_metadata["grouped_preview_text_sha256"],
        "grouped_preview_char_count": hash_metadata["grouped_preview_char_count"],
        "grouped_preview_chunk_count": hash_metadata["grouped_preview_chunk_count"],
        "grouped_preview_hash_differs_from_candidate": hash_differs,
        "preserves_visible_item_count": grouped_item_count == sectioned_visible_count,
        "unsectioned_visible_item_count": unsectioned_count,
        "hidden_low_priority_count": _safe_int(candidate.get("hidden")),
        "section_counts": section_counts,
    }

    quality_limitations = [
        str(note)
        for note in _sequence(quality_report.get("limitations"))
        if isinstance(note, str)
    ]
    return {
        "status": "no_marker_persisted_attention_grouped_preview",
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
        "group_by": query.group_by,
        "no_marker_not_production_truth": True,
        "section_labels": dict(PERSISTED_ATTENTION_SECTION_LABELS),
        "candidate": candidate,
        "grouped_preview": grouped_preview,
        "groups": group_entries,
        "duplicate_quality": duplicate_quality,
        "lifecycle": lifecycle,
        "recommended_next_action": _recommended_next_action(
            candidate=candidate,
            lifecycle=lifecycle,
            linkage_limited=linkage_limited,
            reduces_noise=reduces_noise,
        ),
        "warnings": _warnings(
            quality_report=quality_report,
            lifecycle=lifecycle,
            linkage_limited=linkage_limited,
            reduces_noise=reduces_noise,
        ),
        "limitations": _limitations(
            activity_window_supplied=query.activity_start_at is not None
            and query.activity_end_at is not None,
            quality_limitations=quality_limitations,
            root_limitations=root_limitations,
        ),
        "safety": _safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_report(report: Mapping[str, Any]) -> str:
    candidate = _mapping(report.get("candidate"))
    grouped_preview = _mapping(report.get("grouped_preview"))
    duplicate_quality = _mapping(report.get("duplicate_quality"))
    lifecycle = _mapping(report.get("lifecycle"))
    safety = _mapping(report.get("safety"))
    lines = [
        "No-marker persisted attention grouped preview (read-only)",
        f"Window start: {report.get('start_at')}",
        f"Window end: {report.get('end_at')}",
        f"Activity window start: {report.get('activity_start_at')}",
        f"Activity window end: {report.get('activity_end_at')}",
        f"Limit: {report.get('limit')}",
        f"Debug evidence: {report.get('debug_evidence')}",
        f"Cluster threshold: {report.get('cluster_threshold')}",
        f"Marker filter: {report.get('marker_filter')}",
        f"Group by: {report.get('group_by')}",
        "No-marker is production truth: False",
        f"Candidate visible: {candidate.get('visible')}",
        f"Candidate text SHA-256: {candidate.get('text_sha256')}",
        f"Grouped item count: {grouped_preview.get('grouped_item_count')}",
        f"Grouped entry count: {grouped_preview.get('grouped_entry_count')}",
        f"Groups with repeats: {grouped_preview.get('groups_with_repeats_count')}",
        f"Largest group size: {grouped_preview.get('largest_group_size')}",
        (
            "Preserves visible item count: "
            f"{grouped_preview.get('preserves_visible_item_count')}"
        ),
        (
            "Grouped preview text SHA-256: "
            f"{grouped_preview.get('grouped_preview_text_sha256')}"
        ),
        (
            "Grouped preview hash differs from candidate: "
            f"{grouped_preview.get('grouped_preview_hash_differs_from_candidate')}"
        ),
        f"High duplicate risk: {duplicate_quality.get('high_duplicate_risk')}",
        f"Duplicate-like ratio: {duplicate_quality.get('duplicate_like_ratio')}",
        f"Possible origin: {duplicate_quality.get('possible_origin')}",
        (
            "Matching hash has successful delivery: "
            f"{lifecycle.get('matching_hash_has_successful_delivery_result')}"
        ),
        f"Candidate lifecycle status: {lifecycle.get('candidate_lifecycle_status')}",
        f"Recommended next action: {report.get('recommended_next_action')}",
        f"Warnings: {report.get('warnings')}",
        "Grouped preview is source-of-truth mutation: False",
        "Duplicate-looking is semantic duplicate: False",
        "",
        f"Provider free: {safety.get('provider_free')}",
        f"Read only: {safety.get('read_only')}",
        f"DB write scope: {safety.get('db_write_scope')}",
        f"Grouped preview text included: {safety.get('grouped_preview_text_included')}",
        f"Delivery draft created: {safety.get('delivery_draft_created')}",
        f"Delivery intention created: {safety.get('delivery_intention_created')}",
        f"Delivery result created: {safety.get('delivery_result_created')}",
        f"Telegram invoked: {safety.get('telegram_invoked')}",
        f"Scheduler invoked: {safety.get('scheduler_invoked')}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        report = asyncio.run(
            build_no_marker_persisted_attention_grouped_preview_report(query)
        )
    except NoMarkerGroupedPreviewInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except NoMarkerGroupedPreviewBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except NoMarkerGroupedPreviewRuntimeError as exc:
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
