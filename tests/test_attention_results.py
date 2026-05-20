from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.attention_models import AttentionTriageFeedbackRecord, AttentionTriageResultRecord
from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import IngestedEvent
from app.services.attention_feedback import record_attention_triage_feedback
from app.services.attention_results import (
    AttentionResultValidationError,
    get_attention_triage_result_for_activity_item,
    get_attention_triage_result,
    record_attention_triage_result,
    triage_normalized_activity_item,
)
from app.services.attention_triage import (
    AttentionTriageResult,
    MockAttentionTriageProvider,
    NormalizedActivityItem,
)
from app.services.normalized_activity import record_normalized_activity_item


class _FailingSession:
    def add(self, _record: object) -> None:
        raise AssertionError("invalid payload should fail before session.add")

    async def flush(self) -> None:
        raise AssertionError("invalid payload should fail before session.flush")


async def _ensure_attention_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(IngestedEvent.__table__.create, checkfirst=True)
        await conn.run_sync(SourceEvent.__table__.create, checkfirst=True)
        await conn.run_sync(NormalizedActivityItemRecord.__table__.create, checkfirst=True)
        await conn.run_sync(AttentionTriageResultRecord.__table__.create, checkfirst=True)
        await conn.run_sync(AttentionTriageFeedbackRecord.__table__.create, checkfirst=True)


async def _cleanup_attention_result_fixture(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageFeedbackRecord).where(
                AttentionTriageFeedbackRecord.feedback_id.like(f"atfb_result_{unique}%")
            )
        )
        await session.execute(
            delete(AttentionTriageFeedbackRecord).where(
                AttentionTriageFeedbackRecord.source_object_id.like(
                    f"gmail:test:result:{unique}%"
                )
            )
        )
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.triage_result_id.like(f"atri_test_{unique}%")
            )
        )
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.source_object_id.like(
                    f"gmail:test:result:{unique}%"
                )
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(f"nact_result_{unique}%")
            )
        )
        await session.commit()


def _result(**overrides: object) -> AttentionTriageResult:
    defaults = {
        "attention_class": "requires_my_attention",
        "priority": "high",
        "show_in_digest": True,
        "confidence": 0.91,
        "reason": "validated evidence-backed work request",
        "recommended_action": "reply to the email thread",
        "owner": "me",
        "deadline": "2026-05-20",
        "evidence": [
            {
                "kind": "gmail_message",
                "message_id": "fake-message-id",
                "raw_object_ref": "raw://gmail/fake/message.json",
            }
        ],
    }
    defaults.update(overrides)
    return AttentionTriageResult.model_validate(defaults)


def _activity(unique: str, **overrides: object) -> NormalizedActivityItem:
    defaults = {
        "source": "gmail",
        "source_object_id": f"gmail:test:result:{unique}",
        "activity_type": "email_thread.reply_required.from_external",
        "title": "Validated activity for attention result",
        "actor": "external sender",
        "created_at": datetime(2026, 5, 19, 8, 30, tzinfo=timezone.utc),
        "safe_summary": "Validated activity item for attention result linkage.",
        "evidence_refs": [
            {
                "kind": "gmail_message",
                "message_id": "fake-message-id",
                "raw_object_ref": "raw://gmail/fake/message.json",
            }
        ],
    }
    defaults.update(overrides)
    return NormalizedActivityItem.model_validate(defaults)


@pytest.mark.asyncio
async def test_record_attention_triage_result_persists_and_reads_back_valid_result() -> None:
    await _ensure_attention_tables()
    unique = uuid4().hex
    await _cleanup_attention_result_fixture(unique)
    triage_result_id = f"atri_test_{unique}"
    created_at = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
    expected_result = _result()

    try:
        async with AsyncSessionLocal() as session:
            stored = await record_attention_triage_result(
                session,
                triage_result_id=triage_result_id,
                source="gmail",
                source_object_id=f"gmail:test:result:{unique}",
                activity_item_id=f"activity:test:{unique}",
                result=expected_result,
                created_at=created_at,
            )
            await session.commit()

        assert stored.triage_result_id == triage_result_id
        assert stored.source == "gmail"
        assert stored.source_object_id == f"gmail:test:result:{unique}"
        assert stored.activity_item_id == f"activity:test:{unique}"
        assert stored.attention_class == "requires_my_attention"
        assert stored.priority == "high"
        assert stored.show_in_digest is True
        assert stored.confidence == 0.91
        assert stored.evidence_refs == expected_result.evidence
        assert stored.to_attention_triage_result() == expected_result

        async with AsyncSessionLocal() as session:
            read_back = await get_attention_triage_result(
                session,
                triage_result_id=triage_result_id,
            )
            record = await session.scalar(
                select(AttentionTriageResultRecord).where(
                    AttentionTriageResultRecord.triage_result_id == triage_result_id
                )
            )

        assert read_back is not None
        assert read_back.triage_result_id == triage_result_id
        assert read_back.evidence_refs == expected_result.evidence
        assert read_back.to_attention_triage_result() == expected_result
        assert record is not None
        assert not hasattr(record, "provider_payload")
        assert not hasattr(record, "raw_text")
        assert not hasattr(record, "prompt")

    finally:
        await _cleanup_attention_result_fixture(unique)


