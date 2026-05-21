from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.attention_models import AttentionTriageResultRecord
from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import IngestedEvent
from app.services.attention_results import record_attention_triage_result
from app.services.attention_triage import AttentionTriageResult, NormalizedActivityItem
from app.services.normalized_activity import record_normalized_activity_item
from scripts import preview_persisted_attention_digest as preview_script

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "preview_persisted_attention_digest.py"


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


async def _ensure_preview_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(IngestedEvent.__table__.create, checkfirst=True)
        await conn.run_sync(SourceEvent.__table__.create, checkfirst=True)
        await conn.run_sync(NormalizedActivityItemRecord.__table__.create, checkfirst=True)
        await conn.run_sync(AttentionTriageResultRecord.__table__.create, checkfirst=True)


async def _cleanup_preview_fixture(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.triage_result_id.like(
                    f"atri_preview_{unique}%"
                )
            )
        )
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.source_object_id.like(
                    f"preview:test:{unique}%"
                )
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(
                    f"nact_preview_{unique}%"
                )
            )
        )
        await session.commit()


def _attention_result(**overrides: object) -> AttentionTriageResult:
    defaults = {
        "attention_class": "requires_my_attention",
        "priority": "high",
        "show_in_digest": True,
        "confidence": 0.92,
        "reason": "validated preview fixture",
        "recommended_action": "review the persisted attention preview",
        "owner": "me",
        "deadline": "2412-01-03",
        "evidence": [
            {
                "kind": "source_event",
                "source_event_id": "sevt_preview_fake",
                "source_system": "github",
                "source_object_type": "pull_request",
                "source_object_id": "preview:test:fake",
                "event_type": "github.pull_request.review_requested",
                "raw_object_ref": "raw://preview/fake.json",
                "raw_payload": "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
                "provider_payload": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                "prompt": "PRIVATE_PROMPT_DO_NOT_EXPOSE",
                "source_payload": "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
            }
        ],
    }
    defaults.update(overrides)
    return AttentionTriageResult.model_validate(defaults)


def _activity(unique: str, suffix: str, **overrides: object) -> NormalizedActivityItem:
    defaults = {
        "source": "github",
        "source_object_id": f"preview:test:{unique}:{suffix}",
        "activity_type": "pull_request.review_requested",
        "title": f"Preview persisted attention title {suffix}",
        "actor": "github:preview-user",
        "created_at": _utc(2412, 1, 1, 9),
        "project": "company-knowledge-os",
        "safe_summary": f"Safe persisted attention preview summary {suffix}.",
        "related_people": ["github:preview-user"],
        "related_jira_keys": ["FOS-59"],
        "related_prs": ["https://example.test/company-knowledge-os/pull/59"],
        "related_files": [],
        "evidence_refs": [
            {
                "kind": "source_event",
                "source_event_id": f"sevt_preview_{unique}_{suffix}",
                "source_system": "github",
                "source_object_type": "pull_request",
                "source_object_id": f"preview:test:{unique}:{suffix}",
                "event_type": "github.pull_request.review_requested",
                "raw_object_ref": f"raw://preview/{unique}/{suffix}.json",
                "raw_payload": "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE",
                "provider_payload": "PRIVATE_ACTIVITY_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                "prompt": "PRIVATE_ACTIVITY_PROMPT_DO_NOT_EXPOSE",
            }
        ],
    }
    defaults.update(overrides)
    return NormalizedActivityItem.model_validate(defaults)


async def _record_preview_item(
    *,
    unique: str,
    suffix: str,
    attention_class: str,
    priority: str,
    created_at: datetime,
    show_in_digest: bool = True,
    confidence: float = 0.92,
    title: str | None = None,
) -> str:
    async with AsyncSessionLocal() as session:
        activity = await record_normalized_activity_item(
            session,
            activity_item_id=f"nact_preview_{unique}_{suffix}",
            activity=_activity(
                unique,
                suffix,
                title=title or f"Preview persisted attention title {suffix}",
            ),
        )
        result = _attention_result(
            attention_class=attention_class,
            priority=priority,
            show_in_digest=show_in_digest,
            confidence=confidence,
            recommended_action=f"Handle persisted attention preview {suffix}",
            evidence=activity.evidence_refs,
        )
        stored = await record_attention_triage_result(
            session,
            triage_result_id=f"atri_preview_{unique}_{suffix}",
            source="github",
            source_object_id=activity.source_object_id,
            activity_item_id=activity.activity_item_id,
            result=result,
            created_at=created_at,
        )
        await session.commit()
        return stored.triage_result_id


