from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, or_, select

from app.db.base import AsyncSessionLocal, engine
from app.db.models import AuditLog
import app.services.digest_delivery_drafts as digest_delivery_drafts
import app.services.telegram_delivery as telegram_delivery
from app.services.digest_delivery_drafts import (
    DIGEST_DELIVERY_DRAFT_AUDIT_EVENT_TYPES,
    DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
    approve_digest_delivery_draft,
    build_persisted_attention_digest_delivery_draft,
    create_digest_delivery_intention,
    persist_digest_delivery_draft,
    sanitize_persisted_attention_digest_for_delivery_draft,
)
from app.services.digest_rendering import render_persisted_attention_digest_text
from scripts import review_digest_delivery_intention as review_script

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "review_digest_delivery_intention.py"


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
            "start_at": "2133-01-01T00:00:00+00:00",
            "end_at": "2133-01-02T00:00:00+00:00",
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
                    "id": "atri_review_visible",
                    "triage_result_id": "atri_review_visible",
                    "activity_item_id": "nact_review_visible",
                    "source": "github",
                    "source_object_id": "delivery-review:visible",
                    "attention_class": "requires_my_attention",
                    "priority": "high",
                    "show_in_digest": True,
                    "confidence": 0.93,
                    "title": "Review delivery intention chain",
                    "safe_summary": "Safe delivery intention review summary.",
                    "reason": "validated delivery intention review fixture",
                    "recommended_action": "review the inert delivery chain",
                    "owner": "me",
                    "deadline": "2133-01-02",
                    "project": "company-knowledge-os",
                    "activity_created_at": "2133-01-01T09:00:00+00:00",
                    "triage_created_at": "2133-01-01T10:00:00+00:00",
                    "evidence": "1 triage evidence ref",
                    "evidence_refs": [
                        {
                            "kind": "source_event",
                            "source_event_id": "sevt_review_visible",
                            "source_system": "github",
                            "source_object_type": "pull_request",
                            "source_object_id": "delivery-review:visible",
                            "raw_object_ref": "raw://review/visible.json",
                            "raw_payload": "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
                            "provider_payload": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                            "prompt": "PRIVATE_PROMPT_DO_NOT_EXPOSE",
                            "source_payload": "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
                        }
                    ],
                    "activity_evidence_refs": [
                        {
                            "kind": "normalized_activity_item",
                            "source_event_id": "sevt_review_visible",
                            "raw_object_ref": "raw://review/visible.json",
                            "raw_payload": "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE",
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
                    "id": "atri_review_hidden",
                    "title": "Hidden delivery review title",
                    "evidence_refs": [
                        {
                            "source_event_id": "sevt_review_hidden",
                            "raw_object_ref": "raw://review/hidden.json",
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


def _rendered_digest(digest: dict[str, Any]) -> str:
    safe_digest = sanitize_persisted_attention_digest_for_delivery_draft(
        digest,
        debug_evidence=False,
    )
    return render_persisted_attention_digest_text(
        safe_digest,
        debug_evidence=False,
    )


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
        await session.commit()


async def _audit_log_count_for_chain(
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


async def _create_review_chain(
    *,
    start_at: datetime = _utc(2133, 1, 1),
    end_at: datetime = _utc(2133, 1, 2),
) -> tuple[dict[str, Any], dict[str, Any], str]:
    await _ensure_audit_log_table()
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
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
            note="Approved for operator review.",
        )
        intention = await create_digest_delivery_intention(
            session,
            delivery_draft_id=delivery_draft_id,
            actor="test",
        )
        await session.commit()

    return draft, intention, rendered_text


def _serialized(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _assert_safe_output(output: str) -> None:
    assert "Hidden delivery review title" not in output
    assert "atri_review_hidden" not in output
    assert "sevt_review_hidden" not in output
    assert "evidence_refs" not in output
    assert "chunk_text" not in output
    assert "chat_id" not in output
    assert "bot_token" not in output
    assert "telegram_url" not in output
    assert "webhook_url" not in output
    assert "https://api.telegram.org" not in output
    for marker in (
        "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_PROMPT_DO_NOT_EXPOSE",
        "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_RAW_TEXT_DO_NOT_EXPOSE",
        "raw_payload",
        "provider_payload",
        "prompt",
        "source_payload",
        "raw_text",
    ):
        assert marker not in output


def test_missing_delivery_intention_id_fails_safely() -> None:
    result = _run_script("--format", "json")

    assert result.returncode == 2
    assert "--delivery-intention-id" in result.stderr
    _assert_safe_output(result.stdout + result.stderr)


def test_blank_delivery_intention_id_fails_safely() -> None:
    result = _run_script("--delivery-intention-id", "   ", "--format", "json")

    assert result.returncode == 2
    assert "delivery_intention_id must not be empty" in result.stderr
    _assert_safe_output(result.stdout + result.stderr)


async def test_unknown_delivery_intention_id_fails_safely() -> None:
    await _ensure_audit_log_table()
    result = _run_script(
        "--delivery-intention-id",
        "dint_unknown_fos_066_review",
        "--format",
        "json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["error_code"] == "not_found"
    assert "not found" in payload["message"]
    _assert_safe_output(result.stdout + result.stderr)


async def test_review_bundle_returns_safe_full_chain_and_is_deterministic(
    monkeypatch,
) -> None:
    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("operator review must not send Telegram messages")

    def forbidden_render(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("operator review must not recompute digest text")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    draft, intention, rendered_text = await _create_review_chain(
        start_at=_utc(2133, 1, 3),
        end_at=_utc(2133, 1, 4),
    )
    monkeypatch.setattr(
        digest_delivery_drafts,
        "render_persisted_attention_digest_text",
        forbidden_render,
    )

    try:
        before_count = await _audit_log_count_for_chain(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )
        query = review_script.ReviewQuery(
            delivery_intention_id=intention["delivery_intention_id"],
            output_format="json",
        )
        first = await review_script.build_review(query)
        second = await review_script.build_review(query)
        text_first = review_script.format_text_review(first)
        text_second = review_script.format_text_review(second)
        after_count = await _audit_log_count_for_chain(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )

        assert first == second
        assert text_first == text_second
        assert before_count == after_count
        assert first["status"] == "delivery_intention_review"
        assert first["delivery_intention_id"] == intention["delivery_intention_id"]
        assert first["delivery_draft_id"] == draft["delivery_draft_id"]
        assert first["digest_type"] == "persisted_attention"
        assert first["channel"] == "telegram"
        assert first["text_sha256"] == draft["text_sha256"]
        assert first["char_count"] == len(rendered_text)
        assert first["chunk_count"] == draft["chunk_count"]
        assert first["approval_status"]["current_decision"] == "approved"
        assert first["readiness"]["eligible_for_delivery"] is True
        assert first["telegram_plan"]["status"] == "telegram_delivery_plan"
        assert first["telegram_plan"]["chunks_text_included"] is False
        assert all("text" not in chunk for chunk in first["telegram_plan"]["chunks"])
        assert first["safety"]["provider_free"] is True
        assert first["safety"]["read_only"] is True
        assert first["safety"]["delivery_invoked"] is False
        assert first["safety"]["delivery_adapter_invoked"] is False
        assert first["safety"]["approval_execution_invoked"] is False
        assert first["safety"]["scheduler_invoked"] is False
        assert first["safety"]["sent"] is False
        assert first["safety"]["api_clients_invoked"] is False
        assert "Delivery intention review (review-only; no send)" in text_first
        assert intention["delivery_intention_id"] in text_first
        assert draft["delivery_draft_id"] in text_first
        assert "Stored rendered digest text included: False" in text_first

        dumped = _serialized(first)
        assert "rendered_text" not in dumped
        assert '"rendered_text":' not in dumped
        assert rendered_text not in dumped
        assert "Review delivery intention chain" not in dumped
        _assert_safe_output(dumped)
        _assert_safe_output(text_first)
    finally:
        await _delete_delivery_chain(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )


async def test_json_cli_output_is_sanitized_and_omits_rendered_text_by_default() -> None:
    draft, intention, rendered_text = await _create_review_chain(
        start_at=_utc(2133, 1, 5),
        end_at=_utc(2133, 1, 6),
    )

    try:
        result = _run_script(
            "--delivery-intention-id",
            intention["delivery_intention_id"],
            "--format",
            "json",
        )

        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "delivery_intention_review"
        assert payload["delivery_intention_id"] == intention["delivery_intention_id"]
        assert payload["delivery_draft_id"] == draft["delivery_draft_id"]
        assert payload["stored_digest_text_included"] is False
        assert "rendered_text" not in payload
        assert "rendered_text" not in result.stdout
        assert rendered_text not in result.stdout
        assert payload["telegram_plan"]["chunks_text_included"] is False
        assert all("text" not in chunk for chunk in payload["telegram_plan"]["chunks"])
        _assert_safe_output(result.stdout + result.stderr)
    finally:
        await _delete_delivery_chain(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )


async def test_include_rendered_text_uses_stored_sanitized_text_only() -> None:
    draft, intention, rendered_text = await _create_review_chain(
        start_at=_utc(2133, 1, 7),
        end_at=_utc(2133, 1, 8),
    )

    try:
        review = await review_script.build_review(
            review_script.ReviewQuery(
                delivery_intention_id=intention["delivery_intention_id"],
                output_format="json",
                include_rendered_text=True,
            )
        )
        text_output = review_script.format_text_review(review)
        dumped = _serialized(review)

        assert review["rendered_text"] == rendered_text
        assert review["stored_digest_text_included"] is True
        assert "Review delivery intention chain" in review["rendered_text"]
        assert "Stored rendered digest text included: True" in text_output
        assert "Stored rendered digest text:" in text_output
        assert rendered_text in text_output
        assert '"text":' not in dumped
        assert all("text" not in chunk for chunk in review["telegram_plan"]["chunks"])
        _assert_safe_output(dumped)
        _assert_safe_output(text_output)
    finally:
        await _delete_delivery_chain(
            delivery_draft_id=draft["delivery_draft_id"],
            delivery_intention_id=intention["delivery_intention_id"],
        )


async def test_review_script_does_not_call_write_methods(monkeypatch) -> None:
    rendered_text = "Safe stored digest text for review."
    chunks = telegram_delivery.split_telegram_plain_text(rendered_text)
    chunk_metadata = {
        "chunk_size": telegram_delivery.DEFAULT_TELEGRAM_CHUNK_SIZE,
        "chunk_lengths": [len(chunk) for chunk in chunks],
        "chunks_preview_included": False,
    }
    text_hash = sha256(rendered_text.encode("utf-8")).hexdigest()
    delivery_draft_id = "ddraft_read_only_fos_066"
    delivery_intention_id = "dint_read_only_fos_066"
    source_of_truth = {
        "source": "postgres",
        "draft_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }
    intention = {
        "persisted": True,
        "status": "delivery_intention",
        "delivery_intention_id": delivery_intention_id,
        "delivery_draft_id": delivery_draft_id,
        "digest_type": "persisted_attention",
        "channel": "telegram",
        "current_decision": "approved",
        "eligible_for_delivery": True,
        "delivery_execution_enabled": False,
        "delivery_enabled": False,
        "delivery_invoked": False,
        "approval_execution_invoked": False,
        "sent": False,
        "scheduler_invoked": False,
        "text_sha256": text_hash,
        "char_count": len(rendered_text),
        "chunk_count": len(chunks),
        "chunk_metadata": chunk_metadata,
        "start_at": "2133-02-01T00:00:00+00:00",
        "end_at": "2133-02-02T00:00:00+00:00",
        "limit": 20,
        "debug_evidence": False,
        "source_of_truth": source_of_truth,
    }
    draft = {
        "delivery_draft_id": delivery_draft_id,
        "status": "draft",
        "digest_type": "persisted_attention",
        "channel": "telegram",
        "rendered_text": rendered_text,
        "text_sha256": text_hash,
        "char_count": len(rendered_text),
        "chunk_count": len(chunks),
        "chunk_metadata": chunk_metadata,
        "start_at": "2133-02-01T00:00:00+00:00",
        "end_at": "2133-02-02T00:00:00+00:00",
        "limit": 20,
        "debug_evidence": False,
        "source_of_truth": source_of_truth,
    }
    approval_status = {
        "delivery_draft_id": delivery_draft_id,
        "draft_exists": True,
        "current_decision": "approved",
        "approved": True,
        "rejected": False,
        "delivery_enabled": False,
        "sent": False,
        "delivery_invoked": False,
        "approval_execution_invoked": False,
        "decision_history": [],
        "draft": {
            "digest_type": "persisted_attention",
            "channel": "telegram",
            "status": "draft",
            "start_at": draft["start_at"],
            "end_at": draft["end_at"],
            "limit": 20,
            "debug_evidence": False,
            "text_sha256": text_hash,
            "char_count": len(rendered_text),
            "chunk_count": len(chunks),
            "source_of_truth": source_of_truth,
        },
        "safety": {"delivery_invoked": False},
    }
    readiness = {
        "delivery_draft_id": delivery_draft_id,
        "draft_exists": True,
        "status": "delivery_readiness",
        "digest_type": "persisted_attention",
        "channel": "telegram",
        "current_decision": "approved",
        "approved": True,
        "rejected": False,
        "eligible_for_delivery": True,
        "ineligible_reasons": [],
        "delivery_execution_enabled": False,
        "delivery_enabled": False,
        "delivery_invoked": False,
        "approval_execution_invoked": False,
        "sent": False,
        "text_sha256": text_hash,
        "char_count": len(rendered_text),
        "chunk_count": len(chunks),
        "chunk_metadata": chunk_metadata,
        "start_at": draft["start_at"],
        "end_at": draft["end_at"],
        "limit": 20,
        "debug_evidence": False,
        "decision_history": [],
        "source_of_truth": source_of_truth,
        "safety": {"read_only": True, "delivery_invoked": False},
    }
    telegram_plan = {
        "status": "telegram_delivery_plan",
        "delivery_intention_id": delivery_intention_id,
        "delivery_draft_id": delivery_draft_id,
        "digest_type": "persisted_attention",
        "channel": "telegram",
        "text_sha256": text_hash,
        "char_count": len(rendered_text),
        "chunk_count": len(chunks),
        "chunks_text_included": False,
        "chunks": [
            {
                "index": index,
                "char_count": len(chunk),
                "sha256": sha256(chunk.encode("utf-8")).hexdigest(),
            }
            for index, chunk in enumerate(chunks, start=1)
        ],
        "chunk_metadata": chunk_metadata,
        "delivery_execution_enabled": False,
        "delivery_enabled": False,
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "sent": False,
        "source_of_truth": source_of_truth,
        "safety": {"read_only": True, "delivery_invoked": False},
    }

    async def fake_get_intention(_session: object, *, delivery_intention_id: str):
        assert delivery_intention_id == "dint_read_only_fos_066"
        return intention

    async def fake_get_draft(_session: object, *, delivery_draft_id: str):
        assert delivery_draft_id == "ddraft_read_only_fos_066"
        return draft

    async def fake_get_approval(_session: object, *, delivery_draft_id: str):
        assert delivery_draft_id == "ddraft_read_only_fos_066"
        return approval_status

    async def fake_get_readiness(_session: object, *, delivery_draft_id: str):
        assert delivery_draft_id == "ddraft_read_only_fos_066"
        return readiness

    async def fake_get_plan(_session: object, *, delivery_intention_id: str):
        assert delivery_intention_id == "dint_read_only_fos_066"
        return telegram_plan

    class _ReadOnlySession:
        def add(self, _value: object) -> None:
            raise AssertionError("review script must not add rows")

        async def flush(self) -> None:
            raise AssertionError("review script must not flush rows")

        async def commit(self) -> None:
            raise AssertionError("review script must not commit")

        async def execute(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("review script must not execute write paths")

        async def scalar(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("review script should use composed services")

        async def scalars(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("review script should use composed services")

    class _SessionFactory:
        async def __aenter__(self) -> _ReadOnlySession:
            return _ReadOnlySession()

        async def __aexit__(
            self,
            _exc_type: object,
            _exc: object,
            _traceback: object,
        ) -> None:
            return None

    monkeypatch.setattr(
        digest_delivery_drafts,
        "get_digest_delivery_intention",
        fake_get_intention,
    )
    monkeypatch.setattr(
        digest_delivery_drafts,
        "get_persisted_digest_delivery_draft",
        fake_get_draft,
    )
    monkeypatch.setattr(
        digest_delivery_drafts,
        "get_digest_delivery_draft_approval_status",
        fake_get_approval,
    )
    monkeypatch.setattr(
        digest_delivery_drafts,
        "get_digest_delivery_draft_delivery_readiness",
        fake_get_readiness,
    )
    monkeypatch.setattr(
        digest_delivery_drafts,
        "get_digest_delivery_intention_telegram_plan",
        fake_get_plan,
    )

    review = await review_script.build_review(
        review_script.ReviewQuery(delivery_intention_id=delivery_intention_id),
        session_factory=_SessionFactory,
    )

    assert review["delivery_intention_id"] == delivery_intention_id
    assert review["delivery_draft_id"] == delivery_draft_id
    assert review["telegram_plan"]["chunks_text_included"] is False
