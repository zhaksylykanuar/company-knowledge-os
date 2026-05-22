from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

import pytest
from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal, engine
from app.db.models import AuditLog
import app.services.digest_delivery_drafts as digest_delivery_drafts
import app.services.telegram_delivery as telegram_delivery
from app.services.digest_delivery_drafts import (
    DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
    DIGEST_DELIVERY_DRAFT_AUDIT_EVENT_TYPES,
    DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
    DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE,
    DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
    DeliveryDraftDecisionConflictError,
    DeliveryDraftNotFoundError,
    DeliveryIntentionConflictError,
    DeliveryIntentionNotReadyError,
    DeliveryTelegramPlanConflictError,
    approve_digest_delivery_draft,
    build_delivery_draft_id,
    build_delivery_intention_id,
    build_persisted_attention_digest_delivery_draft,
    build_persisted_attention_digest_delivery_draft_from_db,
    create_digest_delivery_intention,
    get_digest_delivery_draft_approval_status,
    get_digest_delivery_draft_delivery_readiness,
    get_digest_delivery_intention,
    get_digest_delivery_intention_telegram_plan,
    get_persisted_digest_delivery_draft,
    persist_digest_delivery_draft,
    reject_digest_delivery_draft,
    sanitize_persisted_attention_digest_for_delivery_draft,
)
from app.services.digest_rendering import render_persisted_attention_digest_text


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _persisted_attention_digest() -> dict[str, Any]:
    return {
        "section_title": "Persisted attention digest",
        "available": True,
        "window": {
            "start_at": "2132-01-01T00:00:00+00:00",
            "end_at": "2132-01-02T00:00:00+00:00",
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
                    "id": "atri_delivery_visible",
                    "triage_result_id": "atri_delivery_visible",
                    "activity_item_id": "nact_delivery_visible",
                    "source": "github",
                    "source_object_id": "delivery:visible",
                    "attention_class": "requires_my_attention",
                    "priority": "high",
                    "show_in_digest": True,
                    "confidence": 0.93,
                    "title": "Review delivery draft preview",
                    "safe_summary": "Safe delivery draft summary.",
                    "reason": "validated delivery draft fixture",
                    "recommended_action": "review the inert delivery draft",
                    "owner": "me",
                    "deadline": "2132-01-02",
                    "project": "company-knowledge-os",
                    "activity_created_at": "2132-01-01T09:00:00+00:00",
                    "triage_created_at": "2132-01-01T10:00:00+00:00",
                    "evidence": "1 triage evidence ref",
                    "evidence_refs": [
                        {
                            "kind": "source_event",
                            "source_event_id": "sevt_delivery_visible",
                            "source_system": "github",
                            "source_object_type": "pull_request",
                            "source_object_id": "delivery:visible",
                            "raw_object_ref": "raw://delivery/visible.json",
                            "raw_payload": "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
                            "provider_payload": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                            "prompt": "PRIVATE_PROMPT_DO_NOT_EXPOSE",
                            "source_payload": "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
                        }
                    ],
                    "activity_evidence_refs": [
                        {
                            "kind": "normalized_activity_item",
                            "source_event_id": "sevt_delivery_visible",
                            "raw_object_ref": "raw://delivery/visible.json",
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
                    "id": "atri_delivery_hidden",
                    "title": "Hidden delivery draft title",
                    "evidence_refs": [
                        {
                            "source_event_id": "sevt_delivery_hidden",
                            "raw_object_ref": "raw://delivery/hidden.json",
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


def _rendered_digest(
    digest: dict[str, Any],
    *,
    debug_evidence: bool = False,
) -> str:
    safe_digest = sanitize_persisted_attention_digest_for_delivery_draft(
        digest,
        debug_evidence=debug_evidence,
    )
    return render_persisted_attention_digest_text(
        safe_digest,
        debug_evidence=debug_evidence,
    )


async def _ensure_audit_log_table() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(AuditLog.__table__.create, checkfirst=True)


async def _delete_delivery_draft_audit_logs(delivery_draft_id: str) -> None:
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
        await session.commit()


async def _delete_delivery_intention_audit_log(delivery_intention_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AuditLog)
            .where(AuditLog.event_type == DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE)
            .where(AuditLog.after_ref == delivery_intention_id)
        )
        await session.commit()


async def _delivery_draft_audit_log_count(
    delivery_draft_id: str,
    *,
    event_type: str = DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
) -> int:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type == event_type)
            .where(AuditLog.after_ref == delivery_draft_id)
        )
    return int(count or 0)


async def _delivery_draft_audit_log_total(delivery_draft_id: str) -> int:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type.in_(DIGEST_DELIVERY_DRAFT_AUDIT_EVENT_TYPES))
            .where(AuditLog.after_ref == delivery_draft_id)
        )
    return int(count or 0)


async def _delivery_draft_audit_payload(
    delivery_draft_id: str,
    *,
    event_type: str = DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        payload = await session.scalar(
            select(AuditLog.payload)
            .where(AuditLog.event_type == event_type)
            .where(AuditLog.after_ref == delivery_draft_id)
            .order_by(AuditLog.id)
        )
    assert isinstance(payload, dict)
    return payload


async def _delivery_intention_audit_log_count(delivery_intention_id: str) -> int:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type == DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE)
            .where(AuditLog.after_ref == delivery_intention_id)
        )
    return int(count or 0)


async def _delivery_intention_audit_payload(
    delivery_intention_id: str,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        payload = await session.scalar(
            select(AuditLog.payload)
            .where(AuditLog.event_type == DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE)
            .where(AuditLog.after_ref == delivery_intention_id)
            .order_by(AuditLog.id)
        )
    assert isinstance(payload, dict)
    return payload


def test_delivery_draft_builder_returns_inert_review_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery draft builder must not send Telegram messages")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)

    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 1, 1),
        end_at=_utc(2132, 1, 2),
        limit=20,
    )

    assert draft["status"] == "draft"
    assert draft["digest_type"] == "persisted_attention"
    assert draft["channel"] == "telegram"
    assert draft["delivery_enabled"] is False
    assert draft["approval_required"] is True
    assert draft["approved"] is False
    assert draft["sent"] is False
    assert draft["rendered_text"] == rendered_text
    assert draft["text_sha256"] == sha256(rendered_text.encode("utf-8")).hexdigest()
    assert draft["char_count"] == len(rendered_text)
    assert draft["chunk_count"] == len(draft["chunk_metadata"]["chunk_lengths"])
    assert draft["chunk_count"] >= 1
    assert draft["chunk_metadata"]["chunks_preview_included"] is False
    assert draft["safety"] == {
        "provider_free": True,
        "read_only": True,
        "delivery_invoked": False,
        "approval_executed": False,
        "persisted": False,
        "scheduler_invoked": False,
        "triage_run": False,
        "connectors_invoked": False,
        "live_api_calls": False,
    }


