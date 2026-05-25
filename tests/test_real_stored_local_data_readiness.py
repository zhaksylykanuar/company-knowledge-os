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
from scripts import report_real_stored_local_data_readiness as readiness_script
from scripts.seed_local_persisted_attention_digest import (
    _expected_payloads as synthetic_seed_payloads,
)
from tests.test_seed_local_persisted_attention_digest import _ensure_seed_tables

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "report_real_stored_local_data_readiness.py"


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
        "PRIVATE_PROMPT_DO_NOT_EXPOSE",
        "Private readiness title",
        "Private readiness summary",
        "Private readiness action",
        "Private Person",
        "private@example.com",
        "private-file.pdf",
        '"evidence_refs": [',
    )
    folded = output.casefold()
    for marker in forbidden:
        assert marker.casefold() not in folded


def _query(
    *,
    start_at: datetime,
    end_at: datetime,
    window_size_hours: int = 24,
    max_windows: int = 31,
    include_empty: bool = False,
) -> readiness_script.RealStoredReadinessQuery:
    return readiness_script.RealStoredReadinessQuery(
        start_at=start_at,
        end_at=end_at,
        window_size_hours=window_size_hours,
        max_windows=max_windows,
        include_empty=include_empty,
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
            raise AssertionError("readiness report must execute SELECT statements only")
        return await self._session.execute(statement, *args, **kwargs)

    async def scalar(self, statement: Any, *args: object, **kwargs: object) -> Any:
        if statement.__class__.__name__ != "Select":
            raise AssertionError("readiness report must execute SELECT statements only")
        return await self._session.scalar(statement, *args, **kwargs)

    async def scalars(self, statement: Any, *args: object, **kwargs: object) -> Any:
        if statement.__class__.__name__ != "Select":
            raise AssertionError("readiness report must execute SELECT statements only")
        return await self._session.scalars(statement, *args, **kwargs)

    def add(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("readiness report must not add rows")

    def add_all(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("readiness report must not add rows")

    async def commit(self) -> None:
        raise AssertionError("readiness report must not commit")

    async def flush(self) -> None:
        raise AssertionError("readiness report must not flush")

    async def delete(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("readiness report must not delete rows")


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
                    f"atri_fos080_{unique}%"
                )
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(
                    f"nact_fos080_{unique}%"
                )
            )
        )
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_event_id.like(f"sevt_fos080_{unique}%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.event_id.like(f"evt_fos080_{unique}%")
            )
        )
        await session.commit()


def _source_values(unique: str, *, synthetic: bool) -> dict[str, str]:
    if synthetic:
        source_object_id = (
            f"{readiness_script.SYNTHETIC_SOURCE_OBJECT_PREFIX}{unique}:safe"
        )
        return {
            "source_system": "internal",
            "source_object_type": "system_event",
            "source_object_id": source_object_id,
            "event_type": "internal.system_event.recorded",
            "activity_type": "synthetic.persisted_attention_digest.seed",
        }
    return {
        "source_system": "github",
        "source_object_type": "pull_request",
        "source_object_id": f"fos080.local.no_marker.{unique}",
        "event_type": "github.pull_request.opened",
        "activity_type": "github.pull_request.opened",
    }


