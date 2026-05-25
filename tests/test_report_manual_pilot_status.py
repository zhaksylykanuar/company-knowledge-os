from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog
from app.services.digest_delivery_drafts import (
    approve_digest_delivery_draft,
    build_persisted_attention_digest_delivery_draft,
    create_digest_delivery_intention,
    persist_digest_delivery_draft,
    record_digest_delivery_result,
)
from scripts import prepare_manual_pilot_delivery_draft as prepare_script
from scripts import report_manual_pilot_status as pilot_status_script
from scripts import seed_local_persisted_attention_digest as seed_script
from tests.test_prepare_manual_pilot_delivery_draft import (
    _cleanup_delivery_results_for_intention,
    _cleanup_draft,
)
from tests.test_digest_delivery_intention_send_script import (
    _persisted_attention_digest,
    _two_chunk_rendered_text,
)
from tests.test_seed_local_persisted_attention_digest import (
    _cleanup_seed,
    _ensure_seed_tables,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "report_manual_pilot_status.py"


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


def _seed_query(
    *,
    sample_id: str | None = None,
    created_at: datetime | None = None,
) -> seed_script.SeedQuery:
    return seed_script.SeedQuery(
        sample_id=sample_id or f"fos078-{uuid4().hex}",
        created_at=created_at or _utc(2147, 1, 1, 9),
        confirm_local_seed=seed_script.CONFIRM_LOCAL_SEED_PHRASE,
        output_format="json",
    )


def _prepare_query(
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int = 20,
) -> prepare_script.PrepareQuery:
    return prepare_script.PrepareQuery(
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        debug_evidence=False,
        confirm_prepare=prepare_script.CONFIRM_PREPARE_PHRASE,
        output_format="json",
    )


def _status_query(
    *,
    start_at: datetime,
    end_at: datetime,
    sample_id: str | None = None,
    limit: int = 20,
) -> pilot_status_script.ManualPilotStatusQuery:
    return pilot_status_script.ManualPilotStatusQuery(
        start_at=start_at,
        end_at=end_at,
        sample_id=sample_id,
        limit=limit,
        debug_evidence=False,
        output_format="json",
    )


async def _audit_log_count() -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(select(func.count()).select_from(AuditLog)) or 0
        )


async def _seed_window(
    seed_query: seed_script.SeedQuery,
) -> tuple[datetime, datetime]:
    seed_result = await seed_script.execute_seed(
        seed_query,
        settings_override=_local_settings(),
        environ={},
    )
    return (
        datetime.fromisoformat(seed_result["window"]["start_at"]),
        datetime.fromisoformat(seed_result["window"]["end_at"]),
    )


async def _prepare_draft(
    *,
    seed_query: seed_script.SeedQuery,
) -> tuple[str, datetime, datetime]:
    start_at, end_at = await _seed_window(seed_query)
    prepared = await prepare_script.prepare_manual_pilot_delivery_draft(
        _prepare_query(start_at=start_at, end_at=end_at),
        settings_override=_local_settings(),
        environ={},
    )
    return prepared["delivery_draft_id"], start_at, end_at


async def _persist_two_chunk_draft(
    *,
    start_at: datetime,
    end_at: datetime,
) -> str:
    draft = build_persisted_attention_digest_delivery_draft(
        digest=_persisted_attention_digest(),
        rendered_text=_two_chunk_rendered_text(),
        start_at=start_at,
        end_at=end_at,
        limit=20,
    )
    delivery_draft_id = draft["delivery_draft_id"]
    await _cleanup_draft(delivery_draft_id)
    async with AsyncSessionLocal() as session:
        await persist_digest_delivery_draft(session, draft=draft, actor="test")
        await session.commit()
    return delivery_draft_id


def test_missing_required_args_fail_safely() -> None:
    missing_start = _run_script("--end-at", "2147-01-02T00:00:00+00:00")
    missing_end = _run_script("--start-at", "2147-01-01T00:00:00+00:00")

    assert missing_start.returncode == 2
    assert "--start-at" in missing_start.stderr
    assert missing_end.returncode == 2
    assert "--end-at" in missing_end.stderr
    _assert_safe_output(missing_start.stdout + missing_start.stderr)
    _assert_safe_output(missing_end.stdout + missing_end.stderr)


