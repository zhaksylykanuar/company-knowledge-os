from datetime import datetime, timedelta, timezone
from typing import get_args
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.attention_models import AttentionTriageFeedbackRecord
from app.db.base import AsyncSessionLocal, engine
from app.services.attention_feedback import (
    MAX_ATTENTION_FEEDBACK_LIMIT,
    AttentionFeedbackValidationError,
    get_recent_attention_triage_feedback,
    record_attention_triage_feedback,
)
from app.services.attention_triage import AttentionContext, AttentionTriageFeedback, FeedbackAction


async def _ensure_attention_feedback_table() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(AttentionTriageFeedbackRecord.__table__.create, checkfirst=True)


async def _cleanup_attention_feedback(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageFeedbackRecord).where(
                AttentionTriageFeedbackRecord.source_object_id.like(f"feedback-object-{unique}%")
            )
        )
        await session.execute(
            delete(AttentionTriageFeedbackRecord).where(
                AttentionTriageFeedbackRecord.feedback_id.like(f"atfb_test_{unique}%")
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_record_attention_triage_feedback_returns_public_dto() -> None:
    await _ensure_attention_feedback_table()
    unique = uuid4().hex
    await _cleanup_attention_feedback(unique)
    created_at = datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc)

    try:
        async with AsyncSessionLocal() as session:
            feedback = await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_test_{unique}",
                source="gmail",
                source_object_id=f"feedback-object-{unique}",
                triage_result_id=f"atri_{unique}",
                user_action="marked_reply_required",
                created_at=created_at,
            )
            await session.commit()

        assert isinstance(feedback, AttentionTriageFeedback)
        assert feedback.feedback_id == f"atfb_test_{unique}"
        assert feedback.source_object_id == f"feedback-object-{unique}"
        assert feedback.triage_result_id == f"atri_{unique}"
        assert feedback.user_action == "marked_reply_required"
        assert feedback.created_at == created_at

        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(func.count(AttentionTriageFeedbackRecord.id)).where(
                    AttentionTriageFeedbackRecord.feedback_id == f"atfb_test_{unique}"
                )
            )
            assert count == 1

    finally:
        await _cleanup_attention_feedback(unique)


@pytest.mark.asyncio
async def test_record_attention_triage_feedback_allows_nullable_triage_result_id() -> None:
    await _ensure_attention_feedback_table()
    unique = uuid4().hex
    await _cleanup_attention_feedback(unique)

    try:
        async with AsyncSessionLocal() as session:
            feedback = await record_attention_triage_feedback(
                session,
                source_object_id=f"feedback-object-{unique}",
                user_action="marked_important",
            )
            await session.commit()

        assert feedback.feedback_id.startswith("atfb_")
        assert feedback.triage_result_id is None

    finally:
        await _cleanup_attention_feedback(unique)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"source_object_id": "", "user_action": "marked_important"}, "source_object_id"),
        (
            {
                "source_object_id": "feedback-object-validation",
                "source": " ",
                "user_action": "marked_important",
            },
            "source",
        ),
        (
            {
                "source_object_id": "feedback-object-validation",
                "triage_result_id": "",
                "user_action": "marked_important",
            },
            "triage_result_id",
        ),
        (
            {
                "source_object_id": "feedback-object-validation",
                "user_action": "unsupported",
            },
            "user_action",
        ),
    ],
)
async def test_record_attention_triage_feedback_rejects_invalid_inputs(
    kwargs: dict[str, object],
    message: str,
) -> None:
    await _ensure_attention_feedback_table()

    async with AsyncSessionLocal() as session:
        with pytest.raises(AttentionFeedbackValidationError, match=message):
            await record_attention_triage_feedback(session, **kwargs)
        await session.rollback()