@pytest.mark.asyncio
async def test_triage_normalized_activity_item_persists_linked_result() -> None:
    await _ensure_attention_tables()
    unique = uuid4().hex
    await _cleanup_attention_result_fixture(unique)
    activity = _activity(
        unique,
        safe_summary="PRIVATE_RAW_EMAIL_TEXT_DO_NOT_STORE",
    )
    expected_result = _result(evidence=activity.evidence_refs)
    provider = MockAttentionTriageProvider([expected_result])

    try:
        async with AsyncSessionLocal() as session:
            stored_activity = await record_normalized_activity_item(
                session,
                activity_item_id=f"nact_result_{unique}",
                activity=activity,
            )
            stored = await triage_normalized_activity_item(
                session,
                activity_item_id=stored_activity.activity_item_id,
                provider=provider,
            )
            await session.commit()

        assert stored.activity_item_id == stored_activity.activity_item_id
        assert stored.source == "gmail"
        assert stored.source_object_id == f"gmail:test:result:{unique}"
        assert stored.to_attention_triage_result() == expected_result
        assert stored.evidence_refs == activity.evidence_refs
        assert len(provider.calls) == 1

        async with AsyncSessionLocal() as session:
            read_back = await get_attention_triage_result_for_activity_item(
                session,
                activity_item_id=stored_activity.activity_item_id,
            )
            record = await session.scalar(
                select(AttentionTriageResultRecord).where(
                    AttentionTriageResultRecord.activity_item_id
                    == stored_activity.activity_item_id
                )
            )

        assert read_back is not None
        assert read_back.triage_result_id == stored.triage_result_id
        assert record is not None
        rendered_record = str(record.__dict__)
        assert "PRIVATE_RAW_EMAIL_TEXT_DO_NOT_STORE" not in rendered_record
        assert not hasattr(record, "provider_payload")
        assert not hasattr(record, "raw_payload")
        assert not hasattr(record, "raw_text")
        assert not hasattr(record, "prompt")

    finally:
        await _cleanup_attention_result_fixture(unique)


@pytest.mark.asyncio
async def test_triage_normalized_activity_item_is_idempotent_without_second_provider_call() -> None:
    await _ensure_attention_tables()
    unique = uuid4().hex
    await _cleanup_attention_result_fixture(unique)
    provider = MockAttentionTriageProvider([_result()])

    try:
        async with AsyncSessionLocal() as session:
            stored_activity = await record_normalized_activity_item(
                session,
                activity_item_id=f"nact_result_{unique}",
                activity=_activity(unique),
            )
            first = await triage_normalized_activity_item(
                session,
                activity_item_id=stored_activity.activity_item_id,
                provider=provider,
            )
            second = await triage_normalized_activity_item(
                session,
                activity_item_id=stored_activity.activity_item_id,
                provider=provider,
            )
            count = await session.scalar(
                select(func.count(AttentionTriageResultRecord.id)).where(
                    AttentionTriageResultRecord.activity_item_id
                    == stored_activity.activity_item_id
                )
            )
            await session.commit()

        assert second.triage_result_id == first.triage_result_id
        assert second.activity_item_id == stored_activity.activity_item_id
        assert count == 1
        assert len(provider.calls) == 1

    finally:
        await _cleanup_attention_result_fixture(unique)


