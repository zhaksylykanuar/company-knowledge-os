from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.services.digest import (
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
    build_persisted_attention_digest_read_model,
)
from scripts import (
    report_no_marker_persisted_attention_duplicate_root_cause as root_script,
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
SCRIPT = (
    REPO_ROOT
    / "scripts"
    / "report_no_marker_persisted_attention_duplicate_root_cause.py"
)


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
) -> root_script.NoMarkerDuplicateRootCauseQuery:
    return root_script.NoMarkerDuplicateRootCauseQuery(
        start_at=start_at,
        end_at=end_at,
        activity_start_at=activity_start_at,
        activity_end_at=activity_end_at,
        limit=limit,
        debug_evidence=False,
        cluster_threshold=cluster_threshold,
        output_format="json",
    )


async def _insert_custom_source_event(
    unique: str,
    *,
    created_at: datetime,
    source_object_id: str,
) -> str:
    source_event_id = f"sevt_fos086_{unique}"
    async with AsyncSessionLocal() as session:
        session.add(
            IngestedEvent(
                event_id=f"evt_fos086_{unique}",
                event_type="github.pull_request.opened",
                source_system="github",
                source_object_id=source_object_id,
                idempotency_key=f"idem_fos086_{unique}",
                correlation_id=f"corr_fos086_{unique}",
                trace_id=f"trace_fos086_{unique}",
                raw_object_ref="raw://PRIVATE_RAW_BODY_DO_NOT_EXPOSE",
                payload={"body": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE"},
                status="received",
                created_at=created_at,
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=source_event_id,
                source_event_key=f"source-key-fos089-{unique}",
                ingested_event_id=f"evt_fos086_{unique}",
                event_type="github.pull_request.opened",
                source_system="github",
                source_object_type="pull_request",
                source_object_id=source_object_id,
                source_event_ts=created_at,
                actor_external_id="Private No-Marker Actor",
                title="Private no-marker title must not print",
                summary="Private no-marker summary must not print",
                source_url="https://example.invalid/private",
                raw_object_ref="raw://PRIVATE_RAW_BODY_DO_NOT_EXPOSE",
                evidence_refs=[],
                metadata_json={},
                created_at=created_at,
            )
        )
        await session.commit()
    return source_event_id


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
        root_script,
        "build_no_marker_persisted_attention_duplicate_root_cause_report",
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
        root_script.main(
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
        root_script.main(
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
    assert root_script.main([*base, "--limit", "0"]) == 2
    assert root_script.main([*base, "--cluster-threshold", "1"]) == 2
    assert root_script.main([*base, "--cluster-threshold", "51"]) == 2
    assert (
        root_script.main(
            [*base, "--activity-start-at", "2149-01-01T00:00:00+00:00"]
        )
        == 2
    )
    assert (
        root_script.main(
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


async def test_empty_digest_window_reports_safe_empty_root_cause() -> None:
    await _ensure_tables()
    before_audit = await _audit_log_count()

    report = (
        await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
            _query(start_at=_utc(2199, 1, 1), end_at=_utc(2199, 1, 2)),
            settings_override=_local_settings(),
            environ={},
        )
    )

    assert report["candidate"]["visible"] == 0
    assert report["root_cause"]["candidate_visible_count"] == 0
    assert report["root_cause"]["likely_origin"] == "unknown"
    assert report["root_cause"]["confidence"] == "unknown"
    assert report["recommended_next_action"] == (
        "choose_window_with_no_marker_visible_candidates"
    )
    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_audit
    _assert_safe_output(_serialized(report))
    _assert_safe_output(root_script.format_text_report(report))


async def test_synthetic_only_window_reports_no_root_cause() -> None:
    await _ensure_tables()
    unique = f"root_synthetic_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 7, 1, 9),
            synthetic=True,
        )

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(start_at=_utc(2149, 7, 1), end_at=_utc(2149, 7, 2)),
                settings_override=_local_settings(),
                environ={},
            )
        )

        assert report["candidate"]["visible"] == 0
        assert report["quality_summary"]["high_duplicate_risk"] is False
        assert report["root_cause"]["likely_origin"] == "unknown"
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_no_marker_unique_items_report_no_duplicate_signal() -> None:
    await _ensure_tables()
    uniques = [f"root_unique_{uuid4().hex}_{index}" for index in range(3)]
    for unique in uniques:
        await _cleanup(unique)
    try:
        await _insert_attention_result(
            uniques[0],
            created_at=_utc(2149, 7, 3, 9),
            attention_class="review_optional",
            priority="low",
        )
        await _insert_attention_result(
            uniques[1],
            created_at=_utc(2149, 7, 3, 10),
            attention_class="important_info",
            priority="medium",
        )
        await _insert_attention_result(
            uniques[2],
            created_at=_utc(2149, 7, 3, 11),
            attention_class="manual_action",
            priority="high",
        )

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(start_at=_utc(2149, 7, 3), end_at=_utc(2149, 7, 4)),
                settings_override=_local_settings(),
                environ={},
            )
        )

        assert report["candidate"]["visible"] == 3
        assert report["quality_summary"]["high_duplicate_risk"] is False
        assert report["root_cause"]["likely_origin"] in {
            "unknown",
            "insufficient_linkage",
        }
        assert report["root_cause"]["confidence"] in {"unknown", "low"}
        _assert_safe_output(_serialized(report))
    finally:
        for unique in uniques:
            await _cleanup(unique)


