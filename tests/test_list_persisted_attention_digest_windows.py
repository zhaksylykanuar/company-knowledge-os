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
from app.db.models import AuditLog
from app.services.digest_delivery_drafts import (
    approve_digest_delivery_draft,
    create_digest_delivery_intention,
    record_digest_delivery_result,
)
from scripts import list_persisted_attention_digest_windows as discovery_script
from scripts import seed_local_persisted_attention_digest as seed_script
from tests.test_prepare_manual_pilot_delivery_draft import (
    _cleanup_delivery_results_for_intention,
    _cleanup_draft,
)
from tests.test_report_manual_pilot_status import _prepare_draft
from tests.test_report_manual_pilot_status import _persist_two_chunk_draft
from tests.test_seed_local_persisted_attention_digest import (
    _cleanup_seed,
    _ensure_seed_tables,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "list_persisted_attention_digest_windows.py"


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
        "Local synthetic digest seed",
        "Non synthetic private title",
        "non synthetic private summary",
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
        sample_id=sample_id or f"fos079-{uuid4().hex}",
        created_at=created_at or _utc(2148, 1, 1, 9),
        confirm_local_seed=seed_script.CONFIRM_LOCAL_SEED_PHRASE,
        output_format="json",
    )


def _discovery_query(
    *,
    start_at: datetime,
    end_at: datetime,
    window_size_hours: int = 24,
    max_windows: int = 31,
    include_empty: bool = False,
    limit: int = 20,
) -> discovery_script.WindowDiscoveryQuery:
    return discovery_script.WindowDiscoveryQuery(
        start_at=start_at,
        end_at=end_at,
        window_size_hours=window_size_hours,
        max_windows=max_windows,
        limit=limit,
        debug_evidence=False,
        include_empty=include_empty,
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
    result = await seed_script.execute_seed(
        seed_query,
        settings_override=_local_settings(),
        environ={},
    )
    return (
        datetime.fromisoformat(result["window"]["start_at"]),
        datetime.fromisoformat(result["window"]["end_at"]),
    )


async def _insert_non_synthetic_attention_result(
    *,
    triage_result_id: str,
    created_at: datetime,
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            AttentionTriageResultRecord(
                triage_result_id=triage_result_id,
                source="internal",
                source_object_id=f"manual.local.non_synthetic_marker:{triage_result_id}",
                activity_item_id=None,
                attention_class="requires_my_attention",
                priority="high",
                show_in_digest=True,
                confidence=0.99,
                reason="Non synthetic private reason must not be printed.",
                recommended_action=(
                    "Non synthetic private action must not be printed."
                ),
                owner="operator",
                deadline=None,
                evidence_refs=[],
                created_at=created_at,
            )
        )
        await session.commit()


async def _delete_attention_result(triage_result_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.triage_result_id == triage_result_id
            )
        )
        await session.commit()


def test_missing_required_args_fail_safely() -> None:
    missing_start = _run_script("--end-at", "2148-01-02T00:00:00+00:00")
    missing_end = _run_script("--start-at", "2148-01-01T00:00:00+00:00")

    assert missing_start.returncode == 2
    assert "--start-at" in missing_start.stderr
    assert missing_end.returncode == 2
    assert "--end-at" in missing_end.stderr
    _assert_safe_output(missing_start.stdout + missing_start.stderr)
    _assert_safe_output(missing_end.stdout + missing_end.stderr)