def test_delivery_draft_id_is_deterministic_and_changes_with_safe_inputs() -> None:
    stable_id = build_delivery_draft_id(
        digest_type="persisted_attention",
        channel="telegram",
        start_at="2132-01-01T00:00:00+00:00",
        end_at="2132-01-02T00:00:00+00:00",
        limit=20,
        debug_evidence=False,
        text_sha256="a" * 64,
    )
    repeated_id = build_delivery_draft_id(
        digest_type="persisted_attention",
        channel="telegram",
        start_at="2132-01-01T00:00:00+00:00",
        end_at="2132-01-02T00:00:00+00:00",
        limit=20,
        debug_evidence=False,
        text_sha256="a" * 64,
    )
    changed_text_id = build_delivery_draft_id(
        digest_type="persisted_attention",
        channel="telegram",
        start_at="2132-01-01T00:00:00+00:00",
        end_at="2132-01-02T00:00:00+00:00",
        limit=20,
        debug_evidence=False,
        text_sha256="b" * 64,
    )
    changed_window_id = build_delivery_draft_id(
        digest_type="persisted_attention",
        channel="telegram",
        start_at="2132-01-02T00:00:00+00:00",
        end_at="2132-01-03T00:00:00+00:00",
        limit=20,
        debug_evidence=False,
        text_sha256="a" * 64,
    )

    assert stable_id == repeated_id
    assert stable_id.startswith("ddraft_")
    assert stable_id != changed_text_id
    assert stable_id != changed_window_id


def test_delivery_intention_id_is_deterministic_and_changes_with_safe_inputs() -> None:
    stable_id = build_delivery_intention_id(
        delivery_draft_id="ddraft_stable",
        digest_type="persisted_attention",
        channel="telegram",
        text_sha256="a" * 64,
        chunk_count=2,
        chunk_metadata={
            "chunk_size": 3900,
            "chunk_lengths": [120, 80],
            "chunks_preview_included": False,
        },
    )
    repeated_id = build_delivery_intention_id(
        delivery_draft_id="ddraft_stable",
        digest_type="persisted_attention",
        channel="telegram",
        text_sha256="a" * 64,
        chunk_count=2,
        chunk_metadata={
            "chunk_size": 3900,
            "chunk_lengths": [120, 80],
            "chunks_preview_included": False,
        },
    )
    changed_hash_id = build_delivery_intention_id(
        delivery_draft_id="ddraft_stable",
        digest_type="persisted_attention",
        channel="telegram",
        text_sha256="b" * 64,
        chunk_count=2,
        chunk_metadata={
            "chunk_size": 3900,
            "chunk_lengths": [120, 80],
            "chunks_preview_included": False,
        },
    )
    changed_channel_id = build_delivery_intention_id(
        delivery_draft_id="ddraft_stable",
        digest_type="persisted_attention",
        channel="slack",
        text_sha256="a" * 64,
        chunk_count=2,
        chunk_metadata={
            "chunk_size": 3900,
            "chunk_lengths": [120, 80],
            "chunks_preview_included": False,
        },
    )

    assert stable_id == repeated_id
    assert stable_id.startswith("dint_")
    assert stable_id != changed_hash_id
    assert stable_id != changed_channel_id


def test_delivery_draft_keeps_hidden_details_count_only_and_omits_raw_payloads() -> None:
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)

    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 1, 1),
        end_at=_utc(2132, 1, 2),
    )
    dumped = json.dumps(draft, sort_keys=True)

    assert draft["digest"]["hidden_low_priority_summary"] == {
        "total": 1,
        "counts": {"no-action low-priority items": 1},
    }
    assert "Hidden delivery draft title" not in dumped
    assert "atri_delivery_hidden" not in dumped
    assert "sevt_delivery_hidden" not in dumped
    assert "evidence_refs" not in dumped
    assert "activity_evidence_refs" not in dumped
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
        assert marker not in dumped
        assert marker not in draft["rendered_text"]


def test_delivery_draft_debug_evidence_includes_only_safe_evidence_keys() -> None:
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest, debug_evidence=True)

    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 1, 1),
        end_at=_utc(2132, 1, 2),
        debug_evidence=True,
    )
    item = draft["digest"]["groups"]["work_actions"][0]
    dumped = json.dumps(draft, sort_keys=True)

    assert item["evidence_refs"] == [
        {
            "kind": "source_event",
            "source_event_id": "sevt_delivery_visible",
            "source_system": "github",
            "source_object_type": "pull_request",
            "source_object_id": "delivery:visible",
            "raw_object_ref": "raw://delivery/visible.json",
        }
    ]
    assert item["activity_evidence_refs"] == [
        {
            "kind": "normalized_activity_item",
            "source_event_id": "sevt_delivery_visible",
            "raw_object_ref": "raw://delivery/visible.json",
        }
    ]
    assert "Debug evidence refs:" in draft["rendered_text"]
    assert "raw_payload" not in dumped
    assert "provider_payload" not in dumped
    assert "prompt" not in dumped
    assert "source_payload" not in dumped


def test_delivery_draft_records_source_of_truth_metadata_without_becoming_truth() -> None:
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)

    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 1, 1),
        end_at=_utc(2132, 1, 2),
    )

    assert draft["source_of_truth"] == {
        "source": "postgres",
        "raw_storage_authoritative": True,
        "postgres_authoritative": True,
        "draft_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
        "derived_from": [
            "attention_triage_results",
            "normalized_activity_items",
        ],
        "digest_source_model": "attention_triage_results",
        "digest_enrichment_model": "normalized_activity_items",
        "rendered_text_source": "render_persisted_attention_digest_text",
    }


async def test_persisting_delivery_draft_writes_one_audit_log_and_is_idempotent() -> None:
    await _ensure_audit_log_table()
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 1, 1),
        end_at=_utc(2132, 1, 2),
        limit=20,
    )
    delivery_draft_id = draft["delivery_draft_id"]
    await _delete_delivery_draft_audit_logs(delivery_draft_id)

    try:
        async with AsyncSessionLocal() as session:
            created = await persist_digest_delivery_draft(
                session,
                draft=draft,
                actor="test",
            )
            await session.commit()

        async with AsyncSessionLocal() as session:
            existing = await persist_digest_delivery_draft(
                session,
                draft=draft,
                actor="test",
            )
            await session.commit()

        assert created["delivery_draft_id"] == delivery_draft_id
        assert existing["delivery_draft_id"] == delivery_draft_id
        assert created["persisted"] is True
        assert existing["persisted"] is True
        assert created["status"] == "draft"
        assert created["digest_type"] == "persisted_attention"
        assert created["channel"] == "telegram"
        assert created["delivery_enabled"] is False
        assert created["approval_required"] is True
        assert created["approved"] is False
        assert created["sent"] is False
        assert created["persistence"] == {
            "storage": "audit_logs",
            "event_type": DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
            "after_ref": delivery_draft_id,
            "approval_state": "not_requested",
        }
        assert created["audit_log"]["event_type"] == (
            DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE
        )
        assert created["audit_log"]["after_ref"] == delivery_draft_id
        assert created["safety"]["audit_log_backed"] is True
        assert created["safety"]["db_write_scope"] == "audit_logs_only"
        assert created["safety"]["delivery_invoked"] is False
        assert created["safety"]["approval_executed"] is False
        assert await _delivery_draft_audit_log_count(delivery_draft_id) == 1
    finally:
        await _delete_delivery_draft_audit_logs(delivery_draft_id)


