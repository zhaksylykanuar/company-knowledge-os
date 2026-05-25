from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.base import AsyncSessionLocal
from app.services.digest_delivery_drafts import (
    approve_digest_delivery_draft,
    create_digest_delivery_intention,
    record_digest_delivery_result,
)
from scripts import seed_and_prepare_manual_pilot_delivery_draft as combined_script
from scripts import seed_local_persisted_attention_digest as seed_script
from tests.test_prepare_manual_pilot_delivery_draft import (
    _artifact_count_for_draft,
    _cleanup_delivery_results_for_intention,
    _cleanup_draft,
    _draft_record_count,
)
from tests.test_seed_local_persisted_attention_digest import (
    _cleanup_seed,
    _ensure_seed_tables,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "seed_and_prepare_manual_pilot_delivery_draft.py"


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


def _query(
    *,
    sample_id: str | None = None,
    created_at: datetime | None = None,
    limit: int = 20,
    debug_evidence: bool = False,
) -> combined_script.SeedAndPrepareQuery:
    return combined_script.SeedAndPrepareQuery(
        sample_id=sample_id or f"fos076-{uuid4().hex}",
        created_at=created_at or _utc(2145, 1, 1, 9),
        confirm_local_seed=seed_script.CONFIRM_LOCAL_SEED_PHRASE,
        confirm_prepare=combined_script.prepare_script.CONFIRM_PREPARE_PHRASE,
        limit=limit,
        debug_evidence=debug_evidence,
        output_format="json",
    )


def _seed_query(query: combined_script.SeedAndPrepareQuery) -> seed_script.SeedQuery:
    return seed_script.SeedQuery(
        sample_id=query.sample_id,
        created_at=query.created_at,
        confirm_local_seed=seed_script.CONFIRM_LOCAL_SEED_PHRASE,
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


def test_missing_required_args_fail_before_db_write() -> None:
    result = _run_script(
        "--created-at",
        "2145-01-01T09:00:00+00:00",
        "--confirm-local-seed",
        seed_script.CONFIRM_LOCAL_SEED_PHRASE,
        "--confirm-prepare",
        combined_script.prepare_script.CONFIRM_PREPARE_PHRASE,
    )

    assert result.returncode == 2
    assert "--sample-id" in result.stderr
    _assert_safe_output(result.stdout + result.stderr)


def test_invalid_inputs_fail_before_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_execute(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid input must fail before DB execution")

    monkeypatch.setattr(
        combined_script,
        "execute_seed_and_prepare",
        forbidden_execute,
    )

    blank_sample = combined_script.main(
        [
            "--sample-id",
            " ",
            "--created-at",
            "2145-01-01T09:00:00+00:00",
            "--confirm-local-seed",
            seed_script.CONFIRM_LOCAL_SEED_PHRASE,
            "--confirm-prepare",
            combined_script.prepare_script.CONFIRM_PREPARE_PHRASE,
            "--format",
            "json",
        ]
    )
    naive_created_at = combined_script.main(
        [
            "--sample-id",
            "naive-time",
            "--created-at",
            "2145-01-01T09:00:00",
            "--confirm-local-seed",
            seed_script.CONFIRM_LOCAL_SEED_PHRASE,
            "--confirm-prepare",
            combined_script.prepare_script.CONFIRM_PREPARE_PHRASE,
            "--format",
            "json",
        ]
    )
    wrong_seed_confirm = combined_script.main(
        [
            "--sample-id",
            "wrong-seed-confirm",
            "--created-at",
            "2145-01-01T09:00:00+00:00",
            "--confirm-local-seed",
            "SEED AND SEND",
            "--confirm-prepare",
            combined_script.prepare_script.CONFIRM_PREPARE_PHRASE,
            "--format",
            "json",
        ]
    )
    wrong_prepare_confirm = combined_script.main(
        [
            "--sample-id",
            "wrong-prepare-confirm",
            "--created-at",
            "2145-01-01T09:00:00+00:00",
            "--confirm-local-seed",
            seed_script.CONFIRM_LOCAL_SEED_PHRASE,
            "--confirm-prepare",
            "APPROVE AND SEND",
            "--format",
            "json",
        ]
    )
    too_high_limit = combined_script.main(
        [
            "--sample-id",
            "bad-limit",
            "--created-at",
            "2145-01-01T09:00:00+00:00",
            "--confirm-local-seed",
            seed_script.CONFIRM_LOCAL_SEED_PHRASE,
            "--confirm-prepare",
            combined_script.prepare_script.CONFIRM_PREPARE_PHRASE,
            "--limit",
            "51",
            "--format",
            "json",
        ]
    )

    assert blank_sample == 2
    assert naive_created_at == 2
    assert wrong_seed_confirm == 2
    assert wrong_prepare_confirm == 2
    assert too_high_limit == 2


async def test_production_like_environment_is_refused_before_db_write() -> None:
    class FailingSession:
        async def __aenter__(self) -> "FailingSession":
            raise AssertionError("production-like environment must fail before DB access")

        async def __aexit__(self, *_args: object) -> None:
            return None

    with pytest.raises(
        combined_script.SeedAndPrepareBlockedError,
        match="production-like",
    ):
        await combined_script.execute_seed_and_prepare(
            _query(),
            session_factory=FailingSession,
            settings_override=_local_settings(),
            environ={"APP_ENV": "production"},
        )


def test_cli_rejects_credential_and_send_arguments() -> None:
    result = _run_script(
        "--sample-id",
        "extra-arg",
        "--created-at",
        "2145-01-01T09:00:00+00:00",
        "--confirm-local-seed",
        seed_script.CONFIRM_LOCAL_SEED_PHRASE,
        "--confirm-prepare",
        combined_script.prepare_script.CONFIRM_PREPARE_PHRASE,
        "--telegram-bot-token",
        "placeholder",
        "--max-chunks",
        "1",
    )

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    _assert_safe_output(result.stdout + result.stderr)


async def test_valid_seed_and_prepare_creates_one_inert_delivery_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_seed_tables()
    query = _query(created_at=_utc(2145, 1, 2, 9))
    await _cleanup_seed(_seed_query(query))
    delivery_draft_id: str | None = None

    async def forbidden_send(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("combined command must not call Telegram sender")

    from app.services import telegram_delivery

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)

    try:
        first = await combined_script.execute_seed_and_prepare(
            query,
            settings_override=_local_settings(),
            environ={},
        )
        delivery_draft_id = first["delivery_draft_id"]
        second = await combined_script.execute_seed_and_prepare(
            query,
            settings_override=_local_settings(),
            environ={},
        )

        assert first["status"] == "manual_pilot_seed_and_draft_prepared"
        assert first["seeded"] is True
        assert first["seed_idempotent"] is False
        assert first["sample_id"] == query.sample_id
        assert first["start_at"] == "2145-01-02T00:00:00+00:00"
        assert first["end_at"] == "2145-01-03T00:00:00+00:00"
        assert first["delivery_draft_id"].startswith("ddraft_")
        assert first["delivery_draft_record_created"] is True
        assert first["digest_counts"]["visible"] >= 1
        assert first["digest_counts"]["total"] >= 1
        assert first["draft_usage_status"]["blocker"] is None
        assert first["stale_or_already_sent_warning"] is False
        assert first["recommended_next_action"] == "continue_manual_pilot_flow"
        assert first["safety"]["db_write_scope"] == (
            "local_seed_rows_and_delivery_draft_audit"
        )
        assert first["safety"]["approval_created"] is False
        assert first["safety"]["delivery_intention_created"] is False
        assert first["safety"]["delivery_result_created"] is False
        assert first["safety"]["delivery_invoked"] is False
        assert first["safety"]["scheduler_invoked"] is False
        assert "approve_draft" in first["next_steps"]
        assert "bounded_test_send_do_not_run_until_checks_pass" in first["next_steps"]

        assert second["delivery_draft_id"] == first["delivery_draft_id"]
        assert second["seeded"] is False
        assert second["seed_idempotent"] is True
        assert second["delivery_draft_record_created"] is False
        assert second["safety"]["db_write_scope"] == "none"
        assert await _draft_record_count(delivery_draft_id) == 1
        assert await _artifact_count_for_draft(delivery_draft_id) == 0

        _assert_safe_output(_serialized(first))
        _assert_safe_output(combined_script.format_text_result(first))
        _assert_safe_output(_serialized(second))
    finally:
        await _cleanup_seed(_seed_query(query))
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)


async def test_existing_already_sent_draft_reports_stale_warning() -> None:
    await _ensure_seed_tables()
    query = _query(created_at=_utc(2145, 1, 3, 9))
    await _cleanup_seed(_seed_query(query))
    delivery_draft_id: str | None = None
    delivery_intention_id: str | None = None

    try:
        first = await combined_script.execute_seed_and_prepare(
            query,
            settings_override=_local_settings(),
            environ={},
        )
        delivery_draft_id = first["delivery_draft_id"]

        async with AsyncSessionLocal() as session:
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Approved for seed-and-prepare stale warning test.",
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
                execution_attempt_id="fos076-successful-attempt",
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

        second = await combined_script.execute_seed_and_prepare(
            query,
            settings_override=_local_settings(),
            environ={},
        )

        assert second["seeded"] is False
        assert second["seed_idempotent"] is True
        assert second["delivery_draft_id"] == delivery_draft_id
        assert second["delivery_draft_record_created"] is False
        assert second["stale_or_already_sent_warning"] is True
        assert (
            second["recommended_next_action"]
            == "create_new_digest_window_or_synthetic_sample_before_another_send"
        )
        usage = second["draft_usage_status"]
        assert usage["blocker"] == "delivery_draft_already_successfully_sent"
        assert usage["prior_successful_delivery_intention_id"] == delivery_intention_id
        assert (
            usage["prior_successful_delivery_result_id"]
            == result["delivery_result_id"]
        )
        assert (
            usage["prior_successful_execution_attempt_id"]
            == "fos076-successful-attempt"
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

        text = combined_script.format_text_result(second)
        assert "Already-sent warning: True" in text
        assert "delivery_draft_already_successfully_sent" in text
        assert "create_new_digest_window_or_synthetic_sample" in text
        _assert_safe_output(_serialized(second))
        _assert_safe_output(text)
    finally:
        await _cleanup_seed(_seed_query(query))
        if delivery_intention_id is not None:
            await _cleanup_delivery_results_for_intention(delivery_intention_id)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)
