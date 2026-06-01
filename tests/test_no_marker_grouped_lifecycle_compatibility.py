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
    report_no_marker_persisted_attention_grouped_lifecycle_compatibility as compat_script,
)
from scripts import (
    report_no_marker_persisted_attention_grouped_preview as grouped_preview_script,
)
from tests.test_no_marker_persisted_attention_candidates import (
    _assert_safe_output,
    _audit_log_count,
    _cleanup,
    _ensure_tables,
    _insert_attention_result,
    _local_settings,
    _persist_successful_draft_for_digest,
    _serialized,
    _utc,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT
    / "scripts"
    / "report_no_marker_persisted_attention_grouped_lifecycle_compatibility.py"
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
) -> compat_script.NoMarkerGroupedLifecycleQuery:
    return compat_script.NoMarkerGroupedLifecycleQuery(
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


async def _build(query: compat_script.NoMarkerGroupedLifecycleQuery) -> dict:
    return await compat_script.build_no_marker_grouped_lifecycle_compatibility_report(
        query,
        settings_override=_local_settings(),
        environ={},
    )


async def _grouped_preview_hash(
    *,
    start_at: datetime,
    end_at: datetime,
) -> str:
    report = (
        await grouped_preview_script.build_no_marker_persisted_attention_grouped_preview_report(
            grouped_preview_script.NoMarkerGroupedPreviewQuery(
                start_at=start_at,
                end_at=end_at,
                limit=20,
                debug_evidence=False,
                cluster_threshold=2,
                group_by="source_object",
                output_format="json",
            ),
            settings_override=_local_settings(),
            environ={},
        )
    )
    return report["grouped_preview"]["grouped_preview_text_sha256"]


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
        compat_script,
        "build_no_marker_grouped_lifecycle_compatibility_report",
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
        compat_script.main(
            ["--start-at", "2149-01-01T00:00:00", "--end-at", "2149-01-02T00:00:00+00:00"]
        )
        == 2
    )
    assert (
        compat_script.main(
            [
                "--start-at",
                "2149-01-02T00:00:00+00:00",
                "--end-at",
                "2149-01-01T00:00:00+00:00",
            ]
        )
        == 2
    )
    assert compat_script.main([*base, "--limit", "0"]) == 2
    assert compat_script.main([*base, "--limit", "999"]) == 2
    assert compat_script.main([*base, "--cluster-threshold", "1"]) == 2
    assert compat_script.main([*base, "--cluster-threshold", "51"]) == 2
    assert compat_script.main([*base, "--group-by", "rendered_shape"]) == 2
    assert (
        compat_script.main([*base, "--activity-start-at", "2149-01-01T00:00:00+00:00"])
        == 2
    )
    assert (
        compat_script.main(
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


async def test_empty_window_reports_no_visible_candidate() -> None:
    await _ensure_tables()
    before_audit = await _audit_log_count()

    report = await _build(_query(start_at=_utc(2199, 2, 1), end_at=_utc(2199, 2, 2)))

    assert report["status"] == "no_marker_grouped_lifecycle_compatibility"
    assert report["marker_filter"] == "no_marker_only"
    assert report["group_by"] == "source_object"
    assert report["candidate"]["visible"] == 0
    compat = report["lifecycle_compatibility"]
    assert compat["grouped_variant_would_be_treated_as"] == "no_visible_candidate"
    assert compat["presentation_variant_duplicate_send_risk"] is False
    assert report["recommended_next_action"] == (
        "choose_window_with_no_marker_visible_candidates"
    )
    assert report["safety"]["read_only"] is True
    assert report["safety"]["db_write_scope"] == "none"
    assert await _audit_log_count() == before_audit
    _assert_safe_output(_serialized(report))
    _assert_safe_output(compat_script.format_text_report(report))


async def test_already_sent_canonical_flags_presentation_variant_risk() -> None:
    await _ensure_tables()
    unique = f"compat_sent_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 1, 9))
        async with AsyncSessionLocal() as session:
            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=_utc(2149, 9, 1),
                end_at=_utc(2149, 9, 2),
                limit_per_section=20,
                marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
            )
        await _persist_successful_draft_for_digest(
            unique,
            digest=digest,
            start_at=_utc(2149, 9, 1),
            end_at=_utc(2149, 9, 2),
        )
        before_audit = await _audit_log_count()

        report = await _build(_query(start_at=_utc(2149, 9, 1), end_at=_utc(2149, 9, 2)))

        compat = report["lifecycle_compatibility"]
        assert compat["canonical_matching_hash_has_successful_delivery_result"] is True
        assert compat["grouped_preview_hash_differs_from_canonical"] is True
        assert compat["grouped_hash_has_successful_delivery_result"] is False
        assert compat["presentation_variant_duplicate_send_risk"] is True
        assert compat["grouped_variant_would_be_treated_as"] == (
            "new_unsent_presentation_variant"
        )
        assert compat["current_hash_guard_would_allow_grouped_variant"] is True
        assert compat["current_hash_guard_would_block_grouped_variant"] is False
        assert compat["requires_guard_extension_before_grouped_send"] is True
        assert report["recommended_next_action"] == (
            "do_not_send_grouped_variant_of_already_sent_canonical"
        )
        # report did not write anything
        assert await _audit_log_count() == before_audit
        _assert_safe_output(_serialized(report))
        _assert_safe_output(compat_script.format_text_report(report))
    finally:
        await _cleanup(unique)


async def test_unsent_canonical_has_no_presentation_variant_risk() -> None:
    await _ensure_tables()
    unique = f"compat_unsent_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 3, 9))

        report = await _build(_query(start_at=_utc(2149, 9, 3), end_at=_utc(2149, 9, 4)))

        compat = report["lifecycle_compatibility"]
        assert compat["canonical_matching_hash_has_successful_delivery_result"] is False
        assert compat["presentation_variant_duplicate_send_risk"] is False
        assert compat["requires_guard_extension_before_grouped_send"] is False
        assert report["recommended_next_action"] == (
            "continue_no_marker_manual_pilot_review"
        )
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_grouped_hash_matching_successful_delivery_is_already_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    unique = f"compat_match_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 5, 9))

        grouped_hash = await _grouped_preview_hash(
            start_at=_utc(2149, 9, 5),
            end_at=_utc(2149, 9, 6),
        )

        async def fake_facts(*_args: object, **_kwargs: object) -> list[dict]:
            return [{"text_sha256": grouped_hash, "has_successful_delivery": True}]

        monkeypatch.setattr(compat_script, "_load_window_draft_hash_facts", fake_facts)

        report = await _build(_query(start_at=_utc(2149, 9, 5), end_at=_utc(2149, 9, 6)))

        compat = report["lifecycle_compatibility"]
        assert compat["grouped_hash_matches_existing_draft"] is True
        assert compat["grouped_hash_has_successful_delivery_result"] is True
        assert compat["grouped_variant_would_be_treated_as"] == "already_sent"
        assert compat["current_hash_guard_would_block_grouped_variant"] is True
        assert compat["current_hash_guard_would_allow_grouped_variant"] is False
        assert compat["presentation_variant_duplicate_send_risk"] is False
        _assert_safe_output(_serialized(report))
    finally:
        await _cleanup(unique)


async def test_hashes_returned_without_rendering_text() -> None:
    await _ensure_tables()
    unique = f"compat_hashes_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 7, 9))

        report = await _build(_query(start_at=_utc(2149, 9, 7), end_at=_utc(2149, 9, 8)))

        compat = report["lifecycle_compatibility"]
        assert isinstance(compat["canonical_candidate_text_sha256"], str)
        assert isinstance(compat["grouped_preview_text_sha256"], str)
        assert (
            compat["canonical_candidate_text_sha256"]
            == report["candidate"]["text_sha256"]
        )
        assert compat["grouped_hash_is_presentation_variant_not_delivered_content"] is True

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
        _assert_safe_output(compat_script.format_text_report(report))
    finally:
        await _cleanup(unique)


async def test_report_stays_read_only_with_test_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_tables()
    unique = f"compat_read_only_{uuid4().hex}"
    await _cleanup(unique)
    try:
        await _insert_attention_result(unique, created_at=_utc(2149, 9, 9, 9))

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
                raise AssertionError("grouped lifecycle compatibility must stay read-only")

        def session_factory() -> ReadOnlySession:
            return ReadOnlySession()

        report = (
            await compat_script.build_no_marker_grouped_lifecycle_compatibility_report(
                _query(start_at=_utc(2149, 9, 9), end_at=_utc(2149, 9, 10)),
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
    assert parsed["status"] == "no_marker_grouped_lifecycle_compatibility"
    assert parsed["marker_filter"] == "no_marker_only"
    assert parsed["group_by"] == "source_object"
    assert parsed["safety"]["read_only"] is True
    _assert_safe_output(result.stdout)
