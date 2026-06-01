from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog
from app.services.digest import (
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
    build_persisted_attention_digest_read_model,
)
from scripts import (
    report_no_marker_persisted_attention_grouped_lifecycle_compatibility as compat_script,
)
from scripts import (
    report_no_marker_persisted_attention_grouped_preview as grouped_preview_script,
)
from tests.test_no_marker_persisted_attention_candidates import (
    _assert_safe_output,
    _audit_log_count,
    _cleanup,
    _ensure_tables,
    _insert_attention_result,
    _local_settings,
    _persist_successful_draft_for_digest,
    _serialized,
    _utc,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT
    / "scripts"
    / "report_no_marker_persisted_attention_grouped_lifecycle_compatibility.py"
)
OPERATOR_REVIEW_DECISIONS = {
    "already_sent_by_current_hash",
    "blocked_by_linked_canonical_hash",
    "not_blocked",
    "manual_review_needed",
}
GROUPED_VARIANT_TREATMENTS = {
    "already_sent",
    "new_unsent_presentation_variant",
    "no_visible_candidate",
    "unknown",
}
LIFECYCLE_COMPATIBILITY_REQUIRED_FIELDS = {
    "canonical_candidate_text_sha256",
    "grouped_preview_text_sha256",
    "grouped_preview_hash_differs_from_canonical",
    "canonical_candidate_has_matching_draft_hash",
    "canonical_matching_hash_has_successful_delivery_result",
    "canonical_candidate_lifecycle_status",
    "grouped_hash_matches_existing_draft",
    "grouped_hash_has_successful_delivery_result",
    "grouped_variant_would_be_treated_as",
    "current_hash_guard_would_block_grouped_variant",
    "current_hash_guard_would_allow_grouped_variant",
    "presentation_variant_duplicate_send_risk",
    "requires_guard_extension_before_grouped_send",
    "grouped_hash_is_presentation_variant_not_delivered_content",
}
CANONICAL_HASH_GUARD_REQUIRED_FIELDS = {
    "status",
    "available",
    "current_hash_available",
    "linked_canonical_hash_available",
    "canonical_hash_distinct_from_current",
    "current_hash_has_successful_delivery",
    "linked_canonical_hash_has_successful_delivery",
    "blocked_by_canonical_success",
    "current_duplicate_success_guard_would_block",
    "canonical_hash_guard_extension_would_block",
    "blocker_code",
    "recommended_action",
    "conservative_reason",
    "enforced",
    "semantic_duplicate_claimed",
    "read_only",
}
OPERATOR_REVIEW_SUMMARY_REQUIRED_FIELDS = {
    "status",
    "decision",
    "blocker_code",
    "recommended_action",
    "requires_human_review",
    "reason_codes",
    "enforced",
    "semantic_duplicate_claimed",
    "read_only",
}


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _query(
    *,
    start_at: datetime,
    end_at: datetime,
    activity_start_at: datetime | None = None,
    activity_end_at: datetime | None = None,
    limit: int = 20,
    cluster_threshold: int = 2,
    group_by: str = "source_object",
) -> compat_script.NoMarkerGroupedLifecycleQuery:
    return compat_script.NoMarkerGroupedLifecycleQuery(
        start_at=start_at,
        end_at=end_at,
        activity_start_at=activity_start_at,
        activity_end_at=activity_end_at,
        limit=limit,
        debug_evidence=False,
        cluster_threshold=cluster_threshold,
        group_by=group_by,
        output_format="json",
    )


async def _build(query: compat_script.NoMarkerGroupedLifecycleQuery) -> dict:
    return await compat_script.build_no_marker_grouped_lifecycle_compatibility_report(
        query,
        settings_override=_local_settings(),
        environ={},
    )


async def _grouped_preview_hash(
    *,
    start_at: datetime,
    end_at: datetime,
) -> str:
    report = (
        await grouped_preview_script.build_no_marker_persisted_attention_grouped_preview_report(
            grouped_preview_script.NoMarkerGroupedPreviewQuery(
                start_at=start_at,
                end_at=end_at,
                limit=20,
                debug_evidence=False,
                cluster_threshold=2,
                group_by="source_object",
                output_format="json",
            ),
            settings_override=_local_settings(),
            environ={},
        )
    )
    return report["grouped_preview"]["grouped_preview_text_sha256"]