@pytest.mark.asyncio
async def test_triage_normalized_activity_item_missing_activity_fails_before_provider_call() -> None:
    await _ensure_attention_tables()
    unique = uuid4().hex
    await _cleanup_attention_result_fixture(unique)
    missing_activity_item_id = f"nact_result_{unique}_missing"
    provider = MockAttentionTriageProvider([_result()])

    try:
        async with AsyncSessionLocal() as session:
            with pytest.raises(AttentionResultValidationError, match="not found"):
                await triage_normalized_activity_item(
                    session,
                    activity_item_id=missing_activity_item_id,
                    provider=provider,
                )

            count = await session.scalar(
                select(func.count(AttentionTriageResultRecord.id)).where(
                    AttentionTriageResultRecord.activity_item_id == missing_activity_item_id
                )
            )
            assert count == 0
            await session.rollback()

        assert provider.calls == []

    finally:
        await _cleanup_attention_result_fixture(unique)


@pytest.mark.asyncio
async def test_triage_normalized_activity_item_invalid_provider_output_does_not_persist() -> None:
    await _ensure_attention_tables()
    unique = uuid4().hex
    await _cleanup_attention_result_fixture(unique)
    provider = MockAttentionTriageProvider([{"attention_class": "requires_my_attention"}])

    try:
        async with AsyncSessionLocal() as session:
            stored_activity = await record_normalized_activity_item(
                session,
                activity_item_id=f"nact_result_{unique}",
                activity=_activity(unique),
            )

            with pytest.raises(AttentionResultValidationError, match="invalid"):
                await triage_normalized_activity_item(
                    session,
                    activity_item_id=stored_activity.activity_item_id,
                    provider=provider,
                )

            count = await session.scalar(
                select(func.count(AttentionTriageResultRecord.id)).where(
                    AttentionTriageResultRecord.activity_item_id
                    == stored_activity.activity_item_id
                )
            )
            assert count == 0
            await session.rollback()

        assert len(provider.calls) == 1

    finally:
        await _cleanup_attention_result_fixture(unique)


@pytest.mark.asyncio
async def test_triage_normalized_activity_item_loads_feedback_as_advisory_context() -> None:
    await _ensure_attention_tables()
    unique = uuid4().hex
    await _cleanup_attention_result_fixture(unique)
    provider = MockAttentionTriageProvider(
        [
            _result(
                attention_class="requires_my_attention",
                priority="high",
                show_in_digest=True,
                owner="me",
            )
        ]
    )

    try:
        async with AsyncSessionLocal() as session:
            stored_activity = await record_normalized_activity_item(
                session,
                activity_item_id=f"nact_result_{unique}",
                activity=_activity(unique),
            )
            await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_result_{unique}_matching",
                source="gmail",
                source_object_id=f"gmail:test:result:{unique}",
                user_action="always_hide_similar",
            )
            await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_result_{unique}_other_source",
                source="drive",
                source_object_id=f"gmail:test:result:{unique}",
                user_action="always_show_similar",
            )

            stored = await triage_normalized_activity_item(
                session,
                activity_item_id=stored_activity.activity_item_id,
                provider=provider,
            )
            await session.commit()

        assert stored.attention_class == "requires_my_attention"
        assert stored.show_in_digest is True
        assert len(provider.calls) == 1
        feedback = provider.calls[0][1].recent_feedback
        assert [item.feedback_id for item in feedback] == [f"atfb_result_{unique}_matching"]
        assert feedback[0].user_action == "always_hide_similar"

    finally:
        await _cleanup_attention_result_fixture(unique)


@pytest.mark.asyncio
async def test_triage_normalized_activity_item_preserves_empty_evidence_without_fabrication() -> None:
    await _ensure_attention_tables()
    unique = uuid4().hex
    await _cleanup_attention_result_fixture(unique)
    provider = MockAttentionTriageProvider([_result(evidence=[])])

    try:
        async with AsyncSessionLocal() as session:
            stored_activity = await record_normalized_activity_item(
                session,
                activity_item_id=f"nact_result_{unique}",
                activity=_activity(unique),
            )
            stored = await triage_normalized_activity_item(
                session,
                activity_item_id=stored_activity.activity_item_id,
                provider=provider,
            )
            await session.commit()

        assert stored.evidence_refs == []

    finally:
        await _cleanup_attention_result_fixture(unique)