def test_invalid_inputs_fail_before_report_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_report(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid input must fail before report execution")

    monkeypatch.setattr(
        pilot_status_script,
        "build_manual_pilot_status_report",
        forbidden_report,
    )

    naive_start = pilot_status_script.main(
        [
            "--start-at",
            "2147-01-01T00:00:00",
            "--end-at",
            "2147-01-02T00:00:00+00:00",
            "--format",
            "json",
        ]
    )
    reversed_window = pilot_status_script.main(
        [
            "--start-at",
            "2147-01-02T00:00:00+00:00",
            "--end-at",
            "2147-01-01T00:00:00+00:00",
            "--format",
            "json",
        ]
    )
    blank_sample = pilot_status_script.main(
        [
            "--start-at",
            "2147-01-01T00:00:00+00:00",
            "--end-at",
            "2147-01-02T00:00:00+00:00",
            "--sample-id",
            " ",
            "--format",
            "json",
        ]
    )
    too_high_limit = pilot_status_script.main(
        [
            "--start-at",
            "2147-01-01T00:00:00+00:00",
            "--end-at",
            "2147-01-02T00:00:00+00:00",
            "--limit",
            "51",
            "--format",
            "json",
        ]
    )

    assert naive_start == 2
    assert reversed_window == 2
    assert blank_sample == 2
    assert too_high_limit == 2


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
            "2147-01-01T00:00:00+00:00",
            "--end-at",
            "2147-01-02T00:00:00+00:00",
            forbidden_arg,
            "value",
        )
        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr
        _assert_safe_output(result.stdout + result.stderr)


async def test_empty_digest_window_reports_no_items_and_no_writes() -> None:
    await _ensure_seed_tables()
    query = _status_query(
        start_at=_utc(2198, 1, 1),
        end_at=_utc(2198, 1, 2),
    )
    before_count = await _audit_log_count()

    report = await pilot_status_script.build_manual_pilot_status_report(
        query,
        settings_override=_local_settings(),
        environ={},
    )

    assert report["status"] == "manual_pilot_status"
    assert report["digest"]["total"] == 0
    assert report["digest"]["visible"] == 0
    assert report["drafts"]["count"] == 0
    assert report["lifecycle_summary"]["has_digest_items"] is False
    assert report["recommended_next_action"] == "seed_or_choose_non_empty_window"
    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert report["safety"]["delivery_invoked"] is False
    assert await _audit_log_count() == before_count
    _assert_safe_output(_serialized(report))
    _assert_safe_output(pilot_status_script.format_text_report(report))


