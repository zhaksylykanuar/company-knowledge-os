from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.attention_models import AttentionTriageResultRecord
from app.db.base import AsyncSessionLocal
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import AuditLog, IngestedEvent
from scripts import preview_stored_source_event_normalization as preview_script
from tests.test_seed_local_persisted_attention_digest import _ensure_seed_tables

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "preview_stored_source_event_normalization.py"


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
        "source_object_id",
        "raw_object_ref",
        "source_url",
        "prompt",
        "source body",
        "PRIVATE_RAW_BODY_DO_NOT_EXPOSE",
        "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
        "Private preview title",
        "Private preview summary",
        "Private Preview Actor",
        "private-preview@example.com",
        "private-file.pdf",
        "PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE",
        "sevt_fos081_",
        "evt_fos081_",
        "nact_fos081_",
        '"evidence_refs": [',
    )
    folded = output.casefold()
    for marker in forbidden:
        assert marker.casefold() not in folded


def _query(
    *,
    start_at: datetime,
    end_at: datetime,
    max_events: int = 100,
    include_synthetic: bool = False,
    sources: tuple[str, ...] = (),
) -> preview_script.NormalizationPreviewQuery:
    return preview_script.NormalizationPreviewQuery(
        start_at=start_at,
        end_at=end_at,
        max_events=max_events,
        include_synthetic=include_synthetic,
        sources=sources,
        output_format="json",
    )


async def _audit_log_count() -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(select(func.count()).select_from(AuditLog)) or 0
        )


