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
from app.services.attention_results import AttentionResultValidationError
from scripts import preview_stored_source_event_normalization as preview_script
from scripts import triage_normalized_activity_items as triage_script

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "triage_normalized_activity_items.py"


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


def _query(
    *,
    start_at: datetime,
    end_at: datetime,
    max_items: int = 100,
    include_synthetic: bool = False,
    confirm_triage: str = triage_script.CONFIRM_TRIAGE_PHRASE,
) -> triage_script.NormalizedActivityTriageQuery:
    return triage_script.NormalizedActivityTriageQuery(
        start_at=start_at,
        end_at=end_at,
        confirm_triage=confirm_triage,
        max_items=max_items,
        include_synthetic=include_synthetic,
        output_format="json",
    )


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
        "Private triage write title",
        "Private triage write summary",
        "Private Triage Write Actor",
        "private-triage-write@example.com",
        "private-file.pdf",
        "PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE",
        "nact_fos084_",
        "atri_fos084_",
        '"evidence_refs": [',
    )
    folded = output.casefold()
    for marker in forbidden:
        assert marker.casefold() not in folded


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


async def _source_event_count() -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(select(func.count()).select_from(SourceEvent)) or 0
        )


async def _normalized_activity_count_for_unique(unique: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count(NormalizedActivityItemRecord.id)).where(
                    NormalizedActivityItemRecord.activity_item_id.like(
                        f"nact_fos084_{unique}%"
                    )
                )
            )
            or 0
        )


async def _attention_result_count_for_unique(unique: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count(AttentionTriageResultRecord.id)).where(
                    AttentionTriageResultRecord.activity_item_id.like(
                        f"nact_fos084_{unique}%"
                    )
                )
            )
            or 0
        )


async def _cleanup(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.activity_item_id.like(
                    f"nact_fos084_{unique}%"
                )
            )
        )
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.triage_result_id.like(
                    f"atri_fos084_{unique}%"
                )
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(
                    f"nact_fos084_{unique}%"
                )
            )
        )
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_event_id.like(f"sevt_fos084_{unique}%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.event_id.like(f"evt_fos084_{unique}%")
            )
        )
        await session.commit()


async def _insert_normalized_activity(
    unique: str,
    *,
    created_at: datetime,
    kind: str = "github",
    actor: str = "Private Triage Write Actor",
) -> str:
    activity_item_id = f"nact_fos084_{unique}"
    if kind == "synthetic":
        source = "internal"
        source_object_id = f"{preview_script.SYNTHETIC_SOURCE_OBJECT_PREFIX}{unique}:safe"
        activity_type = "synthetic.persisted_attention_digest.seed"
    else:
        source = "github"
        source_object_id = f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}"
        activity_type = "pull_request.updated"

    async with AsyncSessionLocal() as session:
        session.add(
            NormalizedActivityItemRecord(
                activity_item_id=activity_item_id,
                source_event_id=None,
                source=source,
                source_object_id=source_object_id,
                activity_type=activity_type,
                title="Private triage write title must not print",
                actor=actor,
                activity_created_at=created_at,
                project="Private Project",
                safe_summary="Private triage write summary must not print",
                related_people=[
                    "Private Triage Write Actor",
                    "private-triage-write@example.com",
                ],
                related_jira_keys=["FOS-084"],
                related_prs=["private-pr"],
                related_files=["private-file.pdf"],
                evidence_refs=[
                    {
                        "kind": "normalized_activity",
                        "activity_item_id": activity_item_id,
                    }
                ],
                created_at=created_at,
            )
        )
        await session.commit()
    return activity_item_id


async def _insert_attention_result(
    unique: str,
    *,
    activity_item_id: str,
    created_at: datetime,
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            AttentionTriageResultRecord(
                triage_result_id=f"atri_fos084_{unique}",
                source="github",
                source_object_id=f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}",
                activity_item_id=activity_item_id,
                attention_class="review_optional",
                priority="low",
                show_in_digest=True,
                confidence=0.5,
                reason="Private triage write reason must not print",
                recommended_action="Private triage write action must not print",
                owner=None,
                deadline=None,
                evidence_refs=[
                    {
                        "kind": "normalized_activity",
                        "activity_item_id": activity_item_id,
                    }
                ],
                created_at=created_at,
            )
        )
        await session.commit()


