from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.services.attention_triage import (
    AttentionContext,
    AttentionTriageAgent,
    AttentionTriageResult,
    ConservativeFallbackAttentionTriageProvider,
    MockAttentionTriageProvider,
    NormalizedActivityItem,
    apply_attention_confidence_policy,
    parse_attention_triage_result,
)


NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


def _activity(
    object_id: str,
    *,
    source: str = "gmail",
    object_type: str = "email_thread",
    title: str = "Fake activity",
    direction: str = "from_external",
    text: str = "Fake activity preview.",
    metadata: dict | None = None,
) -> NormalizedActivityItem:
    return NormalizedActivityItem(
        source=source,
        object_type=object_type,
        object_id=object_id,
        title=title,
        created_at=NOW,
        updated_at=NOW,
        last_activity_at=NOW,
        last_actor="fake-actor",
        last_activity_direction=direction,
        participants=["fake-user", "fake-counterparty"],
        sender="fake-sender",
        recipients=["fake-recipient"],
        thread_message_count=2,
        clean_text_preview=text,
        thread_summary=text,
        source_metadata=metadata or {},
        links=["https://example.test/fake"],
    )


def _context() -> AttentionContext:
    return AttentionContext(
        user_name="Fake User",
        company_name="Fake Company",
        user_role="operator",
        important_projects=["Fake Project"],
        known_clients=["Fake Client"],
        known_people=["Fake Person"],
        active_jira_projects=["FAKE"],
        active_github_repos=["fake/repo"],
        recent_drive_topics=["Fake Project"],
    )


def _result(
    *,
    attention_class: str,
    action_type: str,
    priority: str,
    show_in_digest: bool = True,
    confidence: float = 0.90,
    owner: str = "unknown",
    is_work_related: bool = True,
    is_automated: bool = False,
    is_marketing: bool = False,
    is_calendar_related: bool = False,
    reason: str = "fake provider classification",
    short_summary: str = "Fake summary",
    section: str | None = None,
    deadline: str | None = None,
) -> dict:
    if section is None:
        section = {
            "requires_my_attention": "Work actions requiring my attention",
            "waiting_on_external": "Waiting for external reply",
            "important_info": "Important project updates",
            "review_optional": "Review optional",
            "low_priority": "Review optional",
            "hidden_noise": "Hidden low-priority summary",
        }[attention_class]

    return {
        "attention_class": attention_class,
        "action_type": action_type,
        "priority": priority,
        "show_in_digest": show_in_digest,
        "confidence": confidence,
        "owner": owner,
        "is_work_related": is_work_related,
        "is_automated": is_automated,
        "is_marketing": is_marketing,
        "is_security_related": False,
        "is_calendar_related": is_calendar_related,
        "deadline": deadline,
        "reason": reason,
        "short_summary": short_summary,
        "suggested_digest_section": section,
    }