async def test_same_source_object_repeated_reports_source_object_origin() -> None:
    await _ensure_tables()
    source_object_token = f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{uuid4().hex}"
    uniques = [f"root_same_obj_{uuid4().hex}_{index}" for index in range(3)]
    for unique in uniques:
        await _cleanup(unique)
    try:
        for index, unique in enumerate(uniques):
            source_event_id = await _insert_custom_source_event(
                unique,
                created_at=_utc(2149, 7, 5, 8 + index),
                source_object_id=source_object_token,
            )
            activity_item_id = await _insert_normalized_activity(
                unique,
                created_at=_utc(2149, 7, 5, 8 + index),
                source_event_id=source_event_id,
            )
            await _insert_attention_result(
                unique,
                created_at=_utc(2149, 7, 6, 9 + index),
                activity_item_id=activity_item_id,
            )

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(
                    start_at=_utc(2149, 7, 6),
                    end_at=_utc(2149, 7, 7),
                    activity_start_at=_utc(2149, 7, 5),
                    activity_end_at=_utc(2149, 7, 6),
                ),
                settings_override=_local_settings(),
                environ={},
            )
        )

        root = report["root_cause"]
        assert root["likely_origin"] == "source_object_repeated"
        assert root["confidence"] == "high"
        assert root["source_object_bucket_count"] == 1
        assert root["largest_source_object_bucket_size"] == 3
        assert root["single_source_object_bucket_covers_candidate"] is True
        assert root["source_event_bucket_count"] == 3
        assert report["recommended_next_action"] == (
            "inspect_source_event_ingestion_duplicates"
        )
        _assert_safe_output(_serialized(report))
        _assert_safe_output(root_script.format_text_report(report))
    finally:
        for unique in uniques:
            await _cleanup(unique)


async def test_distinct_source_objects_same_rendered_shape_reports_collision() -> None:
    await _ensure_tables()
    uniques = [f"root_rendered_{uuid4().hex}_{index}" for index in range(3)]
    for unique in uniques:
        await _cleanup(unique)
    try:
        for index, unique in enumerate(uniques):
            source_event_id = await _insert_source_event(
                unique,
                created_at=_utc(2149, 7, 8, 8 + index),
            )
            activity_item_id = await _insert_normalized_activity(
                unique,
                created_at=_utc(2149, 7, 8, 8 + index),
                source_event_id=source_event_id,
            )
            await _insert_attention_result(
                unique,
                created_at=_utc(2149, 7, 9, 9 + index),
                activity_item_id=activity_item_id,
            )

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(
                    start_at=_utc(2149, 7, 9),
                    end_at=_utc(2149, 7, 10),
                    activity_start_at=_utc(2149, 7, 8),
                    activity_end_at=_utc(2149, 7, 9),
                ),
                settings_override=_local_settings(),
                environ={},
            )
        )

        root = report["root_cause"]
        assert root["likely_origin"] == "rendered_shape_collision"
        assert root["confidence"] == "medium"
        assert root["source_object_bucket_count"] == 3
        assert root["rendered_shape_bucket_count"] == 1
        assert root["rendered_shape_collision_across_distinct_source_objects"] is True
        assert report["recommended_next_action"] == (
            "consider_renderer_grouping_after_review"
        )
        _assert_safe_output(_serialized(report))
    finally:
        for unique in uniques:
            await _cleanup(unique)


