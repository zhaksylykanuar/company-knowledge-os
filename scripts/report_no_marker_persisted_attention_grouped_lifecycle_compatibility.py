#!/usr/bin/env python
"""Compare no-marker grouped preview hash against canonical candidate lifecycle.

This is a read-only, provider-free report. It explains whether a source-object
grouped preview would be treated as already-sent or as a new/unsent presentation
variant under the current hash-oriented duplicate-success guard, and flags the
presentation-variant duplicate-send risk. It never changes the real persisted
digest read model, renderer, delivery draft body, ``text_sha256`` lifecycle, or
the duplicate guard. It also exposes the read-only canonical-hash guard
evaluator result for the explicit canonical/grouped hash pair. It never creates
drafts, approvals, intentions, results, or sends.
"""

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

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.digest import (  # noqa: E402
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script  # noqa: E402
from scripts import (  # noqa: E402
    report_no_marker_persisted_attention_candidates as candidate_script,
)
from scripts import (  # noqa: E402
    report_no_marker_persisted_attention_grouped_preview as grouped_preview_script,
)

DEFAULT_CLUSTER_THRESHOLD = grouped_preview_script.DEFAULT_CLUSTER_THRESHOLD
MAX_CLUSTER_THRESHOLD = grouped_preview_script.MAX_CLUSTER_THRESHOLD
SUPPORTED_GROUP_BY = grouped_preview_script.SUPPORTED_GROUP_BY
DEFAULT_GROUP_BY = grouped_preview_script.DEFAULT_GROUP_BY


class NoMarkerGroupedLifecycleInputError(ValueError):
    pass


class NoMarkerGroupedLifecycleBlockedError(RuntimeError):
    pass


class NoMarkerGroupedLifecycleRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NoMarkerGroupedLifecycleQuery:
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
        raise NoMarkerGroupedLifecycleInputError(str(exc)) from exc


def _clean_limit(value: int) -> int:
    if not isinstance(value, int):
        raise NoMarkerGroupedLifecycleInputError("limit must be an integer")
    if value < 1 or value > MAX_DIGEST_ENTRY_LIMIT:
        raise NoMarkerGroupedLifecycleInputError(
            f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}"
        )
    return value


def _clean_cluster_threshold(value: int) -> int:
    if not isinstance(value, int):
        raise NoMarkerGroupedLifecycleInputError("cluster_threshold must be an integer")
    if value < 2 or value > MAX_CLUSTER_THRESHOLD:
        raise NoMarkerGroupedLifecycleInputError(
            f"cluster_threshold must be between 2 and {MAX_CLUSTER_THRESHOLD}"
        )
    return value