@pytest.mark.parametrize(
    ("activity", "provider_result", "expected_class", "expected_action", "expected_priority"),
    [
        (
            _activity("fake-client-question", text="Fake client asks a direct question."),
            _result(
                attention_class="requires_my_attention",
                action_type="reply_required",
                priority="medium",
                owner="me",
            ),
            "requires_my_attention",
            "reply_required",
            "medium",
        ),
        (
            _activity(
                "fake-partner-deadline",
                text="Fake partner asks for confirmation before a fake deadline.",
            ),
            _result(
                attention_class="requires_my_attention",
                action_type="reply_required",
                priority="high",
                owner="me",
                deadline="2026-05-14",
            ),
            "requires_my_attention",
            "reply_required",
            "high",
        ),
        (
            _activity(
                "fake-badge-ready",
                object_type="event",
                text="Fake badge is ready for a work event.",
            ),
            _result(
                attention_class="requires_my_attention",
                action_type="manual_action_required",
                priority="medium",
                owner="me",
                section="Manual actions",
            ),
            "requires_my_attention",
            "manual_action_required",
            "medium",
        ),
        (
            _activity("fake-event-marketing", object_type="event", text="Fake event promotion."),
            _result(
                attention_class="hidden_noise",
                action_type="no_action_required",
                priority="hidden",
                show_in_digest=False,
                is_work_related=False,
                is_marketing=True,
            ),
            "hidden_noise",
            "no_action_required",
            "hidden",
        ),
        (
            _activity("fake-social-notification", source="other", text="Fake social notification."),
            _result(
                attention_class="hidden_noise",
                action_type="no_action_required",
                priority="hidden",
                show_in_digest=False,
                is_work_related=False,
                is_automated=True,
            ),
            "hidden_noise",
            "no_action_required",
            "hidden",
        ),
        (
            _activity(
                "fake-calendar-update",
                source="calendar",
                object_type="event",
                text="Fake calendar system update.",
                direction="system",
            ),
            _result(
                attention_class="low_priority",
                action_type="no_action_required",
                priority="low",
                is_work_related=False,
                is_automated=True,
                is_calendar_related=True,
            ),
            "low_priority",
            "no_action_required",
            "low",
        ),
        (
            _activity(
                "fake-waiting-external",
                direction="from_me",
                text="Fake last message was from the user.",
            ),
            _result(
                attention_class="waiting_on_external",
                action_type="waiting_external_reply",
                priority="medium",
                owner="external",
            ),
            "waiting_on_external",
            "waiting_external_reply",
            "medium",
        ),
        (
            _activity(
                "fake-pr-review",
                source="github",
                object_type="pull_request",
                text="Fake pull request assigned to the user for review.",
                metadata={"assigned_to_me": True},
            ),
            _result(
                attention_class="requires_my_attention",
                action_type="reply_required",
                priority="medium",
                owner="me",
            ),
            "requires_my_attention",
            "reply_required",
            "medium",
        ),
        (
            _activity(
                "fake-pr-unrelated",
                source="github",
                object_type="pull_request",
                text="Fake pull request update unrelated to the user.",
            ),
            _result(
                attention_class="important_info",
                action_type="review_optional",
                priority="low",
                owner="external",
            ),
            "important_info",
            "review_optional",
            "low",
        ),
        (
            _activity(
                "fake-jira-blocked",
                source="jira",
                object_type="issue",
                text="Fake assigned issue is blocked.",
                metadata={"assigned_to_me": True, "blocked": True},
            ),
            _result(
                attention_class="requires_my_attention",
                action_type="manual_action_required",
                priority="high",
                owner="me",
                section="Manual actions",
            ),
            "requires_my_attention",
            "manual_action_required",
            "high",
        ),
        (
            _activity(
                "fake-jira-update",
                source="jira",
                object_type="issue",
                text="Fake issue updated but not assigned to the user.",
            ),
            _result(
                attention_class="review_optional",
                action_type="review_optional",
                priority="low",
                owner="external",
                is_work_related=True,
            ),
            "review_optional",
            "review_optional",
            "low",
        ),
        (
            _activity(
                "fake-drive-active-project",
                source="google_drive",
                object_type="document",
                text="Fake active project document changed.",
            ),
            _result(
                attention_class="important_info",
                action_type="review_optional",
                priority="medium",
                owner="external",
            ),
            "important_info",
            "review_optional",
            "medium",
        ),
        (
            _activity("fake-ambiguous", text="Fake ambiguous activity."),
            _result(
                attention_class="review_optional",
                action_type="review_optional",
                priority="low",
                is_work_related=False,
            ),
            "review_optional",
            "review_optional",
            "low",
        ),
    ],
)
def test_mock_provider_contract_scenarios(
    activity: NormalizedActivityItem,
    provider_result: dict,
    expected_class: str,
    expected_action: str,
    expected_priority: str,
) -> None:
    agent = AttentionTriageAgent(MockAttentionTriageProvider([provider_result]))

    result = agent.classify_activity(activity, _context())

    assert result.attention_class == expected_class
    assert result.action_type == expected_action
    assert result.priority == expected_priority
    if expected_class == "hidden_noise":
        assert result.show_in_digest is False
    else:
        assert result.show_in_digest is True


def test_medium_confidence_hidden_result_moves_to_review_optional() -> None:
    result = AttentionTriageResult.model_validate(
        _result(
            attention_class="hidden_noise",
            action_type="no_action_required",
            priority="hidden",
            show_in_digest=False,
            confidence=0.70,
            is_work_related=False,
        )
    )

    adjusted = apply_attention_confidence_policy(result)

    assert adjusted.attention_class == "review_optional"
    assert adjusted.action_type == "review_optional"
    assert adjusted.show_in_digest is True
    assert adjusted.priority == "low"


def test_low_confidence_work_related_result_stays_visible_with_medium_priority() -> None:
    result = AttentionTriageResult.model_validate(
        _result(
            attention_class="hidden_noise",
            action_type="reply_required",
            priority="hidden",
            show_in_digest=False,
            confidence=0.30,
            owner="me",
            is_work_related=True,
        )
    )

    adjusted = apply_attention_confidence_policy(result)

    assert adjusted.attention_class == "review_optional"
    assert adjusted.action_type == "review_optional"
    assert adjusted.show_in_digest is True
    assert adjusted.priority == "medium"


def test_invalid_provider_output_uses_fallback_and_is_not_hidden() -> None:
    agent = AttentionTriageAgent(MockAttentionTriageProvider([{"attention_class": "hidden_noise"}]))

    result = agent.classify_activity(_activity("fake-invalid-provider-output"), _context())

    assert result.attention_class == "review_optional"
    assert result.show_in_digest is True
    assert result.priority != "hidden"


def test_conservative_fallback_waits_on_external_when_last_activity_is_from_me() -> None:
    provider = ConservativeFallbackAttentionTriageProvider()

    result = provider.classify_activity(
        _activity("fake-fallback-waiting", direction="from_me"),
        _context(),
    )

    assert result.attention_class == "waiting_on_external"
    assert result.action_type == "waiting_external_reply"
    assert result.show_in_digest is True


def test_strict_result_schema_rejects_unknown_values_and_extra_fields() -> None:
    payload = _result(
        attention_class="review_optional",
        action_type="review_optional",
        priority="low",
    )
    payload["unexpected"] = "not allowed"
    payload["priority"] = "urgent"

    with pytest.raises(ValidationError):
        parse_attention_triage_result(payload)
