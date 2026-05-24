from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.attention_models import AttentionTriageResultRecord
from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import AuditLog, IngestedEvent
from app.services.digest import build_persisted_attention_digest_read_model
from scripts import seed_local_persisted_attention_digest as seed_script

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "seed_local_persisted_attention_digest.py"


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


async def _ensure_seed_tables() -> None:
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
        await conn.run_sync(AuditLog.__table__.create, checkfirst=True)


async def _cleanup_seed(query: seed_script.SeedQuery) -> None:
    expected = seed_script._expected_payloads(query)
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.triage_result_id
                == expected["triage_result_id"]
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id
                == expected["activity_item_id"]
            )
        )
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.ingested_event_id == expected["event_id"]
            )
        )
        await session.execute(
            delete(IngestedEvent).where(IngestedEvent.event_id == expected["event_id"])
        )
        await session.commit()


def _query(
    *,
    sample_id: str | None = None,
    created_at: datetime | None = None,
) -> seed_script.SeedQuery:
    return seed_script.SeedQuery(
        sample_id=sample_id or f"fos071-{uuid4().hex}",
        created_at=created_at or _utc(2141, 1, 1, 9),
        confirm_local_seed=seed_script.CONFIRM_LOCAL_SEED_PHRASE,
        output_format="json",
    )


def _local_settings() -> SimpleNamespace:
    return SimpleNamespace(app_env="local")


def _assert_safe_serialized(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True).casefold()
    forbidden = (
        "rendered_text",
        "chunk text",
        "bot_token",
        "chat_id",
        "webhook",
        "raw_payload",
        "provider_payload",
        "source_payload",
        "prompt",
        "secret",
        "token_value",
    )
    for marker in forbidden:
        assert marker not in serialized


def test_cli_rejects_missing_required_args_without_db_write() -> None:
    result = _run_script("--sample-id", "missing-created-at")

    assert result.returncode == 2
    assert "--created-at" in result.stderr
    assert "secret" not in result.stdout.casefold() + result.stderr.casefold()


def test_input_validation_fails_before_seed_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_execute(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid input must fail before DB execution")

    monkeypatch.setattr(seed_script, "execute_seed", forbidden_execute)

    wrong_confirm = seed_script.main(
        [
            "--sample-id",
            "bad-confirm",
            "--created-at",
            "2141-01-01T09:00:00+00:00",
            "--confirm-local-seed",
            "SEND IT",
            "--format",
            "json",
        ]
    )
    blank_sample = seed_script.main(
        [
            "--sample-id",
            " ",
            "--created-at",
            "2141-01-01T09:00:00+00:00",
            "--confirm-local-seed",
            seed_script.CONFIRM_LOCAL_SEED_PHRASE,
            "--format",
            "json",
        ]
    )
    naive_created_at = seed_script.main(
        [
            "--sample-id",
            "naive-time",
            "--created-at",
            "2141-01-01T09:00:00",
            "--confirm-local-seed",
            seed_script.CONFIRM_LOCAL_SEED_PHRASE,
            "--format",
            "json",
        ]
    )

    assert wrong_confirm == 2
    assert blank_sample == 2
    assert naive_created_at == 2


async def test_production_like_environment_is_refused_before_db_write() -> None:
    class FailingSession:
        async def __aenter__(self) -> "FailingSession":
            raise AssertionError("production-like environment must fail before DB access")

        async def __aexit__(self, *_args: object) -> None:
            return None

    with pytest.raises(seed_script.SeedBlockedError, match="production-like"):
        await seed_script.execute_seed(
            _query(),
            session_factory=FailingSession,
            settings_override=_local_settings(),
            environ={"APP_ENV": "production"},
        )


def test_cli_rejects_credential_like_arguments() -> None:
    result = _run_script(
        "--sample-id",
        "extra-arg",
        "--created-at",
        "2141-01-01T09:00:00+00:00",
        "--confirm-local-seed",
        seed_script.CONFIRM_LOCAL_SEED_PHRASE,
        "--telegram-bot-token",
        "placeholder",
    )

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


async def test_valid_seed_creates_visible_persisted_attention_digest_item() -> None:
    await _ensure_seed_tables()
    query = _query()
    await _cleanup_seed(query)

    try:
        before_audit_count = await _audit_log_count()
        result = await seed_script.execute_seed(
            query,
            settings_override=_local_settings(),
            environ={},
        )
        after_audit_count = await _audit_log_count()

        assert result["status"] == "local_persisted_attention_seed"
        assert result["seeded"] is True
        assert result["idempotent"] is False
        assert result["sample_id"] == query.sample_id
        assert result["window"]["start_at"] == "2141-01-01T00:00:00+00:00"
        assert result["window"]["end_at"] == "2141-01-02T00:00:00+00:00"
        assert result["ids"]["ingested_event_id"].startswith("evt_seed_")
        assert result["ids"]["source_event_id"].startswith("sevt_")
        assert result["ids"]["normalized_activity_item_id"].startswith("nact_seed_")
        assert result["ids"]["attention_triage_result_id"].startswith("atri_seed_")
        assert result["digest_preview"]["counts"]["visible"] >= 1
        assert result["digest_preview"]["counts"]["shown"] >= 1
        assert result["safety"]["provider_free"] is True
        assert result["safety"]["telegram_invoked"] is False
        assert result["safety"]["delivery_draft_created"] is False
        assert result["safety"]["delivery_intention_created"] is False
        assert before_audit_count == after_audit_count
        _assert_safe_serialized(result)
        _assert_safe_serialized(seed_script.format_text_seed(result))

        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=query.created_at.replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                ),
                end_at=query.created_at.replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                + timedelta(days=1),
                limit_per_section=10,
            )

        work_items = digest["groups"]["work_actions"]
        assert any(
            item["triage_result_id"] == result["ids"]["attention_triage_result_id"]
            for item in work_items
        )
        assert all("synthetic" in item["title"].casefold() for item in work_items)
    finally:
        await _cleanup_seed(query)