class _ReadOnlySessionProxy:
    def __init__(self, session: Any) -> None:
        self._session = session

    async def execute(self, statement: Any, *args: object, **kwargs: object) -> Any:
        if statement.__class__.__name__ != "Select":
            raise AssertionError("normalization preview must execute SELECT only")
        return await self._session.execute(statement, *args, **kwargs)

    async def scalars(self, statement: Any, *args: object, **kwargs: object) -> Any:
        if statement.__class__.__name__ != "Select":
            raise AssertionError("normalization preview must execute SELECT only")
        return await self._session.scalars(statement, *args, **kwargs)

    async def scalar(self, statement: Any, *args: object, **kwargs: object) -> Any:
        if statement.__class__.__name__ != "Select":
            raise AssertionError("normalization preview must execute SELECT only")
        return await self._session.scalar(statement, *args, **kwargs)

    def add(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("normalization preview must not add rows")

    def add_all(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("normalization preview must not add rows")

    async def commit(self) -> None:
        raise AssertionError("normalization preview must not commit")

    async def flush(self) -> None:
        raise AssertionError("normalization preview must not flush")

    async def delete(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("normalization preview must not delete rows")


class _ReadOnlySessionFactory:
    def __init__(self) -> None:
        self._session: Any | None = None

    async def __aenter__(self) -> _ReadOnlySessionProxy:
        self._session = AsyncSessionLocal()
        return _ReadOnlySessionProxy(await self._session.__aenter__())

    async def __aexit__(self, *args: object) -> None:
        if self._session is not None:
            await self._session.__aexit__(*args)


async def _cleanup(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.triage_result_id.like(
                    f"atri_fos081_{unique}%"
                )
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(
                    f"nact_fos081_{unique}%"
                )
            )
        )
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_event_id.like(f"sevt_fos081_{unique}%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.event_id.like(f"evt_fos081_{unique}%")
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
    event_id = f"evt_fos081_{unique}"
    source_event_id = f"sevt_fos081_{unique}"
    async with AsyncSessionLocal() as session:
        session.add(
            IngestedEvent(
                event_id=event_id,
                event_type=values["event_type"],
                source_system=values["source_system"],
                source_object_id=values["source_object_id"],
                idempotency_key=f"idem_fos081_{unique}",
                correlation_id=f"corr_fos081_{unique}",
                trace_id=f"trace_fos081_{unique}",
                raw_object_ref=f"raw://private/fos081/{unique}.json",
                payload={
                    "title": "Private preview title must not print",
                    "summary": "Private preview summary must not print",
                    "raw_body": "PRIVATE_RAW_BODY_DO_NOT_EXPOSE",
                    "provider_payload": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                    "source_url": "https://private.example.test/fos081",
                },
                status="received",
                created_at=created_at,
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=source_event_id,
                source_event_key=f"{values['source_system']}:fos081:{unique}",
                ingested_event_id=event_id,
                event_type=values["event_type"],
                source_system=values["source_system"],
                source_object_type=values["source_object_type"],
                source_object_id=values["source_object_id"],
                source_event_ts=created_at,
                actor_external_id="private-preview@example.com",
                title="Private preview title must not print",
                summary="Private preview summary must not print",
                source_url="https://private.example.test/fos081",
                raw_object_ref=f"raw://private/fos081/{unique}.json",
                evidence_refs=[
                    {
                        "kind": "source_event",
                        "source_event_id": source_event_id,
                        "raw_object_ref": f"raw://private/fos081/{unique}.json",
                    }
                ],
                metadata_json={"trace_id": f"trace_fos081_{unique}"},
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
                activity_item_id=f"nact_fos081_{unique}",
                source_event_id=source_event_id,
                source="github",
                source_object_id=f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}",
                activity_type="pull_request.updated",
                title="Private preview title must not print",
                actor="Private Preview Actor",
                activity_created_at=created_at,
                project="Private Project",
                safe_summary="Private preview summary must not print",
                related_people=["Private Preview Actor", "private-preview@example.com"],
                related_jira_keys=["FOS-081"],
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
        preview_script,
        "build_stored_source_event_normalization_preview",
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
        preview_script.main(
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
        preview_script.main(
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
    assert preview_script.main([*base, "--max-events", "0"]) == 2
    assert (
        preview_script.main(
            [
                *base,
                "--max-events",
                str(preview_script.MAX_NORMALIZATION_PREVIEW_EVENTS + 1),
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

    with pytest.raises(preview_script.NormalizationPreviewBlockedError):
        await preview_script.build_stored_source_event_normalization_preview(
            _query(start_at=_utc(2149, 1, 1), end_at=_utc(2149, 1, 2)),
            session_factory=FailingSession,
            settings_override=SimpleNamespace(app_env="production"),
            environ={},
        )


async def test_empty_range_reports_no_source_events() -> None:
    await _ensure_seed_tables()
    before_count = await _audit_log_count()
    report = await preview_script.build_stored_source_event_normalization_preview(
        _query(start_at=_utc(2199, 1, 1), end_at=_utc(2199, 1, 2)),
        settings_override=_local_settings(),
        environ={},
    )

    assert report["scanned_source_event_count"] == 0
    assert report["source_events"]["total"] == 0
    assert report["recommended_next_action"] == "no_source_events_found"
    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_count
    _assert_safe_output(_serialized(report))
    _assert_safe_output(preview_script.format_text_report(report))


async def test_supported_no_marker_github_source_event_is_eligible() -> None:
    await _ensure_seed_tables()
    unique = f"github_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_source_event(unique, created_at=_utc(2149, 1, 3, 9))
        report = await preview_script.build_stored_source_event_normalization_preview(
            _query(start_at=_utc(2149, 1, 3), end_at=_utc(2149, 1, 4)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["source_events"]["total"] == 1
        assert report["source_events"]["synthetic_status"] == "no_synthetic_marker_detected"
        assert report["normalization_preview"]["eligible_for_projection_count"] == 1
        assert report["normalization_preview"]["no_marker_eligible_count"] == 1
        assert (
            report["normalization_preview"]["projected_activity"]["by_source"]
            == {"github": 1}
        )
        assert (
            report["normalization_preview"]["projected_activity"]["by_activity_type"]
            == {"pull_request.updated": 1}
        )
        assert (
            report["recommended_next_action"]
            == "review_projection_preview_before_local_normalization"
        )
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_source_filter_excludes_unselected_events_from_preview() -> None:
    await _ensure_seed_tables()
    drive_unique = f"source_drive_{uuid4().hex}"
    github_unique = f"source_github_{uuid4().hex}"
    for unique in (drive_unique, github_unique):
        await _cleanup(unique)
    try:
        await _insert_source_event(
            drive_unique,
            created_at=_utc(2149, 1, 3, 9),
            kind="drive",
        )
        await _insert_source_event(
            github_unique,
            created_at=_utc(2149, 1, 3, 10),
        )

        report = await preview_script.build_stored_source_event_normalization_preview(
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
        assert report["normalization_preview"]["eligible_for_projection_count"] == 1
        assert report["normalization_preview"]["projected_activity"]["by_source"] == {
            "drive": 1
        }
        assert report["normalization_preview"]["projected_activity"][
            "by_activity_type"
        ] == {"document.changed": 1}
        _assert_safe_output(_serialized(report))
    finally:
        for unique in (drive_unique, github_unique):
            await _cleanup(unique)


async def test_unsupported_source_event_is_counted_without_raw_detail() -> None:
    await _ensure_seed_tables()
    unique = f"unsupported_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 4, 9),
            kind="unsupported",
        )
        report = await preview_script.build_stored_source_event_normalization_preview(
            _query(start_at=_utc(2149, 1, 4), end_at=_utc(2149, 1, 5)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["normalization_preview"]["unsupported_for_projection_count"] == 1
        assert report["normalization_preview"]["eligible_for_projection_count"] == 0
        assert (
            report["recommended_next_action"]
            == "no_supported_source_events_for_normalization"
        )
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_already_normalized_source_event_is_not_eligible_again() -> None:
    await _ensure_seed_tables()
    unique = f"normalized_{uuid4().hex}"
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
        report = await preview_script.build_stored_source_event_normalization_preview(
            _query(start_at=_utc(2149, 1, 5), end_at=_utc(2149, 1, 6)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["normalization_preview"]["already_normalized_count"] == 1
        assert report["normalization_preview"]["eligible_for_projection_count"] == 0
        assert (
            report["existing_normalized_activity"]["total_linked_to_source_events"]
            == 1
        )
        assert (
            report["recommended_next_action"]
            == "proceed_to_normalized_activity_triage_readiness"
        )
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_synthetic_rows_are_excluded_by_default_and_included_explicitly() -> None:
    await _ensure_seed_tables()
    unique = f"synthetic_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 6, 9),
            kind="synthetic",
        )
        default_report = (
            await preview_script.build_stored_source_event_normalization_preview(
                _query(start_at=_utc(2149, 1, 6), end_at=_utc(2149, 1, 7)),
                settings_override=_local_settings(),
                environ={},
            )
        )
        included_report = (
            await preview_script.build_stored_source_event_normalization_preview(
                _query(
                    start_at=_utc(2149, 1, 6),
                    end_at=_utc(2149, 1, 7),
                    include_synthetic=True,
                ),
                settings_override=_local_settings(),
                environ={},
            )
        )

        assert default_report["source_events"]["synthetic_status"] == (
            "synthetic_local_dev_detected"
        )
        assert default_report["normalization_preview"]["synthetic_skipped_count"] == 1
        assert default_report["normalization_preview"]["unsupported_for_projection_count"] == 0
        assert default_report["recommended_next_action"] == (
            "rerun_with_include_synthetic_for_dev_preview_or_choose_no_marker_window"
        )
        assert included_report["source_events"]["synthetic_status"] == (
            "synthetic_local_dev_detected"
        )
        assert included_report["normalization_preview"]["synthetic_skipped_count"] == 0
        assert included_report["normalization_preview"]["unsupported_for_projection_count"] == 1
        _assert_safe_output(_serialized(default_report))
        _assert_safe_output(_serialized(included_report))
    finally:
        await _cleanup(unique)


async def test_mixed_preview_recommends_review_with_existing_counts() -> None:
    await _ensure_seed_tables()
    existing_unique = f"mixed_existing_{uuid4().hex}"
    eligible_unique = f"mixed_eligible_{uuid4().hex}"
    for unique in (existing_unique, eligible_unique):
        await _cleanup(unique)
    try:
        existing_source_event_id = await _insert_source_event(
            existing_unique,
            created_at=_utc(2149, 1, 7, 9),
        )
        await _insert_normalized_activity(
            existing_unique,
            source_event_id=existing_source_event_id,
            created_at=_utc(2149, 1, 7, 9),
        )
        await _insert_source_event(
            eligible_unique,
            created_at=_utc(2149, 1, 7, 10),
        )
        report = await preview_script.build_stored_source_event_normalization_preview(
            _query(start_at=_utc(2149, 1, 7), end_at=_utc(2149, 1, 8)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["normalization_preview"]["already_normalized_count"] == 1
        assert report["normalization_preview"]["eligible_for_projection_count"] == 1
        assert (
            report["recommended_next_action"]
            == "review_projection_preview_and_existing_normalized_counts"
        )
        _assert_safe_output(_serialized(report))
    finally:
        for unique in (existing_unique, eligible_unique):
            await _cleanup(unique)


async def test_max_events_bound_fails_before_processing() -> None:
    await _ensure_seed_tables()
    first_unique = f"bound_a_{uuid4().hex}"
    second_unique = f"bound_b_{uuid4().hex}"
    for unique in (first_unique, second_unique):
        await _cleanup(unique)
    try:
        await _insert_source_event(first_unique, created_at=_utc(2149, 1, 8, 9))
        await _insert_source_event(second_unique, created_at=_utc(2149, 1, 8, 10))
        with pytest.raises(preview_script.NormalizationPreviewInputError):
            await preview_script.build_stored_source_event_normalization_preview(
                _query(
                    start_at=_utc(2149, 1, 8),
                    end_at=_utc(2149, 1, 9),
                    max_events=1,
                ),
                settings_override=_local_settings(),
                environ={},
            )
    finally:
        for unique in (first_unique, second_unique):
            await _cleanup(unique)


async def test_preview_path_uses_read_only_db_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    await _ensure_seed_tables()

    def forbidden_record(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("preview must not write normalized activity")

    def forbidden_triage(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("preview must not triage activity")

    monkeypatch.setattr(
        "app.services.normalized_activity.record_normalized_activity_item",
        forbidden_record,
    )
    monkeypatch.setattr(
        "app.services.attention_results.triage_normalized_activity_item",
        forbidden_triage,
    )
    before_count = await _audit_log_count()

    report = await preview_script.build_stored_source_event_normalization_preview(
        _query(start_at=_utc(2199, 2, 1), end_at=_utc(2199, 2, 2)),
        session_factory=_ReadOnlySessionFactory,
        settings_override=_local_settings(),
        environ={},
    )

    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_count
    _assert_safe_output(_serialized(report))