async def _insert_successful_hash_lifecycle(
    unique: str,
    *,
    text_sha256: str,
    start_at: datetime,
    end_at: datetime,
) -> dict[str, str]:
    actor = f"test_fos086_{unique}"
    delivery_draft_id = f"ddraft_fos093_{unique}"
    delivery_intention_id = f"dint_fos093_{unique}"
    delivery_result_id = f"dres_fos093_{unique}"
    async with AsyncSessionLocal() as session:
        session.add(
            AuditLog(
                event_type="digest.delivery_draft.created",
                actor=actor,
                correlation_id=delivery_draft_id,
                trace_id=delivery_draft_id,
                after_ref=delivery_draft_id,
                payload={
                    "status": "draft",
                    "delivery_draft_id": delivery_draft_id,
                    "digest_type": "persisted_attention",
                    "channel": "telegram",
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                    "limit": 20,
                    "debug_evidence": False,
                    "text_sha256": text_sha256,
                    "char_count": 1,
                    "chunk_count": 1,
                    "sent": False,
                },
            )
        )
        session.add(
            AuditLog(
                event_type="digest.delivery_intention.created",
                actor=actor,
                correlation_id=delivery_draft_id,
                trace_id=delivery_intention_id,
                before_ref=delivery_draft_id,
                after_ref=delivery_intention_id,
                approval_id=f"{delivery_draft_id}:delivery_intention",
                payload={
                    "status": "delivery_intention",
                    "delivery_intention_id": delivery_intention_id,
                    "delivery_draft_id": delivery_draft_id,
                    "digest_type": "persisted_attention",
                    "channel": "telegram",
                    "current_decision": "approved",
                    "eligible_for_delivery": True,
                    "text_sha256": text_sha256,
                    "char_count": 1,
                    "chunk_count": 1,
                    "sent": False,
                    "scheduler_invoked": False,
                },
            )
        )
        session.add(
            AuditLog(
                event_type="digest.delivery_result.recorded",
                actor=actor,
                correlation_id=delivery_intention_id,
                trace_id=delivery_result_id,
                before_ref=delivery_intention_id,
                after_ref=delivery_result_id,
                approval_id=f"{delivery_intention_id}:delivery_result",
                payload={
                    "status": "delivery_result",
                    "delivery_result_id": delivery_result_id,
                    "delivery_intention_id": delivery_intention_id,
                    "execution_attempt_id": f"attempt-fos093-{unique}",
                    "result_status": "succeeded",
                    "sent": True,
                    "attempted_chunk_count": 1,
                    "delivered_chunk_count": 1,
                    "failed_chunk_count": 0,
                },
            )
        )
        await session.commit()
    return {
        "delivery_draft_id": delivery_draft_id,
        "delivery_intention_id": delivery_intention_id,
        "delivery_result_id": delivery_result_id,
    }


def _fake_grouped_report(
    *,
    candidate_hash: str | None,
    grouped_hash: str | None,
    visible: int = 1,
) -> dict:
    return {
        "candidate": {
            "visible": visible,
            "text_sha256": candidate_hash,
        },
        "grouped_preview": {
            "grouped_preview_text_sha256": grouped_hash,
            "grouped_preview_hash_differs_from_candidate": (
                bool(candidate_hash)
                and bool(grouped_hash)
                and candidate_hash != grouped_hash
            ),
        },
        "duplicate_quality": {"high_duplicate_risk": False},
        "lifecycle": {
            "candidate_has_matching_draft_hash": False,
            "matching_hash_has_successful_delivery_result": False,
            "candidate_lifecycle_status": "candidate_not_prepared",
        },
        "warnings": [],
        "limitations": [],
    }


def _assert_operator_summary_is_safe(summary: dict) -> None:
    assert summary["status"] == "operator_review_summary"
    assert summary["enforced"] is False
    assert summary["semantic_duplicate_claimed"] is False
    assert summary["read_only"] is True


def _assert_has_required_fields(section: dict, required_fields: set[str]) -> None:
    missing = required_fields - set(section)
    assert missing == set()


def _assert_optional_string(value: object) -> None:
    assert value is None or isinstance(value, str)