async def test_retrieving_persisted_delivery_draft_returns_sanitized_payload() -> None:
    await _ensure_audit_log_table()
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest, debug_evidence=True)
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 1, 1),
        end_at=_utc(2132, 1, 2),
        limit=20,
        debug_evidence=True,
    )
    delivery_draft_id = draft["delivery_draft_id"]
    await _delete_delivery_draft_audit_logs(delivery_draft_id)

    try:
        async with AsyncSessionLocal() as session:
            await persist_digest_delivery_draft(session, draft=draft, actor="test")
            await session.commit()

        stored_payload = await _delivery_draft_audit_payload(delivery_draft_id)
        async with AsyncSessionLocal() as session:
            retrieved = await get_persisted_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            missing = await get_persisted_digest_delivery_draft(
                session,
                delivery_draft_id=f"{delivery_draft_id}_missing",
            )

        assert retrieved is not None
        assert retrieved["delivery_draft_id"] == delivery_draft_id
        assert retrieved["persisted"] is True
        assert retrieved["rendered_text"] == rendered_text
        assert retrieved["text_sha256"] == sha256(rendered_text.encode("utf-8")).hexdigest()
        assert missing is None
        assert stored_payload["digest"]["hidden_low_priority_summary"] == {
            "total": 1,
            "counts": {"no-action low-priority items": 1},
        }

        dumped = json.dumps({"stored": stored_payload, "retrieved": retrieved})
        assert "Hidden delivery draft title" not in dumped
        assert "atri_delivery_hidden" not in dumped
        assert "sevt_delivery_hidden" not in dumped
        assert "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE" not in dumped
        assert "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE" not in dumped
        assert "PRIVATE_PROMPT_DO_NOT_EXPOSE" not in dumped
        assert "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE" not in dumped
        assert "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE" not in dumped
        assert "raw_payload" not in dumped
        assert "provider_payload" not in dumped
        assert "prompt" not in dumped
        assert "source_payload" not in dumped
    finally:
        await _delete_delivery_draft_audit_logs(delivery_draft_id)


async def test_delivery_draft_approval_status_unknown_returns_none_and_decisions_raise() -> None:
    await _ensure_audit_log_table()
    delivery_draft_id = "ddraft_unknown_fos_062_service"
    await _delete_delivery_draft_audit_logs(delivery_draft_id)

    async with AsyncSessionLocal() as session:
        status = await get_digest_delivery_draft_approval_status(
            session,
            delivery_draft_id=delivery_draft_id,
        )
        readiness = await get_digest_delivery_draft_delivery_readiness(
            session,
            delivery_draft_id=delivery_draft_id,
        )
        missing_intention = await get_digest_delivery_intention(
            session,
            delivery_intention_id="dint_unknown_fos_064_service",
        )
        with pytest.raises(DeliveryDraftNotFoundError, match="not found"):
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
            )
        with pytest.raises(DeliveryDraftNotFoundError, match="not found"):
            await reject_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
            )
        with pytest.raises(DeliveryDraftNotFoundError, match="not found"):
            await create_digest_delivery_intention(
                session,
                delivery_draft_id=delivery_draft_id,
                actor="test",
            )

    assert status is None
    assert readiness is None
    assert missing_intention is None


async def test_approving_delivery_draft_writes_one_safe_audit_event_and_is_idempotent() -> None:
    await _ensure_audit_log_table()
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 4, 1),
        end_at=_utc(2132, 4, 2),
        limit=20,
    )
    delivery_draft_id = draft["delivery_draft_id"]
    await _delete_delivery_draft_audit_logs(delivery_draft_id)

    try:
        async with AsyncSessionLocal() as session:
            await persist_digest_delivery_draft(session, draft=draft, actor="test")
            initial_status = await get_digest_delivery_draft_approval_status(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            approved = await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Approved for digest review.",
            )
            repeated = await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="other reviewer",
                note="This duplicate should not create another row.",
            )
            await session.commit()

        assert initial_status is not None
        assert initial_status["current_decision"] is None
        assert approved == repeated
        assert approved["delivery_draft_id"] == delivery_draft_id
        assert approved["current_decision"] == "approved"
        assert approved["approved"] is True
        assert approved["rejected"] is False
        assert approved["delivery_enabled"] is False
        assert approved["sent"] is False
        assert approved["delivery_invoked"] is False
        assert approved["approval_execution_invoked"] is False
        assert approved["draft"]["text_sha256"] == draft["text_sha256"]
        assert len(approved["decision_history"]) == 1
        history_entry = approved["decision_history"][0]
        assert history_entry["event_type"] == DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE
        assert history_entry["decision"] == "approved"
        assert history_entry["reviewer"] == "founder"
        assert history_entry["draft_text_sha256"] == draft["text_sha256"]
        assert history_entry["audit_log"] == {
            "event_type": DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
            "after_ref": delivery_draft_id,
        }
        assert history_entry["safety"] == approved["safety"]
        assert history_entry["note"] == "Approved for digest review."
        assert "created_at" in history_entry
        assert await _delivery_draft_audit_log_count(
            delivery_draft_id,
            event_type=DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
        ) == 1

        payload = await _delivery_draft_audit_payload(
            delivery_draft_id,
            event_type=DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
        )
        dumped = json.dumps({"payload": payload, "status": approved}, sort_keys=True)
        assert payload["delivery_draft_id"] == delivery_draft_id
        assert payload["decision"] == "approved"
        assert payload["reviewer"] == "founder"
        assert payload["draft_text_sha256"] == draft["text_sha256"]
        assert '"rendered_text":' not in dumped
        assert "Hidden delivery draft title" not in dumped
        assert "atri_delivery_hidden" not in dumped
        assert "sevt_delivery_hidden" not in dumped
        assert "evidence_refs" not in dumped
        for marker in (
            "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_PROMPT_DO_NOT_EXPOSE",
            "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
            "raw_payload",
            "provider_payload",
            "prompt",
            "source_payload",
        ):
            assert marker not in dumped
    finally:
        await _delete_delivery_draft_audit_logs(delivery_draft_id)


