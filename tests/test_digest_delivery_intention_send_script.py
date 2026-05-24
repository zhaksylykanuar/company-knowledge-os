from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, or_, select

from app.db.base import AsyncSessionLocal, engine
from app.db.models import AuditLog
from app.services.digest_delivery_drafts import (
    DIGEST_DELIVERY_DRAFT_AUDIT_EVENT_TYPES,
    DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
    DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
    approve_digest_delivery_draft,
    build_persisted_attention_digest_delivery_draft,
    create_digest_delivery_intention,
    persist_digest_delivery_draft,
    sanitize_persisted_attention_digest_for_delivery_draft,
)
from app.services.digest_rendering import render_persisted_attention_digest_text
from scripts import send_test_telegram_delivery_intention as send_script

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "send_test_telegram_delivery_intention.py"
BOT_TOKEN_VALUE = "TELEGRAM_BOT_TOKEN_TEST_SECRET"
CHAT_ID_VALUE = "TELEGRAM_CHAT_ID_TEST_SECRET"


class FakeTelegramTransport:
    def __init__(self, responses: list[Mapping[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def __call__(self, url: str, payload: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append((url, dict(payload)))
        if self.responses:
            return self.responses.pop(0)
        return {
            "ok": True,
            "result": {
                "message_id": f"test-message-{len(self.calls)}",
            },
        }


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


async def _ensure_audit_log_table() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(AuditLog.__table__.create, checkfirst=True)


def _persisted_attention_digest() -> dict[str, Any]:
    return {
        "section_title": "Persisted attention digest",
        "available": True,
        "window": {
            "start_at": "2134-01-01T00:00:00+00:00",
            "end_at": "2134-01-02T00:00:00+00:00",
        },
        "section_labels": {
            "work_actions": "Work actions requiring my attention",
            "manual_actions": "Manual actions",
            "waiting_external_reply": "Waiting for external reply",
            "work_info": "Important project updates",
            "review_optional": "Review optional",
        },
        "counts": {
            "total": 2,
            "visible": 1,
            "hidden": 1,
            "shown": 1,
            "by_attention_class": {
                "no_action_required": 1,
                "requires_my_attention": 1,
            },
            "by_priority": {
                "high": 1,
                "low": 1,
            },
            "by_show_in_digest": {
                "false": 1,
                "true": 1,
            },
            "by_source": {
                "github": 2,
            },
        },
        "groups": {
            "work_actions": [
                {
                    "id": "atri_send_visible",
                    "triage_result_id": "atri_send_visible",
                    "activity_item_id": "nact_send_visible",
                    "source": "github",
                    "source_object_id": "delivery-send:visible",
                    "attention_class": "requires_my_attention",
                    "priority": "high",
                    "show_in_digest": True,
                    "confidence": 0.93,
                    "title": "Review bounded send command",
                    "safe_summary": "Safe bounded send summary.",
                    "reason": "validated bounded send fixture",
                    "recommended_action": "review the bounded send command",
                    "owner": "me",
                    "deadline": "2134-01-02",
                    "project": "company-knowledge-os",
                    "activity_created_at": "2134-01-01T09:00:00+00:00",
                    "triage_created_at": "2134-01-01T10:00:00+00:00",
                    "evidence": "1 triage evidence ref",
                    "evidence_refs": [
                        {
                            "kind": "source_event",
                            "source_event_id": "sevt_send_visible",
                            "source_system": "github",
                            "source_object_type": "pull_request",
                            "source_object_id": "delivery-send:visible",
                            "raw_object_ref": "raw://send/visible.json",
                            "raw_payload": "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
                            "provider_payload": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                            "prompt": "PRIVATE_PROMPT_DO_NOT_EXPOSE",
                            "source_payload": "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
                        }
                    ],
                    "activity_available": True,
                    "raw_text": "PRIVATE_RAW_TEXT_DO_NOT_EXPOSE",
                    "provider_payload": {"body": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE"},
                    "prompt": "PRIVATE_PROMPT_DO_NOT_EXPOSE",
                }
            ],
            "manual_actions": [],
            "waiting_external_reply": [],
            "work_info": [],
            "review_optional": [],
        },
        "hidden_low_priority_summary": {
            "total": 1,
            "counts": {"no-action low-priority items": 1},
            "items": [
                {
                    "id": "atri_send_hidden",
                    "title": "Hidden bounded send title",
                    "evidence_refs": [
                        {
                            "source_event_id": "sevt_send_hidden",
                            "raw_object_ref": "raw://send/hidden.json",
                        }
                    ],
                }
            ],
        },
        "data_quality_notes": [],
        "metadata": {
            "source_model": "attention_triage_results",
            "enrichment_model": "normalized_activity_items",
            "group_limit": 20,
            "truncated": False,
            "llm_used": False,
            "read_model_only": True,
            "source_activity_digest_replaced": False,
        },
    }


def _rendered_digest() -> str:
    digest = _persisted_attention_digest()
    safe_digest = sanitize_persisted_attention_digest_for_delivery_draft(
        digest,
        debug_evidence=False,
    )
    return render_persisted_attention_digest_text(
        safe_digest,
        debug_evidence=False,
    )


def _two_chunk_rendered_text() -> str:
    return "Bounded Telegram test chunk one.\n" + ("x" * 3900)


async def _delete_delivery_chain(
    *,
    delivery_draft_id: str,
    delivery_intention_id: str | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AuditLog)
            .where(AuditLog.event_type.in_(DIGEST_DELIVERY_DRAFT_AUDIT_EVENT_TYPES))
            .where(AuditLog.after_ref == delivery_draft_id)
        )
        await session.execute(
            delete(AuditLog)
            .where(AuditLog.event_type == DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE)
            .where(AuditLog.before_ref == delivery_draft_id)
        )
        if delivery_intention_id is not None:
            await session.execute(
                delete(AuditLog)
                .where(AuditLog.event_type == DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE)
                .where(AuditLog.after_ref == delivery_intention_id)
            )
            await session.execute(
                delete(AuditLog)
                .where(AuditLog.event_type == DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE)
                .where(AuditLog.before_ref == delivery_intention_id)
            )
        await session.commit()


async def _create_send_chain(
    *,
    start_at: datetime,
    end_at: datetime,
    rendered_text: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    await _ensure_audit_log_table()
    digest = _persisted_attention_digest()
    text = rendered_text or _rendered_digest()
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=text,
        start_at=start_at,
        end_at=end_at,
    )
    delivery_draft_id = draft["delivery_draft_id"]
    await _delete_delivery_chain(delivery_draft_id=delivery_draft_id)

    async with AsyncSessionLocal() as session:
        await persist_digest_delivery_draft(session, draft=draft, actor="test")
        await approve_digest_delivery_draft(
            session,
            delivery_draft_id=delivery_draft_id,
            reviewer="founder",
            note="Approved for bounded test send.",
        )
        intention = await create_digest_delivery_intention(
            session,
            delivery_draft_id=delivery_draft_id,
            actor="test",
        )
        await session.commit()

    return draft, intention, text


async def _delivery_result_count(delivery_intention_id: str) -> int:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type == DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE)
            .where(AuditLog.before_ref == delivery_intention_id)
        )
    return int(count or 0)


async def _chain_event_count(
    *,
    delivery_draft_id: str,
    delivery_intention_id: str,
) -> int:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                or_(
                    AuditLog.after_ref.in_([delivery_draft_id, delivery_intention_id]),
                    AuditLog.before_ref.in_([delivery_draft_id, delivery_intention_id]),
                )
            )
        )
    return int(count or 0)