def _assert_grouped_lifecycle_report_contract(report: dict) -> None:
    assert report["status"] == "no_marker_grouped_lifecycle_compatibility"
    assert report["marker_filter"] == "no_marker_only"
    assert report["group_by"] == "source_object"
    assert report["no_marker_not_production_truth"] is True

    lifecycle_compatibility = report["lifecycle_compatibility"]
    canonical_hash_guard_evaluation = report["canonical_hash_guard_evaluation"]
    operator_review_summary = report["operator_review_summary"]
    safety = report["safety"]

    assert isinstance(lifecycle_compatibility, dict)
    assert isinstance(canonical_hash_guard_evaluation, dict)
    assert isinstance(operator_review_summary, dict)
    assert isinstance(safety, dict)

    _assert_has_required_fields(
        lifecycle_compatibility,
        LIFECYCLE_COMPATIBILITY_REQUIRED_FIELDS,
    )
    assert lifecycle_compatibility["grouped_variant_would_be_treated_as"] in (
        GROUPED_VARIANT_TREATMENTS
    )
    assert isinstance(
        lifecycle_compatibility["grouped_preview_hash_differs_from_canonical"],
        bool,
    )
    assert isinstance(
        lifecycle_compatibility[
            "canonical_matching_hash_has_successful_delivery_result"
        ],
        bool,
    )
    assert isinstance(
        lifecycle_compatibility["grouped_hash_has_successful_delivery_result"],
        bool,
    )
    assert isinstance(
        lifecycle_compatibility["current_hash_guard_would_block_grouped_variant"],
        bool,
    )
    assert isinstance(
        lifecycle_compatibility["current_hash_guard_would_allow_grouped_variant"],
        bool,
    )
    assert isinstance(
        lifecycle_compatibility["presentation_variant_duplicate_send_risk"],
        bool,
    )
    assert isinstance(
        lifecycle_compatibility["requires_guard_extension_before_grouped_send"],
        bool,
    )
    assert (
        lifecycle_compatibility[
            "grouped_hash_is_presentation_variant_not_delivered_content"
        ]
        is True
    )

    _assert_has_required_fields(
        canonical_hash_guard_evaluation,
        CANONICAL_HASH_GUARD_REQUIRED_FIELDS,
    )
    assert canonical_hash_guard_evaluation["status"] == (
        "presentation_variant_duplicate_guard_evaluation"
    )
    for key in (
        "available",
        "current_hash_available",
        "linked_canonical_hash_available",
        "canonical_hash_distinct_from_current",
        "current_hash_has_successful_delivery",
        "linked_canonical_hash_has_successful_delivery",
        "blocked_by_canonical_success",
        "current_duplicate_success_guard_would_block",
        "canonical_hash_guard_extension_would_block",
    ):
        assert isinstance(canonical_hash_guard_evaluation[key], bool)
    _assert_optional_string(canonical_hash_guard_evaluation["blocker_code"])
    _assert_optional_string(canonical_hash_guard_evaluation["recommended_action"])
    _assert_optional_string(canonical_hash_guard_evaluation["conservative_reason"])
    assert canonical_hash_guard_evaluation["enforced"] is False
    assert canonical_hash_guard_evaluation["semantic_duplicate_claimed"] is False
    assert canonical_hash_guard_evaluation["read_only"] is True

    _assert_has_required_fields(
        operator_review_summary,
        OPERATOR_REVIEW_SUMMARY_REQUIRED_FIELDS,
    )
    assert operator_review_summary["decision"] in OPERATOR_REVIEW_DECISIONS
    _assert_optional_string(operator_review_summary["blocker_code"])
    assert isinstance(operator_review_summary["recommended_action"], str)
    assert operator_review_summary["recommended_action"]
    assert isinstance(operator_review_summary["requires_human_review"], bool)
    assert isinstance(operator_review_summary["reason_codes"], list)
    assert operator_review_summary["reason_codes"]
    assert all(
        isinstance(reason_code, str) and reason_code
        for reason_code in operator_review_summary["reason_codes"]
    )
    _assert_operator_summary_is_safe(operator_review_summary)

    assert safety["read_only"] is True
    assert safety["db_write_scope"] == "none"
    assert safety["canonical_hash_guard_enforced"] is False
    assert safety["operator_review_summary_enforced"] is False
    assert safety["semantic_duplicate_claimed"] is False
    assert safety["telegram_invoked"] is False
    assert safety["scheduler_invoked"] is False

    _assert_safe_output(_serialized(report))
    _assert_safe_output(compat_script.format_text_report(report))


