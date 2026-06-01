from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.db.base import AsyncSessionLocal
from scripts import report_no_marker_persisted_attention_candidates as candidate_script
from scripts import report_no_marker_persisted_attention_grouped_preview as preview_script
from tests.test_no_marker_persisted_attention_candidates import (
    _assert_safe_output,
    _audit_log_count,
    _cleanup,
    _ensure_tables,
    _insert_attention_result,
    _insert_normalized_activity,
    _insert_source_event,
    _local_settings,
    _serialized,
    _utc,
)
from tests.test_no_marker_persisted_attention_duplicate_root_cause import (
    _insert_custom_source_event,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT
    / "scripts"
    / "report_no_marker_persisted_attention_grouped_preview.py"
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
    group_by: str = "source_object",
) -> preview_script.NoMarkerGroupedPreviewQuery:
    return preview_script.NoMarkerGroupedPreviewQuery(
        start_at=start_at,
        end_at=end_at,
        activity_start_at=activity_start_at,
        activity_end_at=activity_end_at,
        limit=limit,
        debug_evidence=False,
        cluster_threshold=cluster_threshold,
        group_by=group_by,
        output_format="json",
    )


async def _build(
    query: preview_script.NoMarkerGroupedPreviewQuery,
) -> dict:
    return await preview_script.build_no_marker_persisted_attention_grouped_preview_report(
        query,
        settings_override=_local_settings(),
        environ={},
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
        preview_script,
        "build_no_marker_persisted_attention_grouped_preview_report",
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
    # naive start
    assert (
        preview_script.main(
            [
                "--start-at",
                "2149-01-01T00:00:00",
                "--end-at",
                "2149-01-02T00:00:00+00:00",
            ]
        )
        == 2
    )
    # reversed persisted window
    assert (
        preview_script.main(
            [
                "--start-at",
                "2149-01-02T00:00:00+00:00",
                "--end-at",
                "2149-01-01T00:00:00+00:00",
            ]
        )
        == 2
    )
    assert preview_script.main([*base, "--limit", "0"]) == 2
    assert preview_script.main([*base, "--limit", "999"]) == 2
    assert preview_script.main([*base, "--cluster-threshold", "1"]) == 2
    assert preview_script.main([*base, "--cluster-threshold", "51"]) == 2
    assert preview_script.main([*base, "--group-by", "rendered_shape"]) == 2
    # activity window must be supplied together
    assert (
        preview_script.main(
            [*base, "--activity-start-at", "2149-01-01T00:00:00+00:00"]
        )
        == 2
    )
    # reversed activity window
    assert (
        preview_script.main(
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


async def test_empty_window_reports_safe_empty_grouped_preview() -> None:
    await _ensure_tables()
    before_audit = await _audit_log_count()

    report = await _build(_query(start_at=_utc(2199, 1, 1), end_at=_utc(2199, 1, 2)))

    assert report["status"] == "no_marker_persisted_attention_grouped_preview"
    assert report["marker_filter"] == "no_marker_only"
    assert report["group_by"] == "source_object"
    assert report["candidate"]["visible"] == 0
    grouped = report["grouped_preview"]
    assert grouped["grouped_item_count"] == 0
    assert grouped["grouped_entry_count"] == 0
    assert grouped["largest_group_size"] == 0
    assert grouped["preserves_visible_item_count"] is True
    assert report["groups"] == []
    assert report["recommended_next_action"] == (
        "choose_window_with_no_marker_visible_candidates"
    )
    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_audit
    _assert_safe_output(_serialized(report))
    _assert_safe_output(preview_script.format_text_report(report))


async def test_synthetic_only_window_reports_no_grouped_entries() -> None:
    await _ensure_tables()
    unique = f"prev_synthetic_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(
            unique,
            created_at=_utc(2149, 8, 1, 9),
            synthetic=True,
        )

        report = await _build(_query(start_at=_utc(2149, 8, 1), end_at=_utc(2149, 8, 2)))

        assert report["candidate"]["visible"] == 0
        assert report["grouped_preview"]["grouped_item_count"] == 0
        assert report["groups"] == []
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_unique_source_objects_have_no_reduction() -> None:
    await _ensure_tables()
    uniques = [f"prev_unique_{uuid4().hex}_{index}" for index in range(3)]
    for unique in uniques:
        await _cleanup(unique)
    try:
        for index, unique in enumerate(uniques):
            source_event_id = await _insert_source_event(
                unique,
                created_at=_utc(2149, 8, 3, 8 + index),
            )
            activity_item_id = await _insert_normalized_activity(
                unique,
                created_at=_utc(2149, 8, 3, 8 + index),
                source_event_id=source_event_id,
            )
            await _insert_attention_result(
                unique,
                created_at=_utc(2149, 8, 4, 9 + index),
                activity_item_id=activity_item_id,
            )

        report = await _build(
            _query(
                start_at=_utc(2149, 8, 4),
                end_at=_utc(2149, 8, 5),
                activity_start_at=_utc(2149, 8, 3),
                activity_end_at=_utc(2149, 8, 4),
            )
        )

        grouped = report["grouped_preview"]
        assert report["candidate"]["visible"] == 3
        assert grouped["grouped_item_count"] == 3
        assert grouped["grouped_entry_count"] == 3
        assert grouped["groups_with_repeats_count"] == 0
        assert grouped["largest_group_size"] == 1
        assert grouped["preserves_visible_item_count"] is True
        assert report["recommended_next_action"] == (
            "continue_no_marker_manual_pilot_review"
        )
        _assert_safe_output(_serialized(report))
    finally:
        for unique in uniques:
            await _cleanup(unique)


async def test_repeated_source_object_collapses_into_one_grouped_entry() -> None:
    await _ensure_tables()
    source_object_token = f"PRIVATE_SOURCE_OBJECT_DO_NOT_EXPOSE_{uuid4().hex}"
    uniques = [f"prev_repeat_{uuid4().hex}_{index}" for index in range(3)]
    for unique in uniques:
        await _cleanup(unique)
    try:
        for index, unique in enumerate(uniques):
            source_event_id = await _insert_custom_source_event(
                unique,
                created_at=_utc(2149, 8, 5, 8 + index),
                source_object_id=source_object_token,
            )
            activity_item_id = await _insert_normalized_activity(
                unique,
                created_at=_utc(2149, 8, 5, 8 + index),
                source_event_id=source_event_id,
            )
            await _insert_attention_result(
                unique,
                created_at=_utc(2149, 8, 6, 9 + index),
                activity_item_id=activity_item_id,
            )

        report = await _build(
            _query(
                start_at=_utc(2149, 8, 6),
                end_at=_utc(2149, 8, 7),
                activity_start_at=_utc(2149, 8, 5),
                activity_end_at=_utc(2149, 8, 6),
            )
        )

        grouped = report["grouped_preview"]
        assert report["candidate"]["visible"] == 3
        assert grouped["grouped_item_count"] == 3
        assert grouped["grouped_entry_count"] == 1
        assert grouped["groups_with_repeats_count"] == 1
        assert grouped["largest_group_size"] == 3
        assert grouped["preserves_visible_item_count"] is True

        assert len(report["groups"]) == 1
        group = report["groups"][0]
        assert group["group_id"] == "group_001"
        assert group["item_count"] == 3
        assert group["section"] == "review_optional"
        assert group["duplicate_risk"]["source_object_repeated"] is True
        assert group["duplicate_risk"]["item_count"] == 3
        # group exposes only opaque id + counts + safe enum summary
        assert set(group.keys()) == {
            "group_id",
            "item_count",
            "section",
            "safe_enum_summary",
            "duplicate_risk",
        }
        assert set(group["safe_enum_summary"]).issubset(
            {"by_source", "by_attention_class", "by_priority", "by_activity_type"}
        )

        # section counts preserve item counts
        section = report["grouped_preview"]["section_counts"]["review_optional"]
        assert section["ungrouped_visible_count"] == 3
        assert section["grouped_entry_count"] == 1
        assert section["grouped_item_count"] == 3
        assert section["groups_with_repeats_count"] == 1

        # grouped preview hash is computed separately and differs from candidate
        assert grouped["grouped_preview_hash_differs_from_candidate"] is True
        assert (
            grouped["grouped_preview_text_sha256"]
            != report["candidate"]["text_sha256"]
        )
        assert report["recommended_next_action"] == (
            "review_grouped_preview_before_renderer_change"
        )
        _assert_safe_output(_serialized(report))
        _assert_safe_output(preview_script.format_text_report(report))
    finally:
        for unique in uniques:
            await _cleanup(unique)


async def test_candidate_text_sha256_matches_candidate_report() -> None:
    await _ensure_tables()
    unique = f"prev_hash_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 8, 8, 9))

        candidate_report = (
            await candidate_script.build_no_marker_persisted_attention_candidate_report(
                candidate_script.NoMarkerCandidateQuery(
                    start_at=_utc(2149, 8, 8),
                    end_at=_utc(2149, 8, 9),
                    limit=20,
                    debug_evidence=False,
                    output_format="json",
                ),
                settings_override=_local_settings(),
                environ={},
            )
        )
        report = await _build(_query(start_at=_utc(2149, 8, 8), end_at=_utc(2149, 8, 9)))

        canonical = candidate_report["no_marker_candidate"]["text_sha256"]
        assert report["candidate"]["text_sha256"] == canonical
        assert report["lifecycle"]["candidate_text_sha256"] == canonical
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_grouped_preview_does_not_include_preview_text_or_chunks() -> None:
    await _ensure_tables()
    unique = f"prev_notext_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 8, 10, 9))

        report = await _build(_query(start_at=_utc(2149, 8, 10), end_at=_utc(2149, 8, 11)))

        serialized = _serialized(report)
        assert "grouped_preview_text" not in serialized.replace(
            "grouped_preview_text_sha256", ""
        ).replace("grouped_preview_text_included", "")
        assert report["safety"]["grouped_preview_text_included"] is False
        assert report["safety"]["grouped_preview_chunk_text_included"] is False
        assert report["safety"]["source_object_ids_exposed"] is False
        assert report["safety"]["raw_fingerprints_exposed"] is False
        assert report["safety"]["telegram_invoked"] is False
        assert report["safety"]["openai_invoked"] is False
        assert report["safety"]["live_api_calls"] is False
        _assert_safe_output(serialized)
        _assert_safe_output(preview_script.format_text_report(report))
    finally:
        await _cleanup(unique)


async def test_already_sent_candidate_recommends_no_resend_without_writes() -> None:
    await _ensure_tables()
    unique = f"prev_sent_{uuid4().hex}"
    await _cleanup(unique)
    try:
        from app.services.digest import (
            PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            build_persisted_attention_digest_read_model,
        )
        from tests.test_no_marker_persisted_attention_candidates import (
            _persist_successful_draft_for_digest,
        )

        await _insert_attention_result(unique, created_at=_utc(2149, 8, 12, 9))
        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=_utc(2149, 8, 12),
                end_at=_utc(2149, 8, 13),
                limit_per_section=20,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
        await _persist_successful_draft_for_digest(
            unique,
            digest=digest,
            start_at=_utc(2149, 8, 12),
            end_at=_utc(2149, 8, 13),
        )
        before_audit = await _audit_log_count()

        report = await _build(_query(start_at=_utc(2149, 8, 12), end_at=_utc(2149, 8, 13)))

        assert (
            report["lifecycle"]["matching_hash_has_successful_delivery_result"] is True
        )
        assert report["recommended_next_action"] == "do_not_resend_same_digest_content"
        assert await _audit_log_count() == before_audit
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_grouped_preview_stays_read_only_with_test_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    unique = f"prev_read_only_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 8, 14, 9))

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
                raise AssertionError("grouped preview must stay read-only")

        def session_factory() -> ReadOnlySession:
            return ReadOnlySession()

        report = (
            await preview_script.build_no_marker_persisted_attention_grouped_preview_report(
                _query(start_at=_utc(2149, 8, 14), end_at=_utc(2149, 8, 15)),
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
    assert parsed["status"] == "no_marker_persisted_attention_grouped_preview"
    assert parsed["marker_filter"] == "no_marker_only"
    assert parsed["group_by"] == "source_object"
    assert parsed["safety"]["read_only"] is True
    _assert_safe_output(result.stdout)
