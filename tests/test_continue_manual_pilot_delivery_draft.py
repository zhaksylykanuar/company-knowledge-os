from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog
from app.services.digest_delivery_drafts import (
    DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
    DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
    approve_digest_delivery_draft,
    build_persisted_attention_digest_delivery_draft,
    create_digest_delivery_intention,
    persist_digest_delivery_draft,
    record_digest_delivery_result,
    reject_digest_delivery_draft,
)
from scripts import continue_manual_pilot_delivery_draft as continue_script
from tests.test_digest_delivery_intention_send_script import (
    _assert_safe_output,
    _delete_delivery_chain,
    _ensure_audit_log_table,
    _persisted_attention_digest,
    _rendered_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "continue_manual_pilot_delivery_draft.py"


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


def _query(delivery_draft_id: str) -> continue_script.ContinueQuery:
    return continue_script.ContinueQuery(
        delivery_draft_id=delivery_draft_id,
        confirm_create_intention=continue_script.CONFIRM_CREATE_INTENTION_PHRASE,
        output_format="json",
    )


def _local_settings() -> SimpleNamespace:
    return SimpleNamespace(app_env="local")


def _serialized(value: object) -> str:
    return json.dumps(value, sort_keys=True)


async def _create_draft(
    *,
    start_at: datetime,
    end_at: datetime,
    approved: bool = False,
    rejected: bool = False,
) -> dict[str, Any]:
    await _ensure_audit_log_table()
    draft = build_persisted_attention_digest_delivery_draft(
        digest=_persisted_attention_digest(),
        rendered_text=_rendered_digest(),
        start_at=start_at,
        end_at=end_at,
    )
    delivery_draft_id = draft["delivery_draft_id"]
    await _delete_delivery_chain(delivery_draft_id=delivery_draft_id)

    async with AsyncSessionLocal() as session:
        await persist_digest_delivery_draft(session, draft=draft, actor="test")
        if approved:
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Approved for manual pilot handoff.",
            )
        if rejected:
            await reject_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Rejected for manual pilot handoff.",
            )
        await session.commit()

    return draft


async def _delivery_intention_count_for_draft(delivery_draft_id: str) -> int:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.event_type == DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE
            )
            .where(AuditLog.before_ref == delivery_draft_id)
        )
    return int(count or 0)


async def _delivery_result_count_for_intention(delivery_intention_id: str) -> int:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type == DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE)
            .where(AuditLog.before_ref == delivery_intention_id)
        )
    return int(count or 0)


async def _delete_delivery_result(delivery_result_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AuditLog).where(AuditLog.after_ref == delivery_result_id)
        )
        await session.commit()


def test_missing_required_args_fail_before_db_write() -> None:
    missing_id = _run_script(
        "--confirm-create-intention",
        continue_script.CONFIRM_CREATE_INTENTION_PHRASE,
    )
    missing_confirm = _run_script("--delivery-draft-id", "ddraft_test")

    assert missing_id.returncode == 2
    assert "--delivery-draft-id" in missing_id.stderr
    assert missing_confirm.returncode == 2
    assert "--confirm-create-intention" in missing_confirm.stderr
    _assert_safe_output(missing_id.stdout + missing_id.stderr)
    _assert_safe_output(missing_confirm.stdout + missing_confirm.stderr)


def test_blank_and_wrong_confirmation_fail_safely() -> None:
    blank = _run_script(
        "--delivery-draft-id",
        "   ",
        "--confirm-create-intention",
        continue_script.CONFIRM_CREATE_INTENTION_PHRASE,
        "--format",
        "json",
    )
    wrong_confirm = _run_script(
        "--delivery-draft-id",
        "ddraft_test",
        "--confirm-create-intention",
        "wrong",
        "--format",
        "json",
    )

    assert blank.returncode == 2
    blank_payload = json.loads(blank.stdout)
    assert blank_payload["status"] == "blocked"
    assert blank_payload["error_code"] == "input_error"
    assert "delivery_draft_id must not be empty" in blank_payload["message"]

    assert wrong_confirm.returncode == 2
    wrong_payload = json.loads(wrong_confirm.stdout)
    assert wrong_payload["status"] == "blocked"
    assert wrong_payload["error_code"] == "input_error"
    assert "confirm_create_intention phrase did not match" in wrong_payload["message"]
    _assert_safe_output(blank.stdout + blank.stderr)
    _assert_safe_output(wrong_confirm.stdout + wrong_confirm.stderr)