async def test_source_event_to_normalized_activity_fanout_reports_normalization() -> None:
    await _ensure_tables()
    source_unique = f"root_norm_source_{uuid4().hex}"
    row_uniques = [f"root_norm_{uuid4().hex}_{index}" for index in range(3)]
    for unique in [source_unique, *row_uniques]:
        await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            source_unique,
            created_at=_utc(2149, 7, 11, 8),
        )
        for index, unique in enumerate(row_uniques):
            activity_item_id = await _insert_normalized_activity(
                unique,
                created_at=_utc(2149, 7, 11, 8),
                source_event_id=source_event_id,
            )
            await _insert_attention_result(
                unique,
                created_at=_utc(2149, 7, 12, 9 + index),
                activity_item_id=activity_item_id,
            )

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(
                    start_at=_utc(2149, 7, 12),
                    end_at=_utc(2149, 7, 13),
                    activity_start_at=_utc(2149, 7, 11),
                    activity_end_at=_utc(2149, 7, 12),
                ),
                settings_override=_local_settings(),
                environ={},
            )
        )

        root = report["root_cause"]
        assert root["likely_origin"] == "normalization_fanout"
        assert root["confidence"] == "high"
        assert root["source_event_bucket_count"] == 1
        assert root["source_event_to_normalized_activity_fanout_detected"] is True
        assert root["source_event_to_normalized_activity_max_fanout"] == 3
        assert report["recommended_next_action"] == (
            "inspect_normalization_fanout_before_dedupe"
        )
        _assert_safe_output(_serialized(report))
    finally:
        for unique in row_uniques:
            await _cleanup(unique)
        await _cleanup(source_unique)


async def test_normalized_activity_to_attention_result_fanout_reports_attention() -> None:
    await _ensure_tables()
    source_unique = f"root_attn_source_{uuid4().hex}"
    attention_uniques = [f"root_attn_{uuid4().hex}_{index}" for index in range(3)]
    for unique in [source_unique, *attention_uniques]:
        await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            source_unique,
            created_at=_utc(2149, 7, 14, 8),
        )
        activity_item_id = await _insert_normalized_activity(
            source_unique,
            created_at=_utc(2149, 7, 14, 8),
            source_event_id=source_event_id,
        )
        for index, unique in enumerate(attention_uniques):
            await _insert_attention_result(
                unique,
                created_at=_utc(2149, 7, 15, 9 + index),
                activity_item_id=activity_item_id,
            )

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(
                    start_at=_utc(2149, 7, 15),
                    end_at=_utc(2149, 7, 16),
                    activity_start_at=_utc(2149, 7, 14),
                    activity_end_at=_utc(2149, 7, 15),
                ),
                settings_override=_local_settings(),
                environ={},
            )
        )

        root = report["root_cause"]
        assert root["likely_origin"] == "attention_result_fanout"
        assert root["confidence"] == "high"
        assert root["normalized_activity_bucket_count"] == 1
        assert root["normalized_activity_to_attention_result_fanout_detected"] is True
        assert root["normalized_activity_to_attention_result_max_fanout"] == 3
        assert report["recommended_next_action"] == (
            "inspect_attention_result_fanout_before_dedupe"
        )
        _assert_safe_output(_serialized(report))
    finally:
        for unique in attention_uniques:
            await _cleanup(unique)
        await _cleanup(source_unique)


async def test_conflicting_signals_report_mixed() -> None:
    await _ensure_tables()
    source_unique = f"root_mixed_source_{uuid4().hex}"
    row_uniques = [f"root_mixed_{uuid4().hex}_{index}" for index in range(3)]
    for unique in [source_unique, *row_uniques]:
        await _cleanup(unique)
    try:
        source_event_id = await _insert_source_event(
            source_unique,
            created_at=_utc(2149, 7, 17, 8),
        )
        first_activity = await _insert_normalized_activity(
            row_uniques[0],
            created_at=_utc(2149, 7, 17, 8),
            source_event_id=source_event_id,
        )
        second_activity = await _insert_normalized_activity(
            row_uniques[1],
            created_at=_utc(2149, 7, 17, 8),
            source_event_id=source_event_id,
        )
        await _insert_attention_result(
            row_uniques[0],
            created_at=_utc(2149, 7, 18, 9),
            activity_item_id=first_activity,
        )
        await _insert_attention_result(
            row_uniques[1],
            created_at=_utc(2149, 7, 18, 10),
            activity_item_id=first_activity,
        )
        await _insert_attention_result(
            row_uniques[2],
            created_at=_utc(2149, 7, 18, 11),
            activity_item_id=second_activity,
        )

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(
                    start_at=_utc(2149, 7, 18),
                    end_at=_utc(2149, 7, 19),
                    activity_start_at=_utc(2149, 7, 17),
                    activity_end_at=_utc(2149, 7, 18),
                ),
                settings_override=_local_settings(),
                environ={},
            )
        )

        root = report["root_cause"]
        assert root["likely_origin"] == "mixed"
        assert root["confidence"] == "medium"
        assert root["source_event_to_normalized_activity_fanout_detected"] is True
        assert root["normalized_activity_to_attention_result_fanout_detected"] is True
        assert report["recommended_next_action"] == (
            "review_duplicate_root_cause_before_dedupe"
        )
        _assert_safe_output(_serialized(report))
    finally:
        for unique in row_uniques:
            await _cleanup(unique)
        await _cleanup(source_unique)