async def _delivery_result_payload(delivery_result_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        payload = await session.scalar(
            select(AuditLog.payload)
            .where(AuditLog.event_type == DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE)
            .where(AuditLog.after_ref == delivery_result_id)
            .order_by(AuditLog.id)
        )
    assert isinstance(payload, dict)
    return payload


def _serialized(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _assert_safe_output(output: str, *, rendered_text: str | None = None) -> None:
    assert BOT_TOKEN_VALUE not in output
    assert CHAT_ID_VALUE not in output
    assert "bot_token" not in output
    assert "chat_id" not in output
    assert "telegram_url" not in output
    assert "webhook_url" not in output
    assert "https://api.telegram.org" not in output
    assert "api.telegram.org" not in output
    assert '"rendered_text":' not in output
    assert '"text":' not in output
    assert "Hidden bounded send title" not in output
    assert "atri_send_hidden" not in output
    assert "sevt_send_hidden" not in output
    assert "evidence_refs" not in output
    if rendered_text is not None:
        assert rendered_text not in output
    for marker in (
        "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_PROMPT_DO_NOT_EXPOSE",
        "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_RAW_TEXT_DO_NOT_EXPOSE",
        "provider_payload",
        "prompt",
        "source_payload",
        "raw_text",
        "raw provider body should not be stored",
    ):
        assert marker not in output


def _query(
    delivery_intention_id: str,
    *,
    execution_attempt_id: str = "fos070-test-attempt",
    max_chunks: int = 3,
) -> send_script.SendQuery:
    return send_script.SendQuery(
        delivery_intention_id=delivery_intention_id,
        execution_attempt_id=execution_attempt_id,
        max_chunks=max_chunks,
        test_mode=True,
        confirm_send=send_script.CONFIRM_SEND_PHRASE,
        output_format="json",
    )


def test_missing_required_cli_args_fail_safely_before_sending() -> None:
    result = _run_script("--format", "json")

    assert result.returncode == 2
    assert "--delivery-intention-id" in result.stderr
    assert "--execution-attempt-id" in result.stderr
    assert "--max-chunks" in result.stderr
    _assert_safe_output(result.stdout + result.stderr)


def test_false_test_mode_fails_safely_before_sending() -> None:
    result = _run_script(
        "--delivery-intention-id",
        "dint_fos070_cli",
        "--execution-attempt-id",
        "attempt-false-mode",
        "--max-chunks",
        "1",
        "--test-mode",
        "false",
        "--confirm-send",
        send_script.CONFIRM_SEND_PHRASE,
        "--format",
        "json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["error_code"] == "input_error"
    assert "test_mode must be exactly true" in payload["message"]
    _assert_safe_output(result.stdout + result.stderr)


def test_wrong_confirmation_phrase_fails_safely_before_sending() -> None:
    result = _run_script(
        "--delivery-intention-id",
        "dint_fos070_cli",
        "--execution-attempt-id",
        "attempt-wrong-confirm",
        "--max-chunks",
        "1",
        "--test-mode",
        "true",
        "--confirm-send",
        "send it",
        "--format",
        "json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["error_code"] == "input_error"
    assert "confirm_send phrase did not match" in payload["message"]
    _assert_safe_output(result.stdout + result.stderr)


def test_max_chunks_above_hard_cap_fails_safely_before_sending() -> None:
    result = _run_script(
        "--delivery-intention-id",
        "dint_fos070_cli",
        "--execution-attempt-id",
        "attempt-too-many-chunks",
        "--max-chunks",
        "4",
        "--test-mode",
        "true",
        "--confirm-send",
        send_script.CONFIRM_SEND_PHRASE,
        "--format",
        "json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["error_code"] == "input_error"
    assert "max_chunks must be at most 3" in payload["message"]
    _assert_safe_output(result.stdout + result.stderr)


async def test_unknown_delivery_intention_fails_safely_before_sending() -> None:
    await _ensure_audit_log_table()
    transport = FakeTelegramTransport()

    try:
        await send_script.execute_test_send(
            _query("dint_unknown_fos070_send"),
            telegram_transport=transport,
            telegram_bot_token=BOT_TOKEN_VALUE,
            telegram_chat_id=CHAT_ID_VALUE,
        )
    except send_script.SendNotFoundError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("unknown delivery intention must fail")

    assert transport.calls == []


async def test_missing_credentials_fail_before_sending_without_values() -> None:
    draft, intention, rendered_text = await _create_send_chain(
        start_at=_utc(2134, 1, 3),
        end_at=_utc(2134, 1, 4),
    )
    transport = FakeTelegramTransport()

    try:
        before_count = await _chain_event_count(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )
        try:
            await send_script.execute_test_send(
                _query(intention["delivery_intention_id"]),
                telegram_transport=transport,
                telegram_bot_token=None,
                telegram_chat_id=" ",
            )
        except send_script.SendBlockedError as exc:
            message = str(exc)
        else:
            raise AssertionError("missing credentials must block send")

        after_count = await _chain_event_count(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )
        assert transport.calls == []
        assert before_count == after_count
        _assert_safe_output(message, rendered_text=rendered_text)
    finally:
        await _delete_delivery_chain(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )


async def test_gate_not_ready_fails_before_sending() -> None:
    draft, intention, rendered_text = await _create_send_chain(
        start_at=_utc(2134, 1, 5),
        end_at=_utc(2134, 1, 6),
        rendered_text=_two_chunk_rendered_text(),
    )
    transport = FakeTelegramTransport()

    try:
        try:
            await send_script.execute_test_send(
                _query(
                    intention["delivery_intention_id"],
                    execution_attempt_id="attempt-gate-not-ready",
                    max_chunks=1,
                ),
                telegram_transport=transport,
                telegram_bot_token=BOT_TOKEN_VALUE,
                telegram_chat_id=CHAT_ID_VALUE,
            )
        except send_script.SendBlockedError as exc:
            message = str(exc)
        else:
            raise AssertionError("unsafe chunk bounds must block send")

        assert transport.calls == []
        assert await _delivery_result_count(intention["delivery_intention_id"]) == 0
        _assert_safe_output(message, rendered_text=rendered_text)
    finally:
        await _delete_delivery_chain(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )


async def test_valid_test_mode_send_records_sanitized_result_and_is_idempotent() -> None:
    draft, intention, rendered_text = await _create_send_chain(
        start_at=_utc(2134, 1, 7),
        end_at=_utc(2134, 1, 8),
        rendered_text=_two_chunk_rendered_text(),
    )
    transport = FakeTelegramTransport()

    try:
        result = await send_script.execute_test_send(
            _query(
                intention["delivery_intention_id"],
                execution_attempt_id="attempt-success",
                max_chunks=3,
            ),
            telegram_transport=transport,
            telegram_bot_token=BOT_TOKEN_VALUE,
            telegram_chat_id=CHAT_ID_VALUE,
        )

        assert result["status"] == "telegram_test_send_result"
        assert result["delivery_intention_id"] == intention["delivery_intention_id"]
        assert result["result_status"] == "succeeded"
        assert result["execution_attempt_id"] == "attempt-success"
        assert result["planned_chunk_count"] == 2
        assert result["attempted_chunk_count"] == 2
        assert result["delivered_chunk_count"] == 2
        assert result["failed_chunk_count"] == 0
        assert result["delivery_result_record_created"] is True
        assert result["idempotent_replay"] is False
        assert result["delivery_invoked"] is True
        assert result["delivery_adapter_invoked"] is True
        assert result["scheduler_invoked"] is False
        assert len(transport.calls) == 2
        assert len(transport.calls) <= 3
        assert await _delivery_result_count(intention["delivery_intention_id"]) == 1

        payload = await _delivery_result_payload(result["delivery_result_id"])
        assert payload["result_status"] == "succeeded"
        assert payload["attempted_chunk_count"] == 2
        assert payload["delivered_chunk_count"] == 2
        assert payload["failed_chunk_count"] == 0
        assert len(payload["safe_message_refs"]) == 2
        assert all("chunk_sha256" in ref for ref in payload["safe_message_refs"])
        assert payload["safety"]["credential_values_exposed"] is False
        assert payload["safety"]["telegram_raw_api_response_stored"] is False
        assert payload["safety"]["delivery_invoked"] is True
        assert payload["safety"]["delivery_adapter_invoked"] is True

        second_transport = FakeTelegramTransport()
        replay = await send_script.execute_test_send(
            _query(
                intention["delivery_intention_id"],
                execution_attempt_id="attempt-success",
                max_chunks=3,
            ),
            telegram_transport=second_transport,
            telegram_bot_token=BOT_TOKEN_VALUE,
            telegram_chat_id=CHAT_ID_VALUE,
        )

        assert replay["delivery_result_id"] == result["delivery_result_id"]
        assert replay["idempotent_replay"] is True
        assert replay["delivery_result_record_created"] is False
        assert second_transport.calls == []
        assert await _delivery_result_count(intention["delivery_intention_id"]) == 1

        text_output = send_script.format_text_result(result)
        _assert_safe_output(_serialized(result), rendered_text=rendered_text)
        _assert_safe_output(_serialized(payload), rendered_text=rendered_text)
        _assert_safe_output(text_output, rendered_text=rendered_text)
    finally:
        await _delete_delivery_chain(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )


async def test_failed_send_records_sanitized_failed_result() -> None:
    draft, intention, rendered_text = await _create_send_chain(
        start_at=_utc(2134, 1, 9),
        end_at=_utc(2134, 1, 10),
    )
    transport = FakeTelegramTransport(
        [
            {
                "ok": False,
                "error_code": 429,
                "description": "raw provider body should not be stored",
            }
        ]
    )

    try:
        result = await send_script.execute_test_send(
            _query(
                intention["delivery_intention_id"],
                execution_attempt_id="attempt-failed",
                max_chunks=3,
            ),
            telegram_transport=transport,
            telegram_bot_token=BOT_TOKEN_VALUE,
            telegram_chat_id=CHAT_ID_VALUE,
        )

        assert result["result_status"] == "failed"
        assert result["attempted_chunk_count"] == 1
        assert result["delivered_chunk_count"] == 0
        assert result["failed_chunk_count"] == 1
        assert result["safe_error_code"] == "telegram_send_failed"
        assert result["safe_error_summary"] == (
            "Telegram API sendMessage failed with error_code 429"
        )
        assert await _delivery_result_count(intention["delivery_intention_id"]) == 1

        payload = await _delivery_result_payload(result["delivery_result_id"])
        assert payload["result_status"] == "failed"
        assert payload["safe_message_refs"] == []
        _assert_safe_output(_serialized(result), rendered_text=rendered_text)
        _assert_safe_output(_serialized(payload), rendered_text=rendered_text)
    finally:
        await _delete_delivery_chain(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )


async def test_partial_send_records_sanitized_partial_result() -> None:
    draft, intention, rendered_text = await _create_send_chain(
        start_at=_utc(2134, 1, 11),
        end_at=_utc(2134, 1, 12),
        rendered_text=_two_chunk_rendered_text(),
    )
    transport = FakeTelegramTransport(
        [
            {
                "ok": True,
                "result": {"message_id": "first-message"},
            },
            {
                "ok": False,
                "error_code": 500,
                "description": "raw provider body should not be stored",
            },
        ]
    )

    try:
        result = await send_script.execute_test_send(
            _query(
                intention["delivery_intention_id"],
                execution_attempt_id="attempt-partial",
                max_chunks=3,
            ),
            telegram_transport=transport,
            telegram_bot_token=BOT_TOKEN_VALUE,
            telegram_chat_id=CHAT_ID_VALUE,
        )

        assert result["result_status"] == "partial"
        assert result["attempted_chunk_count"] == 2
        assert result["delivered_chunk_count"] == 1
        assert result["failed_chunk_count"] == 1
        assert len(transport.calls) == 2

        payload = await _delivery_result_payload(result["delivery_result_id"])
        assert payload["result_status"] == "partial"
        assert payload["safe_message_refs"] == [
            {
                "chunk_index": 1,
                "message_id": "first-message",
                "chunk_sha256": payload["safe_message_refs"][0]["chunk_sha256"],
                "status": "sent",
            }
        ]
        _assert_safe_output(_serialized(result), rendered_text=rendered_text)
        _assert_safe_output(_serialized(payload), rendered_text=rendered_text)
    finally:
        await _delete_delivery_chain(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )
