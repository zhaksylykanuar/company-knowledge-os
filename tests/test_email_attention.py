from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.attention_models import AttentionTriageFeedbackRecord
from app.db.base import AsyncSessionLocal, engine
from app.db.gmail_models import EmailThreadState
from app.services.attention_feedback import record_attention_triage_feedback
from app.services.attention_triage import (
    AttentionContext,
    AttentionTriageFeedback,
    AttentionTriageAgent,
    MockAttentionTriageProvider,
)
from app.services.digest_rendering import render_source_activity_digest_text
from app.services.email_attention import (
    classify_email_thread_attention,
    classify_email_thread_state_items,
    classify_email_thread_states,
    email_thread_state_to_attention_result_for_digest,
    email_thread_state_to_activity_item,
)


NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


def _settings(**overrides: object) -> SimpleNamespace:
    defaults = {
        "attention_triage_enabled": False,
        "attention_triage_min_confidence_to_hide": 0.80,
        "attention_triage_review_threshold": 0.55,
        "attention_triage_max_text_chars": 6000,
        "email_me_addresses": "fake-user@example.test",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _thread_state(**overrides: object) -> SimpleNamespace:
    defaults = {
        "source": "gmail",
        "thread_key": "gmail:thread:fake",
        "provider_thread_id": "provider-thread-id-should-not-print",
        "subject_normalized": "private subject normalized",
        "subject_display": "PRIVATE_SUBJECT_DO_NOT_PRINT",
        "participants_json": [
            {"participant_key": "fake-me", "is_me": True},
            {"participant_key": "fake-external", "is_me": False},
        ],
        "first_message_at": NOW,
        "last_message_at": NOW,
        "last_message_from": "private-sender@example.test",
        "last_message_direction": "from_external",
        "last_message_summary": "PRIVATE_SNIPPET_DO_NOT_PRINT",
        "thread_summary": "PRIVATE_THREAD_SUMMARY_DO_NOT_PRINT",
        "status": "needs_my_reply",
        "days_without_reply": 2,
        "messages_count": 3,
        "triage_category": "work_action",
        "triage_action_type": "reply_required",
        "triage_priority": "high",
        "show_in_digest": True,
        "triage_reason": "external_work_request",
        "triage_confidence": 0.78,
        "evidence_refs": [
            {
                "kind": "gmail_message",
                "message_id": "private-message-id",
                "raw_object_ref": "raw://private-ref",
            }
        ],
        "metadata_json": {
            "last_message_from_display": "external sender",
            "last_message_to_display": ["me"],
            "participants_display": "me, 1 external participant",
        },
        "created_at": NOW,
        "updated_at": NOW,
        "computed_at": NOW,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _result(
    *,
    attention_class: str,
    priority: str,
    show_in_digest: bool = True,
    confidence: float = 0.90,
    owner: str | None = "unknown",
    recommended_action: str | None = None,
) -> dict:
    if recommended_action is None:
        recommended_action = {
            "requires_my_attention": "reply to the relevant work request",
            "manual_action": "complete the manual action",
            "waiting_on_external": "wait for an external reply",
            "important_info": "review the project update",
            "review_optional": "review if relevant",
            "no_action_required": "no action required",
        }[attention_class]
    return {
        "attention_class": attention_class,
        "priority": priority,
        "show_in_digest": show_in_digest,
        "confidence": confidence,
        "owner": owner,
        "deadline": None,
        "reason": "fake semantic triage",
        "recommended_action": recommended_action,
        "evidence": [{"kind": "gmail_message", "message_id": "fake-message-id"}],
    }


def _digest_fixture() -> dict:
    return {
        "digest_type": "source_activity",
        "window": {
            "start_at": NOW.isoformat(),
            "end_at": NOW.isoformat(),
        },
        "counts": {"total": 0},
        "entries": [],
        "metadata": {
            "generated_at": NOW.isoformat(),
            "entry_limit": 20,
            "entry_count": 0,
        },
        "email_thread_intelligence": {
            "section_title": "Email threads requiring attention",
            "groups": {
                "work_actions": [
                    {
                        "subject": "Fake digest subject",
                        "action_type": "reply_required",
                        "priority": "high",
                        "summary": "Fake digest summary.",
                        "days_without_reply": 1,
                        "evidence": "1 thread",
                    }
                ],
                "manual_actions": [],
                "waiting_external_reply": [],
                "work_info": [],
                "review_optional": [],
            },
            "hidden_low_priority_summary": {"counts": {}},
            "data_quality_notes": [],
        },
    }


async def _ensure_email_feedback_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(EmailThreadState.__table__.create, checkfirst=True)
        await conn.run_sync(AttentionTriageFeedbackRecord.__table__.create, checkfirst=True)


async def _cleanup_email_feedback_fixture(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageFeedbackRecord).where(
                AttentionTriageFeedbackRecord.feedback_id.like(
                    f"atfb_email_context_{unique}%"
                )
            )
        )
        await session.execute(
            delete(AttentionTriageFeedbackRecord).where(
                AttentionTriageFeedbackRecord.source_object_id.like(
                    f"gmail:test:feedback:{unique}%"
                )
            )
        )
        await session.execute(
            delete(EmailThreadState).where(
                EmailThreadState.thread_key.like(f"gmail:test:feedback:{unique}%")
            )
        )
        await session.commit()


def test_email_thread_state_maps_to_normalized_activity_item() -> None:
    activity = email_thread_state_to_activity_item(_thread_state())

    assert activity.source == "gmail"
    assert activity.source_object_id == "gmail:thread:fake"
    assert activity.activity_type == "email_thread.reply_required.from_external"
    assert activity.actor == "external sender"
    assert activity.related_people == ["fake-me", "fake-external"]
    assert activity.safe_summary == "PRIVATE_THREAD_SUMMARY_DO_NOT_PRINT"


def test_mapping_carries_top_level_evidence_refs() -> None:
    activity = email_thread_state_to_activity_item(_thread_state())

    assert activity.evidence_refs == [
        {
            "kind": "gmail_message",
            "message_id": "private-message-id",
            "raw_object_ref": "raw://private-ref",
        }
    ]


def test_digest_projection_maps_deterministic_fields_to_attention_result() -> None:
    result = email_thread_state_to_attention_result_for_digest(_thread_state())

    assert result.attention_class == "requires_my_attention"
    assert result.priority == "high"
    assert result.show_in_digest is True
    assert result.recommended_action == "reply to the email thread"
    assert result.owner == "me"
    assert result.evidence == [
        {
            "kind": "gmail_message",
            "message_id": "private-message-id",
            "raw_object_ref": "raw://private-ref",
        }
    ]


def test_digest_projection_maps_work_info_to_important_info() -> None:
    result = email_thread_state_to_attention_result_for_digest(
        _thread_state(
            status="informational",
            triage_category="work_info",
            triage_action_type="no_action_required",
            triage_priority="low",
            show_in_digest=True,
            triage_confidence=0.85,
        )
    )

    assert result.attention_class == "important_info"
    assert result.show_in_digest is True
    assert result.recommended_action == "review the project update"


def test_digest_projection_medium_confidence_hidden_moves_to_review_optional() -> None:
    result = email_thread_state_to_attention_result_for_digest(
        _thread_state(
            status="hidden",
            triage_category="marketing",
            triage_action_type="review_optional",
            triage_priority="hidden",
            show_in_digest=False,
            triage_confidence=0.70,
        )
    )

    assert result.attention_class == "review_optional"
    assert result.priority == "low"
    assert result.show_in_digest is True


def test_digest_projection_low_confidence_work_item_stays_visible() -> None:
    result = email_thread_state_to_attention_result_for_digest(
        _thread_state(
            status="hidden",
            triage_category="work_action",
            triage_action_type="reply_required",
            triage_priority="high",
            show_in_digest=False,
            triage_confidence=0.30,
        )
    )

    assert result.attention_class == "review_optional"
    assert result.priority == "medium"
    assert result.show_in_digest is True


def test_digest_projection_does_not_use_attention_agent_provider_path(
    monkeypatch,
) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("digest projection must not invoke provider classification")

    monkeypatch.setattr(AttentionTriageAgent, "classify_activity", fail_if_called)

    result = email_thread_state_to_attention_result_for_digest(_thread_state())

    assert result.attention_class == "requires_my_attention"


def test_batch_safe_output_does_not_include_private_values() -> None:
    result = classify_email_thread_state_items([_thread_state()], settings=_settings())

    rendered = json.dumps(result.to_safe_dict(), sort_keys=True)

    assert result.private_content_printed is False
    assert "PRIVATE_SUBJECT_DO_NOT_PRINT" not in rendered
    assert "PRIVATE_SNIPPET_DO_NOT_PRINT" not in rendered
    assert "private-message-id" not in rendered
    assert "private-sender@example.test" not in rendered


def test_default_classification_uses_fallback_when_attention_disabled() -> None:
    result = classify_email_thread_attention(_thread_state(), settings=_settings())

    assert result.attention_class == "review_optional"
    assert result.recommended_action == "review if relevant"
    assert result.show_in_digest is True


def test_injected_mock_provider_is_used_when_supplied() -> None:
    provider = MockAttentionTriageProvider(
        [
            _result(
                attention_class="requires_my_attention",
                priority="high",
                owner="me",
            )
        ]
    )

    result = classify_email_thread_attention(
        _thread_state(),
        provider=provider,
        context=AttentionContext(),
        settings=_settings(),
    )

    assert result.attention_class == "requires_my_attention"
    assert result.recommended_action == "reply to the relevant work request"
    assert result.priority == "high"
    assert len(provider.calls) == 1


def test_low_confidence_mock_result_cannot_silently_hide_item() -> None:
    provider = MockAttentionTriageProvider(
        [
            _result(
                attention_class="no_action_required",
                priority="low",
                show_in_digest=False,
                confidence=0.30,
                owner=None,
            )
        ]
    )

    result = classify_email_thread_attention(
        _thread_state(),
        provider=provider,
        settings=_settings(),
    )

    assert result.attention_class == "review_optional"
    assert result.priority == "low"
    assert result.show_in_digest is True


def test_high_confidence_no_action_mock_result_can_hide() -> None:
    provider = MockAttentionTriageProvider(
        [
            _result(
                attention_class="no_action_required",
                priority="low",
                show_in_digest=False,
                confidence=0.95,
                owner=None,
            )
        ]
    )

    result = classify_email_thread_attention(
        _thread_state(),
        provider=provider,
        settings=_settings(),
    )

    assert result.attention_class == "no_action_required"
    assert result.priority == "low"
    assert result.show_in_digest is False


def test_feedback_context_is_advisory_and_does_not_force_provider_result() -> None:
    provider = MockAttentionTriageProvider(
        [
            _result(
                attention_class="no_action_required",
                priority="low",
                show_in_digest=False,
                confidence=0.95,
                owner=None,
            )
        ]
    )
    context = AttentionContext(
        recent_feedback=[
            AttentionTriageFeedback(
                feedback_id="atfb_test_email_advisory_show",
                source_object_id="gmail:thread:fake",
                triage_result_id=None,
                user_action="always_show_similar",
                created_at=NOW,
            )
        ]
    )

    result = classify_email_thread_attention(
        _thread_state(),
        provider=provider,
        context=context,
        settings=_settings(),
    )

    assert result.attention_class == "no_action_required"
    assert result.show_in_digest is False
    assert provider.calls[0][1].recent_feedback[0].user_action == "always_show_similar"


def test_low_confidence_policy_still_wins_when_feedback_exists() -> None:
    provider = MockAttentionTriageProvider(
        [
            _result(
                attention_class="no_action_required",
                priority="low",
                show_in_digest=False,
                confidence=0.30,
                owner=None,
            )
        ]
    )
    context = AttentionContext(
        recent_feedback=[
            AttentionTriageFeedback(
                feedback_id="atfb_test_email_advisory_hide",
                source_object_id="gmail:thread:fake",
                triage_result_id=None,
                user_action="always_hide_similar",
                created_at=NOW,
            )
        ]
    )

    result = classify_email_thread_attention(
        _thread_state(),
        provider=provider,
        context=context,
        settings=_settings(),
    )

    assert result.attention_class == "review_optional"
    assert result.show_in_digest is True
    assert provider.calls[0][1].recent_feedback[0].user_action == "always_hide_similar"


def test_fallback_handles_missing_summaries_and_participants_safely() -> None:
    result = classify_email_thread_attention(
        _thread_state(
            subject_display=None,
            subject_normalized=None,
            participants_json=None,
            last_message_summary=None,
            thread_summary=None,
            messages_count=None,
        ),
        settings=_settings(),
    )

    assert result.attention_class == "review_optional"
    assert result.show_in_digest is True


def test_batch_classification_returns_aggregate_counts_only() -> None:
    provider = MockAttentionTriageProvider(
        [
            _result(
                attention_class="requires_my_attention",
                priority="high",
                owner="me",
            ),
            _result(
                attention_class="no_action_required",
                priority="low",
                show_in_digest=False,
                confidence=0.95,
                owner=None,
            ),
        ]
    )

    result = classify_email_thread_state_items(
        [_thread_state(thread_key="fake-1"), _thread_state(thread_key="fake-2")],
        provider=provider,
        settings=_settings(),
    )

    assert result.threads_considered == 2
    assert result.attention_class_counts == {
        "no_action_required": 1,
        "requires_my_attention": 1,
    }
    assert result.action_type_counts == {
        "no action required": 1,
        "reply to the relevant work request": 1,
    }
    assert result.priority_counts == {"low": 1, "high": 1}
    assert result.show_in_digest_counts == {"false": 1, "true": 1}


@pytest.mark.asyncio
async def test_stored_email_triage_loads_feedback_into_context_and_preserves_base_context() -> None:
    await _ensure_email_feedback_tables()
    unique = uuid4().hex
    await _cleanup_email_feedback_fixture(unique)
    thread_key = f"gmail:test:feedback:{unique}"
    created_at = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)

    try:
        async with AsyncSessionLocal() as session:
            session.add(
                EmailThreadState(
                    source="gmail",
                    thread_key=thread_key,
                    provider_thread_id=None,
                    subject_normalized="feedback context thread",
                    subject_display="Feedback context thread",
                    participants_json=[
                        {"participant_key": "fake-me", "is_me": True},
                        {"participant_key": "fake-external", "is_me": False},
                    ],
                    first_message_at=datetime(2126, 1, 1, tzinfo=timezone.utc),
                    last_message_at=datetime(2126, 1, 1, tzinfo=timezone.utc),
                    last_message_from="fake-external",
                    last_message_direction="from_external",
                    last_message_summary="Fake latest message.",
                    thread_summary="Fake thread summary.",
                    status="needs_my_reply",
                    days_without_reply=1,
                    messages_count=2,
                    triage_category="work_action",
                    triage_action_type="reply_required",
                    triage_priority="high",
                    show_in_digest=True,
                    triage_reason="fake_triage_rule",
                    triage_confidence=0.9,
                    evidence_refs=[{"kind": "gmail_message", "message_id": "fake"}],
                    metadata_json={"last_message_from_display": "fake external"},
                    computed_at=created_at,
                )
            )
            await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_email_context_{unique}_gmail_old",
                source="gmail",
                source_object_id=thread_key,
                user_action="marked_reply_required",
                created_at=created_at,
            )
            await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_email_context_{unique}_gmail_new",
                source="gmail",
                source_object_id=thread_key,
                user_action="always_show_similar",
                created_at=created_at.replace(hour=11),
            )
            await record_attention_triage_feedback(
                session,
                feedback_id=f"atfb_email_context_{unique}_drive",
                source="drive",
                source_object_id=thread_key,
                user_action="always_hide_similar",
                created_at=created_at.replace(hour=12),
            )
            await session.commit()

        provider = MockAttentionTriageProvider(
            [
                _result(
                    attention_class="requires_my_attention",
                    priority="high",
                    owner="me",
                )
            ]
        )
        base_context = AttentionContext(
            user_name="Fake User",
            important_projects=["Fake Project"],
            recent_feedback=[
                AttentionTriageFeedback(
                    feedback_id="atfb_stale_context",
                    source_object_id="stale-object",
                    triage_result_id=None,
                    user_action="marked_noise",
                    created_at=created_at,
                )
            ],
        )

        async with AsyncSessionLocal() as session:
            batch = await classify_email_thread_states(
                session,
                provider=provider,
                context=base_context,
                settings=_settings(),
                limit=1,
            )

        assert batch.threads_considered == 1
        assert batch.attention_class_counts == {"requires_my_attention": 1}
        assert len(provider.calls) == 1
        activity, item_context = provider.calls[0]
        assert activity.source == "gmail"
        assert activity.source_object_id == thread_key
        assert item_context.user_name == "Fake User"
        assert item_context.important_projects == ["Fake Project"]
        assert [feedback.feedback_id for feedback in item_context.recent_feedback] == [
            f"atfb_email_context_{unique}_gmail_new",
            f"atfb_email_context_{unique}_gmail_old",
        ]
        assert base_context.recent_feedback[0].feedback_id == "atfb_stale_context"

        async with AsyncSessionLocal() as session:
            stored_thread = await session.scalar(
                select(EmailThreadState).where(EmailThreadState.thread_key == thread_key)
            )
        assert stored_thread is not None
        assert stored_thread.triage_action_type == "reply_required"
        assert stored_thread.show_in_digest is True

    finally:
        await _cleanup_email_feedback_fixture(unique)


def test_existing_deterministic_email_thread_fields_are_not_mutated() -> None:
    thread_state = _thread_state()
    before = dict(vars(thread_state))

    classify_email_thread_attention(
        thread_state,
        provider=MockAttentionTriageProvider(
            [
                _result(
                    attention_class="requires_my_attention",
                    priority="high",
                )
            ]
        ),
        settings=_settings(),
    )

    assert vars(thread_state) == before


def test_existing_digest_rendering_behavior_does_not_change() -> None:
    rendered = render_source_activity_digest_text(_digest_fixture())

    assert "Email threads requiring attention" in rendered
    assert "Work actions requiring my attention:" in rendered
    assert "Action: Reply required" in rendered
