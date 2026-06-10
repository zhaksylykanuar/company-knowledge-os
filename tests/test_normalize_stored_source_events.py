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

from app.db.attention_models import AttentionTriageResultRecord
from app.db.base import AsyncSessionLocal
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import AuditLog, IngestedEvent
from scripts import normalize_stored_source_events as normalize_script
from scripts import preview_stored_source_event_normalization as preview_script
from tests.test_seed_local_persisted_attention_digest import _ensure_seed_tables

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "normalize_stored_source_events.py"


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
    max_events: int = 100,
    include_synthetic: bool = False,
    sources: tuple[str, ...] = (),
    confirm_normalize: str = normalize_script.CONFIRM_NORMALIZE_PHRASE,
) -> normalize_script.StoredSourceEventNormalizationQuery:
    return normalize_script.StoredSourceEventNormalizationQuery(
        start_at=start_at,
        end_at=end_at,
        confirm_normalize=confirm_normalize,
        max_events=max_events,
        include_synthetic=include_synthetic,
        sources=sources,
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
        "Private normalization title",
        "Private normalization summary",
        "Private Normalization Actor",
        "private-normalization@example.com",
        "private-file.pdf",
        "PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE",
        "sevt_fos082_",
        "evt_fos082_",
        "nact_fos082_",
        '"evidence_refs": [',
    )
    folded = output.casefold()
    for marker in forbidden:
        assert marker.casefold() not in folded


async def _audit_log_count() -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(select(func.count()).select_from(AuditLog)) or 0
        )


async def _attention_result_count() -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count()).select_from(AttentionTriageResultRecord)
            )
            or 0
        )


async def _normalized_count_for_source_event(source_event_id: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count(NormalizedActivityItemRecord.id)).where(
                    NormalizedActivityItemRecord.source_event_id == source_event_id
                )
            )
            or 0
        )


async def _source_event_count_for_unique(unique: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count(SourceEvent.id)).where(
                    SourceEvent.source_event_id.like(f"sevt_fos082_{unique}%")
                )
            )
            or 0
        )


async def _cleanup(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.triage_result_id.like(
                    f"atri_fos082_{unique}%"
                )
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.source_event_id.like(
                    f"sevt_fos082_{unique}%"
                )
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(
                    f"nact_fos082_{unique}%"
                )
            )
        )
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_event_id.like(f"sevt_fos082_{unique}%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.event_id.like(f"evt_fos082_{unique}%")
            )
        )
        await session.commit()


def _source_values(unique: str, *, kind: str) -> dict[str, str]:
    if kind == "synthetic":
        return {
            "source_system": "internal",
            "source_object_type": "system_event",
            "source_object_id": (
                f"{preview_script.SYNTHETIC_SOURCE_OBJECT_PREFIX}{unique}:safe"
            ),
            "event_type": "internal.system_event.recorded",
        }
    if kind == "unsupported":
        return {
            "source_system": "calendar",
            "source_object_type": "event",
            "source_object_id": f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}",
            "event_type": "calendar.event.updated",
        }
    if kind == "drive":
        return {
            "source_system": "drive",
            "source_object_type": "file",
            "source_object_id": f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}",
            "event_type": "drive.file.ingested",
        }
    return {
        "source_system": "github",
        "source_object_type": "pull_request",
        "source_object_id": f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}",
        "event_type": "github.pull_request.opened",
    }


async def _insert_source_event(
    unique: str,
    *,
    created_at: datetime,
    kind: str = "github",
) -> str:
    values = _source_values(unique, kind=kind)
    event_id = f"evt_fos082_{unique}"
    source_event_id = f"sevt_fos082_{unique}"
    async with AsyncSessionLocal() as session:
        session.add(
            IngestedEvent(
                event_id=event_id,
                event_type=values["event_type"],
                source_system=values["source_system"],
                source_object_id=values["source_object_id"],
                idempotency_key=f"idem_fos082_{unique}",
                correlation_id=f"corr_fos082_{unique}",
                trace_id=f"trace_fos082_{unique}",
                raw_object_ref=f"raw://private/fos082/{unique}.json",
                payload={
                    "title": "Private normalization title must not print",
                    "summary": "Private normalization summary must not print",
                    "raw_body": "PRIVATE_RAW_BODY_DO_NOT_EXPOSE",
                    "provider_payload": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                    "source_url": "https://private.example.test/fos082",
                },
                status="received",
                created_at=created_at,
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=source_event_id,
                source_event_key=f"{values['source_system']}:fos082:{unique}",
                ingested_event_id=event_id,
                event_type=values["event_type"],
                source_system=values["source_system"],
                source_object_type=values["source_object_type"],
                source_object_id=values["source_object_id"],
                source_event_ts=created_at,
                actor_external_id="private-normalization@example.com",
                title="Private normalization title must not print",
                summary="Private normalization summary must not print",
                source_url="https://private.example.test/fos082",
                raw_object_ref=f"raw://private/fos082/{unique}.json",
                evidence_refs=[
                    {
                        "kind": "source_event",
                        "source_event_id": source_event_id,
                        "raw_object_ref": f"raw://private/fos082/{unique}.json",
                    }
                ],
                metadata_json={"trace_id": f"trace_fos082_{unique}"},
                created_at=created_at,
            )
        )
        await session.commit()
    return source_event_id


