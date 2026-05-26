from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.attention_models import (
    AttentionTriageFeedbackRecord,
    AttentionTriageResultRecord,
)
from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import AuditLog, IngestedEvent
from app.services.digest import (
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
    build_persisted_attention_digest_read_model,
)
from app.services.digest_delivery_drafts import (
    approve_digest_delivery_draft,
    build_persisted_attention_digest_delivery_draft,
    create_digest_delivery_intention,
    persist_digest_delivery_draft,
    record_digest_delivery_result,
    sanitize_persisted_attention_digest_for_delivery_draft,
)
from app.services.digest_rendering import render_persisted_attention_digest_text
from scripts import list_persisted_attention_digest_windows as discovery_script
from scripts import report_no_marker_persisted_attention_candidates as no_marker_script

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "report_no_marker_persisted_attention_candidates.py"


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _local_settings() -> SimpleNamespace:
    return SimpleNamespace(app_env="local")


def _serialized(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _assert_safe_output(output: str) -> None:
    forbidden = (
        "rendered_text",
        '"text":',
        "stored digest text value",
        "chunk text",
        "bot_token",
        "chat_id",
        "api_key",
        "webhook",
        "raw_response",
        "raw_payload",
        "provider_payload",
        "source_payload",
        "raw_object_ref",
        "source_url",
        "prompt",
        "source body",
        "PRIVATE_RAW_BODY_DO_NOT_EXPOSE",
        "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
        "Private no-marker title",
        "Private no-marker summary",
        "Private no-marker action",
        "Private No-Marker Actor",
        "private-no-marker@example.com",
        "private-no-marker.pdf",
        "PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE",
        "nact_fos086_",
        "sevt_fos086_",
        "atri_fos086_",
        '"evidence_refs": [',
    )
    folded = output.casefold()
    for marker in forbidden:
        assert marker.casefold() not in folded


def _query(
    *,
    start_at: datetime,
    end_at: datetime,
    activity_start_at: datetime | None = None,
    activity_end_at: datetime | None = None,
    limit: int = 20,
) -> no_marker_script.NoMarkerCandidateQuery:
    return no_marker_script.NoMarkerCandidateQuery(
        start_at=start_at,
        end_at=end_at,
        activity_start_at=activity_start_at,
        activity_end_at=activity_end_at,
        limit=limit,
        debug_evidence=False,
        output_format="json",
    )


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(IngestedEvent.__table__.create, checkfirst=True)
        await conn.run_sync(SourceEvent.__table__.create, checkfirst=True)
        await conn.run_sync(
            NormalizedActivityItemRecord.__table__.create,
            checkfirst=True,
        )
        await conn.run_sync(
            AttentionTriageResultRecord.__table__.create,
            checkfirst=True,
        )
        await conn.run_sync(
            AttentionTriageFeedbackRecord.__table__.create,
            checkfirst=True,
        )
        await conn.run_sync(AuditLog.__table__.create, checkfirst=True)


async def _audit_log_count() -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(select(func.count()).select_from(AuditLog)) or 0
        )


async def _cleanup(unique: str) -> None:
    actor = f"test_fos086_{unique}"
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AuditLog).where(AuditLog.actor == actor))
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.triage_result_id.like(
                    f"atri_fos086_{unique}%"
                )
            )
        )
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.activity_item_id.like(
                    f"nact_fos086_{unique}%"
                )
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(
                    f"nact_fos086_{unique}%"
                )
            )
        )
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_event_id.like(f"sevt_fos086_{unique}%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.event_id.like(f"evt_fos086_{unique}%")
            )
        )
        await session.commit()