async def test_rejecting_delivery_draft_writes_one_safe_audit_event_and_is_idempotent() -> None:
    await _ensure_audit_log_table()
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 4, 3),
        end_at=_utc(2132, 4, 4),
        limit=20,
    )
    delivery_draft_id = draft["delivery_draft_id"]
    await _delete_delivery_draft_audit_logs(delivery_draft_id)

    try:
        async with AsyncSessionLocal() as session:
            await persist_digest_delivery_draft(session, draft=draft, actor="test")
            rejected = await reject_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Needs revision before delivery.",
            )
            repeated = await reject_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="other reviewer",
            )
            await session.commit()

        assert rejected == repeated
        assert rejected["current_decision"] == "rejected"
        assert rejected["approved"] is False
        assert rejected["rejected"] is True
        assert rejected["delivery_enabled"] is False
        assert rejected["sent"] is False
        assert rejected["decision_history"][0]["event_type"] == (
            DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE
        )
        assert rejected["decision_history"][0]["reviewer"] == "founder"
        assert rejected["decision_history"][0]["note"] == "Needs revision before delivery."
        assert await _delivery_draft_audit_log_count(
            delivery_draft_id,
            event_type=DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE,
        ) == 1
    finally:
        await _delete_delivery_draft_audit_logs(delivery_draft_id)


async def test_delivery_draft_decision_conflicts_reject_opposite_terminal_decision() -> None:
    await _ensure_audit_log_table()
    digest = _persisted_attention_digest()

    approved_draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=_rendered_digest(digest),
        start_at=_utc(2132, 4, 5),
        end_at=_utc(2132, 4, 6),
    )
    rejected_draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=_rendered_digest(digest),
        start_at=_utc(2132, 4, 7),
        end_at=_utc(2132, 4, 8),
    )
    approved_id = approved_draft["delivery_draft_id"]
    rejected_id = rejected_draft["delivery_draft_id"]
    await _delete_delivery_draft_audit_logs(approved_id)
    await _delete_delivery_draft_audit_logs(rejected_id)

    try:
        async with AsyncSessionLocal() as session:
            await persist_digest_delivery_draft(
                session,
                draft=approved_draft,
                actor="test",
            )
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=approved_id,
                reviewer="founder",
            )
            with pytest.raises(DeliveryDraftDecisionConflictError, match="approved"):
                await reject_digest_delivery_draft(
                    session,
                    delivery_draft_id=approved_id,
                    reviewer="founder",
                )

            await persist_digest_delivery_draft(
                session,
                draft=rejected_draft,
                actor="test",
            )
            await reject_digest_delivery_draft(
                session,
                delivery_draft_id=rejected_id,
                reviewer="founder",
            )
            with pytest.raises(DeliveryDraftDecisionConflictError, match="rejected"):
                await approve_digest_delivery_draft(
                    session,
                    delivery_draft_id=rejected_id,
                    reviewer="founder",
                )
            await session.commit()

        assert await _delivery_draft_audit_log_count(
            approved_id,
            event_type=DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE,
        ) == 0
        assert await _delivery_draft_audit_log_count(
            rejected_id,
            event_type=DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
        ) == 0
    finally:
        await _delete_delivery_draft_audit_logs(approved_id)
        await _delete_delivery_draft_audit_logs(rejected_id)


async def test_delivery_draft_delivery_readiness_reports_states_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_audit_log_table()

    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery readiness must not send Telegram messages")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    digest = _persisted_attention_digest()

    unapproved_draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=_rendered_digest(digest),
        start_at=_utc(2132, 5, 1),
        end_at=_utc(2132, 5, 2),
    )
    rejected_draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=_rendered_digest(digest),
        start_at=_utc(2132, 5, 3),
        end_at=_utc(2132, 5, 4),
    )
    approved_draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=_rendered_digest(digest),
        start_at=_utc(2132, 5, 5),
        end_at=_utc(2132, 5, 6),
    )
    draft_ids = [
        unapproved_draft["delivery_draft_id"],
        rejected_draft["delivery_draft_id"],
        approved_draft["delivery_draft_id"],
    ]
    for delivery_draft_id in draft_ids:
        await _delete_delivery_draft_audit_logs(delivery_draft_id)

    try:
        async with AsyncSessionLocal() as session:
            await persist_digest_delivery_draft(
                session,
                draft=unapproved_draft,
                actor="test",
            )
            await persist_digest_delivery_draft(
                session,
                draft=rejected_draft,
                actor="test",
            )
            await reject_digest_delivery_draft(
                session,
                delivery_draft_id=rejected_draft["delivery_draft_id"],
                reviewer="founder",
                note="Not ready.",
            )
            await persist_digest_delivery_draft(
                session,
                draft=approved_draft,
                actor="test",
            )
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=approved_draft["delivery_draft_id"],
                reviewer="founder",
                note="Ready for future delivery gate.",
            )
            await session.commit()

        before_counts = {
            delivery_draft_id: await _delivery_draft_audit_log_total(delivery_draft_id)
            for delivery_draft_id in draft_ids
        }
        async with AsyncSessionLocal() as session:
            unapproved = await get_digest_delivery_draft_delivery_readiness(
                session,
                delivery_draft_id=unapproved_draft["delivery_draft_id"],
            )
            rejected = await get_digest_delivery_draft_delivery_readiness(
                session,
                delivery_draft_id=rejected_draft["delivery_draft_id"],
            )
            approved = await get_digest_delivery_draft_delivery_readiness(
                session,
                delivery_draft_id=approved_draft["delivery_draft_id"],
            )
        after_counts = {
            delivery_draft_id: await _delivery_draft_audit_log_total(delivery_draft_id)
            for delivery_draft_id in draft_ids
        }

        assert before_counts == after_counts
        assert unapproved is not None
        assert rejected is not None
        assert approved is not None

        assert unapproved["status"] == "delivery_readiness"
        assert unapproved["current_decision"] is None
        assert unapproved["approved"] is False
        assert unapproved["rejected"] is False
        assert unapproved["eligible_for_delivery"] is False
        assert unapproved["ineligible_reasons"] == ["not_approved"]

        assert rejected["current_decision"] == "rejected"
        assert rejected["approved"] is False
        assert rejected["rejected"] is True
        assert rejected["eligible_for_delivery"] is False
        assert rejected["ineligible_reasons"] == ["rejected"]

        assert approved["current_decision"] == "approved"
        assert approved["approved"] is True
        assert approved["rejected"] is False
        assert approved["eligible_for_delivery"] is True
        assert approved["ineligible_reasons"] == []

        for readiness, draft in (
            (unapproved, unapproved_draft),
            (rejected, rejected_draft),
            (approved, approved_draft),
        ):
            assert readiness["draft_exists"] is True
            assert readiness["digest_type"] == "persisted_attention"
            assert readiness["channel"] == "telegram"
            assert readiness["delivery_execution_enabled"] is False
            assert readiness["delivery_enabled"] is False
            assert readiness["delivery_invoked"] is False
            assert readiness["approval_execution_invoked"] is False
            assert readiness["sent"] is False
            assert readiness["text_sha256"] == draft["text_sha256"]
            assert readiness["char_count"] == draft["char_count"]
            assert readiness["chunk_count"] == draft["chunk_count"]
            assert readiness["chunk_metadata"] == draft["chunk_metadata"]
            assert readiness["start_at"] == draft["start_at"]
            assert readiness["end_at"] == draft["end_at"]
            assert readiness["limit"] == draft["limit"]
            assert readiness["source_of_truth"] == draft["source_of_truth"]
            assert readiness["safety"] == {
                "provider_free": True,
                "read_only": True,
                "delivery_execution_enabled": False,
                "delivery_invoked": False,
                "approval_execution_invoked": False,
                "scheduler_invoked": False,
                "connectors_invoked": False,
                "live_api_calls": False,
                "db_write_scope": "none",
                "draft_is_source_of_truth": False,
                "telegram_is_source_of_truth": False,
            }
            assert "rendered_text" not in readiness
            assert "digest" not in readiness

        serialized = json.dumps(
            {
                "unapproved": unapproved,
                "rejected": rejected,
                "approved": approved,
            },
            sort_keys=True,
        )
        assert "Hidden delivery draft title" not in serialized
        assert "atri_delivery_hidden" not in serialized
        assert "sevt_delivery_hidden" not in serialized
        assert "evidence_refs" not in serialized
        for marker in (
            "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_PROMPT_DO_NOT_EXPOSE",
            "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
            "raw_payload",
            "provider_payload",
            "prompt",
            "source_payload",
        ):
            assert marker not in serialized
    finally:
        for delivery_draft_id in draft_ids:
            await _delete_delivery_draft_audit_logs(delivery_draft_id)