def _empty_digest(start_at: datetime, end_at: datetime) -> dict[str, Any]:
    return {
        "section_title": "Persisted attention digest",
        "available": True,
        "window": {
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        },
        "section_labels": {},
        "counts": {
            "total": 0,
            "visible": 0,
            "hidden": 0,
            "shown": 0,
            "by_attention_class": {},
            "by_priority": {},
            "by_show_in_digest": {},
            "by_source": {},
        },
        "groups": {
            "work_actions": [],
            "manual_actions": [],
            "waiting_external_reply": [],
            "work_info": [],
            "review_optional": [],
        },
        "hidden_low_priority_summary": {
            "total": 0,
            "counts": {},
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


def _query(
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    output_format: str = "text",
    debug_evidence: bool = False,
) -> preview_script.PreviewQuery:
    return preview_script.PreviewQuery(
        start_at=start_at or _utc(2411, 1, 1),
        end_at=end_at or _utc(2411, 1, 2),
        limit=20,
        output_format=output_format,
        debug_evidence=debug_evidence,
    )


class _FakeSession:
    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def add(self, _value: object) -> None:
        raise AssertionError("preview script must not add rows")

    async def flush(self) -> None:
        raise AssertionError("preview script must not flush rows")

    async def commit(self) -> None:
        raise AssertionError("preview script must not commit")


def test_cli_rejects_missing_start_or_end() -> None:
    missing_start = _run_script("--end-at", "2411-01-02T00:00:00+00:00")
    missing_end = _run_script("--start-at", "2411-01-01T00:00:00+00:00")

    assert missing_start.returncode == 2
    assert missing_end.returncode == 2
    assert "--start-at" in missing_start.stderr
    assert "--end-at" in missing_end.stderr
    assert "PRIVATE" not in missing_start.stderr + missing_end.stderr


def test_cli_rejects_naive_reversed_and_out_of_bounds_windows() -> None:
    naive = _run_script(
        "--start-at",
        "2411-01-01T00:00:00",
        "--end-at",
        "2411-01-02T00:00:00+00:00",
    )
    reversed_window = _run_script(
        "--start-at",
        "2411-01-02T00:00:00+00:00",
        "--end-at",
        "2411-01-01T00:00:00+00:00",
    )

    assert naive.returncode == 2
    assert "start_at must be timezone-aware" in naive.stderr
    assert reversed_window.returncode == 2
    assert "end_at must be after start_at" in reversed_window.stderr


def test_cli_enforces_bounded_limit() -> None:
    too_low = _run_script(
        "--start-at",
        "2411-01-01T00:00:00+00:00",
        "--end-at",
        "2411-01-02T00:00:00+00:00",
        "--limit",
        "0",
    )
    too_high = _run_script(
        "--start-at",
        "2411-01-01T00:00:00+00:00",
        "--end-at",
        "2411-01-02T00:00:00+00:00",
        "--limit",
        str(preview_script.MAX_LIMIT + 1),
    )

    assert too_low.returncode == 2
    assert too_high.returncode == 2
    assert f"limit must be between 1 and {preview_script.MAX_LIMIT}" in too_low.stderr
    assert f"limit must be between 1 and {preview_script.MAX_LIMIT}" in too_high.stderr


async def test_empty_preview_renders_safely_in_text_and_json_modes() -> None:
    async def builder(_session: object, **kwargs: object) -> dict[str, Any]:
        return _empty_digest(kwargs["start_at"], kwargs["end_at"])

    text_preview = await preview_script.build_preview(
        _query(),
        session_factory=_FakeSession,
        builder=builder,
    )
    json_preview = await preview_script.build_preview(
        _query(output_format="json"),
        session_factory=_FakeSession,
        builder=builder,
    )

    assert "No persisted attention items found for this window." in text_preview["rendered_text"]
    assert "Debug evidence refs:" not in text_preview["rendered_text"]
    assert json_preview["status"] == "completed"
    assert json_preview["digest"]["counts"]["total"] == 0
    assert json_preview["query"]["debug_evidence"] is False


async def test_build_preview_path_is_read_only() -> None:
    fake_session = _FakeSession()

    async def builder(session: object, **kwargs: object) -> dict[str, Any]:
        assert session is fake_session
        return _empty_digest(kwargs["start_at"], kwargs["end_at"])

    preview = await preview_script.build_preview(
        _query(),
        session_factory=lambda: fake_session,
        builder=builder,
    )

    assert preview["safety"] == {
        "provider_free": True,
        "read_only": True,
        "delivery": False,
    }


async def test_fixture_rows_render_into_all_visible_sections_and_hide_hidden_details() -> None:
    await _ensure_preview_tables()
    unique = uuid4().hex
    await _cleanup_preview_fixture(unique)
    hidden_title = "Hidden persisted attention preview title"

    try:
        await _record_preview_item(
            unique=unique,
            suffix="reply",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2412, 1, 1, 9),
        )
        await _record_preview_item(
            unique=unique,
            suffix="manual",
            attention_class="manual_action",
            priority="medium",
            created_at=_utc(2412, 1, 1, 10),
        )
        await _record_preview_item(
            unique=unique,
            suffix="waiting",
            attention_class="waiting_on_external",
            priority="medium",
            created_at=_utc(2412, 1, 1, 11),
        )
        await _record_preview_item(
            unique=unique,
            suffix="update",
            attention_class="important_info",
            priority="low",
            created_at=_utc(2412, 1, 1, 12),
        )
        await _record_preview_item(
            unique=unique,
            suffix="review",
            attention_class="review_optional",
            priority="low",
            created_at=_utc(2412, 1, 1, 13),
        )
        await _record_preview_item(
            unique=unique,
            suffix="hidden",
            attention_class="no_action_required",
            priority="low",
            show_in_digest=False,
            created_at=_utc(2412, 1, 1, 14),
            title=hidden_title,
        )

        preview = await preview_script.build_preview(
            _query(start_at=_utc(2412, 1, 1), end_at=_utc(2412, 1, 2)),
        )
        rendered = preview["rendered_text"]
        dumped = json.dumps(preview, sort_keys=True)

        assert "Work actions requiring my attention:" in rendered
        assert "Manual actions:" in rendered
        assert "Waiting for external reply:" in rendered
        assert "Important project updates:" in rendered
        assert "Review optional:" in rendered
        assert "Preview persisted attention title reply" in rendered
        assert "Preview persisted attention title manual" in rendered
        assert "Preview persisted attention title waiting" in rendered
        assert "Preview persisted attention title update" in rendered
        assert "Preview persisted attention title review" in rendered
        assert "Hidden low-priority summary:" in rendered
        assert "- 1 no-action low-priority items" in rendered
        assert hidden_title not in rendered
        assert hidden_title not in dumped
        assert "items" not in preview["digest"]["hidden_low_priority_summary"]

    finally:
        await _cleanup_preview_fixture(unique)


async def test_debug_evidence_is_safe_and_default_omits_evidence_refs() -> None:
    await _ensure_preview_tables()
    unique = uuid4().hex
    await _cleanup_preview_fixture(unique)

    try:
        await _record_preview_item(
            unique=unique,
            suffix="debug",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2413, 1, 1, 9),
        )

        default_preview = await preview_script.build_preview(
            _query(start_at=_utc(2413, 1, 1), end_at=_utc(2413, 1, 2)),
        )
        debug_preview = await preview_script.build_preview(
            _query(
                start_at=_utc(2413, 1, 1),
                end_at=_utc(2413, 1, 2),
                debug_evidence=True,
            ),
        )

        default_dumped = json.dumps(default_preview, sort_keys=True)
        debug_dumped = json.dumps(debug_preview, sort_keys=True)

        assert "Debug evidence refs:" not in default_preview["rendered_text"]
        assert "evidence_refs" not in default_dumped
        assert "Debug evidence refs:" in debug_preview["rendered_text"]
        assert f"source_event_id=sevt_preview_{unique}_debug" in debug_preview["rendered_text"]
        assert "raw_object_ref=raw://preview/" in debug_preview["rendered_text"]
        assert "evidence_refs" in debug_dumped
        assert "raw_payload" not in debug_dumped
        assert "provider_payload" not in debug_dumped
        assert "prompt" not in debug_dumped
        assert "source_payload" not in debug_dumped

    finally:
        await _cleanup_preview_fixture(unique)