async def _insert_source_event(unique: str, *, created_at: datetime) -> str:
    source_event_id = f"sevt_fos086_{unique}"
    async with AsyncSessionLocal() as session:
        session.add(
            IngestedEvent(
                event_id=f"evt_fos086_{unique}",
                event_type="github.pull_request.opened",
                source_system="github",
                source_object_id=f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}",
                idempotency_key=f"idem_fos086_{unique}",
                correlation_id=f"corr_fos086_{unique}",
                trace_id=f"trace_fos086_{unique}",
                raw_object_ref="raw://PRIVATE_RAW_BODY_DO_NOT_EXPOSE",
                payload={"body": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE"},
                status="received",
                created_at=created_at,
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=source_event_id,
                source_event_key=f"source-key-fos086-{unique}",
                ingested_event_id=f"evt_fos086_{unique}",
                event_type="github.pull_request.opened",
                source_system="github",
                source_object_type="pull_request",
                source_object_id=f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}",
                source_event_ts=created_at,
                actor_external_id="Private No-Marker Actor",
                title="Private no-marker title must not print",
                summary="Private no-marker summary must not print",
                source_url="https://example.invalid/private",
                raw_object_ref="raw://PRIVATE_RAW_BODY_DO_NOT_EXPOSE",
                evidence_refs=[],
                metadata_json={},
                created_at=created_at,
            )
        )
        await session.commit()
    return source_event_id


async def _insert_normalized_activity(
    unique: str,
    *,
    created_at: datetime,
    source_event_id: str | None = None,
    synthetic: bool = False,
) -> str:
    activity_item_id = f"nact_fos086_{unique}"
    if synthetic:
        source = "internal"
        source_object_id = (
            f"{discovery_script.SYNTHETIC_SOURCE_OBJECT_PREFIX}{unique}:safe"
        )
        activity_type = "synthetic.persisted_attention_digest.seed"
    else:
        source = "github"
        source_object_id = f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}"
        activity_type = "pull_request.updated"

    async with AsyncSessionLocal() as session:
        session.add(
            NormalizedActivityItemRecord(
                activity_item_id=activity_item_id,
                source_event_id=source_event_id,
                source=source,
                source_object_id=source_object_id,
                activity_type=activity_type,
                title="Private no-marker title must not print",
                actor="Private No-Marker Actor",
                activity_created_at=created_at,
                project="Private Project",
                safe_summary="Private no-marker summary must not print",
                related_people=[
                    "Private No-Marker Actor",
                    "private-no-marker@example.com",
                ],
                related_jira_keys=["FOS-086"],
                related_prs=["private-pr"],
                related_files=["private-no-marker.pdf"],
                evidence_refs=[],
                created_at=created_at,
            )
        )
        await session.commit()
    return activity_item_id


async def _insert_attention_result(
    unique: str,
    *,
    created_at: datetime,
    activity_item_id: str | None = None,
    synthetic: bool = False,
    attention_class: str = "review_optional",
    priority: str = "low",
    visible: bool = True,
) -> None:
    if synthetic:
        source = "internal"
        source_object_id = (
            f"{discovery_script.SYNTHETIC_SOURCE_OBJECT_PREFIX}{unique}:safe"
        )
        attention_class = "requires_my_attention"
        priority = "high"
    else:
        source = "github"
        source_object_id = f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}"

    async with AsyncSessionLocal() as session:
        session.add(
            AttentionTriageResultRecord(
                triage_result_id=f"atri_fos086_{unique}",
                source=source,
                source_object_id=source_object_id,
                activity_item_id=activity_item_id,
                attention_class=attention_class,
                priority=priority,
                show_in_digest=visible,
                confidence=0.9,
                reason="Private no-marker reason must not print",
                recommended_action="Private no-marker action must not print",
                owner=None,
                deadline=None,
                evidence_refs=[],
                created_at=created_at,
            )
        )
        await session.commit()