def test_missing_required_args_fail_safely() -> None:
    missing_start = _run_script(
        "--end-at",
        "2149-01-02T00:00:00+00:00",
        "--confirm-triage",
        triage_script.CONFIRM_TRIAGE_PHRASE,
    )
    missing_end = _run_script(
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--confirm-triage",
        triage_script.CONFIRM_TRIAGE_PHRASE,
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
    assert "--confirm-triage" in missing_confirm.stderr


def test_invalid_inputs_fail_before_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden_triage(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid input must fail before DB execution")

    monkeypatch.setattr(
        triage_script,
        "triage_normalized_activity_items",
        forbidden_triage,
    )

    base = [
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--end-at",
        "2149-01-02T00:00:00+00:00",
        "--confirm-triage",
        triage_script.CONFIRM_TRIAGE_PHRASE,
        "--format",
        "json",
    ]

    assert (
        triage_script.main(
            [
                "--start-at",
                "2149-01-01T00:00:00",
                "--end-at",
                "2149-01-02T00:00:00+00:00",
                "--confirm-triage",
                triage_script.CONFIRM_TRIAGE_PHRASE,
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert (
        triage_script.main(
            [
                "--start-at",
                "2149-01-02T00:00:00+00:00",
                "--end-at",
                "2149-01-01T00:00:00+00:00",
                "--confirm-triage",
                triage_script.CONFIRM_TRIAGE_PHRASE,
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert triage_script.main([*base, "--max-items", "0"]) == 2
    assert (
        triage_script.main(
            [*base, "--max-items", str(triage_script.MAX_TRIAGE_ITEMS + 1)]
        )
        == 2
    )
    assert (
        triage_script.main(
            [
                "--start-at",
                "2149-01-01T00:00:00+00:00",
                "--end-at",
                "2149-01-02T00:00:00+00:00",
                "--confirm-triage",
                "wrong phrase",
                "--format",
                "json",
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
            "--confirm-triage",
            triage_script.CONFIRM_TRIAGE_PHRASE,
            forbidden_arg,
            "value",
        )
        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr


async def test_production_like_environment_is_refused_before_db_access() -> None:
    class FailingSession:
        async def __aenter__(self) -> "FailingSession":
            raise AssertionError("production-like env must fail before DB access")

        async def __aexit__(self, *_args: object) -> None:
            return None

    with pytest.raises(
        triage_script.NormalizedActivityTriageBlockedError,
        match="production-like",
    ):
        await triage_script.triage_normalized_activity_items(
            _query(start_at=_utc(2149, 1, 1), end_at=_utc(2149, 1, 2)),
            session_factory=FailingSession,
            settings_override=SimpleNamespace(app_env="production"),
            environ={},
        )


async def test_empty_range_writes_nothing_and_reports_normalize_first() -> None:
    await _ensure_tables()
    before_audit = await _audit_log_count()
    report = await triage_script.triage_normalized_activity_items(
        _query(start_at=_utc(2199, 1, 1), end_at=_utc(2199, 1, 2)),
        settings_override=_local_settings(),
        environ={},
    )

    assert report["scanned_normalized_activity_count"] == 0
    assert report["normalized_activity"]["total"] == 0
    assert report["triage"]["created_count"] == 0
    assert report["recommended_next_action"] == "normalize_source_events_before_triage"
    assert report["safety"]["db_write_scope"] == "none"
    assert report["safety"]["attention_results_created"] is False
    assert await _audit_log_count() == before_audit
    _assert_safe_output(_serialized(report))
    _assert_safe_output(triage_script.format_text_report(report))


async def test_eligible_no_marker_activity_creates_provider_free_attention_result() -> None:
    await _ensure_tables()
    unique = f"github_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_normalized_activity(unique, created_at=_utc(2149, 1, 3, 9))
        before_audit = await _audit_log_count()
        before_source_count = await _source_event_count()
        before_normalized_count = await _normalized_activity_count_for_unique(unique)

        report = await triage_script.triage_normalized_activity_items(
            _query(start_at=_utc(2149, 1, 3), end_at=_utc(2149, 1, 4)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["normalized_activity"]["total"] == 1
        assert report["normalized_activity"]["synthetic_status"] == (
            "no_synthetic_marker_detected"
        )
        assert report["triage"]["created_count"] == 1
        assert report["triage"]["already_triaged_count"] == 0
        assert report["triage"]["no_marker_created_count"] == 1
        assert report["triage"]["synthetic_created_count"] == 0
        assert report["triage"]["by_attention_class"] == {"review_optional": 1}
        assert report["triage"]["by_priority"] == {"low": 1}
        assert report["triage"]["visible_candidate_count"] == 1
        assert report["triage"]["hidden_count"] == 0
        assert (
            report["recommended_next_action"]
            == "run_real_stored_local_data_readiness_report"
        )
        assert report["safety"]["provider_free"] is True
        assert report["safety"]["db_write_scope"] == "attention_triage_results_only"
        assert report["safety"]["attention_results_created"] is True
        assert report["safety"]["triage_write_invoked"] is True
        assert report["safety"]["source_events_created"] is False
        assert report["safety"]["normalized_activity_created"] is False
        assert report["safety"]["openai_invoked"] is False
        assert report["safety"]["live_api_calls"] is False
        assert await _attention_result_count_for_unique(unique) == 1
        assert await _normalized_activity_count_for_unique(unique) == before_normalized_count
        assert await _source_event_count() == before_source_count
        assert await _audit_log_count() == before_audit
        _assert_safe_output(_serialized(report))
        _assert_safe_output(triage_script.format_text_report(report))
    finally:
        await _cleanup(unique)


async def test_rerun_is_idempotent_and_counts_already_triaged() -> None:
    await _ensure_tables()
    unique = f"idempotent_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_normalized_activity(unique, created_at=_utc(2149, 1, 4, 9))
        first = await triage_script.triage_normalized_activity_items(
            _query(start_at=_utc(2149, 1, 4), end_at=_utc(2149, 1, 5)),
            settings_override=_local_settings(),
            environ={},
        )
        second = await triage_script.triage_normalized_activity_items(
            _query(start_at=_utc(2149, 1, 4), end_at=_utc(2149, 1, 5)),
            settings_override=_local_settings(),
            environ={},
        )

        assert first["triage"]["created_count"] == 1
        assert second["triage"]["created_count"] == 0
        assert second["triage"]["already_triaged_count"] == 1
        assert second["safety"]["db_write_scope"] == "none"
        assert second["safety"]["attention_results_created"] is False
        assert (
            second["recommended_next_action"]
            == "run_real_stored_local_data_readiness_report"
        )
        assert await _attention_result_count_for_unique(unique) == 1
        _assert_safe_output(_serialized(second))
    finally:
        await _cleanup(unique)


async def test_already_triaged_activity_is_counted_and_skipped() -> None:
    await _ensure_tables()
    unique = f"existing_{uuid4().hex}"
    await _cleanup(unique)
    try:
        activity_item_id = await _insert_normalized_activity(
            unique,
            created_at=_utc(2149, 1, 5, 9),
        )
        await _insert_attention_result(
            unique,
            activity_item_id=activity_item_id,
            created_at=_utc(2149, 1, 5, 10),
        )
        report = await triage_script.triage_normalized_activity_items(
            _query(start_at=_utc(2149, 1, 5), end_at=_utc(2149, 1, 6)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["triage"]["already_triaged_count"] == 1
        assert report["triage"]["created_count"] == 0
        assert report["triage"]["visible_candidate_count"] == 0
        assert report["safety"]["db_write_scope"] == "none"
        assert await _attention_result_count_for_unique(unique) == 1
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_synthetic_rows_are_excluded_by_default_and_included_explicitly() -> None:
    await _ensure_tables()
    unique = f"synthetic_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_normalized_activity(
            unique,
            created_at=_utc(2149, 1, 6, 9),
            kind="synthetic",
        )
        default_report = await triage_script.triage_normalized_activity_items(
            _query(start_at=_utc(2149, 1, 6), end_at=_utc(2149, 1, 7)),
            settings_override=_local_settings(),
            environ={},
        )
        included_report = await triage_script.triage_normalized_activity_items(
            _query(
                start_at=_utc(2149, 1, 6),
                end_at=_utc(2149, 1, 7),
                include_synthetic=True,
            ),
            settings_override=_local_settings(),
            environ={},
        )

        assert default_report["normalized_activity"]["synthetic_status"] == (
            "synthetic_local_dev_detected"
        )
        assert default_report["triage"]["synthetic_skipped_count"] == 1
        assert default_report["triage"]["created_count"] == 0
        assert default_report["recommended_next_action"] == (
            "rerun_with_include_synthetic_for_dev_preview_or_choose_no_marker_window"
        )
        assert included_report["normalized_activity"]["synthetic_status"] == (
            "synthetic_local_dev_detected"
        )
        assert included_report["triage"]["synthetic_skipped_count"] == 0
        assert included_report["triage"]["synthetic_created_count"] == 1
        assert included_report["triage"]["created_count"] == 1
        assert await _attention_result_count_for_unique(unique) == 1
        _assert_safe_output(_serialized(default_report))
        _assert_safe_output(_serialized(included_report))
    finally:
        await _cleanup(unique)


async def test_activity_from_user_projects_waiting_external_counts() -> None:
    await _ensure_tables()
    unique = f"from_user_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_normalized_activity(
            unique,
            created_at=_utc(2149, 1, 7, 9),
            actor="me",
        )
        report = await triage_script.triage_normalized_activity_items(
            _query(start_at=_utc(2149, 1, 7), end_at=_utc(2149, 1, 8)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["triage"]["by_attention_class"] == {
            "waiting_on_external": 1
        }
        assert report["triage"]["by_priority"] == {"low": 1}
        assert report["triage"]["visible_candidate_count"] == 1
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_max_items_bound_fails_before_processing() -> None:
    await _ensure_tables()
    first_unique = f"bound_a_{uuid4().hex}"
    second_unique = f"bound_b_{uuid4().hex}"
    for unique in (first_unique, second_unique):
        await _cleanup(unique)
    try:
        await _insert_normalized_activity(
            first_unique,
            created_at=_utc(2149, 1, 8, 9),
        )
        await _insert_normalized_activity(
            second_unique,
            created_at=_utc(2149, 1, 8, 10),
        )
        with pytest.raises(triage_script.NormalizedActivityTriageInputError):
            await triage_script.triage_normalized_activity_items(
                _query(
                    start_at=_utc(2149, 1, 8),
                    end_at=_utc(2149, 1, 9),
                    max_items=1,
                ),
                settings_override=_local_settings(),
                environ={},
            )
        assert await _attention_result_count_for_unique(first_unique) == 0
        assert await _attention_result_count_for_unique(second_unique) == 0
    finally:
        for unique in (first_unique, second_unique):
            await _cleanup(unique)


async def test_invalid_or_unpreviewable_rows_are_counted_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    unique = f"invalid_{uuid4().hex}"
    await _cleanup(unique)

    async def invalid_triage(*_args: object, **_kwargs: object) -> object:
        raise AttentionResultValidationError("attention triage result is invalid")

    monkeypatch.setattr(
        triage_script.attention_results_service,
        "triage_normalized_activity_item",
        invalid_triage,
    )
    try:
        await _insert_normalized_activity(unique, created_at=_utc(2149, 1, 9, 9))
        report = await triage_script.triage_normalized_activity_items(
            _query(start_at=_utc(2149, 1, 9), end_at=_utc(2149, 1, 10)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["triage"]["invalid_or_unpreviewable_count"] == 1
        assert report["triage"]["created_count"] == 0
        assert report["safety"]["db_write_scope"] == "none"
        assert await _attention_result_count_for_unique(unique) == 0
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_unsupported_unknown_rows_are_counted_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    unique = f"unsupported_{uuid4().hex}"
    await _cleanup(unique)

    async def unsupported_triage(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("unsupported test shape")

    monkeypatch.setattr(
        triage_script.attention_results_service,
        "triage_normalized_activity_item",
        unsupported_triage,
    )
    try:
        await _insert_normalized_activity(unique, created_at=_utc(2149, 1, 10, 9))
        report = await triage_script.triage_normalized_activity_items(
            _query(start_at=_utc(2149, 1, 10), end_at=_utc(2149, 1, 11)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["triage"]["unsupported_or_unknown_count"] == 1
        assert report["triage"]["created_count"] == 0
        assert report["recommended_next_action"] == (
            "no_supported_normalized_activity_for_provider_free_triage"
        )
        assert await _attention_result_count_for_unique(unique) == 0
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_command_uses_provider_free_path_and_no_delivery_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    unique = f"provider_free_{uuid4().hex}"
    await _cleanup(unique)

    def forbidden_openai(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("provider-free triage must not call OpenAI clients")

    def forbidden_send(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("provider-free triage must not send messages")

    monkeypatch.setattr(
        "app.services.attention_triage._call_openai_compatible_client",
        forbidden_openai,
    )
    monkeypatch.setattr(
        "app.services.telegram_delivery.send_telegram_plain_text",
        forbidden_send,
    )
    before_audit = await _audit_log_count()

    try:
        await _insert_normalized_activity(unique, created_at=_utc(2149, 1, 11, 9))
        report = await triage_script.triage_normalized_activity_items(
            _query(start_at=_utc(2149, 1, 11), end_at=_utc(2149, 1, 12)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["triage"]["created_count"] == 1
        assert report["safety"]["provider_free"] is True
        assert report["safety"]["openai_invoked"] is False
        assert report["safety"]["live_api_calls"] is False
        assert report["safety"]["telegram_invoked"] is False
        assert report["safety"]["delivery_invoked"] is False
        assert report["safety"]["outbox_record_created"] is False
        assert await _audit_log_count() == before_audit
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)
