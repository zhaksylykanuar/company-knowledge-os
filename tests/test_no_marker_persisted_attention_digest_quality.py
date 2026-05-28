from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.db.base import AsyncSessionLocal
from app.services.digest import (
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
    build_persisted_attention_digest_read_model,
)
from scripts import (
    report_no_marker_persisted_attention_digest_quality as quality_script,
)
from tests.test_no_marker_persisted_attention_candidates import (
    _assert_safe_output,
    _audit_log_count,
    _cleanup,
    _ensure_tables,
    _insert_attention_result,
    _insert_normalized_activity,
    _insert_source_event,
    _local_settings,
    _persist_successful_draft_for_digest,
    _serialized,
    _utc,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "report_no_marker_persisted_attention_digest_quality.py"


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
    start_at: datetime,
    end_at: datetime,
    activity_start_at: datetime | None = None,
    activity_end_at: datetime | None = None,
    limit: int = 20,
    cluster_threshold: int = 2,
) -> quality_script.NoMarkerDigestQualityQuery:
    return quality_script.NoMarkerDigestQualityQuery(
        start_at=start_at,
        end_at=end_at,
        activity_start_at=activity_start_at,
        activity_end_at=activity_end_at,
        limit=limit,
        debug_evidence=False,
        cluster_threshold=cluster_threshold,
        output_format="json",
    )


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
        quality_script,
        "build_no_marker_persisted_attention_digest_quality_report",
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
        quality_script.main(
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
        quality_script.main(
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
    assert quality_script.main([*base, "--limit", "0"]) == 2
    assert quality_script.main([*base, "--cluster-threshold", "1"]) == 2
    assert quality_script.main([*base, "--cluster-threshold", "51"]) == 2
    assert (
        quality_script.main(
            [*base, "--activity-start-at", "2149-01-01T00:00:00+00:00"]
        )
        == 2
    )
    assert (
        quality_script.main(
            [
                *base,
                "--activity-start-at",
                "2149-01-02T00:00:00+00:00",
                "--activity-end-at",
                "2149-01-01T00:00:00+00:00",
            ]
        )
        == 2
    )


def test_cli_rejects_credential_send_mutation_and_marker_filter_args() -> None:
    for forbidden_arg in (
        "--marker-filter",
        "--bot-token",
        "--chat-id",
        "--target-channel",
        "--production-mode",
        "--confirm-send",
        "--confirm-prepare",
        "--confirm-local-seed",
        "--confirm-create-intention",
        "--confirm-normalize",
        "--confirm-triage",
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


async def test_empty_digest_window_reports_safe_empty_quality_status() -> None:
    await _ensure_tables()
    before_audit = await _audit_log_count()

    report = (
        await quality_script.build_no_marker_persisted_attention_digest_quality_report(
            _query(start_at=_utc(2199, 1, 1), end_at=_utc(2199, 1, 2)),
            settings_override=_local_settings(),
            environ={},
        )
    )

    assert report["candidate"]["visible"] == 0
    assert report["duplicate_quality"]["candidate_visible_count"] == 0
    assert report["duplicate_quality"]["duplicate_like_item_count"] == 0
    assert report["duplicate_quality"]["high_duplicate_risk"] is False
    assert report["recommended_next_action"] == (
        "choose_window_with_no_marker_visible_candidates"
    )
    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_audit
    _assert_safe_output(_serialized(report))
    _assert_safe_output(quality_script.format_text_report(report))


async def test_synthetic_only_window_reports_no_no_marker_candidates() -> None:
    await _ensure_tables()
    unique = f"quality_synthetic_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 6, 1, 9),
            synthetic=True,
        )

        report = (
            await quality_script.build_no_marker_persisted_attention_digest_quality_report(
                _query(start_at=_utc(2149, 6, 1), end_at=_utc(2149, 6, 2)),
                settings_override=_local_settings(),
                environ={},
            )
        )

        assert report["candidate"]["visible"] == 0
        assert report["excluded_markers"]["synthetic_marker_count"] == 1
        assert report["excluded_markers"]["synthetic_visible_count"] == 1
        assert report["duplicate_quality"]["high_duplicate_risk"] is False
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_no_marker_unique_items_report_low_duplicate_risk() -> None:
    await _ensure_tables()
    uniques = [f"quality_unique_{uuid4().hex}_{index}" for index in range(3)]
    for unique in uniques:
        await _cleanup(unique)
    try:
        await _insert_attention_result(
            uniques[0],
            created_at=_utc(2149, 6, 3, 9),
            attention_class="review_optional",
            priority="low",
        )
        await _insert_attention_result(
            uniques[1],
            created_at=_utc(2149, 6, 3, 10),
            attention_class="important_info",
            priority="medium",
        )
        await _insert_attention_result(
            uniques[2],
            created_at=_utc(2149, 6, 3, 11),
            attention_class="manual_action",
            priority="high",
        )

        report = (
            await quality_script.build_no_marker_persisted_attention_digest_quality_report(
                _query(start_at=_utc(2149, 6, 3), end_at=_utc(2149, 6, 4)),
                settings_override=_local_settings(),
                environ={},
            )
        )

        assert report["candidate"]["visible"] == 3
        assert report["duplicate_quality"]["candidate_visible_count"] == 3
        assert report["duplicate_quality"]["duplicate_cluster_count"] == 0
        assert report["duplicate_quality"]["duplicate_like_item_count"] == 0
        assert report["duplicate_quality"]["high_duplicate_risk"] is False
        assert report["recommended_next_action"] in {
            "continue_no_marker_manual_pilot_review",
            "inspect_linkage_limitations_before_another_send",
        }
        assert report["clusters"]["rendered_shape"]["top_clusters"] == []
        _assert_safe_output(_serialized(report))
        _assert_safe_output(quality_script.format_text_report(report))
    finally:
        for unique in uniques:
            await _cleanup(unique)


async def test_mixed_window_excludes_synthetic_before_quality_analysis() -> None:
    await _ensure_tables()
    synthetic_unique = f"quality_mixed_synthetic_{uuid4().hex}"
    no_marker_uniques = [
        f"quality_mixed_nomarker_{uuid4().hex}_{index}" for index in range(2)
    ]
    for unique in [synthetic_unique, *no_marker_uniques]:
        await _cleanup(unique)
    try:
        await _insert_attention_result(
            synthetic_unique,
            created_at=_utc(2149, 6, 5, 9),
            synthetic=True,
        )
        for index, unique in enumerate(no_marker_uniques):
            await _insert_attention_result(
                unique,
                created_at=_utc(2149, 6, 5, 10 + index),
            )

        report = (
            await quality_script.build_no_marker_persisted_attention_digest_quality_report(
                _query(start_at=_utc(2149, 6, 5), end_at=_utc(2149, 6, 6)),
                settings_override=_local_settings(),
                environ={},
            )
        )

        assert report["candidate"]["visible"] == 2
        assert report["excluded_markers"]["synthetic_visible_count"] == 1
        assert report["duplicate_quality"]["candidate_visible_count"] == 2
        assert report["duplicate_quality"]["duplicate_like_item_count"] == 2
        assert report["duplicate_quality"]["high_duplicate_risk"] is True
        assert "mixed_synthetic_and_no_marker_attention_results" in report["warnings"]
        _assert_safe_output(_serialized(report))
    finally:
        for unique in [synthetic_unique, *no_marker_uniques]:
            await _cleanup(unique)


async def test_repeated_no_marker_items_report_opaque_duplicate_clusters() -> None:
    await _ensure_tables()
    source_unique = f"quality_source_{uuid4().hex}"
    row_uniques = [f"quality_repeat_{uuid4().hex}_{index}" for index in range(3)]
    for unique in [*row_uniques, source_unique]:
        await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            source_unique,
            created_at=_utc(2149, 6, 7, 8),
        )
        for index, unique in enumerate(row_uniques):
            activity_item_id = await _insert_normalized_activity(
                unique,
                created_at=_utc(2149, 6, 7, 8),
                source_event_id=source_event_id,
            )
            await _insert_attention_result(
                unique,
                created_at=_utc(2149, 6, 8, 9 + index),
                activity_item_id=activity_item_id,
            )

        report = (
            await quality_script.build_no_marker_persisted_attention_digest_quality_report(
                _query(
                    start_at=_utc(2149, 6, 8),
                    end_at=_utc(2149, 6, 9),
                    activity_start_at=_utc(2149, 6, 7),
                    activity_end_at=_utc(2149, 6, 8),
                ),
                settings_override=_local_settings(),
                environ={},
            )
        )

        quality = report["duplicate_quality"]
        assert quality["candidate_visible_count"] == 3
        assert quality["duplicate_like_item_count"] == 3
        assert quality["duplicate_like_ratio"] == 1.0
        assert quality["duplicate_cluster_count"] == 1
        assert quality["largest_cluster_size"] == 3
        assert quality["high_duplicate_risk"] is True
        assert quality["possible_origin"] == "mixed"
        assert report["recommended_next_action"] == (
            "review_duplicate_noise_before_another_send"
        )
        assert "duplicate_noise_risk_detected" in report["warnings"]
        assert "duplicate_looking_not_semantic_duplicate" in report["warnings"]

        rendered_clusters = report["clusters"]["rendered_shape"]["top_clusters"]
        assert rendered_clusters == [
            {
                "cluster_id": "cluster_001",
                "count": 3,
                "safe_enum_summary": {
                    "by_attention_class": {"review_optional": 3},
                    "by_priority": {"low": 3},
                    "by_source": {"github": 3},
                },
            }
        ]
        assert report["clusters"]["attention_result"]["duplicate_cluster_count"] == 1
        assert (
            report["clusters"]["normalized_activity"]["duplicate_cluster_count"] == 1
        )
        assert (
            report["clusters"]["source_event_linkage"]["duplicate_cluster_count"] == 1
        )
        _assert_safe_output(_serialized(report))
        _assert_safe_output(quality_script.format_text_report(report))
    finally:
        for unique in row_uniques:
            await _cleanup(unique)
        await _cleanup(source_unique)


async def test_candidate_lifecycle_marks_already_sent_hash_without_writes() -> None:
    await _ensure_tables()
    unique = f"quality_sent_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 6, 10, 9),
        )
        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=_utc(2149, 6, 10),
                end_at=_utc(2149, 6, 11),
                limit_per_section=20,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
        await _persist_successful_draft_for_digest(
            unique,
            digest=digest,
            start_at=_utc(2149, 6, 10),
            end_at=_utc(2149, 6, 11),
        )
        before_audit = await _audit_log_count()

        report = (
            await quality_script.build_no_marker_persisted_attention_digest_quality_report(
                _query(start_at=_utc(2149, 6, 10), end_at=_utc(2149, 6, 11)),
                settings_override=_local_settings(),
                environ={},
            )
        )

        lifecycle = report["lifecycle"]
        assert lifecycle["candidate_has_matching_draft_hash"] is True
        assert lifecycle["matching_hash_has_successful_delivery_result"] is True
        assert lifecycle["candidate_lifecycle_status"] == (
            "candidate_already_successfully_sent"
        )
        assert report["recommended_next_action"] == "do_not_resend_same_digest_content"
        assert await _audit_log_count() == before_audit
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_output_contains_no_raw_or_trivially_mapped_fingerprint_values() -> None:
    await _ensure_tables()
    unique = f"quality_safety_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 6, 12, 9),
        )

        report = (
            await quality_script.build_no_marker_persisted_attention_digest_quality_report(
                _query(start_at=_utc(2149, 6, 12), end_at=_utc(2149, 6, 13)),
                settings_override=_local_settings(),
                environ={},
            )
        )

        rendered = _serialized(report)
        _assert_safe_output(rendered)
        assert "cluster_001" not in rendered
        assert "fingerprint" not in rendered.casefold()
        assert "sha256:" not in rendered.casefold()
        assert "PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE" not in rendered
        assert "private-pr" not in rendered
        assert report["safety"]["telegram_invoked"] is False
        assert report["safety"]["openai_invoked"] is False
        assert report["safety"]["delivery_draft_created"] is False
    finally:
        await _cleanup(unique)