async def test_delivery_intention_rejects_unapproved_and_rejected_drafts() -> None:
    await _ensure_audit_log_table()
    digest = _persisted_attention_digest()
    unapproved_draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=_rendered_digest(digest),
        start_at=_utc(2132, 7, 1),
        end_at=_utc(2132, 7, 2),
    )
    rejected_draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=_rendered_digest(digest),
        start_at=_utc(2132, 7, 3),
        end_at=_utc(2132, 7, 4),
    )
    draft_ids = [
        unapproved_draft["delivery_draft_id"],
        rejected_draft["delivery_draft_id"],
    ]
    for delivery_draft_id in draft_ids:
        await _delete_delivery_draft_audit_logs(delivery_draft_id)

    try:
        async with AsyncSessionLocal() as session:
            await persist_digest_delivery_draft(
                session,
                draft=unapproved_draft,
                actor="test",
            )
            await persist_digest_delivery_draft(
                session,
                draft=rejected_draft,
                actor="test",
            )
            await reject_digest_delivery_draft(
                session,
                delivery_draft_id=rejected_draft["delivery_draft_id"],
                reviewer="founder",
            )

            with pytest.raises(DeliveryIntentionNotReadyError, match="not_approved"):
                await create_digest_delivery_intention(
                    session,
                    delivery_draft_id=unapproved_draft["delivery_draft_id"],
                    actor="test",
                )
            with pytest.raises(DeliveryIntentionNotReadyError, match="rejected"):
                await create_digest_delivery_intention(
                    session,
                    delivery_draft_id=rejected_draft["delivery_draft_id"],
                    actor="test",
                )
            await session.commit()

        for delivery_draft_id in draft_ids:
            async with AsyncSessionLocal() as session:
                result = await session.scalar(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(
                        AuditLog.event_type
                        == DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE
                    )
                    .where(AuditLog.before_ref == delivery_draft_id)
                )
            assert int(result or 0) == 0
    finally:
        for delivery_draft_id in draft_ids:
            await _delete_delivery_draft_audit_logs(delivery_draft_id)


async def test_delivery_intention_creates_one_safe_audit_event_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_audit_log_table()

    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery intention must not send Telegram messages")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    digest = _persisted_attention_digest()
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=_rendered_digest(digest),
        start_at=_utc(2132, 7, 5),
        end_at=_utc(2132, 7, 6),
    )
    delivery_draft_id = draft["delivery_draft_id"]
    await _delete_delivery_draft_audit_logs(delivery_draft_id)

    try:
        async with AsyncSessionLocal() as session:
            await persist_digest_delivery_draft(session, draft=draft, actor="test")
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Approved for intention.",
            )
            created = await create_digest_delivery_intention(
                session,
                delivery_draft_id=delivery_draft_id,
                actor="test",
            )
            repeated = await create_digest_delivery_intention(
                session,
                delivery_draft_id=delivery_draft_id,
                actor="duplicate",
            )
            await session.commit()

        delivery_intention_id = created["delivery_intention_id"]
        stored_payload = await _delivery_intention_audit_payload(
            delivery_intention_id
        )
        async with AsyncSessionLocal() as session:
            retrieved = await get_digest_delivery_intention(
                session,
                delivery_intention_id=delivery_intention_id,
            )

        assert retrieved is not None
        assert created["delivery_intention_id"] == repeated["delivery_intention_id"]
        assert retrieved["delivery_intention_id"] == delivery_intention_id
        assert created["delivery_draft_id"] == delivery_draft_id
        assert created["status"] == "delivery_intention"
        assert created["persisted"] is True
        assert created["digest_type"] == "persisted_attention"
        assert created["channel"] == "telegram"
        assert created["current_decision"] == "approved"
        assert created["eligible_for_delivery"] is True
        assert created["delivery_execution_enabled"] is False
        assert created["delivery_enabled"] is False
        assert created["delivery_invoked"] is False
        assert created["approval_execution_invoked"] is False
        assert created["sent"] is False
        assert created["scheduler_invoked"] is False
        assert created["text_sha256"] == draft["text_sha256"]
        assert created["char_count"] == draft["char_count"]
        assert created["chunk_count"] == draft["chunk_count"]
        assert created["chunk_metadata"] == draft["chunk_metadata"]
        assert created["start_at"] == draft["start_at"]
        assert created["end_at"] == draft["end_at"]
        assert created["limit"] == draft["limit"]
        assert created["readiness"] == {
            "status": "delivery_readiness",
            "current_decision": "approved",
            "approved": True,
            "rejected": False,
            "eligible_for_delivery": True,
            "ineligible_reasons": [],
        }
        assert created["source_of_truth"] == draft["source_of_truth"]
        assert created["safety"] == {
            "provider_free": True,
            "read_only": False,
            "db_write_scope": "audit_logs_only",
            "audit_log_backed": True,
            "delivery_execution_enabled": False,
            "delivery_enabled": False,
            "delivery_invoked": False,
            "delivery_adapter_invoked": False,
            "approval_execution_invoked": False,
            "scheduler_invoked": False,
            "connectors_invoked": False,
            "live_api_calls": False,
            "draft_is_source_of_truth": False,
            "intention_is_source_of_truth": False,
            "telegram_is_source_of_truth": False,
        }
        assert created["audit_log"]["event_type"] == (
            DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE
        )
        assert created["audit_log"]["before_ref"] == delivery_draft_id
        assert created["audit_log"]["after_ref"] == delivery_intention_id
        assert stored_payload["delivery_intention_id"] == delivery_intention_id
        assert stored_payload["delivery_draft_id"] == delivery_draft_id
        assert await _delivery_intention_audit_log_count(delivery_intention_id) == 1

        expected_id = build_delivery_intention_id(
            delivery_draft_id=delivery_draft_id,
            digest_type="persisted_attention",
            channel="telegram",
            text_sha256=draft["text_sha256"],
            chunk_count=draft["chunk_count"],
            chunk_metadata=draft["chunk_metadata"],
        )
        assert delivery_intention_id == expected_id

        dumped = json.dumps(
            {
                "created": created,
                "repeated": repeated,
                "retrieved": retrieved,
                "stored_payload": stored_payload,
            },
            sort_keys=True,
        )
        assert '"rendered_text":' not in dumped
        assert '"digest":' not in dumped
        assert "Hidden delivery draft title" not in dumped
        assert "atri_delivery_hidden" not in dumped
        assert "sevt_delivery_hidden" not in dumped
        assert "evidence_refs" not in dumped
        for marker in (
            "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_PROMPT_DO_NOT_EXPOSE",
            "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE",
            "raw_payload",
            "provider_payload",
            "prompt",
            "source_payload",
        ):
            assert marker not in dumped
    finally:
        await _delete_delivery_draft_audit_logs(delivery_draft_id)