async def test_raw_provider_prompt_payload_markers_are_not_printed() -> None:
    await _ensure_preview_tables()
    unique = uuid4().hex
    await _cleanup_preview_fixture(unique)

    try:
        await _record_preview_item(
            unique=unique,
            suffix="safe",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2414, 1, 1, 9),
        )

        preview = await preview_script.build_preview(
            _query(
                start_at=_utc(2414, 1, 1),
                end_at=_utc(2414, 1, 2),
                debug_evidence=True,
            ),
        )
        dumped = json.dumps(preview, sort_keys=True)
        combined = f"{dumped}\n{preview['rendered_text']}"

        for marker in (
            "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_PROMPT_DO_NOT_EXPOSE",
            "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_ACTIVITY_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_ACTIVITY_PROMPT_DO_NOT_EXPOSE",
            "raw_payload",
            "provider_payload",
            "prompt",
            "source_payload",
        ):
            assert marker not in combined

    finally:
        await _cleanup_preview_fixture(unique)


async def test_preview_fails_closed_when_builder_is_unavailable() -> None:
    async def builder(_session: object, **_kwargs: object) -> dict[str, Any]:
        raise RuntimeError("PRIVATE_DATABASE_URL_DO_NOT_EXPOSE")

    with pytest.raises(preview_script.PreviewRuntimeError) as exc_info:
        await preview_script.build_preview(
            _query(),
            session_factory=_FakeSession,
            builder=builder,
        )

    message = str(exc_info.value)
    assert "persisted attention digest preview blocked" in message
    assert "PRIVATE_DATABASE_URL_DO_NOT_EXPOSE" not in message


def test_script_source_avoids_live_delivery_provider_api_and_write_paths() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden_tokens = [
        "openai",
        "slack_sdk",
        "telegram_delivery",
        "send_telegram",
        "httpx",
        "requests",
        "app.api",
        "app.connectors",
        "googleapiclient",
        "alembic",
        ".commit(",
        ".flush(",
        ".add(",
        "session.execute(insert",
        "session.execute(update",
        "session.execute(delete",
        "AttentionTriageAgent",
        "triage_normalized_activity_item",
        "classify_email_thread_states",
    ]

    for token in forbidden_tokens:
        assert token not in source