async def _insert_source_event(
    unique: str,
    *,
    created_at: datetime,
    synthetic: bool = False,
) -> str:
    values = _source_values(unique, synthetic=synthetic)
    event_id = f"evt_fos080_{unique}"
    source_event_id = f"sevt_fos080_{unique}"
    async with AsyncSessionLocal() as session:
        session.add(
            IngestedEvent(
                event_id=event_id,
                event_type=values["event_type"],
                source_system=values["source_system"],
                source_object_id=values["source_object_id"],
                idempotency_key=f"idem_fos080_{unique}",
                correlation_id=f"corr_fos080_{unique}",
                trace_id=f"trace_fos080_{unique}",
                raw_object_ref=f"raw://private/fos080/{unique}.json",
                payload={
                    "title": "Private readiness title must not print",
                    "summary": "Private readiness summary must not print",
                    "raw_body": "PRIVATE_RAW_BODY_DO_NOT_EXPOSE",
                    "provider_payload": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                    "source_url": "https://private.example.test/fos080",
                },
                status="received",
                created_at=created_at,
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=source_event_id,
                source_event_key=f"{values['source_system']}:fos080:{unique}",
                ingested_event_id=event_id,
                event_type=values["event_type"],
                source_system=values["source_system"],
                source_object_type=values["source_object_type"],
                source_object_id=values["source_object_id"],
                source_event_ts=created_at,
                actor_external_id="private@example.com",
                title="Private readiness title must not print",
                summary="Private readiness summary must not print",
                source_url="https://private.example.test/fos080",
                raw_object_ref=f"raw://private/fos080/{unique}.json",
                evidence_refs=[
                    {
                        "kind": "source_event",
                        "source_event_id": source_event_id,
                        "raw_object_ref": f"raw://private/fos080/{unique}.json",
                    }
                ],
                metadata_json={"trace_id": f"trace_fos080_{unique}"},
                created_at=created_at,
            )
        )
        await session.commit()
    return source_event_id