async def test_delivery_intention_telegram_plan_returns_safe_read_only_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_audit_log_table()

    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Telegram plan must not send Telegram messages")

    def forbidden_render(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("Telegram plan must not recompute digest text")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 7, 9),
        end_at=_utc(2132, 7, 10),
    )
    delivery_draft_id = draft["delivery_draft_id"]
    await _delete_delivery_draft_audit_logs(delivery_draft_id)

    try:
        async with AsyncSessionLocal() as session:
            await persist_digest_delivery_draft(session, draft=draft, actor="test")
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
                note="Ready for Telegram plan.",
            )
            intention = await create_digest_delivery_intention(
                session,
                delivery_draft_id=delivery_draft_id,
                actor="test",
            )
            await session.commit()

        delivery_intention_id = intention["delivery_intention_id"]
        draft_event_total_before = await _delivery_draft_audit_log_total(
            delivery_draft_id
        )
        intention_count_before = await _delivery_intention_audit_log_count(
            delivery_intention_id
        )
        monkeypatch.setattr(
            digest_delivery_drafts,
            "render_persisted_attention_digest_text",
            forbidden_render,
        )

        async with AsyncSessionLocal() as session:
            plan = await get_digest_delivery_intention_telegram_plan(
                session,
                delivery_intention_id=delivery_intention_id,
            )

        assert plan is not None
        expected_chunks = telegram_delivery.split_telegram_plain_text(rendered_text)
        assert plan["status"] == "telegram_delivery_plan"
        assert plan["delivery_intention_id"] == delivery_intention_id
        assert plan["delivery_draft_id"] == delivery_draft_id
        assert plan["digest_type"] == "persisted_attention"
        assert plan["channel"] == "telegram"
        assert plan["text_sha256"] == draft["text_sha256"]
        assert plan["char_count"] == len(rendered_text)
        assert plan["chunk_count"] == len(expected_chunks)
        assert plan["chunks_text_included"] is False
        assert plan["chunks"] == [
            {
                "index": index,
                "char_count": len(chunk),
                "sha256": sha256(chunk.encode("utf-8")).hexdigest(),
            }
            for index, chunk in enumerate(expected_chunks, start=1)
        ]
        assert all("text" not in chunk for chunk in plan["chunks"])
        assert plan["chunk_metadata"] == {
            "chunk_size": telegram_delivery.DEFAULT_TELEGRAM_CHUNK_SIZE,
            "chunk_lengths": [len(chunk) for chunk in expected_chunks],
            "chunks_preview_included": False,
        }
        assert plan["delivery_execution_enabled"] is False
        assert plan["delivery_enabled"] is False
        assert plan["delivery_invoked"] is False
        assert plan["delivery_adapter_invoked"] is False
        assert plan["approval_execution_invoked"] is False
        assert plan["scheduler_invoked"] is False
        assert plan["sent"] is False
        assert plan["start_at"] == draft["start_at"]
        assert plan["end_at"] == draft["end_at"]
        assert plan["limit"] == draft["limit"]
        assert plan["debug_evidence"] is False
        assert plan["intention"]["status"] == "delivery_intention"
        assert plan["intention"]["persisted"] is True
        assert plan["intention"]["audit_log"]["after_ref"] == delivery_intention_id
        assert plan["intention"]["audit_log"]["before_ref"] == delivery_draft_id
        assert plan["source_of_truth"] == draft["source_of_truth"]
        assert plan["safety"] == {
            "provider_free": True,
            "read_only": True,
            "db_write_scope": "none",
            "delivery_execution_enabled": False,
            "delivery_enabled": False,
            "delivery_invoked": False,
            "delivery_adapter_invoked": False,
            "approval_execution_invoked": False,
            "scheduler_invoked": False,
            "delivery_result_audit_event_created": False,
            "outbox_record_created": False,
            "connectors_invoked": False,
            "live_api_calls": False,
            "draft_is_source_of_truth": False,
            "intention_is_source_of_truth": False,
            "telegram_plan_is_source_of_truth": False,
            "telegram_is_source_of_truth": False,
        }
        assert (
            await _delivery_draft_audit_log_total(delivery_draft_id)
            == draft_event_total_before
        )
        assert (
            await _delivery_intention_audit_log_count(delivery_intention_id)
            == intention_count_before
        )

        dumped = json.dumps(plan, sort_keys=True)
        assert '"rendered_text":' not in dumped
        assert '"digest":' not in dumped
        assert '"text":' not in dumped
        assert "chat_id" not in dumped
        assert "bot_token" not in dumped
        assert "https://api.telegram.org" not in dumped
        assert "Hidden delivery draft title" not in dumped
        assert "atri_delivery_hidden" not in dumped
        assert "sevt_delivery_hidden" not in dumped
        assert "evidence_refs" not in dumped
        for marker in (
            "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_PROMPT_DO_NOT_EXPOSE",
            "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
            "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE",
            "raw_payload",
            "provider_payload",
            "prompt",
            "source_payload",
        ):
            assert marker not in dumped
    finally:
        await _delete_delivery_draft_audit_logs(delivery_draft_id)