async def test_non_empty_digest_without_draft_recommends_prepare() -> None:
    await _ensure_seed_tables()
    seed_query = _seed_query(created_at=_utc(2147, 2, 1, 9))
    await _cleanup_seed(seed_query)
    try:
        start_at, end_at = await _seed_window(seed_query)
        report = await pilot_status_script.build_manual_pilot_status_report(
            _status_query(
                start_at=start_at,
                end_at=end_at,
                sample_id=seed_query.sample_id,
            ),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["sample"]["provided"] is True
        assert report["sample"]["match_found"] is True
        assert report["sample"]["synthetic_local_dev_only"] is True
        assert report["digest"]["visible"] >= 1
        assert report["drafts"]["count"] == 0
        assert (
            report["recommended_next_action"]
            == "prepare_manual_pilot_delivery_draft"
        )
        assert "prepare_manual_pilot_delivery_draft.py" in report["next_steps"][
            "prepare_manual_pilot_delivery_draft"
        ]
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup_seed(seed_query)


async def test_unapproved_draft_recommends_approval() -> None:
    await _ensure_seed_tables()
    seed_query = _seed_query(created_at=_utc(2147, 2, 2, 9))
    await _cleanup_seed(seed_query)
    delivery_draft_id: str | None = None
    try:
        delivery_draft_id, start_at, end_at = await _prepare_draft(
            seed_query=seed_query
        )
        before_count = await _audit_log_count()
        report = await pilot_status_script.build_manual_pilot_status_report(
            _status_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["drafts"]["count"] == 1
        draft = report["drafts"]["items"][0]
        assert draft["delivery_draft_id"] == delivery_draft_id
        assert draft["approval_status"]["approved"] is False
        assert draft["approval_status"]["rejected"] is False
        assert report["recommended_next_action"] == "approve_delivery_draft"
        assert report["lifecycle_summary"]["has_delivery_draft"] is True
        assert await _audit_log_count() == before_count
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup_seed(seed_query)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)


async def test_approved_ready_draft_without_intention_recommends_handoff() -> None:
    await _ensure_seed_tables()
    seed_query = _seed_query(created_at=_utc(2147, 2, 3, 9))
    await _cleanup_seed(seed_query)
    delivery_draft_id: str | None = None
    try:
        delivery_draft_id, start_at, end_at = await _prepare_draft(
            seed_query=seed_query
        )
        async with AsyncSessionLocal() as session:
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Approved for FOS-078 status test.",
            )
            await session.commit()

        report = await pilot_status_script.build_manual_pilot_status_report(
            _status_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["drafts"]["count"] == 1
        assert report["drafts"]["items"][0]["approval_status"]["approved"] is True
        assert report["drafts"]["items"][0]["readiness"]["eligible_for_delivery"] is True
        assert report["drafts"]["items"][0]["associated_delivery_intentions"] == []
        assert report["recommended_next_action"] == "continue_approved_draft_handoff"
        assert "continue_manual_pilot_delivery_draft.py" in report["next_steps"][
            "continue_approved_draft_handoff"
        ]
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup_seed(seed_query)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)


async def test_intention_without_success_recommends_review_gate_before_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_seed_tables()
    seed_query = _seed_query(created_at=_utc(2147, 2, 4, 9))
    await _cleanup_seed(seed_query)
    delivery_draft_id: str | None = None
    delivery_intention_id: str | None = None

    from app.services import telegram_delivery

    async def forbidden_send(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("manual pilot status report must not send")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    try:
        delivery_draft_id, start_at, end_at = await _prepare_draft(
            seed_query=seed_query
        )
        async with AsyncSessionLocal() as session:
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Approved for FOS-078 intention status test.",
            )
            intention = await create_digest_delivery_intention(
                session,
                delivery_draft_id=delivery_draft_id,
                actor="test",
            )
            delivery_intention_id = intention["delivery_intention_id"]
            await session.commit()

        report = await pilot_status_script.build_manual_pilot_status_report(
            _status_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        draft = report["drafts"]["items"][0]
        intention_summary = draft["associated_delivery_intentions"][0]
        assert intention_summary["delivery_intention_id"] == delivery_intention_id
        assert intention_summary["delivery_results"]["count"] == 0
        assert (
            intention_summary["duplicate_guard"][
                "would_block_new_execution_attempt"
            ]
            is False
        )
        assert report["recommended_next_action"] == "review_gate_before_bounded_send"
        assert "DO NOT RUN UNTIL CHECKS PASS" in report["next_steps"][
            "bounded_test_send_do_not_run_until_checks_pass"
        ]
        _assert_safe_output(_serialized(report))
        _assert_safe_output(pilot_status_script.format_text_report(report))
    finally:
        await _cleanup_seed(seed_query)
        if delivery_intention_id is not None:
            await _cleanup_delivery_results_for_intention(delivery_intention_id)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)


