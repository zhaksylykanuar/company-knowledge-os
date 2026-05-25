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

from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog
from app.services.digest_delivery_drafts import (
    DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
    DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
    DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE,
    DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
    DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
    approve_digest_delivery_draft,
    create_digest_delivery_intention,
    record_digest_delivery_result,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script
from scripts import seed_local_persisted_attention_digest as seed_script
from tests.test_seed_local_persisted_attention_digest import (
    _cleanup_seed,
    _ensure_seed_tables,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "prepare_manual_pilot_delivery_draft.py"


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


def _seed_query(created_at: datetime) -> seed_script.SeedQuery:
    return seed_script.SeedQuery(
        sample_id=f"fos074-{uuid4().hex}",
        created_at=created_at,
        confirm_local_seed=seed_script.CONFIRM_LOCAL_SEED_PHRASE,
        output_format="json",
    )


def _prepare_query(
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int = 20,
    debug_evidence: bool = False,
) -> prepare_script.PrepareQuery:
    return prepare_script.PrepareQuery(
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        debug_evidence=debug_evidence,
        confirm_prepare=prepare_script.CONFIRM_PREPARE_PHRASE,
        output_format="json",
    )


def _local_settings() -> SimpleNamespace:
    return SimpleNamespace(app_env="local")


def _serialized(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _assert_safe_output(output: str) -> None:
    forbidden = (
        "rendered_text",
        '"text":',
        "chunk text",
        "bot_token",
        "chat_id",
        "api_key",
        "webhook",
        "raw_response",
        "raw_payload",
        "provider_payload",
        "source_payload",
        "prompt",
        "source body",
        "PRIVATE_TELEGRAM_RAW_RESPONSE",
        "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_PROMPT_DO_NOT_EXPOSE",
        "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
        "Hidden bounded send title",
        "evidence_refs",
        "secret",
    )
    folded = output.casefold()
    for marker in forbidden:
        assert marker.casefold() not in folded


async def _draft_record_count(delivery_draft_id: str | None = None) -> int:
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


async def _cleanup_delivery_results_for_intention(delivery_intention_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AuditLog).where(
                AuditLog.event_type == DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
                AuditLog.before_ref == delivery_intention_id,
            )
        )
        await session.commit()


def test_missing_required_args_fail_before_db_write() -> None:
    missing_start = _run_script(
        "--end-at",
        "2144-01-02T00:00:00+00:00",
        "--confirm-prepare",
        prepare_script.CONFIRM_PREPARE_PHRASE,
    )
    missing_end = _run_script(
        "--start-at",
        "2144-01-01T00:00:00+00:00",
        "--confirm-prepare",
        prepare_script.CONFIRM_PREPARE_PHRASE,
    )
    missing_confirm = _run_script(
        "--start-at",
        "2144-01-01T00:00:00+00:00",
        "--end-at",
        "2144-01-02T00:00:00+00:00",
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
    def forbidden_execute(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid input must fail before preparation")

    monkeypatch.setattr(
        prepare_script,
        "prepare_manual_pilot_delivery_draft",
        forbidden_execute,
    )

    bad_start = prepare_script.main(
        [
            "--start-at",
            "2144-01-01T00:00:00",
            "--end-at",
            "2144-01-02T00:00:00+00:00",
            "--confirm-prepare",
            prepare_script.CONFIRM_PREPARE_PHRASE,
            "--format",
            "json",
        ]
    )
    reversed_window = prepare_script.main(
        [
            "--start-at",
            "2144-01-02T00:00:00+00:00",
            "--end-at",
            "2144-01-01T00:00:00+00:00",
            "--confirm-prepare",
            prepare_script.CONFIRM_PREPARE_PHRASE,
            "--format",
            "json",
        ]
    )
    wrong_confirm = prepare_script.main(
        [
            "--start-at",
            "2144-01-01T00:00:00+00:00",
            "--end-at",
            "2144-01-02T00:00:00+00:00",
            "--confirm-prepare",
            "APPROVE AND SEND",
            "--format",
            "json",
        ]
    )
    too_high_limit = prepare_script.main(
        [
            "--start-at",
            "2144-01-01T00:00:00+00:00",
            "--end-at",
            "2144-01-02T00:00:00+00:00",
            "--confirm-prepare",
            prepare_script.CONFIRM_PREPARE_PHRASE,
            "--limit",
            "51",
            "--format",
            "json",
        ]
    )

    assert bad_start == 2
    assert reversed_window == 2
    assert wrong_confirm == 2
    assert too_high_limit == 2


async def test_production_like_environment_is_refused_before_db_write() -> None:
    class FailingSession:
        async def __aenter__(self) -> "FailingSession":
            raise AssertionError("production-like environment must fail before DB access")

        async def __aexit__(self, *_args: object) -> None:
            return None

    with pytest.raises(prepare_script.PrepareBlockedError, match="production-like"):
        await prepare_script.prepare_manual_pilot_delivery_draft(
            _prepare_query(
                start_at=_utc(2144, 1, 1),
                end_at=_utc(2144, 1, 2),
            ),
            session_factory=FailingSession,
            settings_override=_local_settings(),
            environ={"APP_ENV": "production"},
        )


def test_cli_rejects_credential_and_send_arguments() -> None:
    result = _run_script(
        "--start-at",
        "2144-01-01T00:00:00+00:00",
        "--end-at",
        "2144-01-02T00:00:00+00:00",
        "--confirm-prepare",
        prepare_script.CONFIRM_PREPARE_PHRASE,
        "--telegram-bot-token",
        "placeholder",
        "--max-chunks",
        "1",
    )

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    _assert_safe_output(result.stdout + result.stderr)


async def test_empty_digest_window_fails_before_draft_creation() -> None:
    await _ensure_seed_tables()
    before_count = await _draft_record_count()

    with pytest.raises(prepare_script.PrepareBlockedError, match="no visible items"):
        await prepare_script.prepare_manual_pilot_delivery_draft(
            _prepare_query(
                start_at=_utc(2199, 1, 1),
                end_at=_utc(2199, 1, 2),
            ),
            settings_override=_local_settings(),
            environ={},
        )

    assert await _draft_record_count() == before_count


async def test_non_empty_digest_prepares_one_inert_delivery_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_seed_tables()
    seed_query = _seed_query(_utc(2144, 2, 1, 9))
    await _cleanup_seed(seed_query)
    delivery_draft_id: str | None = None

    async def forbidden_send(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("prepare command must not call Telegram sender")

    from app.services import telegram_delivery

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)

    try:
        seed_result = await seed_script.execute_seed(
            seed_query,
            settings_override=_local_settings(),
            environ={},
        )
        start_at = datetime.fromisoformat(seed_result["window"]["start_at"])
        end_at = datetime.fromisoformat(seed_result["window"]["end_at"])

        first = await prepare_script.prepare_manual_pilot_delivery_draft(
            _prepare_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )
        delivery_draft_id = first["delivery_draft_id"]
        second = await prepare_script.prepare_manual_pilot_delivery_draft(
            _prepare_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        assert first["status"] == "manual_pilot_delivery_draft_prepared"
        assert first["prepared"] is True
        assert first["delivery_draft_id"].startswith("ddraft_")
        assert first["digest_type"] == "persisted_attention"
        assert first["channel"] == "telegram"
        assert first["digest_counts"]["total"] >= 1
        assert first["digest_counts"]["visible"] >= 1
        assert first["hidden_low_priority_count"] >= 0
        assert first["delivery_draft_record_created"] is True
        assert first["existing"] is False
        assert first["idempotent"] is False
        assert first["safety"]["approval_created"] is False
        assert first["safety"]["delivery_intention_created"] is False
        assert first["safety"]["delivery_result_created"] is False
        assert first["safety"]["delivery_invoked"] is False
        assert first["safety"]["scheduler_invoked"] is False
        assert first["stale_or_already_sent_warning"] is False
        assert first["recommended_next_action"] == "continue_manual_pilot_flow"
        assert first["draft_usage_status"]["blocker"] is None
        assert (
            first["draft_usage_status"]["associated_delivery_intention_count"]
            == 0
        )
        assert first["associated_delivery_intentions"] == []
        assert first["delivery_results_summary"] == {
            "count": 0,
            "successful_count": 0,
            "failed_count": 0,
            "partial_count": 0,
            "skipped_count": 0,
        }
        assert "approve_draft" in first["next_steps"]
        assert "PREPARE MANUAL PILOT DRAFT" not in _serialized(first["next_steps"])

        assert second["delivery_draft_id"] == first["delivery_draft_id"]
        assert second["delivery_draft_record_created"] is False
        assert second["existing"] is True
        assert second["idempotent"] is True
        assert second["stale_or_already_sent_warning"] is False
        assert await _draft_record_count(delivery_draft_id) == 1
        assert await _artifact_count_for_draft(delivery_draft_id) == 0

        _assert_safe_output(_serialized(first))
        _assert_safe_output(prepare_script.format_text_prepare(first))
        _assert_safe_output(_serialized(second))
    finally:
        await _cleanup_seed(seed_query)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)


async def test_existing_already_sent_draft_reports_stale_warning() -> None:
    await _ensure_seed_tables()
    seed_query = _seed_query(_utc(2144, 2, 3, 9))
    await _cleanup_seed(seed_query)
    delivery_draft_id: str | None = None
    delivery_intention_id: str | None = None

    try:
        seed_result = await seed_script.execute_seed(
            seed_query,
            settings_override=_local_settings(),
            environ={},
        )
        start_at = datetime.fromisoformat(seed_result["window"]["start_at"])
        end_at = datetime.fromisoformat(seed_result["window"]["end_at"])

        first = await prepare_script.prepare_manual_pilot_delivery_draft(
            _prepare_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )
        delivery_draft_id = first["delivery_draft_id"]

        async with AsyncSessionLocal() as session:
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Approved for stale draft warning test.",
            )
            intention = await create_digest_delivery_intention(
                session,
                delivery_draft_id=delivery_draft_id,
                actor="test",
            )
            delivery_intention_id = intention["delivery_intention_id"]
            result = await record_digest_delivery_result(
                session,
                delivery_intention_id=delivery_intention_id,
                execution_attempt_id="fos075-successful-attempt",
                result_status="succeeded",
                attempted_chunk_count=1,
                delivered_chunk_count=1,
                failed_chunk_count=0,
                safe_message_refs=[
                    {
                        "chunk_index": 1,
                        "message_id": "safe-message-1",
                        "chat_id": "TELEGRAM_CHAT_ID_TEST_VALUE",
                        "raw_response": "PRIVATE_TELEGRAM_RAW_RESPONSE",
                    }
                ],
                delivery_invoked=True,
                delivery_adapter_invoked=True,
                actor="test",
            )
            await session.commit()

        second = await prepare_script.prepare_manual_pilot_delivery_draft(
            _prepare_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        assert second["delivery_draft_id"] == delivery_draft_id
        assert second["delivery_draft_record_created"] is False
        assert second["existing"] is True
        assert second["idempotent"] is True
        assert second["stale_or_already_sent_warning"] is True
        assert (
            second["recommended_next_action"]
            == "create_new_digest_window_or_synthetic_sample_before_another_send"
        )
        usage = second["draft_usage_status"]
        assert usage["blocker"] == "delivery_draft_already_successfully_sent"
        assert usage["associated_delivery_intention_count"] == 1
        assert usage["prior_successful_delivery_intention_id"] == delivery_intention_id
        assert (
            usage["prior_successful_delivery_result_id"]
            == result["delivery_result_id"]
        )
        assert (
            usage["prior_successful_execution_attempt_id"]
            == "fos075-successful-attempt"
        )
        assert usage["prior_successful_delivered_chunk_count"] == 1
        assert second["delivery_results_summary"] == {
            "count": 1,
            "successful_count": 1,
            "failed_count": 0,
            "partial_count": 0,
            "skipped_count": 0,
        }
        assert await _draft_record_count(delivery_draft_id) == 1

        text = prepare_script.format_text_prepare(second)
        assert "Already-sent warning: True" in text
        assert "delivery_draft_already_successfully_sent" in text
        assert "create_new_digest_window_or_synthetic_sample" in text
        _assert_safe_output(_serialized(second))
        _assert_safe_output(text)
    finally:
        await _cleanup_seed(seed_query)
        if delivery_intention_id is not None:
            await _cleanup_delivery_results_for_intention(delivery_intention_id)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)