def _clean_group_by(value: str) -> str:
    if not isinstance(value, str) or value not in SUPPORTED_GROUP_BY:
        raise NoMarkerGroupedLifecycleInputError(
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
        choices=("text", "json", "review-json"),
        default="json",
        help="Output format. Use review-json for decision-only review metadata.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> NoMarkerGroupedLifecycleQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise NoMarkerGroupedLifecycleInputError("end_at must be after start_at")

    activity_start_at = None
    activity_end_at = None
    if args.activity_start_at is not None or args.activity_end_at is not None:
        if args.activity_start_at is None or args.activity_end_at is None:
            raise NoMarkerGroupedLifecycleInputError(
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
            raise NoMarkerGroupedLifecycleInputError(
                "activity_end_at must be after activity_start_at"
            )

    return NoMarkerGroupedLifecycleQuery(
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


async def _load_window_draft_hash_facts(
    *,
    session_factory: Callable[[], Any] | None,
    start_at: datetime,
    end_at: datetime,
    limit: int,
    debug_evidence: bool,
) -> list[dict[str, Any]]:
    """Return safe per-draft hash lifecycle facts for the window (read-only).

    Each fact contains only the draft ``text_sha256`` and a derived
    ``has_successful_delivery`` boolean. No rendered text, chunk text, payloads,
    or item details are read or returned.
    """

    from app.db.base import AsyncSessionLocal
    from app.services.digest_delivery_drafts import (
        list_persisted_digest_delivery_drafts_for_window,
    )
    from scripts import report_manual_pilot_status as pilot_status_script

    factory = session_factory or AsyncSessionLocal
    facts: list[dict[str, Any]] = []
    async with factory() as session:
        drafts = await list_persisted_digest_delivery_drafts_for_window(
            session,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
            debug_evidence=debug_evidence,
        )
        for draft in drafts:
            summary = await pilot_status_script._draft_lifecycle_summary(
                session,
                draft=draft,
            )
            facts.append(
                {
                    "text_sha256": summary.get("text_sha256"),
                    "has_successful_delivery": (
                        candidate_script._draft_has_successful_delivery(summary)
                    ),
                }
            )
    return facts


def _grouped_hash_lifecycle(
    *,
    grouped_hash: str | None,
    draft_facts: Sequence[Mapping[str, Any]],
) -> tuple[bool, bool]:
    matches = False
    has_success = False
    for fact in draft_facts:
        if fact.get("text_sha256") != grouped_hash:
            continue
        matches = True
        if fact.get("has_successful_delivery") is True:
            has_success = True
    return matches, has_success


def _compatibility(
    *,
    visible_count: int,
    canonical_lifecycle: Mapping[str, Any],
    canonical_text_sha256: str | None,
    grouped_text_sha256: str | None,
    grouped_hash_differs_from_canonical: bool,
    grouped_hash_matches_existing_draft: bool,
    grouped_hash_has_successful_delivery_result: bool,
) -> dict[str, Any]:
    canonical_matching_success = (
        canonical_lifecycle.get("matching_hash_has_successful_delivery_result") is True
    )

    if visible_count < 1:
        treated_as = "no_visible_candidate"
    elif grouped_hash_has_successful_delivery_result:
        treated_as = "already_sent"
    elif grouped_hash_differs_from_canonical:
        treated_as = "new_unsent_presentation_variant"
    else:
        treated_as = "unknown"

    would_block = grouped_hash_has_successful_delivery_result
    would_allow = visible_count >= 1 and not would_block
    presentation_variant_duplicate_send_risk = (
        canonical_matching_success
        and grouped_hash_differs_from_canonical
        and not grouped_hash_has_successful_delivery_result
    )
    return {
        "canonical_candidate_text_sha256": canonical_text_sha256,
        "grouped_preview_text_sha256": grouped_text_sha256,
        "grouped_preview_hash_differs_from_canonical": (
            grouped_hash_differs_from_canonical
        ),
        "canonical_candidate_has_matching_draft_hash": (
            canonical_lifecycle.get("candidate_has_matching_draft_hash") is True
        ),
        "canonical_matching_hash_has_successful_delivery_result": (
            canonical_matching_success
        ),
        "canonical_candidate_lifecycle_status": (
            canonical_lifecycle.get("candidate_lifecycle_status")
        ),
        "grouped_hash_matches_existing_draft": grouped_hash_matches_existing_draft,
        "grouped_hash_has_successful_delivery_result": (
            grouped_hash_has_successful_delivery_result
        ),
        "grouped_variant_would_be_treated_as": treated_as,
        "current_hash_guard_would_block_grouped_variant": would_block,
        "current_hash_guard_would_allow_grouped_variant": would_allow,
        "presentation_variant_duplicate_send_risk": (
            presentation_variant_duplicate_send_risk
        ),
        "requires_guard_extension_before_grouped_send": (
            presentation_variant_duplicate_send_risk
        ),
        "grouped_hash_is_presentation_variant_not_delivered_content": True,
    }


def _recommended_next_action(
    *,
    visible_count: int,
    compatibility: Mapping[str, Any],
) -> str:
    if visible_count < 1:
        return "choose_window_with_no_marker_visible_candidates"
    if compatibility.get("presentation_variant_duplicate_send_risk") is True:
        return "do_not_send_grouped_variant_of_already_sent_canonical"
    if compatibility.get("grouped_variant_would_be_treated_as") == "unknown":
        return "inspect_grouped_lifecycle_before_grouped_draft"
    return "continue_no_marker_manual_pilot_review"


def _warnings(
    *,
    grouped_preview_report: Mapping[str, Any],
    compatibility: Mapping[str, Any],
    canonical_hash_guard_evaluation: Mapping[str, Any],
) -> list[str]:
    warnings = [
        str(warning)
        for warning in _sequence(grouped_preview_report.get("warnings"))
        if isinstance(warning, str)
    ]
    if compatibility.get("presentation_variant_duplicate_send_risk") is True:
        warnings.append("presentation_variant_duplicate_send_risk")
    if (
        compatibility.get("grouped_variant_would_be_treated_as")
        == "new_unsent_presentation_variant"
    ):
        warnings.append("grouped_variant_would_be_new_unsent_presentation_variant")
    if canonical_hash_guard_evaluation.get("blocked_by_canonical_success") is True:
        warnings.append("canonical_hash_guard_evaluator_would_block_grouped_variant")
    warnings.append("grouped_hash_is_presentation_variant_not_delivered_content")
    warnings.append("duplicate_looking_not_semantic_duplicate")
    return sorted(set(warnings))


def _limitations(grouped_preview_report: Mapping[str, Any]) -> list[str]:
    notes = [
        "grouped_lifecycle_compatibility_is_count_only_operational_metadata_not_company_facts",
        "grouped_preview_hash_is_presentation_variant_hash_not_delivered_content",
        "canonical_candidate_text_sha256_is_unchanged",
        "current_duplicate_success_guard_is_hash_oriented",
        "grouped_send_requires_guard_extension_or_canonical_hash_linkage",
        "report_does_not_change_renderer_read_model_draft_or_duplicate_guard",
        "no_marker_is_not_proof_of_production_truth",
        "duplicate_looking_does_not_prove_semantic_duplicate",
        "hidden_low_priority_items_remain_count_only",
        "delivery_execution_remains_separately_gated",
    ]
    notes.extend(
        str(note)
        for note in _sequence(grouped_preview_report.get("limitations"))
        if isinstance(note, str)
    )
    return list(dict.fromkeys(notes))


def _safety_metadata() -> dict[str, Any]:
    safety = dict(grouped_preview_script._safety_metadata())
    safety["canonical_hash_guard_evaluator_invoked"] = True
    safety["canonical_hash_guard_enforced"] = False
    safety["operator_review_summary_included"] = True
    safety["operator_review_summary_enforced"] = False
    safety["semantic_duplicate_claimed"] = False
    return safety


def _conservative_canonical_hash_guard_evaluation(
    *,
    reason: str,
    current_hash: str | None,
    canonical_hash: str | None,
) -> dict[str, Any]:
    return {
        "status": "presentation_variant_duplicate_guard_evaluation",
        "available": False,
        "current_hash_available": bool(current_hash),
        "linked_canonical_hash_available": bool(canonical_hash),
        "canonical_hash_distinct_from_current": (
            bool(current_hash)
            and bool(canonical_hash)
            and current_hash != canonical_hash
        ),
        "current_hash_has_successful_delivery": False,
        "linked_canonical_hash_has_successful_delivery": False,
        "blocked_by_canonical_success": False,
        "current_duplicate_success_guard_would_block": False,
        "canonical_hash_guard_extension_would_block": False,
        "blocker_code": None,
        "recommended_action": "continue_no_marker_manual_pilot_review",
        "conservative_reason": reason,
        "enforced": False,
        "semantic_duplicate_claimed": False,
        "read_only": True,
    }


def _safe_canonical_hash_guard_evaluation(
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "status": evaluation.get("status"),
        "available": True,
        "current_hash_available": bool(evaluation.get("presentation_text_sha256")),
        "linked_canonical_hash_available": bool(
            evaluation.get("canonical_text_sha256")
        ),
        "canonical_hash_distinct_from_current": (
            evaluation.get("canonical_hash_distinct_from_presentation") is True
        ),
        "current_hash_has_successful_delivery": (
            evaluation.get("presentation_hash_has_successful_delivery_result") is True
        ),
        "linked_canonical_hash_has_successful_delivery": (
            evaluation.get("canonical_hash_has_successful_delivery_result") is True
        ),
        "blocked_by_canonical_success": (
            evaluation.get("presentation_variant_blocked_by_canonical_success") is True
        ),
        "current_duplicate_success_guard_would_block": (
            evaluation.get("current_duplicate_success_guard_would_block") is True
        ),
        "canonical_hash_guard_extension_would_block": (
            evaluation.get("canonical_hash_guard_extension_would_block") is True
        ),
        "blocker_code": evaluation.get("blocker"),
        "recommended_action": evaluation.get("recommended_next_action"),
        "conservative_reason": None,
        "enforced": evaluation.get("enforced") is True,
        "semantic_duplicate_claimed": (
            evaluation.get("semantic_duplicate_claimed") is True
        ),
        "read_only": _mapping(evaluation.get("safety")).get("read_only") is True,
    }


def _operator_review_summary(
    *,
    compatibility: Mapping[str, Any],
    canonical_hash_guard_evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    reason_codes: list[str] = []
    current_hash_has_success = (
        canonical_hash_guard_evaluation.get("current_hash_has_successful_delivery")
        is True
    )

    if (
        compatibility.get("grouped_hash_has_successful_delivery_result") is True
        or current_hash_has_success
    ):
        decision = "already_sent_by_current_hash"
        blocker_code = (
            canonical_hash_guard_evaluation.get("blocker_code")
            or "delivery_draft_already_successfully_sent"
        )
        recommended_action = (
            canonical_hash_guard_evaluation.get("recommended_action")
            if current_hash_has_success
            else None
        ) or "do_not_resend_grouped_presentation"
        requires_human_review = False
        reason_codes.append("current_grouped_hash_has_successful_delivery")
    elif canonical_hash_guard_evaluation.get("blocked_by_canonical_success") is True:
        decision = "blocked_by_linked_canonical_hash"
        blocker_code = (
            canonical_hash_guard_evaluation.get("blocker_code")
            or "presentation_variant_canonical_hash_already_successfully_sent"
        )
        recommended_action = (
            canonical_hash_guard_evaluation.get("recommended_action")
            or "do_not_send_presentation_variant_of_successful_canonical_digest"
        )
        requires_human_review = False
        reason_codes.append("linked_canonical_hash_has_successful_delivery")
    elif (
        compatibility.get("grouped_variant_would_be_treated_as")
        == "no_visible_candidate"
    ):
        decision = "manual_review_needed"
        blocker_code = None
        recommended_action = "choose_window_with_no_marker_visible_candidates"
        requires_human_review = True
        reason_codes.append("no_visible_candidate")
    elif canonical_hash_guard_evaluation.get("available") is not True:
        decision = "manual_review_needed"
        blocker_code = None
        recommended_action = "manual_review_required_before_grouped_send"
        requires_human_review = True
        reason = canonical_hash_guard_evaluation.get("conservative_reason")
        reason_codes.append(
            reason
            if isinstance(reason, str) and reason
            else "insufficient_hash_evidence"
        )
    else:
        decision = "not_blocked"
        blocker_code = None
        recommended_action = (
            canonical_hash_guard_evaluation.get("recommended_action")
            or "continue_no_marker_manual_pilot_review"
        )
        requires_human_review = False
        reason_codes.append("no_current_or_linked_canonical_successful_delivery")

    if compatibility.get("presentation_variant_duplicate_send_risk") is True:
        reason_codes.append("presentation_variant_duplicate_send_risk")
    if (
        canonical_hash_guard_evaluation.get("canonical_hash_distinct_from_current")
        is True
    ):
        reason_codes.append("explicit_canonical_presentation_hash_link")

    return {
        "status": "operator_review_summary",
        "decision": decision,
        "blocker_code": blocker_code,
        "recommended_action": recommended_action,
        "requires_human_review": requires_human_review,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "enforced": False,
        "semantic_duplicate_claimed": False,
        "read_only": True,
    }


async def _evaluate_canonical_hash_guard(
    *,
    session_factory: Callable[[], Any] | None,
    current_hash: str | None,
    canonical_hash: str | None,
    start_at: datetime,
    end_at: datetime,
    limit: int,
    debug_evidence: bool,
) -> dict[str, Any]:
    if not current_hash:
        return _conservative_canonical_hash_guard_evaluation(
            reason="missing_current_presentation_hash",
            current_hash=current_hash,
            canonical_hash=canonical_hash,
        )
    if not canonical_hash:
        return _conservative_canonical_hash_guard_evaluation(
            reason="missing_linked_canonical_hash",
            current_hash=current_hash,
            canonical_hash=canonical_hash,
        )
    if current_hash == canonical_hash:
        return _conservative_canonical_hash_guard_evaluation(
            reason="canonical_hash_matches_current_hash",
            current_hash=current_hash,
            canonical_hash=canonical_hash,
        )

    from app.db.base import AsyncSessionLocal
    from app.services.digest_delivery_drafts import (
        evaluate_digest_delivery_presentation_variant_duplicate_guard,
    )

    factory = session_factory or AsyncSessionLocal
    try:
        async with factory() as session:
            evaluation = (
                await evaluate_digest_delivery_presentation_variant_duplicate_guard(
                    session,
                    presentation_text_sha256=current_hash,
                    canonical_text_sha256=canonical_hash,
                    start_at=start_at,
                    end_at=end_at,
                    limit=limit,
                    debug_evidence=debug_evidence,
                )
            )
    except ValueError:
        return _conservative_canonical_hash_guard_evaluation(
            reason="invalid_explicit_hash_link",
            current_hash=current_hash,
            canonical_hash=canonical_hash,
        )

    return _safe_canonical_hash_guard_evaluation(evaluation)


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _safety_metadata(),
    }


async def build_no_marker_grouped_lifecycle_compatibility_report(
    query: NoMarkerGroupedLifecycleQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    settings_override: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    from app.core.config import settings

    try:
        prepare_script._assert_local_environment(
            settings=settings_override or settings,
            environ=environ if environ is not None else os.environ,
        )
    except prepare_script.PrepareBlockedError as exc:
        raise NoMarkerGroupedLifecycleBlockedError(str(exc)) from exc

    grouped_query = grouped_preview_script.NoMarkerGroupedPreviewQuery(
        start_at=query.start_at,
        end_at=query.end_at,
        activity_start_at=query.activity_start_at,
        activity_end_at=query.activity_end_at,
        limit=query.limit,
        debug_evidence=query.debug_evidence,
        cluster_threshold=query.cluster_threshold,
        group_by=query.group_by,
        output_format="json",
    )
    try:
        grouped_report = (
            await grouped_preview_script.build_no_marker_persisted_attention_grouped_preview_report(
                grouped_query,
                session_factory=session_factory,
                settings_override=settings_override,
                environ=environ,
            )
        )
    except grouped_preview_script.NoMarkerGroupedPreviewInputError as exc:
        raise NoMarkerGroupedLifecycleInputError(str(exc)) from exc
    except grouped_preview_script.NoMarkerGroupedPreviewBlockedError as exc:
        raise NoMarkerGroupedLifecycleBlockedError(str(exc)) from exc
    except grouped_preview_script.NoMarkerGroupedPreviewRuntimeError as exc:
        raise NoMarkerGroupedLifecycleRuntimeError(str(exc)) from exc

    candidate = _mapping(grouped_report.get("candidate"))
    grouped_preview = _mapping(grouped_report.get("grouped_preview"))
    duplicate_quality = _mapping(grouped_report.get("duplicate_quality"))
    canonical_lifecycle = _mapping(grouped_report.get("lifecycle"))

    canonical_text_sha256 = candidate.get("text_sha256")
    grouped_text_sha256 = grouped_preview.get("grouped_preview_text_sha256")
    grouped_hash_differs_from_canonical = (
        grouped_preview.get("grouped_preview_hash_differs_from_candidate") is True
    )
    visible_count = _safe_int(candidate.get("visible"))

    try:
        draft_facts = await _load_window_draft_hash_facts(
            session_factory=session_factory,
            start_at=query.start_at,
            end_at=query.end_at,
            limit=query.limit,
            debug_evidence=query.debug_evidence,
        )
    except (
        NoMarkerGroupedLifecycleInputError,
        NoMarkerGroupedLifecycleBlockedError,
    ):
        raise
    except ValueError as exc:
        raise NoMarkerGroupedLifecycleInputError(str(exc)) from exc
    except Exception as exc:
        raise NoMarkerGroupedLifecycleRuntimeError(
            "grouped lifecycle compatibility blocked; database, schema, or configuration is unavailable"
        ) from exc

    grouped_matches, grouped_success = _grouped_hash_lifecycle(
        grouped_hash=grouped_text_sha256,
        draft_facts=draft_facts,
    )
    compatibility = _compatibility(
        visible_count=visible_count,
        canonical_lifecycle=canonical_lifecycle,
        canonical_text_sha256=canonical_text_sha256,
        grouped_text_sha256=grouped_text_sha256,
        grouped_hash_differs_from_canonical=grouped_hash_differs_from_canonical,
        grouped_hash_matches_existing_draft=grouped_matches,
        grouped_hash_has_successful_delivery_result=grouped_success,
    )
    canonical_hash_guard_evaluation = await _evaluate_canonical_hash_guard(
        session_factory=session_factory,
        current_hash=(
            grouped_text_sha256 if isinstance(grouped_text_sha256, str) else None
        ),
        canonical_hash=(
            canonical_text_sha256 if isinstance(canonical_text_sha256, str) else None
        ),
        start_at=query.start_at,
        end_at=query.end_at,
        limit=query.limit,
        debug_evidence=query.debug_evidence,
    )
    operator_review_summary = _operator_review_summary(
        compatibility=compatibility,
        canonical_hash_guard_evaluation=canonical_hash_guard_evaluation,
    )

    return {
        "status": "no_marker_grouped_lifecycle_compatibility",
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
        "candidate": dict(candidate),
        "grouped_preview": dict(grouped_preview),
        "lifecycle_compatibility": compatibility,
        "canonical_hash_guard_evaluation": canonical_hash_guard_evaluation,
        "operator_review_summary": operator_review_summary,
        "duplicate_quality": dict(duplicate_quality),
        "recommended_next_action": _recommended_next_action(
            visible_count=visible_count,
            compatibility=compatibility,
        ),
        "warnings": _warnings(
            grouped_preview_report=grouped_report,
            compatibility=compatibility,
            canonical_hash_guard_evaluation=canonical_hash_guard_evaluation,
        ),
        "limitations": _limitations(grouped_report),
        "safety": _safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_review_json_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the sanitized decision/review surface for operator review."""

    return {
        "status": report.get("status"),
        "start_at": report.get("start_at"),
        "end_at": report.get("end_at"),
        "activity_start_at": report.get("activity_start_at"),
        "activity_end_at": report.get("activity_end_at"),
        "limit": report.get("limit"),
        "debug_evidence": report.get("debug_evidence"),
        "cluster_threshold": report.get("cluster_threshold"),
        "marker_filter": report.get("marker_filter"),
        "group_by": report.get("group_by"),
        "no_marker_not_production_truth": (
            report.get("no_marker_not_production_truth") is True
        ),
        "lifecycle_compatibility": dict(
            _mapping(report.get("lifecycle_compatibility"))
        ),
        "canonical_hash_guard_evaluation": dict(
            _mapping(report.get("canonical_hash_guard_evaluation"))
        ),
        "operator_review_summary": dict(
            _mapping(report.get("operator_review_summary"))
        ),
        "safety": dict(_mapping(report.get("safety"))),
    }


def format_text_report(report: Mapping[str, Any]) -> str:
    candidate = _mapping(report.get("candidate"))
    grouped_preview = _mapping(report.get("grouped_preview"))
    compatibility = _mapping(report.get("lifecycle_compatibility"))
    canonical_guard = _mapping(report.get("canonical_hash_guard_evaluation"))
    operator_summary = _mapping(report.get("operator_review_summary"))
    duplicate_quality = _mapping(report.get("duplicate_quality"))
    safety = _mapping(report.get("safety"))
    lines = [
        "No-marker grouped lifecycle compatibility (read-only)",
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
        (
            "Grouped preview text SHA-256: "
            f"{grouped_preview.get('grouped_preview_text_sha256')}"
        ),
        (
            "Grouped hash differs from canonical: "
            f"{compatibility.get('grouped_preview_hash_differs_from_canonical')}"
        ),
        (
            "Canonical lifecycle status: "
            f"{compatibility.get('canonical_candidate_lifecycle_status')}"
        ),
        (
            "Canonical matching hash successful delivery: "
            f"{compatibility.get('canonical_matching_hash_has_successful_delivery_result')}"
        ),
        (
            "Grouped hash matches existing draft: "
            f"{compatibility.get('grouped_hash_matches_existing_draft')}"
        ),
        (
            "Grouped hash successful delivery: "
            f"{compatibility.get('grouped_hash_has_successful_delivery_result')}"
        ),
        (
            "Grouped variant would be treated as: "
            f"{compatibility.get('grouped_variant_would_be_treated_as')}"
        ),
        (
            "Current guard would block grouped variant: "
            f"{compatibility.get('current_hash_guard_would_block_grouped_variant')}"
        ),
        (
            "Current guard would allow grouped variant: "
            f"{compatibility.get('current_hash_guard_would_allow_grouped_variant')}"
        ),
        (
            "Presentation-variant duplicate-send risk: "
            f"{compatibility.get('presentation_variant_duplicate_send_risk')}"
        ),
        (
            "Requires guard extension before grouped send: "
            f"{compatibility.get('requires_guard_extension_before_grouped_send')}"
        ),
        (
            "Canonical-hash guard current hash successful delivery: "
            f"{canonical_guard.get('current_hash_has_successful_delivery')}"
        ),
        (
            "Canonical-hash guard linked canonical successful delivery: "
            f"{canonical_guard.get('linked_canonical_hash_has_successful_delivery')}"
        ),
        (
            "Canonical-hash guard blocked by canonical success: "
            f"{canonical_guard.get('blocked_by_canonical_success')}"
        ),
        f"Canonical-hash guard blocker: {canonical_guard.get('blocker_code')}",
        (
            "Canonical-hash guard recommended action: "
            f"{canonical_guard.get('recommended_action')}"
        ),
        f"Canonical-hash guard enforced: {canonical_guard.get('enforced')}",
        (
            "Canonical-hash guard semantic duplicate claimed: "
            f"{canonical_guard.get('semantic_duplicate_claimed')}"
        ),
        f"Operator review decision: {operator_summary.get('decision')}",
        f"Operator review blocker: {operator_summary.get('blocker_code')}",
        (
            "Operator review recommended action: "
            f"{operator_summary.get('recommended_action')}"
        ),
        (
            "Operator review requires human review: "
            f"{operator_summary.get('requires_human_review')}"
        ),
        f"Operator review reason codes: {operator_summary.get('reason_codes')}",
        f"Operator review enforced: {operator_summary.get('enforced')}",
        (
            "Operator review semantic duplicate claimed: "
            f"{operator_summary.get('semantic_duplicate_claimed')}"
        ),
        f"High duplicate risk: {duplicate_quality.get('high_duplicate_risk')}",
        f"Recommended next action: {report.get('recommended_next_action')}",
        f"Warnings: {report.get('warnings')}",
        "Grouped hash is delivered content: False",
        "Duplicate-looking is semantic duplicate: False",
        "",
        f"Provider free: {safety.get('provider_free')}",
        f"Read only: {safety.get('read_only')}",
        f"DB write scope: {safety.get('db_write_scope')}",
        f"Grouped preview text included: {safety.get('grouped_preview_text_included')}",
        (
            "Canonical-hash guard evaluator invoked: "
            f"{safety.get('canonical_hash_guard_evaluator_invoked')}"
        ),
        (
            "Canonical-hash guard enforced: "
            f"{safety.get('canonical_hash_guard_enforced')}"
        ),
        (
            "Operator review summary included: "
            f"{safety.get('operator_review_summary_included')}"
        ),
        (
            "Operator review summary enforced: "
            f"{safety.get('operator_review_summary_enforced')}"
        ),
        f"Delivery draft created: {safety.get('delivery_draft_created')}",
        f"Delivery result created: {safety.get('delivery_result_created')}",
        f"Telegram invoked: {safety.get('telegram_invoked')}",
        f"Scheduler invoked: {safety.get('scheduler_invoked')}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    json_output_formats = {"json", "review-json"}
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        report = asyncio.run(
            build_no_marker_grouped_lifecycle_compatibility_report(query)
        )
    except NoMarkerGroupedLifecycleInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format in json_output_formats:
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except NoMarkerGroupedLifecycleBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format in json_output_formats:
            _print_json(_blocked_result(error_code="blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except NoMarkerGroupedLifecycleRuntimeError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format in json_output_formats:
            _print_json(_blocked_result(error_code="runtime_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    if query.output_format == "json":
        _print_json(report)
    elif query.output_format == "review-json":
        _print_json(format_review_json_report(report))
    else:
        print(format_text_report(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
