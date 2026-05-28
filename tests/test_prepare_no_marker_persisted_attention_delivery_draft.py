from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog
from app.services.digest import (
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
    build_persisted_attention_digest_read_model,
)
from app.services.digest_delivery_drafts import (
    DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
    DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
    DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE,
    DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
    DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
    get_persisted_digest_delivery_draft,
)
from scripts import prepare_no_marker_persisted_attention_delivery_draft as prepare_script
from tests import test_no_marker_persisted_attention_candidates as no_marker_fixtures

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT
    / "scripts"
    / "prepare_no_marker_persisted_attention_delivery_draft.py"
)


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


def _query(
    *,
    start_at,
    end_at,
    activity_start_at=None,
    activity_end_at=None,
    limit: int = 20,
) -> prepare_script.NoMarkerDraftPrepareQuery:
    return prepare_script.NoMarkerDraftPrepareQuery(
        start_at=start_at,
        end_at=end_at,
        activity_start_at=activity_start_at,
        activity_end_at=activity_end_at,
        limit=limit,
        debug_evidence=False,
        confirm_prepare=prepare_script.CONFIRM_PREPARE_PHRASE,
        output_format="json",
    )


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


async def _delivery_draft_record_count(delivery_draft_id: str | None = None) -> int:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(func.count(AuditLog.id))
            .select_from(AuditLog)
            .where(AuditLog.event_type == DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE)
        )
        if delivery_draft_id is not None:
            stmt = stmt.where(AuditLog.after_ref == delivery_draft_id)
        return int(await session.scalar(stmt) or 0)


async def _artifact_count_for_draft(delivery_draft_id: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count(AuditLog.id))
                .select_from(AuditLog)
                .where(
                    AuditLog.event_type.in_(
                        [
                            DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
                            DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE,
                            DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
                            DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
                        ]
                    )
                )
                .where(
                    (AuditLog.before_ref == delivery_draft_id)
                    | (AuditLog.after_ref == delivery_draft_id)
                )
            )
            or 0
        )


async def _cleanup_draft(delivery_draft_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AuditLog).where(AuditLog.after_ref == delivery_draft_id)
        )
        await session.execute(
            delete(AuditLog).where(AuditLog.before_ref == delivery_draft_id)
        )
        await session.commit()