async def test_delivery_intention_telegram_plan_fails_closed_for_unsafe_state() -> None:
    await _ensure_audit_log_table()
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 7, 11),
        end_at=_utc(2132, 7, 12),
    )
    delivery_draft_id = draft["delivery_draft_id"]
    manual_ids = [
        "dint_fos_065_missing_draft",
        "dint_fos_065_hash_mismatch",
        "dint_fos_065_non_telegram",
        "dint_fos_065_not_ready",
    ]
    await _delete_delivery_draft_audit_logs(delivery_draft_id)
    for delivery_intention_id in manual_ids:
        await _delete_delivery_intention_audit_log(delivery_intention_id)

    def intention_payload(
        *,
        delivery_intention_id: str,
        draft_id: str,
        channel: str = "telegram",
        text_sha256: str | None = None,
        current_decision: str | None = "approved",
        eligible_for_delivery: bool = True,
    ) -> dict[str, Any]:
        return {
            "persisted": True,
            "status": "delivery_intention",
            "delivery_intention_id": delivery_intention_id,
            "delivery_draft_id": draft_id,
            "digest_type": "persisted_attention",
            "channel": channel,
            "current_decision": current_decision,
            "eligible_for_delivery": eligible_for_delivery,
            "delivery_execution_enabled": False,
            "delivery_enabled": False,
            "delivery_invoked": False,
            "approval_execution_invoked": False,
            "sent": False,
            "scheduler_invoked": False,
            "text_sha256": text_sha256 or draft["text_sha256"],
            "char_count": draft["char_count"],
            "chunk_count": draft["chunk_count"],
            "chunk_metadata": draft["chunk_metadata"],
            "start_at": draft["start_at"],
            "end_at": draft["end_at"],
            "limit": draft["limit"],
            "debug_evidence": draft["debug_evidence"],
            "source_of_truth": draft["source_of_truth"],
        }

    try:
        async with AsyncSessionLocal() as session:
            await persist_digest_delivery_draft(session, draft=draft, actor="test")
            session.add_all(
                [
                    AuditLog(
                        event_type=DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
                        actor="test",
                        correlation_id="ddraft_fos_065_missing",
                        trace_id="dint_fos_065_missing_draft",
                        before_ref="ddraft_fos_065_missing",
                        after_ref="dint_fos_065_missing_draft",
                        approval_id="ddraft_fos_065_missing:delivery_intention",
                        payload=intention_payload(
                            delivery_intention_id="dint_fos_065_missing_draft",
                            draft_id="ddraft_fos_065_missing",
                        ),
                    ),
                    AuditLog(
                        event_type=DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
                        actor="test",
                        correlation_id=delivery_draft_id,
                        trace_id="dint_fos_065_hash_mismatch",
                        before_ref=delivery_draft_id,
                        after_ref="dint_fos_065_hash_mismatch",
                        approval_id=f"{delivery_draft_id}:delivery_intention",
                        payload=intention_payload(
                            delivery_intention_id="dint_fos_065_hash_mismatch",
                            draft_id=delivery_draft_id,
                            text_sha256="mismatched",
                        ),
                    ),
                    AuditLog(
                        event_type=DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
                        actor="test",
                        correlation_id=delivery_draft_id,
                        trace_id="dint_fos_065_non_telegram",
                        before_ref=delivery_draft_id,
                        after_ref="dint_fos_065_non_telegram",
                        approval_id=f"{delivery_draft_id}:delivery_intention",
                        payload=intention_payload(
                            delivery_intention_id="dint_fos_065_non_telegram",
                            draft_id=delivery_draft_id,
                            channel="slack",
                        ),
                    ),
                    AuditLog(
                        event_type=DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
                        actor="test",
                        correlation_id=delivery_draft_id,
                        trace_id="dint_fos_065_not_ready",
                        before_ref=delivery_draft_id,
                        after_ref="dint_fos_065_not_ready",
                        approval_id=f"{delivery_draft_id}:delivery_intention",
                        payload=intention_payload(
                            delivery_intention_id="dint_fos_065_not_ready",
                            draft_id=delivery_draft_id,
                            current_decision=None,
                            eligible_for_delivery=False,
                        ),
                    ),
                ]
            )
            await session.commit()

        async with AsyncSessionLocal() as session:
            missing = await get_digest_delivery_intention_telegram_plan(
                session,
                delivery_intention_id="dint_unknown_fos_065_service",
            )
            assert missing is None

            for delivery_intention_id, expected_message in (
                ("dint_fos_065_missing_draft", "referenced delivery draft"),
                ("dint_fos_065_hash_mismatch", "text_sha256"),
                ("dint_fos_065_non_telegram", "channel is not telegram"),
                ("dint_fos_065_not_ready", "not approved"),
            ):
                with pytest.raises(
                    DeliveryTelegramPlanConflictError,
                    match=expected_message,
                ):
                    await get_digest_delivery_intention_telegram_plan(
                        session,
                        delivery_intention_id=delivery_intention_id,
                    )
    finally:
        await _delete_delivery_draft_audit_logs(delivery_draft_id)
        for delivery_intention_id in manual_ids:
            await _delete_delivery_intention_audit_log(delivery_intention_id)