async def test_seed_is_idempotent_for_same_sample_and_created_at() -> None:
    await _ensure_seed_tables()
    query = _query(created_at=_utc(2141, 1, 2, 10))
    await _cleanup_seed(query)

    try:
        first = await seed_script.execute_seed(
            query,
            settings_override=_local_settings(),
            environ={},
        )
        second = await seed_script.execute_seed(
            query,
            settings_override=_local_settings(),
            environ={},
        )

        assert first["seeded"] is True
        assert second["seeded"] is False
        assert second["idempotent"] is True
        assert second["ids"] == first["ids"]
        assert second["digest_preview"]["counts"]["visible"] >= 1

        async with AsyncSessionLocal() as session:
            expected = seed_script._expected_payloads(query)
            attention_count = await session.scalar(
                select(func.count(AttentionTriageResultRecord.id)).where(
                    AttentionTriageResultRecord.triage_result_id
                    == expected["triage_result_id"]
                )
            )
            activity_count = await session.scalar(
                select(func.count(NormalizedActivityItemRecord.id)).where(
                    NormalizedActivityItemRecord.activity_item_id
                    == expected["activity_item_id"]
                )
            )

        assert attention_count == 1
        assert activity_count == 1
    finally:
        await _cleanup_seed(query)


async def test_seed_conflict_fails_closed_for_mismatched_existing_payload() -> None:
    await _ensure_seed_tables()
    query = _query(created_at=_utc(2141, 1, 3, 11))
    await _cleanup_seed(query)

    try:
        first = await seed_script.execute_seed(
            query,
            settings_override=_local_settings(),
            environ={},
        )
        async with AsyncSessionLocal() as session:
            record = await session.scalar(
                select(AttentionTriageResultRecord).where(
                    AttentionTriageResultRecord.triage_result_id
                    == first["ids"]["attention_triage_result_id"]
                )
            )
            assert record is not None
            record.reason = "conflicting synthetic reason"
            await session.commit()

        with pytest.raises(
            seed_script.SeedConflictError,
            match="attention triage result",
        ):
            await seed_script.execute_seed(
                query,
                settings_override=_local_settings(),
                environ={},
            )
    finally:
        await _cleanup_seed(query)


async def _audit_log_count() -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count(AuditLog.id))) or 0)