async def _stored_draft(delivery_draft_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        draft = await get_persisted_digest_delivery_draft(
            session,
            delivery_draft_id=delivery_draft_id,
        )
    assert isinstance(draft, dict)
    return draft


def test_missing_required_args_fail_before_db_write() -> None:
    missing_start = _run_script(
        "--end-at",
        "2149-01-02T00:00:00+00:00",
        "--confirm-prepare",
        prepare_script.CONFIRM_PREPARE_PHRASE,
    )
    missing_end = _run_script(
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--confirm-prepare",
        prepare_script.CONFIRM_PREPARE_PHRASE,
    )
    missing_confirm = _run_script(
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--end-at",
        "2149-01-02T00:00:00+00:00",
    )

    assert missing_start.returncode == 2
    assert "--start-at" in missing_start.stderr
    assert missing_end.returncode == 2
    assert "--end-at" in missing_end.stderr
    assert missing_confirm.returncode == 2
    assert "--confirm-prepare" in missing_confirm.stderr
    _assert_safe_output(
        missing_start.stdout
        + missing_start.stderr
        + missing_end.stdout
        + missing_end.stderr
        + missing_confirm.stdout
        + missing_confirm.stderr
    )


def test_invalid_inputs_fail_before_prepare_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_prepare(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid input must fail before DB write")

    monkeypatch.setattr(
        prepare_script,
        "prepare_no_marker_persisted_attention_delivery_draft",
        forbidden_prepare,
    )
    base = [
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--end-at",
        "2149-01-02T00:00:00+00:00",
        "--confirm-prepare",
        prepare_script.CONFIRM_PREPARE_PHRASE,
        "--format",
        "json",
    ]

    assert (
        prepare_script.main(
            [
                "--start-at",
                "2149-01-01T00:00:00",
                "--end-at",
                "2149-01-02T00:00:00+00:00",
                "--confirm-prepare",
                prepare_script.CONFIRM_PREPARE_PHRASE,
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert (
        prepare_script.main(
            [
                "--start-at",
                "2149-01-02T00:00:00+00:00",
                "--end-at",
                "2149-01-01T00:00:00+00:00",
                "--confirm-prepare",
                prepare_script.CONFIRM_PREPARE_PHRASE,
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert prepare_script.main([*base, "--limit", "0"]) == 2
    assert prepare_script.main([*base, "--confirm-prepare", "SEND IT"]) == 2
    assert (
        prepare_script.main(
            [*base, "--activity-start-at", "2149-01-01T00:00:00+00:00"]
        )
        == 2
    )
    assert (
        prepare_script.main(
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


def test_cli_rejects_marker_filter_credentials_send_and_mutation_arguments() -> None:
    for forbidden_arg in (
        "--marker-filter",
        "--bot-token",
        "--chat-id",
        "--target-channel",
        "--production-mode",
        "--confirm-send",
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
            "--confirm-prepare",
            prepare_script.CONFIRM_PREPARE_PHRASE,
            forbidden_arg,
            "value",
        )
        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr
        _assert_safe_output(result.stdout + result.stderr)


async def test_production_like_environment_is_refused_before_db_write() -> None:
    await no_marker_fixtures._ensure_tables()
    before_count = await _delivery_draft_record_count()

    with pytest.raises(
        prepare_script.NoMarkerDraftPrepareBlockedError,
        match="production-like",
    ):
        await prepare_script.prepare_no_marker_persisted_attention_delivery_draft(
            _query(
                start_at=no_marker_fixtures._utc(2199, 1, 1),
                end_at=no_marker_fixtures._utc(2199, 1, 2),
            ),
            settings_override=SimpleNamespace(app_env="production"),
            environ={},
        )

    assert await _delivery_draft_record_count() == before_count


async def test_empty_and_synthetic_only_windows_do_not_create_drafts() -> None:
    await no_marker_fixtures._ensure_tables()
    synthetic_unique = f"synthetic_{uuid4().hex}"
    await no_marker_fixtures._cleanup(synthetic_unique)
    before_count = await _delivery_draft_record_count()
    try:
        empty = await prepare_script.prepare_no_marker_persisted_attention_delivery_draft(
            _query(
                start_at=no_marker_fixtures._utc(2199, 2, 1),
                end_at=no_marker_fixtures._utc(2199, 2, 2),
            ),
            settings_override=_local_settings(),
            environ={},
        )
        await no_marker_fixtures._insert_attention_result(
            synthetic_unique,
            created_at=no_marker_fixtures._utc(2149, 2, 1, 9),
            synthetic=True,
        )
        synthetic = await prepare_script.prepare_no_marker_persisted_attention_delivery_draft(
            _query(
                start_at=no_marker_fixtures._utc(2149, 2, 1),
                end_at=no_marker_fixtures._utc(2149, 2, 2),
            ),
            settings_override=_local_settings(),
            environ={},
        )

        assert empty["prepared"] is False
        assert empty["recommended_next_action"] == (
            "choose_window_with_no_marker_visible_candidates"
        )
        assert synthetic["prepared"] is False
        assert synthetic["candidate"]["visible"] == 0
        assert synthetic["excluded_markers"]["synthetic_marker_count"] == 1
        assert synthetic["safety"]["db_write_scope"] == "none"
        assert await _delivery_draft_record_count() == before_count
        _assert_safe_output(_serialized(empty))
        _assert_safe_output(_serialized(synthetic))
    finally:
        await no_marker_fixtures._cleanup(synthetic_unique)


async def test_mixed_window_prepares_no_marker_only_draft_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await no_marker_fixtures._ensure_tables()
    synthetic_unique = f"mixedsynthetic_{uuid4().hex}"
    no_marker_unique = f"mixednomarker_{uuid4().hex}"
    for unique in (synthetic_unique, no_marker_unique):
        await no_marker_fixtures._cleanup(unique)
    delivery_draft_id: str | None = None

    async def forbidden_send(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("no-marker prepare must not call Telegram sender")

    from app.services import telegram_delivery

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)

    try:
        source_event_id = await no_marker_fixtures._insert_source_event(
            no_marker_unique,
            created_at=no_marker_fixtures._utc(2149, 3, 1, 9),
        )
        activity_item_id = await no_marker_fixtures._insert_normalized_activity(
            no_marker_unique,
            created_at=no_marker_fixtures._utc(2149, 3, 1, 9),
            source_event_id=source_event_id,
        )
        await no_marker_fixtures._insert_attention_result(
            no_marker_unique,
            created_at=no_marker_fixtures._utc(2149, 3, 2, 9),
            activity_item_id=activity_item_id,
        )
        await no_marker_fixtures._insert_attention_result(
            synthetic_unique,
            created_at=no_marker_fixtures._utc(2149, 3, 2, 10),
            synthetic=True,
        )

        query = _query(
            start_at=no_marker_fixtures._utc(2149, 3, 2),
            end_at=no_marker_fixtures._utc(2149, 3, 3),
            activity_start_at=no_marker_fixtures._utc(2149, 3, 1),
            activity_end_at=no_marker_fixtures._utc(2149, 3, 2),
        )
        first = await prepare_script.prepare_no_marker_persisted_attention_delivery_draft(
            query,
            settings_override=_local_settings(),
            environ={},
        )
        second = await prepare_script.prepare_no_marker_persisted_attention_delivery_draft(
            query,
            settings_override=_local_settings(),
            environ={},
        )
        delivery_draft_id = str(first["delivery_draft_id"])
        stored = await _stored_draft(delivery_draft_id)
        metadata = stored["digest"]["metadata"]
        source_of_truth = stored["source_of_truth"]

        assert first["status"] == "no_marker_delivery_draft_prepared"
        assert first["prepared"] is True
        assert first["delivery_draft_id"].startswith("ddraft_")
        assert first["marker_filter"] == PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY
        assert first["no_marker_not_production_truth"] is True
        assert first["candidate"]["visible"] == 1
        assert first["excluded_markers"]["synthetic_marker_count"] == 1
        assert first["timestamp_reconciliation"]["timestamp_mismatch_detected"] is True
        assert "timestamp_mismatch_detected" in first["warnings"]
        assert "mixed_synthetic_and_no_marker_attention_results" in first["warnings"]
        assert first["delivery_draft_record_created"] is True
        assert first["existing"] is False
        assert first["idempotent"] is False
        assert first["recommended_next_action"] == "approve_delivery_draft"
        assert first["safety"]["db_write_scope"] == "delivery_draft_audit_log_only"
        assert first["safety"]["delivery_draft_created"] is True
        assert first["safety"]["approval_created"] is False
        assert first["safety"]["delivery_intention_created"] is False
        assert first["safety"]["delivery_result_created"] is False
        assert first["safety"]["delivery_invoked"] is False
        assert first["safety"]["telegram_invoked"] is False
        assert first["safety"]["openai_invoked"] is False
        assert first["delivery_results_summary"] == {
            "count": 0,
            "successful_count": 0,
            "failed_count": 0,
            "partial_count": 0,
            "skipped_count": 0,
        }

        assert metadata["marker_filter"] == PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY
        assert metadata["no_marker_not_production_truth"] is True
        assert metadata["timestamp_mismatch_detected"] is True
        assert metadata["excluded_markers"]["synthetic_marker_count"] == 1
        assert source_of_truth["marker_filter"] == (
            PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY
        )
        assert source_of_truth["filtered_digest"] is True
        assert source_of_truth["synthetic_local_dev_excluded"] is True
        assert source_of_truth["no_marker_not_production_truth"] is True
        assert source_of_truth["draft_is_source_of_truth"] is False

        assert second["delivery_draft_id"] == first["delivery_draft_id"]
        assert second["delivery_draft_record_created"] is False
        assert second["existing"] is True
        assert second["idempotent"] is True
        assert second["safety"]["db_write_scope"] == "none"
        assert await _delivery_draft_record_count(delivery_draft_id) == 1
        assert await _artifact_count_for_draft(delivery_draft_id) == 0

        _assert_safe_output(_serialized(first))
        _assert_safe_output(prepare_script.format_text_prepare(first))
        _assert_safe_output(_serialized(second))
    finally:
        for unique in (synthetic_unique, no_marker_unique):
            await no_marker_fixtures._cleanup(unique)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)


async def test_prior_different_hash_success_warns_but_does_not_block_draft() -> None:
    await no_marker_fixtures._ensure_tables()
    unique = f"different_hash_{uuid4().hex}"
    await no_marker_fixtures._cleanup(unique)
    delivery_draft_id: str | None = None
    try:
        await no_marker_fixtures._insert_attention_result(
            unique,
            created_at=no_marker_fixtures._utc(2149, 4, 1, 9),
        )
        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=no_marker_fixtures._utc(2149, 4, 1),
                end_at=no_marker_fixtures._utc(2149, 4, 2),
                limit_per_section=20,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
        different_hash_draft = await no_marker_fixtures._persist_successful_draft_for_digest(
            unique,
            digest=digest,
            start_at=no_marker_fixtures._utc(2149, 4, 1),
            end_at=no_marker_fixtures._utc(2149, 4, 2),
            rendered_text_override=f"Different safe rendered body {unique}",
        )

        result = await prepare_script.prepare_no_marker_persisted_attention_delivery_draft(
            _query(
                start_at=no_marker_fixtures._utc(2149, 4, 1),
                end_at=no_marker_fixtures._utc(2149, 4, 2),
                activity_start_at=no_marker_fixtures._utc(2149, 4, 1),
                activity_end_at=no_marker_fixtures._utc(2149, 4, 2),
            ),
            settings_override=_local_settings(),
            environ={},
        )
        delivery_draft_id = str(result["delivery_draft_id"])

        assert result["prepared"] is True
        assert result["recommended_next_action"] == "approve_delivery_draft"
        assert result["lifecycle"]["prior_successful_delivery_for_different_digest_hash"] is True
        assert result["lifecycle"]["matching_hash_has_successful_delivery_result"] is False
        assert "prior_successful_delivery_for_different_digest_hash" in result["warnings"]
        assert different_hash_draft["delivery_draft_id"] != delivery_draft_id
        assert different_hash_draft["text_sha256"] != result["candidate"]["text_sha256"]
        _assert_safe_output(_serialized(result))
    finally:
        await no_marker_fixtures._cleanup(unique)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)


async def test_matching_hash_success_does_not_create_new_draft() -> None:
    await no_marker_fixtures._ensure_tables()
    unique = f"matching_hash_{uuid4().hex}"
    await no_marker_fixtures._cleanup(unique)
    try:
        await no_marker_fixtures._insert_attention_result(
            unique,
            created_at=no_marker_fixtures._utc(2149, 5, 1, 9),
        )
        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=no_marker_fixtures._utc(2149, 5, 1),
                end_at=no_marker_fixtures._utc(2149, 5, 2),
                limit_per_section=20,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
        current_draft = await no_marker_fixtures._persist_successful_draft_for_digest(
            unique,
            digest=digest,
            start_at=no_marker_fixtures._utc(2149, 5, 1),
            end_at=no_marker_fixtures._utc(2149, 5, 2),
        )
        before_count = await _delivery_draft_record_count()

        result = await prepare_script.prepare_no_marker_persisted_attention_delivery_draft(
            _query(
                start_at=no_marker_fixtures._utc(2149, 5, 1),
                end_at=no_marker_fixtures._utc(2149, 5, 2),
                activity_start_at=no_marker_fixtures._utc(2149, 5, 1),
                activity_end_at=no_marker_fixtures._utc(2149, 5, 2),
            ),
            settings_override=_local_settings(),
            environ={},
        )

        assert result["status"] == "no_marker_delivery_draft_already_sent"
        assert result["prepared"] is False
        assert result["delivery_draft_id"] == current_draft["delivery_draft_id"]
        assert result["recommended_next_action"] == "do_not_resend_same_digest_content"
        assert result["lifecycle"]["matching_hash_has_successful_delivery_result"] is True
        assert result["safety"]["db_write_scope"] == "none"
        assert await _delivery_draft_record_count() == before_count
        _assert_safe_output(_serialized(result))
    finally:
        await no_marker_fixtures._cleanup(unique)