def test_cli_rejects_credential_send_and_window_arguments() -> None:
    for forbidden_arg in (
        "--bot-token",
        "--chat-id",
        "--target-channel",
        "--production-mode",
        "--confirm-send",
        "--execution-attempt-id",
        "--max-chunks",
        "--api-key",
        "--provider-credential",
        "--start-at",
        "--end-at",
    ):
        result = _run_script(
            "--delivery-draft-id",
            "ddraft_test",
            "--confirm-create-intention",
            continue_script.CONFIRM_CREATE_INTENTION_PHRASE,
            forbidden_arg,
            "value",
        )
        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr


async def test_production_like_environment_is_refused_before_db_write() -> None:
    with pytest.raises(continue_script.ContinueBlockedError) as exc:
        await continue_script.continue_manual_pilot_delivery_draft(
            _query("ddraft_fos077_prod_refusal"),
            settings_override=SimpleNamespace(app_env="production"),
            environ={},
        )

    assert exc.value.blocker == "production_like_environment"


async def test_unknown_delivery_draft_fails_safely() -> None:
    await _ensure_audit_log_table()

    with pytest.raises(continue_script.ContinueNotFoundError):
        await continue_script.continue_manual_pilot_delivery_draft(
            _query("ddraft_unknown_fos077_handoff"),
            settings_override=_local_settings(),
            environ={},
        )


async def test_unapproved_and_rejected_drafts_fail_before_intention_creation() -> None:
    unapproved = await _create_draft(
        start_at=_utc(2146, 1, 1),
        end_at=_utc(2146, 1, 2),
    )
    rejected = await _create_draft(
        start_at=_utc(2146, 1, 3),
        end_at=_utc(2146, 1, 4),
        rejected=True,
    )
    try:
        with pytest.raises(continue_script.ContinueBlockedError) as unapproved_exc:
            await continue_script.continue_manual_pilot_delivery_draft(
                _query(unapproved["delivery_draft_id"]),
                settings_override=_local_settings(),
                environ={},
            )
        assert unapproved_exc.value.blocker == "not_approved"

        with pytest.raises(continue_script.ContinueBlockedError) as rejected_exc:
            await continue_script.continue_manual_pilot_delivery_draft(
                _query(rejected["delivery_draft_id"]),
                settings_override=_local_settings(),
                environ={},
            )
        assert rejected_exc.value.blocker == "rejected"

        assert (
            await _delivery_intention_count_for_draft(
                unapproved["delivery_draft_id"]
            )
            == 0
        )
        assert (
            await _delivery_intention_count_for_draft(rejected["delivery_draft_id"])
            == 0
        )
    finally:
        await _delete_delivery_chain(
            delivery_draft_id=unapproved["delivery_draft_id"]
        )
        await _delete_delivery_chain(delivery_draft_id=rejected["delivery_draft_id"])