def test_missing_required_args_fail_safely() -> None:
    missing_start = _run_script("--end-at", "2149-01-02T00:00:00+00:00")
    missing_end = _run_script("--start-at", "2149-01-01T00:00:00+00:00")

    assert missing_start.returncode == 2
    assert "--start-at" in missing_start.stderr
    assert missing_end.returncode == 2
    assert "--end-at" in missing_end.stderr


def test_invalid_inputs_fail_before_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden_report(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid input must fail before DB execution")

    monkeypatch.setattr(
        compat_script,
        "build_no_marker_grouped_lifecycle_compatibility_report",
        forbidden_report,
    )

    base = [
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--end-at",
        "2149-01-02T00:00:00+00:00",
        "--format",
        "json",
    ]
    assert (
        compat_script.main(
            ["--start-at", "2149-01-01T00:00:00", "--end-at", "2149-01-02T00:00:00+00:00"]
        )
        == 2
    )
    assert (
        compat_script.main(
            [
                "--start-at",
                "2149-01-02T00:00:00+00:00",
                "--end-at",
                "2149-01-01T00:00:00+00:00",
            ]
        )
        == 2
    )
    assert compat_script.main([*base, "--limit", "0"]) == 2
    assert compat_script.main([*base, "--limit", "999"]) == 2
    assert compat_script.main([*base, "--cluster-threshold", "1"]) == 2
    assert compat_script.main([*base, "--cluster-threshold", "51"]) == 2
    assert compat_script.main([*base, "--group-by", "rendered_shape"]) == 2
    assert (
        compat_script.main([*base, "--activity-start-at", "2149-01-01T00:00:00+00:00"])
        == 2
    )
    assert (
        compat_script.main(
            [
                *base,
                "--activity-start-at",
                "2149-01-02T00:00:00+00:00",
                "--activity-end-at",
                "2149-01-01T00:00:00+00:00",
            ]
        )
        == 2
    )


def test_cli_rejects_credential_send_mutation_and_marker_filter_args() -> None:
    for forbidden_arg in (
        "--marker-filter",
        "--bot-token",
        "--chat-id",
        "--target-channel",
        "--production-mode",
        "--confirm-send",
        "--confirm-prepare",
        "--confirm-local-seed",
        "--confirm-create-intention",
        "--confirm-normalize",
        "--confirm-triage",
        "--execution-attempt-id",
        "--max-chunks",
        "--api-key",
        "--provider-credential",
    ):
        result = _run_script(
            "--start-at",
            "2149-01-01T00:00:00+00:00",
            "--end-at",
            "2149-01-02T00:00:00+00:00",
            forbidden_arg,
            "value",
        )
        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr


async def test_empty_window_reports_no_visible_candidate() -> None:
    await _ensure_tables()
    before_audit = await _audit_log_count()

    report = await _build(_query(start_at=_utc(2199, 2, 1), end_at=_utc(2199, 2, 2)))

    assert report["status"] == "no_marker_grouped_lifecycle_compatibility"
    assert report["marker_filter"] == "no_marker_only"
    assert report["group_by"] == "source_object"
    assert report["candidate"]["visible"] == 0
    compat = report["lifecycle_compatibility"]
    assert compat["grouped_variant_would_be_treated_as"] == "no_visible_candidate"
    assert compat["presentation_variant_duplicate_send_risk"] is False
    assert report["recommended_next_action"] == (
        "choose_window_with_no_marker_visible_candidates"
    )
    summary = report["operator_review_summary"]
    assert summary["decision"] == "manual_review_needed"
    assert summary["blocker_code"] is None
    assert summary["recommended_action"] == (
        "choose_window_with_no_marker_visible_candidates"
    )
    assert summary["requires_human_review"] is True
    assert "no_visible_candidate" in summary["reason_codes"]
    _assert_operator_summary_is_safe(summary)
    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_audit
    _assert_grouped_lifecycle_report_contract(report)
    _assert_safe_output(_serialized(report))
    _assert_safe_output(compat_script.format_text_report(report))


async def test_already_sent_canonical_flags_presentation_variant_risk() -> None:
    await _ensure_tables()
    unique = f"compat_sent_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 1, 9))
        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=_utc(2149, 9, 1),
                end_at=_utc(2149, 9, 2),
                limit_per_section=20,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
        await _persist_successful_draft_for_digest(
            unique,
            digest=digest,
            start_at=_utc(2149, 9, 1),
            end_at=_utc(2149, 9, 2),
        )
        before_audit = await _audit_log_count()

        report = await _build(_query(start_at=_utc(2149, 9, 1), end_at=_utc(2149, 9, 2)))

        compat = report["lifecycle_compatibility"]
        assert compat["canonical_matching_hash_has_successful_delivery_result"] is True
        assert compat["grouped_preview_hash_differs_from_canonical"] is True
        assert compat["grouped_hash_has_successful_delivery_result"] is False
        assert compat["presentation_variant_duplicate_send_risk"] is True
        assert compat["grouped_variant_would_be_treated_as"] == (
            "new_unsent_presentation_variant"
        )
        assert compat["current_hash_guard_would_allow_grouped_variant"] is True
        assert compat["current_hash_guard_would_block_grouped_variant"] is False
        assert compat["requires_guard_extension_before_grouped_send"] is True
        assert report["recommended_next_action"] == (
            "do_not_send_grouped_variant_of_already_sent_canonical"
        )
        guard = report["canonical_hash_guard_evaluation"]
        assert guard["current_hash_has_successful_delivery"] is False
        assert guard["linked_canonical_hash_has_successful_delivery"] is True
        assert guard["blocked_by_canonical_success"] is True
        assert guard["current_duplicate_success_guard_would_block"] is False
        assert guard["canonical_hash_guard_extension_would_block"] is True
        assert (
            guard["blocker_code"]
            == "presentation_variant_canonical_hash_already_successfully_sent"
        )
        assert guard["enforced"] is False
        assert guard["semantic_duplicate_claimed"] is False
        summary = report["operator_review_summary"]
        assert summary["decision"] == "blocked_by_linked_canonical_hash"
        assert (
            summary["blocker_code"]
            == "presentation_variant_canonical_hash_already_successfully_sent"
        )
        assert summary["recommended_action"] == (
            "do_not_send_presentation_variant_of_successful_canonical_digest"
        )
        assert summary["requires_human_review"] is False
        assert (
            "linked_canonical_hash_has_successful_delivery"
            in summary["reason_codes"]
        )
        assert "presentation_variant_duplicate_send_risk" in summary["reason_codes"]
        assert "explicit_canonical_presentation_hash_link" in summary["reason_codes"]
        _assert_operator_summary_is_safe(summary)
        assert "canonical_hash_guard_evaluator_would_block_grouped_variant" in report[
            "warnings"
        ]
        # report did not write anything
        assert await _audit_log_count() == before_audit
        _assert_grouped_lifecycle_report_contract(report)
        _assert_safe_output(_serialized(report))
        _assert_safe_output(compat_script.format_text_report(report))
    finally:
        await _cleanup(unique)


async def test_unsent_canonical_has_no_presentation_variant_risk() -> None:
    await _ensure_tables()
    unique = f"compat_unsent_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 3, 9))

        report = await _build(_query(start_at=_utc(2149, 9, 3), end_at=_utc(2149, 9, 4)))

        compat = report["lifecycle_compatibility"]
        assert compat["canonical_matching_hash_has_successful_delivery_result"] is False
        assert compat["presentation_variant_duplicate_send_risk"] is False
        assert compat["requires_guard_extension_before_grouped_send"] is False
        guard = report["canonical_hash_guard_evaluation"]
        assert guard["linked_canonical_hash_has_successful_delivery"] is False
        assert guard["blocked_by_canonical_success"] is False
        assert guard["blocker_code"] is None
        assert guard["recommended_action"] == "continue_manual_pilot_flow"
        assert guard["enforced"] is False
        assert guard["semantic_duplicate_claimed"] is False
        assert report["recommended_next_action"] == (
            "continue_no_marker_manual_pilot_review"
        )
        summary = report["operator_review_summary"]
        assert summary["decision"] == "not_blocked"
        assert summary["blocker_code"] is None
        assert summary["recommended_action"] == "continue_manual_pilot_flow"
        assert summary["requires_human_review"] is False
        assert (
            "no_current_or_linked_canonical_successful_delivery"
            in summary["reason_codes"]
        )
        assert "explicit_canonical_presentation_hash_link" in summary["reason_codes"]
        _assert_operator_summary_is_safe(summary)
        _assert_grouped_lifecycle_report_contract(report)
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_grouped_hash_matching_successful_delivery_is_already_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    unique = f"compat_match_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 5, 9))

        grouped_hash = await _grouped_preview_hash(
            start_at=_utc(2149, 9, 5),
            end_at=_utc(2149, 9, 6),
        )

        async def fake_facts(*_args: object, **_kwargs: object) -> list[dict]:
            return [{"text_sha256": grouped_hash, "has_successful_delivery": True}]

        monkeypatch.setattr(compat_script, "_load_window_draft_hash_facts", fake_facts)

        report = await _build(_query(start_at=_utc(2149, 9, 5), end_at=_utc(2149, 9, 6)))

        compat = report["lifecycle_compatibility"]
        assert compat["grouped_hash_matches_existing_draft"] is True
        assert compat["grouped_hash_has_successful_delivery_result"] is True
        assert compat["grouped_variant_would_be_treated_as"] == "already_sent"
        assert compat["current_hash_guard_would_block_grouped_variant"] is True
        assert compat["current_hash_guard_would_allow_grouped_variant"] is False
        assert compat["presentation_variant_duplicate_send_risk"] is False
        guard = report["canonical_hash_guard_evaluation"]
        assert guard["current_hash_has_successful_delivery"] is False
        assert guard["linked_canonical_hash_has_successful_delivery"] is False
        assert guard["blocked_by_canonical_success"] is False
        assert guard["blocker_code"] is None
        summary = report["operator_review_summary"]
        assert summary["decision"] == "already_sent_by_current_hash"
        assert summary["blocker_code"] == "delivery_draft_already_successfully_sent"
        assert summary["recommended_action"] == "do_not_resend_grouped_presentation"
        assert summary["requires_human_review"] is False
        assert (
            "current_grouped_hash_has_successful_delivery"
            in summary["reason_codes"]
        )
        _assert_operator_summary_is_safe(summary)
        _assert_grouped_lifecycle_report_contract(report)
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_current_grouped_hash_success_takes_precedence_in_guard_evaluation() -> None:
    await _ensure_tables()
    unique = f"compat_guard_current_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 11, 9))
        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=_utc(2149, 9, 11),
                end_at=_utc(2149, 9, 12),
                limit_per_section=20,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
        canonical_draft = await _persist_successful_draft_for_digest(
            unique,
            digest=digest,
            start_at=_utc(2149, 9, 11),
            end_at=_utc(2149, 9, 12),
        )
        grouped_hash = await _grouped_preview_hash(
            start_at=_utc(2149, 9, 11),
            end_at=_utc(2149, 9, 12),
        )
        assert grouped_hash != canonical_draft["text_sha256"]
        await _insert_successful_hash_lifecycle(
            unique,
            text_sha256=grouped_hash,
            start_at=_utc(2149, 9, 11),
            end_at=_utc(2149, 9, 12),
        )
        before_audit = await _audit_log_count()

        report = await _build(_query(start_at=_utc(2149, 9, 11), end_at=_utc(2149, 9, 12)))

        compat = report["lifecycle_compatibility"]
        assert compat["grouped_hash_has_successful_delivery_result"] is True
        assert compat["current_hash_guard_would_block_grouped_variant"] is True
        assert compat["presentation_variant_duplicate_send_risk"] is False
        guard = report["canonical_hash_guard_evaluation"]
        assert guard["current_hash_has_successful_delivery"] is True
        assert guard["linked_canonical_hash_has_successful_delivery"] is True
        assert guard["blocked_by_canonical_success"] is False
        assert guard["current_duplicate_success_guard_would_block"] is True
        assert guard["canonical_hash_guard_extension_would_block"] is False
        assert guard["blocker_code"] == "delivery_draft_already_successfully_sent"
        assert guard["enforced"] is False
        assert guard["semantic_duplicate_claimed"] is False
        summary = report["operator_review_summary"]
        assert summary["decision"] == "already_sent_by_current_hash"
        assert summary["blocker_code"] == "delivery_draft_already_successfully_sent"
        assert summary["requires_human_review"] is False
        assert (
            "current_grouped_hash_has_successful_delivery"
            in summary["reason_codes"]
        )
        assert "explicit_canonical_presentation_hash_link" in summary["reason_codes"]
        assert "linked_canonical_hash_has_successful_delivery" not in summary[
            "reason_codes"
        ]
        _assert_operator_summary_is_safe(summary)
        assert await _audit_log_count() == before_audit
        _assert_grouped_lifecycle_report_contract(report)
        _assert_safe_output(_serialized(report))
        _assert_safe_output(compat_script.format_text_report(report))
    finally:
        await _cleanup(unique)


async def test_missing_canonical_hash_is_conservative_in_guard_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    grouped_hash = "a" * 64

    async def fake_grouped_report(*_args: object, **_kwargs: object) -> dict:
        return _fake_grouped_report(
            candidate_hash=None,
            grouped_hash=grouped_hash,
        )

    monkeypatch.setattr(
        grouped_preview_script,
        "build_no_marker_persisted_attention_grouped_preview_report",
        fake_grouped_report,
    )

    report = await _build(_query(start_at=_utc(2149, 9, 13), end_at=_utc(2149, 9, 14)))

    guard = report["canonical_hash_guard_evaluation"]
    assert guard["available"] is False
    assert guard["current_hash_available"] is True
    assert guard["linked_canonical_hash_available"] is False
    assert guard["blocked_by_canonical_success"] is False
    assert guard["blocker_code"] is None
    assert guard["conservative_reason"] == "missing_linked_canonical_hash"
    assert guard["enforced"] is False
    assert guard["semantic_duplicate_claimed"] is False
    summary = report["operator_review_summary"]
    assert summary["decision"] == "manual_review_needed"
    assert summary["blocker_code"] is None
    assert summary["recommended_action"] == "manual_review_required_before_grouped_send"
    assert summary["requires_human_review"] is True
    assert "missing_linked_canonical_hash" in summary["reason_codes"]
    _assert_operator_summary_is_safe(summary)
    _assert_grouped_lifecycle_report_contract(report)
    _assert_safe_output(_serialized(report))
    _assert_safe_output(compat_script.format_text_report(report))


async def test_equal_canonical_and_grouped_hash_is_not_variant_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    same_hash = "b" * 64

    async def fake_grouped_report(*_args: object, **_kwargs: object) -> dict:
        return _fake_grouped_report(
            candidate_hash=same_hash,
            grouped_hash=same_hash,
        )

    monkeypatch.setattr(
        grouped_preview_script,
        "build_no_marker_persisted_attention_grouped_preview_report",
        fake_grouped_report,
    )

    report = await _build(_query(start_at=_utc(2149, 9, 15), end_at=_utc(2149, 9, 16)))

    guard = report["canonical_hash_guard_evaluation"]
    assert guard["available"] is False
    assert guard["current_hash_available"] is True
    assert guard["linked_canonical_hash_available"] is True
    assert guard["canonical_hash_distinct_from_current"] is False
    assert guard["blocked_by_canonical_success"] is False
    assert guard["blocker_code"] is None
    assert guard["conservative_reason"] == "canonical_hash_matches_current_hash"
    assert guard["enforced"] is False
    assert guard["semantic_duplicate_claimed"] is False
    summary = report["operator_review_summary"]
    assert summary["decision"] == "manual_review_needed"
    assert summary["blocker_code"] is None
    assert summary["recommended_action"] == "manual_review_required_before_grouped_send"
    assert summary["requires_human_review"] is True
    assert "canonical_hash_matches_current_hash" in summary["reason_codes"]
    _assert_operator_summary_is_safe(summary)
    _assert_grouped_lifecycle_report_contract(report)
    _assert_safe_output(_serialized(report))


async def test_invalid_grouped_hash_is_conservative_in_guard_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()

    async def fake_grouped_report(*_args: object, **_kwargs: object) -> dict:
        return _fake_grouped_report(
            candidate_hash="c" * 64,
            grouped_hash="not-a-sha256",
        )

    monkeypatch.setattr(
        grouped_preview_script,
        "build_no_marker_persisted_attention_grouped_preview_report",
        fake_grouped_report,
    )

    report = await _build(_query(start_at=_utc(2149, 9, 17), end_at=_utc(2149, 9, 18)))

    guard = report["canonical_hash_guard_evaluation"]
    assert guard["available"] is False
    assert guard["blocked_by_canonical_success"] is False
    assert guard["blocker_code"] is None
    assert guard["conservative_reason"] == "invalid_explicit_hash_link"
    assert guard["enforced"] is False
    assert guard["semantic_duplicate_claimed"] is False
    summary = report["operator_review_summary"]
    assert summary["decision"] == "manual_review_needed"
    assert summary["blocker_code"] is None
    assert summary["recommended_action"] == "manual_review_required_before_grouped_send"
    assert summary["requires_human_review"] is True
    assert "invalid_explicit_hash_link" in summary["reason_codes"]
    _assert_operator_summary_is_safe(summary)
    _assert_grouped_lifecycle_report_contract(report)
    _assert_safe_output(_serialized(report))


async def test_hashes_returned_without_rendering_text() -> None:
    await _ensure_tables()
    unique = f"compat_hashes_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 7, 9))

        report = await _build(_query(start_at=_utc(2149, 9, 7), end_at=_utc(2149, 9, 8)))

        compat = report["lifecycle_compatibility"]
        assert isinstance(compat["canonical_candidate_text_sha256"], str)
        assert isinstance(compat["grouped_preview_text_sha256"], str)
        assert (
            compat["canonical_candidate_text_sha256"]
            == report["candidate"]["text_sha256"]
        )
        assert compat["grouped_hash_is_presentation_variant_not_delivered_content"] is True

        serialized = _serialized(report)
        assert "grouped_preview_text" not in serialized.replace(
            "grouped_preview_text_sha256", ""
        ).replace("grouped_preview_text_included", "")
        assert report["safety"]["grouped_preview_text_included"] is False
        assert report["safety"]["grouped_preview_chunk_text_included"] is False
        assert report["safety"]["source_object_ids_exposed"] is False
        assert report["safety"]["raw_fingerprints_exposed"] is False
        assert report["safety"]["telegram_invoked"] is False
        assert report["safety"]["openai_invoked"] is False
        assert report["safety"]["live_api_calls"] is False
        assert report["safety"]["canonical_hash_guard_evaluator_invoked"] is True
        assert report["safety"]["canonical_hash_guard_enforced"] is False
        assert report["safety"]["operator_review_summary_included"] is True
        assert report["safety"]["operator_review_summary_enforced"] is False
        assert report["safety"]["semantic_duplicate_claimed"] is False
        assert report["canonical_hash_guard_evaluation"]["enforced"] is False
        assert (
            report["canonical_hash_guard_evaluation"]["semantic_duplicate_claimed"]
            is False
        )
        _assert_operator_summary_is_safe(report["operator_review_summary"])
        _assert_grouped_lifecycle_report_contract(report)
        _assert_safe_output(serialized)
        _assert_safe_output(compat_script.format_text_report(report))
    finally:
        await _cleanup(unique)


async def test_report_stays_read_only_with_test_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    unique = f"compat_read_only_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 9, 9))

        class ReadOnlySession:
            def __init__(self) -> None:
                self._session_cm = AsyncSessionLocal()
                self.session: object | None = None

            async def __aenter__(self) -> object:
                self.session = await self._session_cm.__aenter__()
                for method_name in ("add", "flush", "commit", "delete"):
                    monkeypatch.setattr(
                        self.session,
                        method_name,
                        self._forbidden_write,
                    )
                return self.session

            async def __aexit__(self, *exc_info: object) -> object:
                return await self._session_cm.__aexit__(*exc_info)

            async def _forbidden_write(self, *_args: object, **_kwargs: object) -> None:
                raise AssertionError("grouped lifecycle compatibility must stay read-only")

        def session_factory() -> ReadOnlySession:
            return ReadOnlySession()

        report = (
            await compat_script.build_no_marker_grouped_lifecycle_compatibility_report(
                _query(start_at=_utc(2149, 9, 9), end_at=_utc(2149, 9, 10)),
                session_factory=session_factory,
                settings_override=_local_settings(),
                environ={},
            )
        )

        assert report["safety"]["db_write_scope"] == "none"
        _assert_grouped_lifecycle_report_contract(report)
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


def test_json_output_is_stable_and_sanitized() -> None:
    result = _run_script(
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--end-at",
        "2149-01-02T00:00:00+00:00",
    )

    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["status"] == "no_marker_grouped_lifecycle_compatibility"
    assert parsed["marker_filter"] == "no_marker_only"
    assert parsed["group_by"] == "source_object"
    assert parsed["safety"]["read_only"] is True
    assert parsed["operator_review_summary"]["enforced"] is False
    assert parsed["operator_review_summary"]["semantic_duplicate_claimed"] is False
    _assert_grouped_lifecycle_report_contract(parsed)
    _assert_safe_output(result.stdout)