@pytest.mark.asyncio
async def test_recent_feedback_filters_by_source_object_source_action_and_orders_newest_first() -> None:
    await _ensure_attention_feedback_table()
    unique = uuid4().hex
    await _cleanup_attention_feedback(unique)
    base_time = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)

    try:
        async with AsyncSessionLocal() as session:
            await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_test_{unique}_old_gmail",
                source="gmail",
                source_object_id=f"feedback-object-{unique}",
                user_action="marked_important",
                created_at=base_time,
            )
            await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_test_{unique}_new_gmail",
                source="gmail",
                source_object_id=f"feedback-object-{unique}",
                user_action="marked_noise",
                created_at=base_time + timedelta(minutes=1),
            )
            await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_test_{unique}_drive",
                source="drive",
                source_object_id=f"feedback-object-{unique}",
                user_action="marked_no_action",
                created_at=base_time + timedelta(minutes=2),
            )
            await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_test_{unique}_other",
                source="gmail",
                source_object_id=f"feedback-object-{unique}-other",
                user_action="marked_reply_required",
                created_at=base_time + timedelta(minutes=3),
            )
            await session.commit()

        async with AsyncSessionLocal() as session:
            all_matching = await get_recent_attention_triage_feedback(
                session,
                source_object_id=f"feedback-object-{unique}",
            )
            gmail_matching = await get_recent_attention_triage_feedback(
                session,
                source="gmail",
                source_object_id=f"feedback-object-{unique}",
            )
            noise_matching = await get_recent_attention_triage_feedback(
                session,
                source_object_id=f"feedback-object-{unique}",
                user_action="marked_noise",
            )

        assert [item.feedback_id for item in all_matching] == [
            f"atfb_test_{unique}_drive",
            f"atfb_test_{unique}_new_gmail",
            f"atfb_test_{unique}_old_gmail",
        ]
        assert [item.feedback_id for item in gmail_matching] == [
            f"atfb_test_{unique}_new_gmail",
            f"atfb_test_{unique}_old_gmail",
        ]
        assert [item.feedback_id for item in noise_matching] == [
            f"atfb_test_{unique}_new_gmail"
        ]

    finally:
        await _cleanup_attention_feedback(unique)


@pytest.mark.asyncio
async def test_recent_feedback_limit_is_honored_and_bounded() -> None:
    await _ensure_attention_feedback_table()
    unique = uuid4().hex
    await _cleanup_attention_feedback(unique)
    base_time = datetime(2026, 5, 15, 13, 0, tzinfo=timezone.utc)

    try:
        async with AsyncSessionLocal() as session:
            for index in range(MAX_ATTENTION_FEEDBACK_LIMIT + 5):
                await record_attention_triage_feedback(
                    session,
                    feedback_id=f"atfb_test_{unique}_{index}",
                    source_object_id=f"feedback-object-{unique}",
                    user_action="marked_important",
                    created_at=base_time + timedelta(minutes=index),
                )
            await session.commit()

        async with AsyncSessionLocal() as session:
            limited = await get_recent_attention_triage_feedback(
                session,
                source_object_id=f"feedback-object-{unique}",
                limit=2,
            )
            bounded = await get_recent_attention_triage_feedback(
                session,
                source_object_id=f"feedback-object-{unique}",
                limit=MAX_ATTENTION_FEEDBACK_LIMIT + 50,
            )

        assert [item.feedback_id for item in limited] == [
            f"atfb_test_{unique}_{MAX_ATTENTION_FEEDBACK_LIMIT + 4}",
            f"atfb_test_{unique}_{MAX_ATTENTION_FEEDBACK_LIMIT + 3}",
        ]
        assert len(bounded) == MAX_ATTENTION_FEEDBACK_LIMIT

    finally:
        await _cleanup_attention_feedback(unique)


@pytest.mark.asyncio
async def test_all_feedback_actions_can_be_stored_without_triage_result_persistence() -> None:
    await _ensure_attention_feedback_table()
    unique = uuid4().hex
    await _cleanup_attention_feedback(unique)
    actions = list(get_args(FeedbackAction))

    try:
        async with AsyncSessionLocal() as session:
            for index, action in enumerate(actions):
                feedback = await record_attention_triage_feedback(
                    session,
                    feedback_id=f"atfb_test_{unique}_{action}",
                    source_object_id=f"feedback-object-{unique}-{index}",
                    user_action=action,
                )
                assert feedback.user_action == action
                assert feedback.triage_result_id is None
            await session.commit()

        async with AsyncSessionLocal() as session:
            rows = list(
                (
                    await session.scalars(
                        select(AttentionTriageFeedbackRecord).where(
                            AttentionTriageFeedbackRecord.feedback_id.like(
                                f"atfb_test_{unique}%"
                            )
                        )
                    )
                ).all()
            )

        assert {row.user_action for row in rows} == set(actions)

    finally:
        await _cleanup_attention_feedback(unique)


@pytest.mark.asyncio
async def test_recent_feedback_output_is_ready_for_attention_context() -> None:
    await _ensure_attention_feedback_table()
    unique = uuid4().hex
    await _cleanup_attention_feedback(unique)

    try:
        async with AsyncSessionLocal() as session:
            await record_attention_triage_feedback(
                session,
                source_object_id=f"feedback-object-{unique}",
                user_action="always_show_similar",
            )
            await session.commit()

        async with AsyncSessionLocal() as session:
            recent_feedback = await get_recent_attention_triage_feedback(
                session,
                source_object_id=f"feedback-object-{unique}",
            )

        context = AttentionContext(recent_feedback=recent_feedback)

        assert context.recent_feedback[0].source_object_id == f"feedback-object-{unique}"
        assert context.recent_feedback[0].user_action == "always_show_similar"

    finally:
        await _cleanup_attention_feedback(unique)