async def test_not_ready_draft_fails_before_intention_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import digest_delivery_drafts as delivery_service

    draft = await _create_draft(
        start_at=_utc(2146, 1, 4),
        end_at=_utc(2146, 1, 5),
        approved=True,
    )
    delivery_draft_id = draft["delivery_draft_id"]

    async def not_ready(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {
            "delivery_draft_id": delivery_draft_id,
            "eligible_for_delivery": False,
            "ineligible_reasons": ["not_ready_test"],
        }

    monkeypatch.setattr(
        delivery_service,
        "get_digest_delivery_draft_delivery_readiness",
        not_ready,
    )
    try:
        with pytest.raises(continue_script.ContinueBlockedError) as exc:
            await continue_script.continue_manual_pilot_delivery_draft(
                _query(delivery_draft_id),
                settings_override=_local_settings(),
                environ={},
            )

        assert exc.value.blocker == "not_ready_test"
        assert await _delivery_intention_count_for_draft(delivery_draft_id) == 0
    finally:
        await _delete_delivery_chain(delivery_draft_id=delivery_draft_id)


async def test_approved_ready_draft_creates_safe_intention_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import telegram_delivery

    async def forbidden_send(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("handoff command must not call Telegram sender")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    draft = await _create_draft(
        start_at=_utc(2146, 1, 5),
        end_at=_utc(2146, 1, 6),
        approved=True,
    )
    delivery_draft_id = draft["delivery_draft_id"]
    delivery_intention_id: str | None = None
    try:
        first = await continue_script.continue_manual_pilot_delivery_draft(
            _query(delivery_draft_id),
            settings_override=_local_settings(),
            environ={},
        )
        delivery_intention_id = first["delivery_intention_id"]
        second = await continue_script.continue_manual_pilot_delivery_draft(
            _query(delivery_draft_id),
            settings_override=_local_settings(),
            environ={},
        )

        assert first["status"] == "manual_pilot_delivery_intention_ready"
        assert first["delivery_draft_id"] == delivery_draft_id
        assert first["delivery_intention_id"].startswith("dint_")
        assert first["delivery_intention_record_created"] is True
        assert first["existing"] is False
        assert first["idempotent"] is False
        assert first["approval_status"]["current_decision"] == "approved"
        assert first["readiness"]["eligible_for_delivery"] is True
        assert first["send_status"]["delivery_results"]["count"] == 0
        assert first["duplicate_guard"]["would_block_new_execution_attempt"] is False
        assert first["duplicate_guard"]["blocker"] is None
        assert first["recommended_next_action"] == "run_bounded_test_send_after_human_checks"
        assert "delivery_execution_not_implemented" in first["blockers"]
        assert "bounded_operator_request_required" in first["blockers"]
        assert "telegram_bot_token_missing" not in first["blockers"]
        assert "telegram_chat_id_missing" not in first["blockers"]
        assert first["execution_gate"]["credential_presence_evaluated"] is False
        assert first["execution_gate"]["max_chunks_allowed"] == 1
        assert first["safety"]["delivery_intention_created"] is True
        assert first["safety"]["db_write_scope"] == "audit_logs_delivery_intention_only"
        assert first["safety"]["approval_created"] is False
        assert first["safety"]["delivery_result_created"] is False
        assert first["safety"]["delivery_invoked"] is False
        assert first["safety"]["telegram_invoked"] is False
        assert first["safety"]["scheduler_invoked"] is False
        assert first["safety"]["outbox_record_created"] is False
        assert first["next_steps"]["bounded_test_send_do_not_run_until_checks_pass"].endswith(
            '--confirm-send "SEND TEST TELEGRAM DIGEST" --format json'
        )

        assert second["delivery_intention_id"] == delivery_intention_id
        assert second["delivery_intention_record_created"] is False
        assert second["existing"] is True
        assert second["idempotent"] is True
        assert second["safety"]["db_write_scope"] == "none"
        assert await _delivery_intention_count_for_draft(delivery_draft_id) == 1
        assert await _delivery_result_count_for_intention(delivery_intention_id) == 0

        _assert_safe_output(_serialized(first))
        _assert_safe_output(continue_script.format_text_result(first))
        _assert_safe_output(_serialized(second))
    finally:
        await _delete_delivery_chain(
            delivery_draft_id=delivery_draft_id,
            delivery_intention_id=delivery_intention_id,
        )


async def test_already_sent_draft_fails_before_new_intention_creation() -> None:
    draft = await _create_draft(
        start_at=_utc(2146, 1, 7),
        end_at=_utc(2146, 1, 8),
        approved=True,
    )
    delivery_draft_id = draft["delivery_draft_id"]
    delivery_intention_id: str | None = None
    delivery_result_id: str | None = None
    try:
        async with AsyncSessionLocal() as session:
            intention = await create_digest_delivery_intention(
                session,
                delivery_draft_id=delivery_draft_id,
                actor="test",
            )
            delivery_intention_id = intention["delivery_intention_id"]
            result = await record_digest_delivery_result(
                session,
                delivery_intention_id=delivery_intention_id,
                execution_attempt_id="fos077-successful-attempt",
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
            delivery_result_id = result["delivery_result_id"]
            await session.commit()

        with pytest.raises(continue_script.ContinueBlockedError) as exc:
            await continue_script.continue_manual_pilot_delivery_draft(
                _query(delivery_draft_id),
                settings_override=_local_settings(),
                environ={},
            )

        assert exc.value.blocker == "delivery_draft_already_successfully_sent"
        assert exc.value.metadata["delivery_draft_id"] == delivery_draft_id
        assert exc.value.metadata["delivery_intention_id"] == delivery_intention_id
        assert exc.value.metadata["delivery_result_id"] == delivery_result_id
        assert exc.value.metadata["execution_attempt_id"] == "fos077-successful-attempt"
        assert exc.value.metadata["delivered_chunk_count"] == 1
        assert await _delivery_intention_count_for_draft(delivery_draft_id) == 1

        blocked = continue_script._blocked_result(
            error_code="blocked",
            message=str(exc.value),
            blocker=exc.value.blocker,
            metadata=exc.value.metadata,
        )
        assert blocked["blocker"] == "delivery_draft_already_successfully_sent"
        assert blocked["delivery_intention_id"] == delivery_intention_id
        assert blocked["delivery_result_id"] == delivery_result_id
        _assert_safe_output(_serialized(blocked))
    finally:
        if delivery_result_id is not None:
            await _delete_delivery_result(delivery_result_id)
        await _delete_delivery_chain(
            delivery_draft_id=delivery_draft_id,
            delivery_intention_id=delivery_intention_id,
        )