@pytest.mark.asyncio
async def test_invalid_attention_result_payload_fails_before_persistence() -> None:
    unique = uuid4().hex

    invalid_payload = {
        "attention_class": "requires_my_attention",
        "priority": "high",
        "show_in_digest": True,
        "confidence": 0.9,
        "reason": "valid-looking reason",
        "recommended_action": "reply",
        "owner": "me",
        "deadline": None,
        "evidence": [{"kind": "gmail_message", "message_id": "fake-message-id"}],
        "provider_payload": {"raw": "must not be persisted"},
    }

    with pytest.raises(AttentionResultValidationError, match="invalid"):
        await record_attention_triage_result(
            _FailingSession(),  # type: ignore[arg-type]
            source="gmail",
            source_object_id=f"gmail:test:result:{unique}",
            result=invalid_payload,
        )


@pytest.mark.asyncio
async def test_invalid_attention_result_payload_does_not_create_db_record() -> None:
    await _ensure_attention_tables()
    unique = uuid4().hex
    await _cleanup_attention_result_fixture(unique)

    invalid_payload = {
        "attention_class": "requires_my_attention",
        "priority": "high",
        "show_in_digest": True,
        "confidence": 0.9,
        "reason": "valid-looking reason",
        "recommended_action": "reply",
        "owner": "me",
        "deadline": None,
        "evidence": [{"kind": "gmail_message", "message_id": "fake-message-id"}],
        "provider_payload": {"raw": "must not be persisted"},
    }

    try:
        async with AsyncSessionLocal() as session:
            with pytest.raises(AttentionResultValidationError, match="invalid"):
                await record_attention_triage_result(
                    session,
                    source="gmail",
                    source_object_id=f"gmail:test:result:{unique}",
                    result=invalid_payload,
                )

            count = await session.scalar(
                select(func.count(AttentionTriageResultRecord.id)).where(
                    AttentionTriageResultRecord.source_object_id
                    == f"gmail:test:result:{unique}"
                )
            )
            assert count == 0
            await session.rollback()

    finally:
        await _cleanup_attention_result_fixture(unique)


@pytest.mark.asyncio
async def test_attention_result_persistence_preserves_empty_evidence_without_fabrication() -> None:
    await _ensure_attention_tables()
    unique = uuid4().hex
    await _cleanup_attention_result_fixture(unique)
    triage_result_id = f"atri_test_{unique}"

    try:
        async with AsyncSessionLocal() as session:
            stored = await record_attention_triage_result(
                session,
                triage_result_id=triage_result_id,
                source="gmail",
                source_object_id=f"gmail:test:result:{unique}",
                result=_result(evidence=[]),
            )
            await session.commit()

        assert stored.evidence_refs == []

        async with AsyncSessionLocal() as session:
            read_back = await get_attention_triage_result(
                session,
                triage_result_id=triage_result_id,
            )

        assert read_back is not None
        assert read_back.evidence_refs == []

    finally:
        await _cleanup_attention_result_fixture(unique)


@pytest.mark.asyncio
async def test_feedback_can_reference_stored_result_and_remains_nullable() -> None:
    await _ensure_attention_tables()
    unique = uuid4().hex
    await _cleanup_attention_result_fixture(unique)
    triage_result_id = f"atri_test_{unique}"

    try:
        async with AsyncSessionLocal() as session:
            stored_activity = await record_normalized_activity_item(
                session,
                activity_item_id=f"nact_result_{unique}",
                activity=_activity(unique),
            )
            stored = await record_attention_triage_result(
                session,
                triage_result_id=triage_result_id,
                source="gmail",
                source_object_id=f"gmail:test:result:{unique}",
                activity_item_id=stored_activity.activity_item_id,
                result=_result(),
            )
            linked_feedback = await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_result_{unique}_linked",
                source="gmail",
                source_object_id=f"gmail:test:result:{unique}",
                triage_result_id=stored.triage_result_id,
                user_action="marked_reply_required",
            )
            nullable_feedback = await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_result_{unique}_nullable",
                source="gmail",
                source_object_id=f"gmail:test:result:{unique}",
                user_action="marked_important",
            )
            await session.commit()

        assert stored.activity_item_id == f"nact_result_{unique}"
        assert linked_feedback.triage_result_id == triage_result_id
        assert nullable_feedback.triage_result_id is None

    finally:
        await _cleanup_attention_result_fixture(unique)