async def test_delivery_intention_conflicts_on_mismatched_existing_payload() -> None:
    await _ensure_audit_log_table()
    digest = _persisted_attention_digest()
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=_rendered_digest(digest),
        start_at=_utc(2132, 7, 7),
        end_at=_utc(2132, 7, 8),
    )
    delivery_draft_id = draft["delivery_draft_id"]
    await _delete_delivery_draft_audit_logs(delivery_draft_id)

    try:
        async with AsyncSessionLocal() as session:
            await persist_digest_delivery_draft(session, draft=draft, actor="test")
            await approve_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
                reviewer="founder",
            )
            readiness = await get_digest_delivery_draft_delivery_readiness(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            assert readiness is not None
            delivery_intention_id = build_delivery_intention_id(
                delivery_draft_id=delivery_draft_id,
                digest_type=readiness["digest_type"],
                channel=readiness["channel"],
                text_sha256=readiness["text_sha256"],
                chunk_count=readiness["chunk_count"],
                chunk_metadata=readiness["chunk_metadata"],
            )
            session.add(
                AuditLog(
                    event_type=DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
                    actor="test",
                    correlation_id=delivery_draft_id,
                    trace_id=delivery_intention_id,
                    before_ref=delivery_draft_id,
                    after_ref=delivery_intention_id,
                    payload={
                        "persisted": True,
                        "status": "delivery_intention",
                        "delivery_intention_id": delivery_intention_id,
                        "delivery_draft_id": delivery_draft_id,
                        "text_sha256": "mismatched",
                    },
                )
            )
            await session.flush()

            with pytest.raises(DeliveryIntentionConflictError, match="does not match"):
                await create_digest_delivery_intention(
                    session,
                    delivery_draft_id=delivery_draft_id,
                    actor="test",
                )
            await session.rollback()
    finally:
        await _delete_delivery_draft_audit_logs(delivery_draft_id)


class _FakeScalars:
    def all(self) -> list[Any]:
        return []


class _FakeAuditLogRecord:
    def __init__(
        self,
        *,
        delivery_draft_id: str,
        payload: dict[str, Any],
        event_type: str = DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
        before_ref: str | None = None,
        after_ref: str | None = None,
    ) -> None:
        self.event_type = event_type
        self.before_ref = before_ref
        self.after_ref = after_ref or delivery_draft_id
        self.created_at = None
        self.payload = payload


class _ReadOnlyReadinessSession:
    def __init__(self, *, record: _FakeAuditLogRecord) -> None:
        self._record = record

    async def scalar(self, *_args: object, **_kwargs: object) -> _FakeAuditLogRecord:
        return self._record

    async def scalars(self, *_args: object, **_kwargs: object) -> _FakeScalars:
        return _FakeScalars()

    def add(self, _value: object) -> None:
        raise AssertionError("delivery readiness must not add rows")

    async def flush(self) -> None:
        raise AssertionError("delivery readiness must not flush rows")

    async def commit(self) -> None:
        raise AssertionError("delivery readiness must not commit")

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery readiness must not execute write paths")


async def test_delivery_readiness_does_not_call_write_methods() -> None:
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 6, 1),
        end_at=_utc(2132, 6, 2),
    )
    payload = dict(draft)
    payload["persisted"] = True
    fake_record = _FakeAuditLogRecord(
        delivery_draft_id=draft["delivery_draft_id"],
        payload=payload,
    )

    readiness = await get_digest_delivery_draft_delivery_readiness(
        _ReadOnlyReadinessSession(record=fake_record),  # type: ignore[arg-type]
        delivery_draft_id=draft["delivery_draft_id"],
    )

    assert readiness is not None
    assert readiness["delivery_draft_id"] == draft["delivery_draft_id"]
    assert readiness["eligible_for_delivery"] is False
    assert readiness["ineligible_reasons"] == ["not_approved"]
    assert "rendered_text" not in readiness
    assert "digest" not in readiness


class _ReadOnlyTelegramPlanSession:
    def __init__(self, *, records: list[_FakeAuditLogRecord]) -> None:
        self._records = list(records)

    async def scalar(self, *_args: object, **_kwargs: object) -> _FakeAuditLogRecord:
        return self._records.pop(0)

    def add(self, _value: object) -> None:
        raise AssertionError("Telegram plan must not add rows")

    async def flush(self) -> None:
        raise AssertionError("Telegram plan must not flush rows")

    async def commit(self) -> None:
        raise AssertionError("Telegram plan must not commit")

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("Telegram plan must not execute write paths")


async def test_telegram_plan_does_not_call_write_methods() -> None:
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)
    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 6, 3),
        end_at=_utc(2132, 6, 4),
    )
    delivery_intention_id = "dint_read_only_plan_fos_065"
    intention_payload = {
        "persisted": True,
        "status": "delivery_intention",
        "delivery_intention_id": delivery_intention_id,
        "delivery_draft_id": draft["delivery_draft_id"],
        "digest_type": "persisted_attention",
        "channel": "telegram",
        "current_decision": "approved",
        "eligible_for_delivery": True,
        "delivery_execution_enabled": False,
        "text_sha256": draft["text_sha256"],
        "char_count": draft["char_count"],
        "chunk_count": draft["chunk_count"],
        "chunk_metadata": draft["chunk_metadata"],
        "start_at": draft["start_at"],
        "end_at": draft["end_at"],
        "limit": draft["limit"],
        "debug_evidence": draft["debug_evidence"],
        "source_of_truth": draft["source_of_truth"],
    }
    draft_payload = dict(draft)
    draft_payload["persisted"] = True

    plan = await get_digest_delivery_intention_telegram_plan(
        _ReadOnlyTelegramPlanSession(
            records=[
                _FakeAuditLogRecord(
                    delivery_draft_id=draft["delivery_draft_id"],
                    event_type=DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
                    before_ref=draft["delivery_draft_id"],
                    after_ref=delivery_intention_id,
                    payload=intention_payload,
                ),
                _FakeAuditLogRecord(
                    delivery_draft_id=draft["delivery_draft_id"],
                    payload=draft_payload,
                ),
            ]
        ),  # type: ignore[arg-type]
        delivery_intention_id=delivery_intention_id,
    )

    assert plan is not None
    assert plan["delivery_intention_id"] == delivery_intention_id
    assert plan["delivery_draft_id"] == draft["delivery_draft_id"]
    assert plan["status"] == "telegram_delivery_plan"
    assert "rendered_text" not in plan
    assert "digest" not in plan


class _ReadOnlySession:
    async def scalars(self, *_args: object, **_kwargs: object) -> _FakeScalars:
        return _FakeScalars()

    def add(self, _value: object) -> None:
        raise AssertionError("delivery draft builder must not add rows")

    async def flush(self) -> None:
        raise AssertionError("delivery draft builder must not flush rows")

    async def commit(self) -> None:
        raise AssertionError("delivery draft builder must not commit")

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery draft builder must not execute write paths")


async def test_db_read_delivery_draft_builder_does_not_call_write_methods() -> None:
    draft = await build_persisted_attention_digest_delivery_draft_from_db(
        _ReadOnlySession(),  # type: ignore[arg-type]
        start_at=_utc(2132, 2, 1),
        end_at=_utc(2132, 2, 2),
        limit=20,
    )

    assert draft["status"] == "draft"
    assert draft["delivery_enabled"] is False
    assert draft["approved"] is False
    assert draft["sent"] is False
    assert "No persisted attention items found for this window." in draft["rendered_text"]


async def test_db_read_delivery_draft_builder_rejects_invalid_windows_before_query() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await build_persisted_attention_digest_delivery_draft_from_db(
            _ReadOnlySession(),  # type: ignore[arg-type]
            start_at=datetime(2132, 3, 1),
            end_at=_utc(2132, 3, 2),
        )

    with pytest.raises(ValueError, match="after start_at"):
        await build_persisted_attention_digest_delivery_draft_from_db(
            _ReadOnlySession(),  # type: ignore[arg-type]
            start_at=_utc(2132, 3, 2),
            end_at=_utc(2132, 3, 1),
        )