def test_invalid_inputs_fail_before_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden_discovery(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid input must fail before DB execution")

    monkeypatch.setattr(
        discovery_script,
        "build_persisted_attention_window_discovery",
        forbidden_discovery,
    )

    base = [
        "--start-at",
        "2148-01-01T00:00:00+00:00",
        "--end-at",
        "2148-01-02T00:00:00+00:00",
        "--format",
        "json",
    ]
    naive_start = discovery_script.main(
        [
            "--start-at",
            "2148-01-01T00:00:00",
            "--end-at",
            "2148-01-02T00:00:00+00:00",
            "--format",
            "json",
        ]
    )
    reversed_range = discovery_script.main(
        [
            "--start-at",
            "2148-01-02T00:00:00+00:00",
            "--end-at",
            "2148-01-01T00:00:00+00:00",
            "--format",
            "json",
        ]
    )
    bad_window_size = discovery_script.main(
        [*base, "--window-size-hours", "0"]
    )
    too_high_window_size = discovery_script.main(
        [
            *base,
            "--window-size-hours",
            str(discovery_script.MAX_WINDOW_SIZE_HOURS + 1),
        ]
    )
    bad_max_windows = discovery_script.main([*base, "--max-windows", "0"])
    too_high_max_windows = discovery_script.main(
        [*base, "--max-windows", str(discovery_script.MAX_DISCOVERY_WINDOWS + 1)]
    )
    too_high_limit = discovery_script.main([*base, "--limit", "51"])
    too_many_windows = discovery_script.main(
        [
            "--start-at",
            "2148-01-01T00:00:00+00:00",
            "--end-at",
            "2148-01-04T00:00:00+00:00",
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
    assert too_high_limit == 2
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
            "2148-01-01T00:00:00+00:00",
            "--end-at",
            "2148-01-02T00:00:00+00:00",
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

    with pytest.raises(discovery_script.WindowDiscoveryBlockedError):
        await discovery_script.build_persisted_attention_window_discovery(
            _discovery_query(start_at=_utc(2148, 1, 1), end_at=_utc(2148, 1, 2)),
            session_factory=FailingSession,
            settings_override=SimpleNamespace(app_env="production"),
            environ={},
        )


async def test_empty_windows_are_omitted_or_included_safely() -> None:
    await _ensure_seed_tables()
    query = _discovery_query(
        start_at=_utc(2199, 1, 1),
        end_at=_utc(2199, 1, 2),
        include_empty=False,
    )
    before_count = await _audit_log_count()

    omitted = await discovery_script.build_persisted_attention_window_discovery(
        query,
        settings_override=_local_settings(),
        environ={},
    )
    included = await discovery_script.build_persisted_attention_window_discovery(
        _discovery_query(
            start_at=_utc(2199, 1, 1),
            end_at=_utc(2199, 1, 2),
            include_empty=True,
        ),
        settings_override=_local_settings(),
        environ={},
    )

    assert omitted["status"] == "persisted_attention_window_discovery"
    assert omitted["scanned_window_count"] == 1
    assert omitted["returned_window_count"] == 0
    assert omitted["windows"] == []
    assert omitted["aggregate_summary"]["non_empty_window_count"] == 0

    assert included["returned_window_count"] == 1
    window = included["windows"][0]
    assert window["digest"]["total"] == 0
    assert window["digest"]["visible"] == 0
    assert window["recommended_next_action"] == "seed_or_choose_non_empty_window"
    assert window["synthetic_status"] == "no_synthetic_marker_detected"
    assert included["safety"]["read_only"] is True
    assert included["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_count
    _assert_safe_output(_serialized(omitted))
    _assert_safe_output(_serialized(included))
    _assert_safe_output(discovery_script.format_text_report(included))


async def test_non_empty_synthetic_window_without_draft_recommends_prepare() -> None:
    await _ensure_seed_tables()
    seed_query = _seed_query(created_at=_utc(2148, 1, 2, 9))
    await _cleanup_seed(seed_query)
    try:
        start_at, end_at = await _seed_window(seed_query)
        report = await discovery_script.build_persisted_attention_window_discovery(
            _discovery_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["returned_window_count"] == 1
        assert report["aggregate_summary"]["non_empty_window_count"] == 1
        assert report["aggregate_summary"]["visible_window_count"] == 1
        assert report["aggregate_summary"]["synthetic_local_dev_window_count"] == 1
        window = report["windows"][0]
        assert window["digest"]["visible"] >= 1
        assert window["synthetic_status"] == "synthetic_local_dev_detected"
        assert window["drafts"]["count"] == 0
        assert (
            window["recommended_next_action"]
            == "prepare_manual_pilot_delivery_draft"
        )
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup_seed(seed_query)


async def test_window_without_synthetic_marker_is_labeled_conservatively() -> None:
    await _ensure_seed_tables()
    triage_result_id = f"atri_fos079_{uuid4().hex}"
    start_at = _utc(2148, 1, 3)
    end_at = _utc(2148, 1, 4)
    try:
        await _insert_non_synthetic_attention_result(
            triage_result_id=triage_result_id,
            created_at=_utc(2148, 1, 3, 9),
        )
        report = await discovery_script.build_persisted_attention_window_discovery(
            _discovery_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        assert report["returned_window_count"] == 1
        window = report["windows"][0]
        assert window["digest"]["visible"] == 1
        assert window["synthetic_status"] == "no_synthetic_marker_detected"
        assert window["synthetic_status"] != "production"
        assert (
            "no_synthetic_marker_is_not_proof_of_production_truth"
            in window["limitations"]
        )
        _assert_safe_output(_serialized(report))
        _assert_safe_output(discovery_script.format_text_report(report))
    finally:
        await _delete_attention_result(triage_result_id)


async def test_lifecycle_actions_progress_from_draft_to_handoff_and_send() -> None:
    await _ensure_seed_tables()
    unapproved_seed = _seed_query(created_at=_utc(2148, 1, 4, 9))
    approved_seed = _seed_query(created_at=_utc(2148, 1, 5, 9))
    intention_seed = _seed_query(created_at=_utc(2148, 1, 6, 9))
    for seed_query in (unapproved_seed, approved_seed, intention_seed):
        await _cleanup_seed(seed_query)

    draft_ids: list[str] = []
    delivery_intention_id: str | None = None
    try:
        unapproved_draft_id, _, _ = await _prepare_draft(seed_query=unapproved_seed)
        approved_draft_id, _, _ = await _prepare_draft(seed_query=approved_seed)
        intention_draft_id, _, _ = await _prepare_draft(seed_query=intention_seed)
        draft_ids.extend([unapproved_draft_id, approved_draft_id, intention_draft_id])

        async with AsyncSessionLocal() as session:
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=approved_draft_id,
                reviewer="founder",
                note="Approved for FOS-079 handoff candidate.",
            )
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=intention_draft_id,
                reviewer="founder",
                note="Approved for FOS-079 send candidate.",
            )
            intention = await create_digest_delivery_intention(
                session,
                delivery_draft_id=intention_draft_id,
                actor="test",
            )
            delivery_intention_id = intention["delivery_intention_id"]
            await session.commit()

        report = await discovery_script.build_persisted_attention_window_discovery(
            _discovery_query(
                start_at=_utc(2148, 1, 4),
                end_at=_utc(2148, 1, 7),
                max_windows=3,
            ),
            settings_override=_local_settings(),
            environ={},
        )

        actions = {
            window["start_at"]: window["recommended_next_action"]
            for window in report["windows"]
        }
        assert actions["2148-01-04T00:00:00+00:00"] == "approve_delivery_draft"
        assert (
            actions["2148-01-05T00:00:00+00:00"]
            == "continue_approved_draft_handoff"
        )
        assert (
            actions["2148-01-06T00:00:00+00:00"]
            == "review_gate_before_bounded_send"
        )
        assert report["aggregate_summary"]["candidate_approval_window_count"] == 1
        assert report["aggregate_summary"]["candidate_handoff_window_count"] == 1
        assert report["aggregate_summary"]["candidate_send_window_count"] == 1
        _assert_safe_output(_serialized(report))
    finally:
        for seed_query in (unapproved_seed, approved_seed, intention_seed):
            await _cleanup_seed(seed_query)
        if delivery_intention_id is not None:
            await _cleanup_delivery_results_for_intention(delivery_intention_id)
        for delivery_draft_id in draft_ids:
            await _cleanup_draft(delivery_draft_id)


async def test_successful_result_reports_duplicate_and_stale_warning() -> None:
    await _ensure_seed_tables()
    seed_query = _seed_query(created_at=_utc(2148, 1, 7, 9))
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
                note="Approved for FOS-079 duplicate warning.",
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
                execution_attempt_id="fos079-successful-attempt",
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

        report = await discovery_script.build_persisted_attention_window_discovery(
            _discovery_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        window = report["windows"][0]
        lifecycle = window["lifecycle_summary"]
        assert lifecycle["has_successful_delivery_result"] is True
        assert lifecycle["duplicate_guard_would_block_any_known_intention"] is True
        assert lifecycle["stale_or_already_sent_warning"] is True
        assert (
            window["recommended_next_action"]
            == "create_new_digest_window_or_synthetic_sample_before_another_send"
        )
        draft = window["drafts"]["items"][0]
        assert draft["blocker"] == "delivery_draft_already_successfully_sent"
        assert (
            draft["draft_usage_status"]["prior_successful_delivery_result_id"]
            == result["delivery_result_id"]
        )
        assert report["aggregate_summary"]["already_sent_window_count"] == 1
        text = discovery_script.format_text_report(report)
        assert "Already-sent windows: 1" in text
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
    seed_query = _seed_query(created_at=_utc(2148, 1, 8, 9))
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
                note="Approved for FOS-079 non-success results.",
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
                execution_attempt_id="fos079-failed-attempt",
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
                execution_attempt_id="fos079-partial-attempt",
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
                execution_attempt_id="fos079-skipped-attempt",
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

        report = await discovery_script.build_persisted_attention_window_discovery(
            _discovery_query(start_at=start_at, end_at=end_at),
            settings_override=_local_settings(),
            environ={},
        )

        window = report["windows"][0]
        assert window["lifecycle_summary"]["has_successful_delivery_result"] is False
        assert (
            window["lifecycle_summary"]["duplicate_guard_would_block_any_known_intention"]
            is False
        )
        assert window["lifecycle_summary"]["stale_or_already_sent_warning"] is False
        assert window["recommended_next_action"] == "review_gate_before_bounded_send"
        draft = window["drafts"]["items"][0]
        assert draft["delivery_results_summary"] == {
            "count": 3,
            "successful_count": 0,
            "failed_count": 1,
            "partial_count": 1,
            "skipped_count": 1,
        }
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup_seed(seed_query)
        if delivery_intention_id is not None:
            await _cleanup_delivery_results_for_intention(delivery_intention_id)
        if delivery_draft_id is not None:
            await _cleanup_draft(delivery_draft_id)