async def _insert_normalized_activity(
    unique: str,
    *,
    source_event_id: str,
    created_at: datetime,
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            NormalizedActivityItemRecord(
                activity_item_id=f"nact_fos082_{unique}",
                source_event_id=source_event_id,
                source="github",
                source_object_id=f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}",
                activity_type="pull_request.updated",
                title="Private normalization title must not print",
                actor="Private Normalization Actor",
                activity_created_at=created_at,
                project="Private Project",
                safe_summary="Private normalization summary must not print",
                related_people=[
                    "Private Normalization Actor",
                    "private-normalization@example.com",
                ],
                related_jira_keys=["FOS-082"],
                related_prs=["private-pr"],
                related_files=["private-file.pdf"],
                evidence_refs=[
                    {
                        "kind": "source_event",
                        "source_event_id": source_event_id,
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
        "--confirm-normalize",
        normalize_script.CONFIRM_NORMALIZE_PHRASE,
    )
    missing_end = _run_script(
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--confirm-normalize",
        normalize_script.CONFIRM_NORMALIZE_PHRASE,
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
    assert "--confirm-normalize" in missing_confirm.stderr


def test_invalid_inputs_fail_before_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden_report(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid input must fail before DB execution")

    monkeypatch.setattr(normalize_script, "normalize_stored_source_events", forbidden_report)

    base = [
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--end-at",
        "2149-01-02T00:00:00+00:00",
        "--confirm-normalize",
        normalize_script.CONFIRM_NORMALIZE_PHRASE,
        "--format",
        "json",
    ]

    assert (
        normalize_script.main(
            [
                "--start-at",
                "2149-01-01T00:00:00",
                "--end-at",
                "2149-01-02T00:00:00+00:00",
                "--confirm-normalize",
                normalize_script.CONFIRM_NORMALIZE_PHRASE,
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert (
        normalize_script.main(
            [
                "--start-at",
                "2149-01-02T00:00:00+00:00",
                "--end-at",
                "2149-01-01T00:00:00+00:00",
                "--confirm-normalize",
                normalize_script.CONFIRM_NORMALIZE_PHRASE,
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert normalize_script.main([*base, "--max-events", "0"]) == 2
    assert (
        normalize_script.main(
            [*base, "--max-events", str(normalize_script.MAX_NORMALIZE_EVENTS + 1)]
        )
        == 2
    )
    assert (
        normalize_script.main(
            [
                "--start-at",
                "2149-01-01T00:00:00+00:00",
                "--end-at",
                "2149-01-02T00:00:00+00:00",
                "--confirm-normalize",
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
            "--confirm-normalize",
            normalize_script.CONFIRM_NORMALIZE_PHRASE,
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
        normalize_script.StoredSourceEventNormalizationBlockedError,
        match="production-like",
    ):
        await normalize_script.normalize_stored_source_events(
            _query(start_at=_utc(2149, 1, 1), end_at=_utc(2149, 1, 2)),
            session_factory=FailingSession,
            settings_override=SimpleNamespace(app_env="production"),
            environ={},
        )


async def test_empty_range_writes_nothing_and_reports_no_source_events() -> None:
    await _ensure_seed_tables()
    before_audit = await _audit_log_count()
    before_attention = await _attention_result_count()
    report = await normalize_script.normalize_stored_source_events(
        _query(start_at=_utc(2199, 1, 1), end_at=_utc(2199, 1, 2)),
        settings_override=_local_settings(),
        environ={},
    )

    assert report["scanned_source_event_count"] == 0
    assert report["source_events"]["total"] == 0
    assert report["normalization"]["created_count"] == 0
    assert report["recommended_next_action"] == "no_source_events_found"
    assert report["safety"]["db_write_scope"] == "none"
    assert report["safety"]["normalized_activity_created"] is False
    assert await _audit_log_count() == before_audit
    assert await _attention_result_count() == before_attention
    _assert_safe_output(_serialized(report))
    _assert_safe_output(normalize_script.format_text_report(report))


async def test_supported_no_marker_github_source_event_creates_normalized_activity() -> None:
    await _ensure_seed_tables()
    unique = f"github_{uuid4().hex}"
    await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 3, 9),
        )
        before_source_count = await _source_event_count_for_unique(unique)
        before_audit = await _audit_log_count()
        before_attention = await _attention_result_count()

        report = await normalize_script.normalize_stored_source_events(
            _query(start_at=_utc(2149, 1, 3), end_at=_utc(2149, 1, 4)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["source_events"]["total"] == 1
        assert report["source_events"]["synthetic_status"] == (
            "no_synthetic_marker_detected"
        )
        assert report["normalization"]["created_count"] == 1
        assert report["normalization"]["no_marker_created_count"] == 1
        assert report["normalization"]["synthetic_created_count"] == 0
        assert report["normalization"]["already_normalized_count"] == 0
        assert report["normalization"]["by_projected_source"] == {"github": 1}
        assert report["normalization"]["by_projected_activity_type"] == {
            "pull_request.updated": 1
        }
        assert (
            report["recommended_next_action"]
            == "run_real_stored_local_data_readiness_report"
        )
        assert report["safety"]["db_write_scope"] == "normalized_activity_items_only"
        assert report["safety"]["normalized_activity_created"] is True
        assert report["safety"]["source_events_created"] is False
        assert report["safety"]["attention_results_created"] is False
        assert await _normalized_count_for_source_event(source_event_id) == 1
        assert await _source_event_count_for_unique(unique) == before_source_count
        assert await _audit_log_count() == before_audit
        assert await _attention_result_count() == before_attention
        _assert_safe_output(_serialized(report))
        _assert_safe_output(normalize_script.format_text_report(report))
    finally:
        await _cleanup(unique)


async def test_source_filter_excludes_unselected_events_from_normalization_write() -> None:
    await _ensure_seed_tables()
    drive_unique = f"source_drive_{uuid4().hex}"
    github_unique = f"source_github_{uuid4().hex}"
    for unique in (drive_unique, github_unique):
        await _cleanup(unique)
    try:
        drive_source_event_id = await _insert_source_event(
            drive_unique,
            created_at=_utc(2149, 1, 3, 9),
            kind="drive",
        )
        github_source_event_id = await _insert_source_event(
            github_unique,
            created_at=_utc(2149, 1, 3, 10),
        )

        report = await normalize_script.normalize_stored_source_events(
            _query(
                start_at=_utc(2149, 1, 3),
                end_at=_utc(2149, 1, 4),
                sources=("drive",),
            ),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["sources"] == ["drive"]
        assert report["source_events"]["total"] == 1
        assert report["source_events"]["by_source_system"] == {"drive": 1}
        assert report["normalization"]["created_count"] == 1
        assert report["normalization"]["by_projected_source"] == {"drive": 1}
        assert report["normalization"]["by_projected_activity_type"] == {
            "document.changed": 1
        }
        assert await _normalized_count_for_source_event(drive_source_event_id) == 1
        assert await _normalized_count_for_source_event(github_source_event_id) == 0
        _assert_safe_output(_serialized(report))
    finally:
        for unique in (drive_unique, github_unique):
            await _cleanup(unique)


async def test_rerun_is_idempotent_and_counts_already_normalized() -> None:
    await _ensure_seed_tables()
    unique = f"idempotent_{uuid4().hex}"
    await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 4, 9),
        )
        first = await normalize_script.normalize_stored_source_events(
            _query(start_at=_utc(2149, 1, 4), end_at=_utc(2149, 1, 5)),
            settings_override=_local_settings(),
            environ={},
        )
        second = await normalize_script.normalize_stored_source_events(
            _query(start_at=_utc(2149, 1, 4), end_at=_utc(2149, 1, 5)),
            settings_override=_local_settings(),
            environ={},
        )

        assert first["normalization"]["created_count"] == 1
        assert second["normalization"]["created_count"] == 0
        assert second["normalization"]["already_normalized_count"] == 1
        assert second["safety"]["db_write_scope"] == "none"
        assert (
            second["recommended_next_action"]
            == "proceed_to_normalized_activity_triage_readiness"
        )
        assert await _normalized_count_for_source_event(source_event_id) == 1
        _assert_safe_output(_serialized(second))
    finally:
        await _cleanup(unique)


async def test_already_normalized_source_event_is_counted_and_skipped() -> None:
    await _ensure_seed_tables()
    unique = f"existing_{uuid4().hex}"
    await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 5, 9),
        )
        await _insert_normalized_activity(
            unique,
            source_event_id=source_event_id,
            created_at=_utc(2149, 1, 5, 9),
        )
        report = await normalize_script.normalize_stored_source_events(
            _query(start_at=_utc(2149, 1, 5), end_at=_utc(2149, 1, 6)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["normalization"]["already_normalized_count"] == 1
        assert report["normalization"]["created_count"] == 0
        assert await _normalized_count_for_source_event(source_event_id) == 1
        assert (
            report["recommended_next_action"]
            == "proceed_to_normalized_activity_triage_readiness"
        )
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_synthetic_rows_are_excluded_by_default_and_labeled_when_included() -> None:
    await _ensure_seed_tables()
    unique = f"synthetic_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 6, 9),
            kind="synthetic",
        )
        default_report = await normalize_script.normalize_stored_source_events(
            _query(start_at=_utc(2149, 1, 6), end_at=_utc(2149, 1, 7)),
            settings_override=_local_settings(),
            environ={},
        )
        included_report = await normalize_script.normalize_stored_source_events(
            _query(
                start_at=_utc(2149, 1, 6),
                end_at=_utc(2149, 1, 7),
                include_synthetic=True,
            ),
            settings_override=_local_settings(),
            environ={},
        )

        assert default_report["source_events"]["synthetic_status"] == (
            "synthetic_local_dev_detected"
        )
        assert default_report["normalization"]["synthetic_skipped_count"] == 1
        assert default_report["normalization"]["created_count"] == 0
        assert default_report["recommended_next_action"] == (
            "rerun_with_include_synthetic_for_dev_preview_or_choose_no_marker_window"
        )
        assert included_report["source_events"]["synthetic_status"] == (
            "synthetic_local_dev_detected"
        )
        assert included_report["normalization"]["synthetic_skipped_count"] == 0
        assert included_report["normalization"]["unsupported_count"] == 1
        assert included_report["normalization"]["created_count"] == 0
        _assert_safe_output(_serialized(default_report))
        _assert_safe_output(_serialized(included_report))
    finally:
        await _cleanup(unique)


async def test_unsupported_source_event_is_counted_without_raw_detail() -> None:
    await _ensure_seed_tables()
    unique = f"unsupported_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 7, 9),
            kind="unsupported",
        )
        report = await normalize_script.normalize_stored_source_events(
            _query(start_at=_utc(2149, 1, 7), end_at=_utc(2149, 1, 8)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["normalization"]["unsupported_count"] == 1
        assert report["normalization"]["created_count"] == 0
        assert (
            report["recommended_next_action"]
            == "no_supported_source_events_for_normalization"
        )
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_max_events_bound_fails_before_projection() -> None:
    await _ensure_seed_tables()
    first_unique = f"bound_a_{uuid4().hex}"
    second_unique = f"bound_b_{uuid4().hex}"
    for unique in (first_unique, second_unique):
        await _cleanup(unique)
    try:
        await _insert_source_event(first_unique, created_at=_utc(2149, 1, 8, 9))
        await _insert_source_event(second_unique, created_at=_utc(2149, 1, 8, 10))
        with pytest.raises(normalize_script.StoredSourceEventNormalizationInputError):
            await normalize_script.normalize_stored_source_events(
                _query(
                    start_at=_utc(2149, 1, 8),
                    end_at=_utc(2149, 1, 9),
                    max_events=1,
                ),
                settings_override=_local_settings(),
                environ={},
            )

        assert await _normalized_count_for_source_event(f"sevt_fos082_{first_unique}") == 0
        assert await _normalized_count_for_source_event(f"sevt_fos082_{second_unique}") == 0
    finally:
        for unique in (first_unique, second_unique):
            await _cleanup(unique)


async def test_command_does_not_call_triage_send_or_live_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_seed_tables()
    unique = f"no_adapters_{uuid4().hex}"
    await _cleanup(unique)

    def forbidden_triage(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("normalization command must not triage activity")

    def forbidden_send(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("normalization command must not send messages")

    monkeypatch.setattr(
        "app.services.attention_results.triage_normalized_activity_item",
        forbidden_triage,
    )
    monkeypatch.setattr(
        "app.services.telegram_delivery.send_telegram_plain_text",
        forbidden_send,
    )

    try:
        await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 9, 9),
            kind="unsupported",
        )
        report = await normalize_script.normalize_stored_source_events(
            _query(start_at=_utc(2149, 1, 9), end_at=_utc(2149, 1, 10)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["normalization"]["unsupported_count"] == 1
        assert report["safety"]["delivery_invoked"] is False
        assert report["safety"]["telegram_invoked"] is False
        assert report["safety"]["openai_invoked"] is False
        assert report["safety"]["live_api_calls"] is False
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)
