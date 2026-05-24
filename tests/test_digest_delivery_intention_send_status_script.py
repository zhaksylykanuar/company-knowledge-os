from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog
from app.services.digest_delivery_drafts import (
    DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
    record_digest_delivery_result,
)
from scripts import report_digest_delivery_intention_send_status as status_script
from tests.test_digest_delivery_intention_send_script import (
    _assert_safe_output,
    _chain_event_count,
    _create_send_chain,
    _delete_delivery_chain,
    _delivery_result_count,
    _ensure_audit_log_table,
    _serialized,
    _two_chunk_rendered_text,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "report_digest_delivery_intention_send_status.py"


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


def _query(delivery_intention_id: str) -> status_script.SendStatusQuery:
    return status_script.SendStatusQuery(
        delivery_intention_id=delivery_intention_id,
        output_format="json",
    )


def test_missing_delivery_intention_id_fails_safely() -> None:
    result = _run_script("--format", "json")

    assert result.returncode == 2
    assert "--delivery-intention-id" in result.stderr
    _assert_safe_output(result.stdout + result.stderr)


def test_blank_delivery_intention_id_fails_safely() -> None:
    result = _run_script(
        "--delivery-intention-id",
        "   ",
        "--format",
        "json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["error_code"] == "input_error"
    assert "delivery_intention_id must not be empty" in payload["message"]
    _assert_safe_output(result.stdout + result.stderr)


async def test_unknown_delivery_intention_id_fails_safely() -> None:
    await _ensure_audit_log_table()

    with pytest.raises(status_script.SendStatusNotFoundError):
        await status_script.build_send_status_report(
            _query("dint_unknown_fos073_status")
        )


async def test_existing_intention_with_no_results_reports_guard_not_blocking() -> None:
    draft: dict[str, Any] | None = None
    intention: dict[str, Any] | None = None
    try:
        draft, intention, rendered_text = await _create_send_chain(
            start_at=_utc(2134, 7, 1),
            end_at=_utc(2134, 7, 2),
        )
        delivery_intention_id = intention["delivery_intention_id"]
        before_count = await _chain_event_count(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=delivery_intention_id,
        )

        report = await status_script.build_send_status_report(
            _query(delivery_intention_id)
        )

        assert report["status"] == "delivery_intention_send_status"
        assert report["delivery_intention_id"] == delivery_intention_id
        assert report["delivery_results"]["count"] == 0
        assert report["delivery_results"]["successful_count"] == 0
        assert (
            report["duplicate_guard"]["would_block_new_execution_attempt"]
            is False
        )
        assert report["duplicate_guard"]["blocker"] is None
        assert report["recommended_next_action"] == "safe_to_consider_new_bounded_attempt"
        assert report["safety"]["read_only"] is True
        assert report["safety"]["delivery_invoked"] is False
        assert await _delivery_result_count(delivery_intention_id) == 0
        assert (
            await _chain_event_count(
                delivery_draft_id=draft["delivery_draft_id"],
                delivery_intention_id=delivery_intention_id,
            )
            == before_count
        )
        _assert_safe_output(_serialized(report), rendered_text=rendered_text)
        _assert_safe_output(
            status_script.format_text_report(report),
            rendered_text=rendered_text,
        )
    finally:
        if draft is not None:
            await _delete_delivery_chain(
                delivery_draft_id=draft["delivery_draft_id"],
                delivery_intention_id=(
                    intention["delivery_intention_id"] if intention else None
                ),
            )


async def test_prior_successful_result_reports_duplicate_guard_blocking() -> None:
    draft: dict[str, Any] | None = None
    intention: dict[str, Any] | None = None
    try:
        draft, intention, rendered_text = await _create_send_chain(
            start_at=_utc(2134, 7, 3),
            end_at=_utc(2134, 7, 4),
        )
        delivery_intention_id = intention["delivery_intention_id"]
        async with AsyncSessionLocal() as session:
            recorded = await record_digest_delivery_result(
                session,
                delivery_intention_id=delivery_intention_id,
                execution_attempt_id="fos073-successful-attempt",
                result_status="succeeded",
                attempted_chunk_count=1,
                delivered_chunk_count=1,
                failed_chunk_count=0,
                safe_message_refs=[{"message_id": "safe-message-1"}],
                delivery_invoked=True,
                delivery_adapter_invoked=True,
                actor="test",
            )
            await session.commit()

        before_result_count = await _delivery_result_count(delivery_intention_id)
        report = await status_script.build_send_status_report(
            _query(delivery_intention_id)
        )

        assert report["delivery_results"]["count"] == 1
        assert report["delivery_results"]["successful_count"] == 1
        assert report["duplicate_guard"] == {
            "would_block_new_execution_attempt": True,
            "blocker": "delivery_intention_already_successfully_sent",
            "prior_successful_delivery_result_id": recorded["delivery_result_id"],
            "prior_successful_execution_attempt_id": "fos073-successful-attempt",
            "prior_successful_result_status": "succeeded",
            "prior_successful_delivered_chunk_count": 1,
        }
        assert report["recommended_next_action"] == "do_not_resend_same_intention"
        assert await _delivery_result_count(delivery_intention_id) == before_result_count
        text = status_script.format_text_report(report)
        assert "Duplicate guard would block new execution attempt: True" in text
        assert "delivery_intention_already_successfully_sent" in _serialized(report)
        _assert_safe_output(_serialized(report), rendered_text=rendered_text)
        _assert_safe_output(text, rendered_text=rendered_text)
    finally:
        if draft is not None:
            await _delete_delivery_chain(
                delivery_draft_id=draft["delivery_draft_id"],
                delivery_intention_id=(
                    intention["delivery_intention_id"] if intention else None
                ),
            )


async def test_failed_partial_skipped_and_incomplete_results_do_not_block() -> None:
    draft: dict[str, Any] | None = None
    intention: dict[str, Any] | None = None
    try:
        draft, intention, rendered_text = await _create_send_chain(
            start_at=_utc(2134, 7, 5),
            end_at=_utc(2134, 7, 6),
            rendered_text=_two_chunk_rendered_text(),
        )
        delivery_intention_id = intention["delivery_intention_id"]
        async with AsyncSessionLocal() as session:
            await record_digest_delivery_result(
                session,
                delivery_intention_id=delivery_intention_id,
                execution_attempt_id="fos073-failed-attempt",
                result_status="failed",
                attempted_chunk_count=1,
                delivered_chunk_count=0,
                failed_chunk_count=1,
                safe_error_code="telegram_send_failed",
                safe_error_summary="Safe failed attempt.",
                delivery_invoked=True,
                delivery_adapter_invoked=True,
                actor="test",
            )
            await record_digest_delivery_result(
                session,
                delivery_intention_id=delivery_intention_id,
                execution_attempt_id="fos073-partial-attempt",
                result_status="partial",
                attempted_chunk_count=2,
                delivered_chunk_count=1,
                failed_chunk_count=1,
                safe_message_refs=[{"message_id": "safe-partial-message"}],
                safe_error_code="telegram_send_failed",
                safe_error_summary="Safe partial attempt.",
                delivery_invoked=True,
                delivery_adapter_invoked=True,
                actor="test",
            )
            await record_digest_delivery_result(
                session,
                delivery_intention_id=delivery_intention_id,
                execution_attempt_id="fos073-skipped-attempt",
                result_status="skipped",
                attempted_chunk_count=0,
                delivered_chunk_count=0,
                failed_chunk_count=0,
                delivery_invoked=False,
                delivery_adapter_invoked=False,
                actor="test",
            )
            session.add(
                AuditLog(
                    event_type=DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
                    actor="test",
                    correlation_id=delivery_intention_id,
                    trace_id="dres_fos073_incomplete",
                    before_ref=delivery_intention_id,
                    after_ref="dres_fos073_incomplete",
                    approval_id=f"{delivery_intention_id}:delivery_result",
                    payload={
                        "status": "delivery_result",
                        "delivery_result_id": "dres_fos073_incomplete",
                        "delivery_intention_id": delivery_intention_id,
                        "execution_attempt_id": "fos073-incomplete-attempt",
                        "result_status": "succeeded",
                        "sent": True,
                        "rendered_text": "PRIVATE_RENDERED_TEXT_DO_NOT_EXPOSE",
                        "raw_response": "PRIVATE_TELEGRAM_RAW_RESPONSE",
                    },
                )
            )
            await session.commit()

        report = await status_script.build_send_status_report(
            _query(delivery_intention_id)
        )

        assert report["delivery_results"]["count"] == 4
        assert report["delivery_results"]["successful_count"] == 0
        assert report["delivery_results"]["failed_count"] == 1
        assert report["delivery_results"]["partial_count"] == 1
        assert report["delivery_results"]["skipped_count"] == 1
        assert (
            report["duplicate_guard"]["would_block_new_execution_attempt"]
            is False
        )
        assert report["duplicate_guard"]["blocker"] is None
        assert report["recommended_next_action"] == "safe_to_consider_new_bounded_attempt"
        _assert_safe_output(_serialized(report), rendered_text=rendered_text)
        _assert_safe_output(
            status_script.format_text_report(report),
            rendered_text=rendered_text,
        )
    finally:
        if draft is not None:
            await _delete_delivery_chain(
                delivery_draft_id=draft["delivery_draft_id"],
                delivery_intention_id=(
                    intention["delivery_intention_id"] if intention else None
                ),
            )
