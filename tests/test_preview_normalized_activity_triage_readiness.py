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
from scripts import preview_normalized_activity_triage_readiness as readiness_script
from scripts import preview_stored_source_event_normalization as preview_script
from tests.test_seed_local_persisted_attention_digest import _ensure_seed_tables

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "preview_normalized_activity_triage_readiness.py"


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
    sources: tuple[str, ...] = (),
) -> readiness_script.TriageReadinessQuery:
    return readiness_script.TriageReadinessQuery(
        start_at=start_at,
        end_at=end_at,
        max_items=max_items,
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
        "Private triage title",
        "Private triage summary",
        "Private Triage Actor",
        "private-triage@example.com",
        "private-file.pdf",
        "PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE",
        "nact_fos083_",
        "atri_fos083_",
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


async def _attention_result_count_for_unique(unique: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count(AttentionTriageResultRecord.id)).where(
                    AttentionTriageResultRecord.triage_result_id.like(
                        f"atri_fos083_{unique}%"
                    )
                )
            )
            or 0
        )


async def _cleanup(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.triage_result_id.like(
                    f"atri_fos083_{unique}%"
                )
            )
        )
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.activity_item_id.like(
                    f"nact_fos083_{unique}%"
                )
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(
                    f"nact_fos083_{unique}%"
                )
            )
        )
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_event_id.like(f"sevt_fos083_{unique}%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.event_id.like(f"evt_fos083_{unique}%")
            )
        )
        await session.commit()


async def _insert_normalized_activity(
    unique: str,
    *,
    created_at: datetime,
    kind: str = "github",
    actor: str = "Private Triage Actor",
) -> str:
    activity_item_id = f"nact_fos083_{unique}"
    if kind == "synthetic":
        source = "internal"
        source_object_id = f"{preview_script.SYNTHETIC_SOURCE_OBJECT_PREFIX}{unique}:safe"
        activity_type = "synthetic.persisted_attention_digest.seed"
    elif kind == "drive":
        source = "drive"
        source_object_id = f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}"
        activity_type = "document.changed"
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
                title="Private triage title must not print",
                actor=actor,
                activity_created_at=created_at,
                project="Private Project",
                safe_summary="Private triage summary must not print",
                related_people=["Private Triage Actor", "private-triage@example.com"],
                related_jira_keys=["FOS-083"],
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
                triage_result_id=f"atri_fos083_{unique}",
                source="github",
                source_object_id=f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{unique}",
                activity_item_id=activity_item_id,
                attention_class="review_optional",
                priority="low",
                show_in_digest=True,
                confidence=0.5,
                reason="Private triage reason must not print",
                recommended_action="Private triage action must not print",
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


class _ReadOnlySessionProxy:
    def __init__(self, session: object) -> None:
        self._session = session

    async def execute(self, statement: object, *args: object, **kwargs: object) -> object:
        if statement.__class__.__name__ != "Select":
            raise AssertionError("triage readiness preview must execute SELECT only")
        return await self._session.execute(statement, *args, **kwargs)  # type: ignore[attr-defined]

    async def scalars(self, statement: object, *args: object, **kwargs: object) -> object:
        if statement.__class__.__name__ != "Select":
            raise AssertionError("triage readiness preview must execute SELECT only")
        return await self._session.scalars(statement, *args, **kwargs)  # type: ignore[attr-defined]

    async def scalar(self, statement: object, *args: object, **kwargs: object) -> object:
        if statement.__class__.__name__ != "Select":
            raise AssertionError("triage readiness preview must execute SELECT only")
        return await self._session.scalar(statement, *args, **kwargs)  # type: ignore[attr-defined]

    def add(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("triage readiness preview must not add rows")

    def add_all(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("triage readiness preview must not add rows")

    async def commit(self) -> None:
        raise AssertionError("triage readiness preview must not commit")

    async def flush(self) -> None:
        raise AssertionError("triage readiness preview must not flush")

    async def delete(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("triage readiness preview must not delete rows")


class _ReadOnlySessionFactory:
    def __init__(self) -> None:
        self._session: object | None = None

    async def __aenter__(self) -> _ReadOnlySessionProxy:
        self._session = AsyncSessionLocal()
        return _ReadOnlySessionProxy(await self._session.__aenter__())  # type: ignore[attr-defined]

    async def __aexit__(self, *args: object) -> None:
        if self._session is not None:
            await self._session.__aexit__(*args)  # type: ignore[attr-defined]


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
        readiness_script,
        "build_normalized_activity_triage_readiness_preview",
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
        readiness_script.main(
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
        readiness_script.main(
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
    assert readiness_script.main([*base, "--max-items", "0"]) == 2
    assert (
        readiness_script.main(
            [
                *base,
                "--max-items",
                str(readiness_script.MAX_TRIAGE_READINESS_ITEMS + 1),
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

    with pytest.raises(readiness_script.TriageReadinessBlockedError):
        await readiness_script.build_normalized_activity_triage_readiness_preview(
            _query(start_at=_utc(2149, 1, 1), end_at=_utc(2149, 1, 2)),
            session_factory=FailingSession,
            settings_override=SimpleNamespace(app_env="production"),
            environ={},
        )


async def test_empty_range_reports_no_normalized_activity() -> None:
    await _ensure_seed_tables()
    before_audit = await _audit_log_count()
    report = await readiness_script.build_normalized_activity_triage_readiness_preview(
        _query(start_at=_utc(2199, 1, 1), end_at=_utc(2199, 1, 2)),
        settings_override=_local_settings(),
        environ={},
    )

    assert report["scanned_normalized_activity_count"] == 0
    assert report["normalized_activity"]["total"] == 0
    assert report["recommended_next_action"] == "normalize_source_events_before_triage"
    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert report["safety"]["attention_results_created"] is False
    assert await _audit_log_count() == before_audit
    _assert_safe_output(_serialized(report))
    _assert_safe_output(readiness_script.format_text_report(report))


async def test_untriaged_no_marker_activity_is_eligible_for_provider_free_triage() -> None:
    await _ensure_seed_tables()
    unique = f"github_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_normalized_activity(unique, created_at=_utc(2149, 1, 3, 9))
        report = await readiness_script.build_normalized_activity_triage_readiness_preview(
            _query(start_at=_utc(2149, 1, 3), end_at=_utc(2149, 1, 4)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["normalized_activity"]["total"] == 1
        assert report["normalized_activity"]["synthetic_status"] == (
            "no_synthetic_marker_detected"
        )
        assert report["triage_readiness"]["untriaged_count"] == 1
        assert (
            report["triage_readiness"]["eligible_for_provider_free_triage_count"]
            == 1
        )
        assert report["triage_readiness"]["no_marker_eligible_count"] == 1
        assert report["projected_provider_free_triage"]["available"] is True
        assert report["projected_provider_free_triage"]["by_attention_class"] == {
            "review_optional": 1
        }
        assert report["projected_provider_free_triage"]["by_priority"] == {"low": 1}
        assert report["projected_provider_free_triage"]["visible_candidate_count"] == 1
        assert report["projected_provider_free_triage"]["hidden_count"] == 0
        assert (
            report["recommended_next_action"]
            == "review_triage_readiness_before_local_provider_free_triage"
        )
        assert await _attention_result_count_for_unique(unique) == 0
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_source_filter_excludes_unselected_activity_from_readiness_preview() -> None:
    await _ensure_seed_tables()
    drive_unique = f"source_drive_{uuid4().hex}"
    github_unique = f"source_github_{uuid4().hex}"
    for unique in (drive_unique, github_unique):
        await _cleanup(unique)
    try:
        await _insert_normalized_activity(
            drive_unique,
            created_at=_utc(2149, 1, 3, 9),
            kind="drive",
        )
        await _insert_normalized_activity(
            github_unique,
            created_at=_utc(2149, 1, 3, 10),
        )

        report = await readiness_script.build_normalized_activity_triage_readiness_preview(
            _query(
                start_at=_utc(2149, 1, 3),
                end_at=_utc(2149, 1, 4),
                sources=("drive",),
            ),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["sources"] == ["drive"]
        assert report["normalized_activity"]["total"] == 1
        assert report["normalized_activity"]["by_source"] == {"drive": 1}
        assert report["triage_readiness"]["untriaged_count"] == 1
        assert (
            report["triage_readiness"]["eligible_for_provider_free_triage_count"]
            == 1
        )
        assert report["projected_provider_free_triage"]["by_attention_class"] == {
            "review_optional": 1
        }
        _assert_safe_output(_serialized(report))
    finally:
        for unique in (drive_unique, github_unique):
            await _cleanup(unique)


async def test_already_triaged_activity_is_counted_and_not_eligible_again() -> None:
    await _ensure_seed_tables()
    unique = f"triaged_{uuid4().hex}"
    await _cleanup(unique)
    try:
        activity_item_id = await _insert_normalized_activity(
            unique,
            created_at=_utc(2149, 1, 4, 9),
        )
        await _insert_attention_result(
            unique,
            activity_item_id=activity_item_id,
            created_at=_utc(2149, 1, 4, 10),
        )
        report = await readiness_script.build_normalized_activity_triage_readiness_preview(
            _query(start_at=_utc(2149, 1, 4), end_at=_utc(2149, 1, 5)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["triage_readiness"]["already_triaged_count"] == 1
        assert report["triage_readiness"]["eligible_for_provider_free_triage_count"] == 0
        assert report["projected_provider_free_triage"]["visible_candidate_count"] == 0
        assert (
            report["recommended_next_action"]
            == "run_real_stored_local_data_readiness_report"
        )
        assert await _attention_result_count_for_unique(unique) == 1
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_synthetic_rows_are_excluded_by_default_and_included_explicitly() -> None:
    await _ensure_seed_tables()
    unique = f"synthetic_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_normalized_activity(
            unique,
            created_at=_utc(2149, 1, 5, 9),
            kind="synthetic",
        )
        default_report = (
            await readiness_script.build_normalized_activity_triage_readiness_preview(
                _query(start_at=_utc(2149, 1, 5), end_at=_utc(2149, 1, 6)),
                settings_override=_local_settings(),
                environ={},
            )
        )
        included_report = (
            await readiness_script.build_normalized_activity_triage_readiness_preview(
                _query(
                    start_at=_utc(2149, 1, 5),
                    end_at=_utc(2149, 1, 6),
                    include_synthetic=True,
                ),
                settings_override=_local_settings(),
                environ={},
            )
        )

        assert default_report["normalized_activity"]["synthetic_status"] == (
            "synthetic_local_dev_detected"
        )
        assert default_report["triage_readiness"]["synthetic_skipped_count"] == 1
        assert default_report["triage_readiness"]["eligible_for_provider_free_triage_count"] == 0
        assert default_report["recommended_next_action"] == (
            "rerun_with_include_synthetic_for_dev_preview_or_choose_no_marker_window"
        )
        assert included_report["normalized_activity"]["synthetic_status"] == (
            "synthetic_local_dev_detected"
        )
        assert included_report["triage_readiness"]["synthetic_skipped_count"] == 0
        assert included_report["triage_readiness"]["synthetic_eligible_count"] == 1
        assert (
            included_report["triage_readiness"][
                "eligible_for_provider_free_triage_count"
            ]
            == 1
        )
        _assert_safe_output(_serialized(default_report))
        _assert_safe_output(_serialized(included_report))
    finally:
        await _cleanup(unique)


async def test_activity_from_user_projects_waiting_external_counts() -> None:
    await _ensure_seed_tables()
    unique = f"from_user_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_normalized_activity(
            unique,
            created_at=_utc(2149, 1, 6, 9),
            actor="me",
        )
        report = await readiness_script.build_normalized_activity_triage_readiness_preview(
            _query(start_at=_utc(2149, 1, 6), end_at=_utc(2149, 1, 7)),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["projected_provider_free_triage"]["by_attention_class"] == {
            "waiting_on_external": 1
        }
        assert report["projected_provider_free_triage"]["by_priority"] == {"low": 1}
        assert report["projected_provider_free_triage"]["visible_candidate_count"] == 1
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_max_items_bound_fails_before_processing() -> None:
    await _ensure_seed_tables()
    first_unique = f"bound_a_{uuid4().hex}"
    second_unique = f"bound_b_{uuid4().hex}"
    for unique in (first_unique, second_unique):
        await _cleanup(unique)
    try:
        await _insert_normalized_activity(
            first_unique,
            created_at=_utc(2149, 1, 7, 9),
        )
        await _insert_normalized_activity(
            second_unique,
            created_at=_utc(2149, 1, 7, 10),
        )
        with pytest.raises(readiness_script.TriageReadinessInputError):
            await readiness_script.build_normalized_activity_triage_readiness_preview(
                _query(
                    start_at=_utc(2149, 1, 7),
                    end_at=_utc(2149, 1, 8),
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


async def test_preview_path_uses_read_only_db_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_seed_tables()

    def forbidden_triage(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("readiness preview must not write triage results")

    def forbidden_send(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("readiness preview must not send messages")

    monkeypatch.setattr(
        "app.services.attention_results.triage_normalized_activity_item",
        forbidden_triage,
    )
    monkeypatch.setattr(
        "app.services.telegram_delivery.send_telegram_plain_text",
        forbidden_send,
    )
    before_audit = await _audit_log_count()

    report = await readiness_script.build_normalized_activity_triage_readiness_preview(
        _query(start_at=_utc(2199, 2, 1), end_at=_utc(2199, 2, 2)),
        session_factory=_ReadOnlySessionFactory,
        settings_override=_local_settings(),
        environ={},
    )

    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert report["safety"]["triage_write_invoked"] is False
    assert report["safety"]["telegram_invoked"] is False
    assert report["safety"]["openai_invoked"] is False
    assert report["safety"]["live_api_calls"] is False
    assert await _audit_log_count() == before_audit
    _assert_safe_output(_serialized(report))