async def _persist_successful_draft_for_digest(
    unique: str,
    *,
    digest: dict,
    start_at: datetime,
    end_at: datetime,
    rendered_text_override: str | None = None,
) -> dict:
    actor = f"test_fos086_{unique}"
    safe_digest = sanitize_persisted_attention_digest_for_delivery_draft(
        digest,
        debug_evidence=False,
    )
    rendered_text = rendered_text_override or render_persisted_attention_digest_text(
        safe_digest,
        debug_evidence=False,
    )
    draft = build_persisted_attention_digest_delivery_draft(
        digest=safe_digest,
        rendered_text=rendered_text,
        start_at=start_at,
        end_at=end_at,
        limit=20,
        debug_evidence=False,
    )
    async with AsyncSessionLocal() as session:
        persisted = await persist_digest_delivery_draft(
            session,
            draft=draft,
            actor=actor,
        )
        await approve_digest_delivery_draft(
            session,
            delivery_draft_id=str(persisted["delivery_draft_id"]),
            reviewer=actor,
        )
        intention = await create_digest_delivery_intention(
            session,
            delivery_draft_id=str(persisted["delivery_draft_id"]),
            actor=actor,
        )
        await record_digest_delivery_result(
            session,
            delivery_intention_id=str(intention["delivery_intention_id"]),
            execution_attempt_id=f"attempt-{unique}",
            result_status="succeeded",
            attempted_chunk_count=int(persisted["chunk_count"]),
            delivered_chunk_count=int(persisted["chunk_count"]),
            failed_chunk_count=0,
            safe_message_refs=[],
            delivery_invoked=False,
            delivery_adapter_invoked=False,
            actor=actor,
        )
        await session.commit()
    return persisted


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
        no_marker_script,
        "build_no_marker_persisted_attention_candidate_report",
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
        no_marker_script.main(
            [
                "--start-at",
                "2149-01-01T00:00:00",
                "--end-at",
                "2149-01-02T00:00:00+00:00",
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert (
        no_marker_script.main(
            [
                "--start-at",
                "2149-01-02T00:00:00+00:00",
                "--end-at",
                "2149-01-01T00:00:00+00:00",
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert no_marker_script.main([*base, "--limit", "0"]) == 2
    assert (
        no_marker_script.main(
            [*base, "--activity-start-at", "2149-01-01T00:00:00+00:00"]
        )
        == 2
    )
    assert (
        no_marker_script.main(
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


def test_cli_rejects_credential_send_and_mutation_arguments() -> None:
    for forbidden_arg in (
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


async def test_empty_digest_window_reports_no_candidates() -> None:
    await _ensure_tables()
    before_audit = await _audit_log_count()
    report = await no_marker_script.build_no_marker_persisted_attention_candidate_report(
        _query(start_at=_utc(2199, 1, 1), end_at=_utc(2199, 1, 2)),
        settings_override=_local_settings(),
        environ={},
    )

    assert report["no_marker_candidate"]["total"] == 0
    assert report["no_marker_candidate"]["visible"] == 0
    assert report["marker_summary"]["synthetic_status"] == "unknown"
    assert report["recommended_next_action"] == (
        "choose_window_with_no_marker_visible_candidates"
    )
    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_audit
    _assert_safe_output(_serialized(report))
    _assert_safe_output(no_marker_script.format_text_report(report))


async def test_marker_windows_report_no_marker_candidate_counts_and_exclusions() -> None:
    await _ensure_tables()
    synthetic_unique = f"synthetic_{uuid4().hex}"
    no_marker_unique = f"nomarker_{uuid4().hex}"
    mixed_synthetic_unique = f"mixedsynthetic_{uuid4().hex}"
    mixed_no_marker_unique = f"mixednomarker_{uuid4().hex}"
    for unique in (
        synthetic_unique,
        no_marker_unique,
        mixed_synthetic_unique,
        mixed_no_marker_unique,
    ):
        await _cleanup(unique)
    try:
        await _insert_attention_result(
            synthetic_unique,
            created_at=_utc(2149, 2, 1, 9),
            synthetic=True,
        )
        await _insert_attention_result(
            no_marker_unique,
            created_at=_utc(2149, 2, 2, 9),
        )
        await _insert_attention_result(
            mixed_synthetic_unique,
            created_at=_utc(2149, 2, 3, 9),
            synthetic=True,
        )
        await _insert_attention_result(
            mixed_no_marker_unique,
            created_at=_utc(2149, 2, 3, 10),
        )

        synthetic_report = await no_marker_script.build_no_marker_persisted_attention_candidate_report(
            _query(start_at=_utc(2149, 2, 1), end_at=_utc(2149, 2, 2)),
            settings_override=_local_settings(),
            environ={},
        )
        no_marker_report = await no_marker_script.build_no_marker_persisted_attention_candidate_report(
            _query(start_at=_utc(2149, 2, 2), end_at=_utc(2149, 2, 3)),
            settings_override=_local_settings(),
            environ={},
        )
        mixed_report = await no_marker_script.build_no_marker_persisted_attention_candidate_report(
            _query(start_at=_utc(2149, 2, 3), end_at=_utc(2149, 2, 4)),
            settings_override=_local_settings(),
            environ={},
        )

        assert synthetic_report["no_marker_candidate"]["visible"] == 0
        assert synthetic_report["excluded_markers"]["synthetic_marker_count"] == 1
        assert synthetic_report["marker_summary"]["synthetic_status"] == (
            "synthetic_local_dev_detected"
        )
        assert no_marker_report["no_marker_candidate"]["visible"] == 1
        assert no_marker_report["marker_summary"]["synthetic_status"] == (
            "no_synthetic_marker_detected"
        )
        assert no_marker_report["marker_summary"]["no_marker_not_production_truth"] is True
        assert no_marker_report["no_marker_candidate"]["text_sha256"]
        assert no_marker_report["no_marker_candidate"]["chunk_count"] >= 1
        assert mixed_report["marker_summary"]["synthetic_status"] == "mixed"
        assert mixed_report["marker_summary"]["mixed_source_window"] is True
        assert mixed_report["excluded_markers"]["synthetic_marker_count"] == 1
        assert mixed_report["no_marker_candidate"]["total"] == 1
        assert mixed_report["no_marker_candidate"]["by_source"] == {"github": 1}
        assert "mixed_synthetic_and_no_marker_attention_results" in mixed_report["warnings"]
        _assert_safe_output(_serialized(mixed_report))
        _assert_safe_output(no_marker_script.format_text_report(mixed_report))
    finally:
        for unique in (
            synthetic_unique,
            no_marker_unique,
            mixed_synthetic_unique,
            mixed_no_marker_unique,
        ):
            await _cleanup(unique)


async def test_timestamp_mismatch_is_counted_for_no_marker_candidate() -> None:
    await _ensure_tables()
    unique = f"mismatch_{uuid4().hex}"
    await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            unique,
            created_at=_utc(2149, 3, 1, 9),
        )
        activity_item_id = await _insert_normalized_activity(
            unique,
            created_at=_utc(2149, 3, 1, 9),
            source_event_id=source_event_id,
        )
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 3, 2, 9),
            activity_item_id=activity_item_id,
        )

        report = await no_marker_script.build_no_marker_persisted_attention_candidate_report(
            _query(
                start_at=_utc(2149, 3, 2),
                end_at=_utc(2149, 3, 3),
                activity_start_at=_utc(2149, 3, 1),
                activity_end_at=_utc(2149, 3, 2),
            ),
            settings_override=_local_settings(),
            environ={},
        )

        timestamp = report["timestamp_reconciliation"]
        assert timestamp["activity_window_supplied"] is True
        assert timestamp["no_marker_attention_results_in_persisted_window_count"] == 1
        assert (
            timestamp[
                "linked_no_marker_normalized_activity_in_activity_window_count"
            ]
            == 1
        )
        assert timestamp["linked_no_marker_source_events_in_activity_window_count"] == 1
        assert timestamp["no_marker_attention_results_linked_to_activity_window_count"] == 1
        assert (
            timestamp[
                "no_marker_attention_results_in_persisted_window_linked_to_activity_window_count"
            ]
            == 1
        )
        assert (
            timestamp[
                "no_marker_attention_results_write_time_outside_activity_window_count"
            ]
            == 1
        )
        assert (
            timestamp[
                "no_marker_normalized_items_in_activity_window_with_attention_result_count"
            ]
            == 1
        )
        assert timestamp["timestamp_mismatch_detected"] is True
        assert report["recommended_next_action"] == (
            "review_no_marker_timestamp_linkage_before_draft_prepare"
        )
        _assert_safe_output(_serialized(report))
        _assert_safe_output(no_marker_script.format_text_report(report))
    finally:
        await _cleanup(unique)


async def test_different_hash_success_does_not_mark_candidate_sent() -> None:
    await _ensure_tables()
    unique = f"different_hash_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 4, 1, 9),
        )
        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=_utc(2149, 4, 1),
                end_at=_utc(2149, 4, 2),
                limit_per_section=20,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
        different_hash_draft = await _persist_successful_draft_for_digest(
            unique,
            digest=digest,
            start_at=_utc(2149, 4, 1),
            end_at=_utc(2149, 4, 2),
            rendered_text_override=f"Different safe rendered body {unique}",
        )

        report = await no_marker_script.build_no_marker_persisted_attention_candidate_report(
            _query(
                start_at=_utc(2149, 4, 1),
                end_at=_utc(2149, 4, 2),
                activity_start_at=_utc(2149, 4, 1),
                activity_end_at=_utc(2149, 4, 2),
            ),
            settings_override=_local_settings(),
            environ={},
        )

        lifecycle = report["candidate_lifecycle_reconciliation"]
        assert lifecycle["associated_window_draft_count"] == 1
        assert lifecycle["candidate_has_matching_draft_hash"] is False
        assert lifecycle["matching_hash_has_successful_delivery_result"] is False
        assert lifecycle["any_window_successful_delivery_result"] is True
        assert lifecycle["prior_successful_delivery_for_different_digest_hash"] is True
        assert lifecycle["candidate_lifecycle_status"] == (
            "prior_successful_delivery_for_different_digest_hash"
        )
        assert different_hash_draft["text_sha256"] != lifecycle["candidate_text_sha256"]
        assert report["recommended_next_action"] == "prepare_no_marker_draft_after_review"
        assert "prior_successful_delivery_for_different_digest_hash" in report["warnings"]
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_matching_hash_success_marks_candidate_already_sent() -> None:
    await _ensure_tables()
    unique = f"matching_hash_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 5, 1, 9),
        )
        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=_utc(2149, 5, 1),
                end_at=_utc(2149, 5, 2),
                limit_per_section=20,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
        current_draft = await _persist_successful_draft_for_digest(
            unique,
            digest=digest,
            start_at=_utc(2149, 5, 1),
            end_at=_utc(2149, 5, 2),
        )

        report = await no_marker_script.build_no_marker_persisted_attention_candidate_report(
            _query(
                start_at=_utc(2149, 5, 1),
                end_at=_utc(2149, 5, 2),
                activity_start_at=_utc(2149, 5, 1),
                activity_end_at=_utc(2149, 5, 2),
            ),
            settings_override=_local_settings(),
            environ={},
        )

        lifecycle = report["candidate_lifecycle_reconciliation"]
        assert lifecycle["candidate_has_matching_draft_hash"] is True
        assert lifecycle["matching_hash_delivery_draft_ids"] == [
            current_draft["delivery_draft_id"]
        ]
        assert lifecycle["matching_hash_has_successful_delivery_result"] is True
        assert lifecycle["candidate_lifecycle_status"] == (
            "candidate_already_successfully_sent"
        )
        assert report["recommended_next_action"] == "do_not_resend_same_digest_content"
        assert "candidate_already_successfully_sent" in report["warnings"]
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)
