from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.attention_triage import (
    AttentionContext,
    AttentionTriageAgent,
    AttentionTriageResult,
    ConservativeFallbackAttentionTriageProvider,
    MockAttentionTriageProvider,
    NormalizedActivityItem,
    OpenAIAttentionTriageProvider,
    apply_attention_confidence_policy,
    build_attention_triage_provider,
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


class _FakeOpenAICompatibleClient:
    def __init__(self, responses: list[object] | None = None, *, raises: bool = False) -> None:
        self.responses = list(responses or [])
        self.raises = raises
        self.calls: list[dict] = []

    def __call__(self, payload: dict) -> object:
        self.calls.append(payload)
        if self.raises:
            raise RuntimeError("fake provider failure")
        if not self.responses:
            raise RuntimeError("fake provider response missing")
        return self.responses.pop(0)


def _fake_settings(**overrides: object) -> SimpleNamespace:
    defaults = {
        "attention_triage_enabled": True,
        "attention_triage_provider": "openai",
        "attention_triage_model": "fake-model",
        "attention_triage_min_confidence_to_hide": 0.80,
        "attention_triage_review_threshold": 0.55,
        "attention_triage_max_text_chars": 6000,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_openai_provider_disabled_returns_fallback_without_client_call() -> None:
    fake_client = _FakeOpenAICompatibleClient(
        [
            json.dumps(
                _result(
                    attention_class="requires_my_attention",
                    action_type="reply_required",
                    priority="high",
                    owner="me",
                )
            )
        ]
    )
    provider = OpenAIAttentionTriageProvider(client=fake_client, enabled=False)

    result = provider.classify_activity(_activity("fake-openai-disabled"), _context())

    assert result.attention_class == "review_optional"
    assert result.show_in_digest is True
    assert fake_client.calls == []


def test_openai_provider_enabled_with_fake_valid_json_returns_result() -> None:
    fake_client = _FakeOpenAICompatibleClient(
        [
            json.dumps(
                _result(
                    attention_class="requires_my_attention",
                    action_type="reply_required",
                    priority="high",
                    owner="me",
                )
            )
        ]
    )
    provider = OpenAIAttentionTriageProvider(
        client=fake_client,
        enabled=True,
        model="fake-model",
    )

    result = provider.classify_activity(_activity("fake-openai-valid"), _context())

    assert result.attention_class == "requires_my_attention"
    assert result.action_type == "reply_required"
    assert result.priority == "high"
    assert result.show_in_digest is True
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["text"]["format"]["strict"] is True


def test_openai_provider_low_confidence_result_is_forced_visible() -> None:
    fake_client = _FakeOpenAICompatibleClient(
        [
            json.dumps(
                _result(
                    attention_class="hidden_noise",
                    action_type="no_action_required",
                    priority="hidden",
                    show_in_digest=False,
                    confidence=0.30,
                    is_work_related=False,
                )
            )
        ]
    )
    provider = OpenAIAttentionTriageProvider(client=fake_client, enabled=True)

    result = provider.classify_activity(_activity("fake-openai-low-confidence"), _context())

    assert result.attention_class == "review_optional"
    assert result.action_type == "review_optional"
    assert result.show_in_digest is True
    assert result.priority == "low"


def test_openai_provider_invalid_json_retries_once_then_falls_back() -> None:
    fake_client = _FakeOpenAICompatibleClient(["not json", "still not json"])
    provider = OpenAIAttentionTriageProvider(client=fake_client, enabled=True)

    result = provider.classify_activity(_activity("fake-openai-invalid-json"), _context())

    assert result.attention_class == "review_optional"
    assert result.show_in_digest is True
    assert len(fake_client.calls) == 2


def test_openai_provider_invalid_enum_falls_back() -> None:
    payload = _result(
        attention_class="requires_my_attention",
        action_type="reply_required",
        priority="high",
    )
    payload["attention_class"] = "urgent"
    fake_client = _FakeOpenAICompatibleClient([json.dumps(payload), json.dumps(payload)])
    provider = OpenAIAttentionTriageProvider(client=fake_client, enabled=True)

    result = provider.classify_activity(_activity("fake-openai-invalid-enum"), _context())

    assert result.attention_class == "review_optional"
    assert result.show_in_digest is True
    assert len(fake_client.calls) == 2


def test_openai_provider_extra_field_falls_back() -> None:
    payload = _result(
        attention_class="requires_my_attention",
        action_type="reply_required",
        priority="high",
    )
    payload["unexpected"] = "not allowed"
    fake_client = _FakeOpenAICompatibleClient([json.dumps(payload), json.dumps(payload)])
    provider = OpenAIAttentionTriageProvider(client=fake_client, enabled=True)

    result = provider.classify_activity(_activity("fake-openai-extra-field"), _context())

    assert result.attention_class == "review_optional"
    assert result.show_in_digest is True


def test_openai_provider_exception_falls_back() -> None:
    fake_client = _FakeOpenAICompatibleClient(raises=True)
    provider = OpenAIAttentionTriageProvider(client=fake_client, enabled=True)

    result = provider.classify_activity(_activity("fake-openai-exception"), _context())

    assert result.attention_class == "review_optional"
    assert result.show_in_digest is True


def test_openai_provider_truncates_text_before_client_receives_payload() -> None:
    long_text = "x" * 80
    fake_client = _FakeOpenAICompatibleClient(
        [
            json.dumps(
                _result(
                    attention_class="important_info",
                    action_type="review_optional",
                    priority="low",
                )
            )
        ]
    )
    provider = OpenAIAttentionTriageProvider(
        client=fake_client,
        enabled=True,
        max_text_chars=12,
    )

    provider.classify_activity(
        _activity("fake-openai-truncated", text=long_text),
        _context(),
    )

    user_payload = fake_client.calls[0]["input"][1]["content"]
    assert long_text not in user_payload
    assert '"clean_text_preview":"xxxxxxxxxxxx"' in user_payload
    assert '"thread_summary":"xxxxxxxxxxxx"' in user_payload


def test_openai_provider_does_not_require_live_client_when_disabled() -> None:
    provider = OpenAIAttentionTriageProvider(enabled=False)

    result = provider.classify_activity(_activity("fake-openai-no-live-client"), _context())

    assert result.attention_class == "review_optional"
    assert result.show_in_digest is True


def test_attention_provider_factory_returns_fallback_for_unknown_provider() -> None:
    provider = build_attention_triage_provider(
        _fake_settings(attention_triage_provider="unknown"),
        client=_FakeOpenAICompatibleClient(),
    )

    assert isinstance(provider, ConservativeFallbackAttentionTriageProvider)


def test_attention_provider_factory_returns_fallback_when_enabled_without_client() -> None:
    provider = build_attention_triage_provider(_fake_settings(), client=None)

    assert isinstance(provider, ConservativeFallbackAttentionTriageProvider)


def test_attention_provider_factory_returns_openai_provider_with_fake_client() -> None:
    provider = build_attention_triage_provider(
        _fake_settings(),
        client=_FakeOpenAICompatibleClient(),
    )

    assert isinstance(provider, OpenAIAttentionTriageProvider)


def test_openai_provider_high_confidence_requires_attention_is_trusted() -> None:
    fake_client = _FakeOpenAICompatibleClient(
        [
            json.dumps(
                _result(
                    attention_class="requires_my_attention",
                    action_type="manual_action_required",
                    priority="high",
                    confidence=0.95,
                    owner="me",
                    section="Manual actions",
                )
            )
        ]
    )
    provider = OpenAIAttentionTriageProvider(client=fake_client, enabled=True)

    result = provider.classify_activity(_activity("fake-openai-trusted-action"), _context())

    assert result.attention_class == "requires_my_attention"
    assert result.action_type == "manual_action_required"
    assert result.priority == "high"


def test_openai_provider_hidden_noise_requires_high_confidence_to_stay_hidden() -> None:
    high_confidence_client = _FakeOpenAICompatibleClient(
        [
            json.dumps(
                _result(
                    attention_class="hidden_noise",
                    action_type="no_action_required",
                    priority="hidden",
                    show_in_digest=False,
                    confidence=0.95,
                    is_work_related=False,
                )
            )
        ]
    )
    medium_confidence_client = _FakeOpenAICompatibleClient(
        [
            json.dumps(
                _result(
                    attention_class="hidden_noise",
                    action_type="no_action_required",
                    priority="hidden",
                    show_in_digest=False,
                    confidence=0.79,
                    is_work_related=False,
                )
            )
        ]
    )

    hidden_result = OpenAIAttentionTriageProvider(
        client=high_confidence_client,
        enabled=True,
    ).classify_activity(_activity("fake-openai-hidden-high"), _context())
    review_result = OpenAIAttentionTriageProvider(
        client=medium_confidence_client,
        enabled=True,
    ).classify_activity(_activity("fake-openai-hidden-medium"), _context())

    assert hidden_result.attention_class == "hidden_noise"
    assert hidden_result.show_in_digest is False
    assert hidden_result.priority == "hidden"
    assert review_result.attention_class == "review_optional"
    assert review_result.show_in_digest is True
    assert review_result.priority == "low"