async def test_quality_report_does_not_commit_or_flush_with_test_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    unique = f"quality_read_only_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 6, 14, 9),
        )

        class ReadOnlySession:
            def __init__(self) -> None:
                self._session_cm = AsyncSessionLocal()
                self.session: object | None = None

            async def __aenter__(self) -> object:
                self.session = await self._session_cm.__aenter__()
                for method_name in ("add", "flush", "commit", "delete"):
                    monkeypatch.setattr(
                        self.session,
                        method_name,
                        self._forbidden_write,
                    )
                return self.session

            async def __aexit__(self, *exc_info: object) -> object:
                return await self._session_cm.__aexit__(*exc_info)

            async def _forbidden_write(self, *_args: object, **_kwargs: object) -> None:
                raise AssertionError("quality report must stay read-only")

        def session_factory() -> ReadOnlySession:
            return ReadOnlySession()

        report = (
            await quality_script.build_no_marker_persisted_attention_digest_quality_report(
                _query(start_at=_utc(2149, 6, 14), end_at=_utc(2149, 6, 15)),
                session_factory=session_factory,
                settings_override=_local_settings(),
                environ={},
            )
        )

        assert report["safety"]["db_write_scope"] == "none"
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


def test_json_output_is_stable_and_sanitized() -> None:
    result = _run_script(
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--end-at",
        "2149-01-02T00:00:00+00:00",
    )

    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["status"] == "no_marker_persisted_attention_digest_quality"
    assert parsed["marker_filter"] == "no_marker_only"
    _assert_safe_output(result.stdout)