async def test_successful_result_surfaces_duplicate_and_stale_warning() -> None:
    await _ensure_seed_tables()
    seed_query = _seed_query(created_at=_utc(2147, 2, 5, 9))
    await _cleanup_seed(seed_query)
    delivery_draft_id: str | None = None
    delivery_intention_id: str | None = None
    try:
        delivery_draft_id, start_at, end_at = await _prepare_draft(
            seed_query=seed_query
        )
        async with AsyncSessionLocal() as session:
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Approved for FOS-078 successful status test.",
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
                execution_attempt_id="fos078-successful-attempt",
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

        report = await pilot_status_script.build_manual_pilot_status_report(
            _status_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        lifecycle = report["lifecycle_summary"]
        assert lifecycle["has_successful_delivery_result"] is True
        assert lifecycle["duplicate_guard_would_block_any_known_intention"] is True
        assert lifecycle["stale_or_already_sent_warning"] is True
        assert (
            report["recommended_next_action"]
            == "create_new_digest_window_or_synthetic_sample_before_another_send"
        )
        draft = report["drafts"]["items"][0]
        assert draft["stale_or_already_sent_warning"] is True
        assert draft["blocker"] == "delivery_draft_already_successfully_sent"
        assert (
            draft["draft_usage_status"]["prior_successful_delivery_result_id"]
            == result["delivery_result_id"]
        )
        intention_summary = draft["associated_delivery_intentions"][0]
        assert (
            intention_summary["duplicate_guard"]["blocker"]
            == "delivery_intention_already_successfully_sent"
        )
        assert (
            intention_summary["duplicate_guard"][
                "prior_successful_execution_attempt_id"
            ]
            == "fos078-successful-attempt"
        )
        text = pilot_status_script.format_text_report(report)
        assert "Stale or already-sent warning: True" in text
        assert "create_new_digest_window_or_synthetic_sample" in text
        _assert_safe_output(_serialized(report))
        _assert_safe_output(text)
    finally:
        await _cleanup_seed(seed_query)
        if delivery_intention_id is not None:
            await _cleanup_delivery_results_for_intention(delivery_intention_id)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)


async def test_failed_partial_and_skipped_results_do_not_count_as_success() -> None:
    await _ensure_seed_tables()
    seed_query = _seed_query(created_at=_utc(2147, 2, 6, 9))
    await _cleanup_seed(seed_query)
    delivery_draft_id: str | None = None
    delivery_intention_id: str | None = None
    try:
        start_at, end_at = await _seed_window(seed_query)
        delivery_draft_id = await _persist_two_chunk_draft(
            start_at=start_at,
            end_at=end_at,
        )
        async with AsyncSessionLocal() as session:
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Approved for FOS-078 non-success status test.",
            )
            intention = await create_digest_delivery_intention(
                session,
                delivery_draft_id=delivery_draft_id,
                actor="test",
            )
            delivery_intention_id = intention["delivery_intention_id"]
            await record_digest_delivery_result(
                session,
                delivery_intention_id=delivery_intention_id,
                execution_attempt_id="fos078-failed-attempt",
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
                execution_attempt_id="fos078-partial-attempt",
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
                execution_attempt_id="fos078-skipped-attempt",
                result_status="skipped",
                attempted_chunk_count=0,
                delivered_chunk_count=0,
                failed_chunk_count=0,
                safe_error_code="operator_skipped",
                safe_error_summary="Operator skipped before send.",
                delivery_invoked=False,
                delivery_adapter_invoked=False,
                actor="test",
            )
            await session.commit()

        report = await pilot_status_script.build_manual_pilot_status_report(
            _status_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        draft = report["drafts"]["items"][0]
        assert draft["delivery_results_summary"] == {
            "count": 3,
            "successful_count": 0,
            "failed_count": 1,
            "partial_count": 1,
            "skipped_count": 1,
        }
        intention_summary = draft["associated_delivery_intentions"][0]
        assert intention_summary["delivery_results"]["successful_count"] == 0
        assert (
            intention_summary["duplicate_guard"][
                "would_block_new_execution_attempt"
            ]
            is False
        )
        assert report["lifecycle_summary"]["has_successful_delivery_result"] is False
        assert report["lifecycle_summary"]["stale_or_already_sent_warning"] is False
        assert report["recommended_next_action"] == "review_gate_before_bounded_send"
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup_seed(seed_query)
        if delivery_intention_id is not None:
            await _cleanup_delivery_results_for_intention(delivery_intention_id)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)