async def test_missing_linkage_reports_insufficient_linkage() -> None:
    await _ensure_tables()
    uniques = [f"root_missing_{uuid4().hex}_{index}" for index in range(2)]
    for unique in uniques:
        await _cleanup(unique)
    try:
        for index, unique in enumerate(uniques):
            await _insert_attention_result(
                unique,
                created_at=_utc(2149, 7, 20, 9 + index),
            )

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(start_at=_utc(2149, 7, 20), end_at=_utc(2149, 7, 21)),
                settings_override=_local_settings(),
                environ={},
            )
        )

        root = report["root_cause"]
        assert root["likely_origin"] == "insufficient_linkage"
        assert root["confidence"] == "low"
        assert root["linkage_missing_count"] == 2
        assert "root_cause_linkage_limitations_present" in report["warnings"]
        _assert_safe_output(_serialized(report))
    finally:
        for unique in uniques:
            await _cleanup(unique)


async def test_candidate_lifecycle_marks_already_sent_hash_without_writes() -> None:
    await _ensure_tables()
    unique = f"root_sent_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 7, 22, 9),
        )
        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=_utc(2149, 7, 22),
                end_at=_utc(2149, 7, 23),
                limit_per_section=20,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
        await _persist_successful_draft_for_digest(
            unique,
            digest=digest,
            start_at=_utc(2149, 7, 22),
            end_at=_utc(2149, 7, 23),
        )
        before_audit = await _audit_log_count()

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(start_at=_utc(2149, 7, 22), end_at=_utc(2149, 7, 23)),
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


async def test_output_uses_opaque_clusters_and_safe_enums_only() -> None:
    await _ensure_tables()
    uniques = [f"root_safe_{uuid4().hex}_{index}" for index in range(2)]
    for unique in uniques:
        await _cleanup(unique)
    try:
        for index, unique in enumerate(uniques):
            source_event_id = await _insert_source_event(
                unique,
                created_at=_utc(2149, 7, 24, 8 + index),
            )
            activity_item_id = await _insert_normalized_activity(
                unique,
                created_at=_utc(2149, 7, 24, 8 + index),
                source_event_id=source_event_id,
            )
            await _insert_attention_result(
                unique,
                created_at=_utc(2149, 7, 25, 9 + index),
                activity_item_id=activity_item_id,
            )

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(start_at=_utc(2149, 7, 25), end_at=_utc(2149, 7, 26)),
                settings_override=_local_settings(),
                environ={},
            )
        )

        rendered = _serialized(report)
        _assert_safe_output(rendered)
        assert "cluster_001" in rendered
        assert "PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE" not in rendered
        assert "private-pr" not in rendered
        assert report["safety"]["source_object_ids_exposed"] is False
        assert report["safety"]["raw_fingerprints_exposed"] is False
        assert report["safety"]["telegram_invoked"] is False
        assert report["safety"]["openai_invoked"] is False
        _assert_safe_output(root_script.format_text_report(report))
    finally:
        for unique in uniques:
            await _cleanup(unique)


async def test_root_cause_report_does_not_commit_or_flush_with_test_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    unique = f"root_read_only_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 7, 27, 9),
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
                raise AssertionError("root-cause report must stay read-only")

        def session_factory() -> ReadOnlySession:
            return ReadOnlySession()

        report = (
            await root_script.build_no_marker_persisted_attention_duplicate_root_cause_report(
                _query(start_at=_utc(2149, 7, 27), end_at=_utc(2149, 7, 28)),
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
    assert parsed["status"] == "no_marker_persisted_attention_duplicate_root_cause"
    assert parsed["marker_filter"] == "no_marker_only"
    assert parsed["safety"]["read_only"] is True
    _assert_safe_output(result.stdout)