async def _insert_normalized_activity(
    unique: str,
    *,
    created_at: datetime,
    synthetic: bool = False,
    source_event_id: str | None = None,
) -> str:
    values = _source_values(unique, synthetic=synthetic)
    activity_item_id = f"nact_fos080_{unique}"
    async with AsyncSessionLocal() as session:
        session.add(
            NormalizedActivityItemRecord(
                activity_item_id=activity_item_id,
                source_event_id=source_event_id,
                source=values["source_system"],
                source_object_id=values["source_object_id"],
                activity_type=values["activity_type"],
                title="Private readiness title must not print",
                actor="Private Person",
                activity_created_at=created_at,
                project="Private Project",
                safe_summary="Private readiness summary must not print",
                related_people=["Private Person", "private@example.com"],
                related_jira_keys=["FOS-080"],
                related_prs=["private-pr"],
                related_files=["private-file.pdf"],
                evidence_refs=[
                    {
                        "kind": "source_event",
                        "raw_object_ref": f"raw://private/fos080/{unique}.json",
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
    created_at: datetime,
    synthetic: bool = False,
    activity_item_id: str | None = None,
    visible: bool = True,
) -> str:
    values = _source_values(unique, synthetic=synthetic)
    triage_result_id = f"atri_fos080_{unique}"
    async with AsyncSessionLocal() as session:
        session.add(
            AttentionTriageResultRecord(
                triage_result_id=triage_result_id,
                source=values["source_system"],
                source_object_id=values["source_object_id"],
                activity_item_id=activity_item_id,
                attention_class=(
                    "requires_my_attention" if visible else "no_action_required"
                ),
                priority="high" if visible else "low",
                show_in_digest=visible,
                confidence=0.99,
                reason="Private readiness reason must not print.",
                recommended_action="Private readiness action must not print.",
                owner="Private Person",
                deadline=None,
                evidence_refs=[
                    {
                        "kind": "source_event",
                        "raw_object_ref": f"raw://private/fos080/{unique}.json",
                    }
                ],
                created_at=created_at,
            )
        )
        await session.commit()
    return triage_result_id


def test_missing_required_args_fail_safely() -> None:
    missing_start = _run_script("--end-at", "2149-01-02T00:00:00+00:00")
    missing_end = _run_script("--start-at", "2149-01-01T00:00:00+00:00")

    assert missing_start.returncode == 2
    assert "--start-at" in missing_start.stderr
    assert missing_end.returncode == 2
    assert "--end-at" in missing_end.stderr
    _assert_safe_output(missing_start.stdout + missing_start.stderr)
    _assert_safe_output(missing_end.stdout + missing_end.stderr)


def test_invalid_inputs_fail_before_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden_report(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid input must fail before DB execution")

    monkeypatch.setattr(
        readiness_script,
        "build_real_stored_local_data_readiness_report",
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
    naive_start = readiness_script.main(
        [
            "--start-at",
            "2149-01-01T00:00:00",
            "--end-at",
            "2149-01-02T00:00:00+00:00",
            "--format",
            "json",
        ]
    )
    reversed_range = readiness_script.main(
        [
            "--start-at",
            "2149-01-02T00:00:00+00:00",
            "--end-at",
            "2149-01-01T00:00:00+00:00",
            "--format",
            "json",
        ]
    )
    bad_window_size = readiness_script.main([*base, "--window-size-hours", "0"])
    too_high_window_size = readiness_script.main(
        [
            *base,
            "--window-size-hours",
            str(readiness_script.MAX_WINDOW_SIZE_HOURS + 1),
        ]
    )
    bad_max_windows = readiness_script.main([*base, "--max-windows", "0"])
    too_high_max_windows = readiness_script.main(
        [*base, "--max-windows", str(readiness_script.MAX_READINESS_WINDOWS + 1)]
    )
    too_many_windows = readiness_script.main(
        [
            "--start-at",
            "2149-01-01T00:00:00+00:00",
            "--end-at",
            "2149-01-04T00:00:00+00:00",
            "--window-size-hours",
            "24",
            "--max-windows",
            "2",
            "--format",
            "json",
        ]
    )

    assert naive_start == 2
    assert reversed_range == 2
    assert bad_window_size == 2
    assert too_high_window_size == 2
    assert bad_max_windows == 2
    assert too_high_max_windows == 2
    assert too_many_windows == 2


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
        _assert_safe_output(result.stdout + result.stderr)


async def test_production_like_environment_is_refused_before_db_write() -> None:
    class FailingSession:
        async def __aenter__(self) -> "FailingSession":
            raise AssertionError("production-like env must fail before DB access")

        async def __aexit__(self, *_args: object) -> None:
            return None

    with pytest.raises(readiness_script.RealStoredReadinessBlockedError):
        await readiness_script.build_real_stored_local_data_readiness_report(
            _query(start_at=_utc(2149, 1, 1), end_at=_utc(2149, 1, 2)),
            session_factory=FailingSession,
            settings_override=SimpleNamespace(app_env="production"),
            environ={},
        )


async def test_empty_windows_are_omitted_or_included_safely() -> None:
    await _ensure_seed_tables()
    before_count = await _audit_log_count()

    omitted = await readiness_script.build_real_stored_local_data_readiness_report(
        _query(start_at=_utc(2199, 1, 1), end_at=_utc(2199, 1, 2)),
        settings_override=_local_settings(),
        environ={},
    )
    included = await readiness_script.build_real_stored_local_data_readiness_report(
        _query(
            start_at=_utc(2199, 1, 1),
            end_at=_utc(2199, 1, 2),
            include_empty=True,
        ),
        settings_override=_local_settings(),
        environ={},
    )

    assert omitted["returned_window_count"] == 0
    assert omitted["windows"] == []
    assert included["returned_window_count"] == 1
    window = included["windows"][0]
    assert window["source_events"]["total"] == 0
    assert window["normalized_activity"]["total"] == 0
    assert window["attention_results"]["total"] == 0
    assert window["synthetic_status"] == "unknown"
    assert window["recommended_next_action"] == "no_real_stored_candidates_found"
    assert included["safety"]["read_only"] is True
    assert included["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_count
    _assert_safe_output(_serialized(omitted))
    _assert_safe_output(_serialized(included))
    _assert_safe_output(readiness_script.format_text_report(included))


async def test_report_path_uses_read_only_db_operations() -> None:
    await _ensure_seed_tables()
    before_count = await _audit_log_count()

    report = await readiness_script.build_real_stored_local_data_readiness_report(
        _query(
            start_at=_utc(2199, 2, 1),
            end_at=_utc(2199, 2, 2),
            include_empty=True,
        ),
        session_factory=_ReadOnlySessionFactory,
        settings_override=_local_settings(),
        environ={},
    )

    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_count
    _assert_safe_output(_serialized(report))


async def test_source_only_window_recommends_projection() -> None:
    await _ensure_seed_tables()
    unique = f"source_{uuid4().hex}"
    start_at = _utc(2149, 1, 2)
    end_at = _utc(2149, 1, 3)
    await _cleanup(unique)
    try:
        await _insert_source_event(unique, created_at=_utc(2149, 1, 2, 9))
        report = await readiness_script.build_real_stored_local_data_readiness_report(
            _query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        window = report["windows"][0]
        assert window["source_events"]["total"] == 1
        assert window["normalized_activity"]["total"] == 0
        assert window["attention_results"]["total"] == 0
        assert window["pipeline_coverage"]["source_only_count"] == 1
        assert (
            window["recommended_next_action"]
            == "project_source_events_before_real_pilot"
        )
        assert window["synthetic_status"] == "no_synthetic_marker_detected"
        assert report["aggregate_summary"]["needs_normalization_window_count"] == 1
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_normalized_without_attention_recommends_triage() -> None:
    await _ensure_seed_tables()
    unique = f"norm_{uuid4().hex}"
    start_at = _utc(2149, 1, 3)
    end_at = _utc(2149, 1, 4)
    await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 3, 9),
        )
        await _insert_normalized_activity(
            unique,
            created_at=_utc(2149, 1, 3, 9),
            source_event_id=source_event_id,
        )
        report = await readiness_script.build_real_stored_local_data_readiness_report(
            _query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        window = report["windows"][0]
        assert window["source_events"]["total"] == 1
        assert window["normalized_activity"]["total"] == 1
        assert window["attention_results"]["total"] == 0
        assert window["pipeline_coverage"]["source_with_normalized_count"] == 1
        assert (
            window["recommended_next_action"]
            == "triage_normalized_activity_before_real_pilot"
        )
        assert report["aggregate_summary"]["needs_attention_triage_window_count"] == 1
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_hidden_attention_results_recommend_visibility_review() -> None:
    await _ensure_seed_tables()
    unique = f"hidden_{uuid4().hex}"
    start_at = _utc(2149, 1, 4)
    end_at = _utc(2149, 1, 5)
    await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 4, 9),
        )
        activity_item_id = await _insert_normalized_activity(
            unique,
            created_at=_utc(2149, 1, 4, 9),
            source_event_id=source_event_id,
        )
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 1, 4, 9),
            activity_item_id=activity_item_id,
            visible=False,
        )
        report = await readiness_script.build_real_stored_local_data_readiness_report(
            _query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        window = report["windows"][0]
        assert window["attention_results"]["total"] == 1
        assert window["attention_results"]["visible_persisted_attention_candidate_count"] == 0
        assert window["attention_results"]["hidden_count"] == 1
        assert (
            window["recommended_next_action"]
            == "review_attention_results_visibility_before_real_pilot"
        )
        assert (
            window["pipeline_coverage"]["pipeline_ready_for_manual_digest_pilot"]
            is False
        )
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_visible_no_marker_attention_recommends_manual_review() -> None:
    await _ensure_seed_tables()
    unique = f"visible_{uuid4().hex}"
    start_at = _utc(2149, 1, 5)
    end_at = _utc(2149, 1, 6)
    await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            unique,
            created_at=_utc(2149, 1, 5, 9),
        )
        activity_item_id = await _insert_normalized_activity(
            unique,
            created_at=_utc(2149, 1, 5, 9),
            source_event_id=source_event_id,
        )
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 1, 5, 9),
            activity_item_id=activity_item_id,
        )
        report = await readiness_script.build_real_stored_local_data_readiness_report(
            _query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        window = report["windows"][0]
        assert window["attention_results"]["visible_no_marker_count"] == 1
        assert window["synthetic_status"] == "no_synthetic_marker_detected"
        assert (
            window["pipeline_coverage"]["pipeline_ready_for_manual_digest_pilot"]
            is True
        )
        assert (
            window["recommended_next_action"]
            == "review_no_marker_window_before_manual_pilot"
        )
        assert (
            report["aggregate_summary"][
                "ready_for_manual_digest_pilot_window_count"
            ]
            == 1
        )
        text = readiness_script.format_text_report(report)
        assert "review_no_marker_window_before_manual_pilot" in text
        _assert_safe_output(_serialized(report))
        _assert_safe_output(text)
    finally:
        await _cleanup(unique)


async def test_synthetic_and_mixed_marker_windows_are_labeled_safely() -> None:
    await _ensure_seed_tables()
    synthetic_unique = f"synthetic_{uuid4().hex}"
    mixed_synthetic_unique = f"mixed_syn_{uuid4().hex}"
    mixed_no_marker_unique = f"mixed_real_{uuid4().hex}"
    start_at = _utc(2149, 1, 6)
    end_at = _utc(2149, 1, 8)
    for unique in (synthetic_unique, mixed_synthetic_unique, mixed_no_marker_unique):
        await _cleanup(unique)
    try:
        await _insert_attention_result(
            synthetic_unique,
            created_at=_utc(2149, 1, 6, 9),
            synthetic=True,
        )
        await _insert_attention_result(
            mixed_synthetic_unique,
            created_at=_utc(2149, 1, 7, 9),
            synthetic=True,
        )
        await _insert_attention_result(
            mixed_no_marker_unique,
            created_at=_utc(2149, 1, 7, 10),
            synthetic=False,
        )
        report = await readiness_script.build_real_stored_local_data_readiness_report(
            _query(
                start_at=start_at,
                end_at=end_at,
                max_windows=2,
            ),
            settings_override=_local_settings(),
            environ={},
        )

        windows = {window["start_at"]: window for window in report["windows"]}
        synthetic_window = windows["2149-01-06T00:00:00+00:00"]
        mixed_window = windows["2149-01-07T00:00:00+00:00"]
        assert synthetic_window["synthetic_status"] == "synthetic_local_dev_detected"
        assert (
            synthetic_window["recommended_next_action"]
            == "continue_synthetic_manual_pilot_or_find_non_synthetic_window"
        )
        assert mixed_window["synthetic_status"] == "mixed"
        assert (
            mixed_window["recommended_next_action"]
            == "review_no_marker_window_before_manual_pilot"
        )
        assert report["aggregate_summary"]["synthetic_local_dev_window_count"] == 1
        assert report["aggregate_summary"]["mixed_marker_window_count"] == 1
        _assert_safe_output(_serialized(report))
    finally:
        for unique in (
            synthetic_unique,
            mixed_synthetic_unique,
            mixed_no_marker_unique,
        ):
            await _cleanup(unique)


async def test_existing_seed_marker_shape_is_detected_without_running_seed() -> None:
    await _ensure_seed_tables()
    unique = f"seedshape_{uuid4().hex}"
    start_at = _utc(2149, 1, 8)
    end_at = _utc(2149, 1, 9)
    await _cleanup(unique)
    payloads = synthetic_seed_payloads(
        type(
            "SeedLike",
            (),
            {
                "sample_id": unique,
                "created_at": _utc(2149, 1, 8, 9),
            },
        )()
    )
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                AttentionTriageResultRecord(
                    triage_result_id=f"atri_fos080_{unique}",
                    source="internal",
                    source_object_id=payloads["source_object_id"],
                    activity_item_id=None,
                    attention_class="requires_my_attention",
                    priority="high",
                    show_in_digest=True,
                    confidence=0.99,
                    reason="Private readiness reason must not print.",
                    recommended_action="Private readiness action must not print.",
                    owner=None,
                    deadline=None,
                    evidence_refs=[],
                    created_at=_utc(2149, 1, 8, 9),
                )
            )
            await session.commit()
        report = await readiness_script.build_real_stored_local_data_readiness_report(
            _query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["windows"][0]["synthetic_status"] == "synthetic_local_dev_detected"
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)
