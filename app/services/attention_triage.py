from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

AttentionClass = Literal[
    "requires_my_attention",
    "waiting_on_external",
    "important_info",
    "review_optional",
    "low_priority",
    "hidden_noise",
]
ActionType = Literal[
    "reply_required",
    "manual_action_required",
    "waiting_external_reply",
    "no_action_required",
    "review_optional",
]
Priority = Literal["high", "medium", "low", "hidden"]
SourceType = Literal["gmail", "github", "jira", "google_drive", "calendar", "other"]
ObjectType = Literal["email_thread", "pull_request", "issue", "document", "event", "message"]
ActivityDirection = Literal["from_me", "from_external", "system", "unknown"]
AttentionOwner = Literal["me", "external", "system", "nobody", "unknown"]
FeedbackAction = Literal[
    "marked_important",
    "marked_noise",
    "marked_no_action",
    "marked_reply_required",
    "always_show_similar",
    "always_hide_similar",
]
DigestSection = Literal[
    "Work actions requiring my attention",
    "Manual actions",
    "Waiting for external reply",
    "Important project updates",
    "Review optional",
    "Hidden low-priority summary",
]

DEFAULT_ATTENTION_TRIAGE_MIN_CONFIDENCE_TO_HIDE = 0.80
DEFAULT_ATTENTION_TRIAGE_REVIEW_THRESHOLD = 0.55


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NormalizedActivityItem(_StrictModel):
    source: SourceType
    object_type: ObjectType
    object_id: str
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_activity_at: datetime | None = None
    last_actor: str | None = None
    last_activity_direction: ActivityDirection = "unknown"
    participants: list[str] = Field(default_factory=list)
    sender: str | None = None
    recipients: list[str] = Field(default_factory=list)
    thread_message_count: int = Field(default=0, ge=0)
    clean_text_preview: str | None = None
    thread_summary: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    links: list[str] = Field(default_factory=list)


class AttentionTriageFeedback(_StrictModel):
    feedback_id: str
    source_object_id: str
    triage_result_id: str | None = None
    user_action: FeedbackAction
    created_at: datetime


class AttentionContext(_StrictModel):
    user_name: str | None = None
    user_email_addresses: list[str] = Field(default_factory=list)
    company_name: str | None = None
    user_role: str | None = None
    important_projects: list[str] = Field(default_factory=list)
    known_clients: list[str] = Field(default_factory=list)
    known_people: list[str] = Field(default_factory=list)
    active_jira_projects: list[str] = Field(default_factory=list)
    active_github_repos: list[str] = Field(default_factory=list)
    recent_drive_topics: list[str] = Field(default_factory=list)
    recent_feedback: list[AttentionTriageFeedback] = Field(default_factory=list)
    instructions: str = "Prioritize work-relevant items. If uncertain, do not hide."


class AttentionTriageResult(_StrictModel):
    attention_class: AttentionClass
    action_type: ActionType
    priority: Priority
    show_in_digest: bool
    confidence: float = Field(ge=0.0, le=1.0)
    owner: AttentionOwner = "unknown"
    is_work_related: bool = False
    is_automated: bool = False
    is_marketing: bool = False
    is_security_related: bool = False
    is_calendar_related: bool = False
    deadline: str | None = None
    reason: str
    short_summary: str
    suggested_digest_section: DigestSection


class AttentionTriageProvider(Protocol):
    def classify_activity(
        self,
        activity: NormalizedActivityItem,
        context: AttentionContext,
    ) -> AttentionTriageResult:
        ...


def parse_attention_triage_result(value: str | bytes | Mapping[str, Any]) -> AttentionTriageResult:
    """Parse strict JSON-compatible provider output into the triage schema."""

    if isinstance(value, str | bytes):
        parsed = json.loads(value)
    else:
        parsed = dict(value)
    return AttentionTriageResult.model_validate(parsed)


def _policy_reason(reason: str, policy_note: str) -> str:
    cleaned = " ".join(reason.strip().split())
    if not cleaned:
        return policy_note
    return f"{cleaned}; {policy_note}"


def _possibly_work_relevant(result: AttentionTriageResult) -> bool:
    if result.is_work_related or result.owner in {"me", "external"}:
        return True
    if result.action_type in {
        "reply_required",
        "manual_action_required",
        "waiting_external_reply",
    }:
        return True
    return result.attention_class in {
        "requires_my_attention",
        "waiting_on_external",
        "important_info",
    }


def _review_priority(result: AttentionTriageResult) -> Priority:
    if result.priority != "hidden":
        return result.priority
    return "medium" if _possibly_work_relevant(result) else "low"


def apply_attention_confidence_policy(
    result: AttentionTriageResult,
    *,
    min_confidence_to_hide: float = DEFAULT_ATTENTION_TRIAGE_MIN_CONFIDENCE_TO_HIDE,
    review_threshold: float = DEFAULT_ATTENTION_TRIAGE_REVIEW_THRESHOLD,
) -> AttentionTriageResult:
    """Apply conservative visibility rules after provider classification."""

    if result.confidence >= min_confidence_to_hide:
        return result

    if result.confidence >= review_threshold:
        if result.show_in_digest:
            return result
        return result.model_copy(
            update={
                "attention_class": "review_optional",
                "action_type": "review_optional",
                "priority": _review_priority(result),
                "show_in_digest": True,
                "suggested_digest_section": "Review optional",
                "reason": _policy_reason(
                    result.reason,
                    "medium confidence item was moved to review instead of hidden",
                ),
            }
        )

    priority: Priority = "medium" if _possibly_work_relevant(result) else "low"
    return result.model_copy(
        update={
            "attention_class": "review_optional",
            "action_type": "review_optional",
            "priority": priority,
            "show_in_digest": True,
            "suggested_digest_section": "Review optional",
            "reason": _policy_reason(
                result.reason,
                "low confidence item was kept visible for review",
            ),
        }
    )


class ConservativeFallbackAttentionTriageProvider:
    """Safe fallback used when a model/provider output is unavailable or invalid."""

    def classify_activity(
        self,
        activity: NormalizedActivityItem,
        context: AttentionContext,
    ) -> AttentionTriageResult:
        del context

        if activity.last_activity_direction == "from_me":
            return AttentionTriageResult(
                attention_class="waiting_on_external",
                action_type="waiting_external_reply",
                priority="low",
                show_in_digest=True,
                confidence=0.60,
                owner="external",
                is_work_related=True,
                reason="last activity is from the user; external response may still be pending",
                short_summary=activity.title or "Waiting on external activity",
                suggested_digest_section="Waiting for external reply",
            )

        return AttentionTriageResult(
            attention_class="review_optional",
            action_type="review_optional",
            priority="low",
            show_in_digest=True,
            confidence=0.50,
            owner="unknown",
            is_work_related=False,
            reason="fallback triage keeps uncertain activity visible",
            short_summary=activity.title or "Activity needs optional review",
            suggested_digest_section="Review optional",
        )


class MockAttentionTriageProvider:
    """Test provider that returns preloaded schema-valid outputs without external calls."""

    def __init__(
        self,
        outputs: Sequence[AttentionTriageResult | Mapping[str, Any] | str] | None = None,
        *,
        results_by_object_id: Mapping[str, AttentionTriageResult | Mapping[str, Any] | str]
        | None = None,
    ) -> None:
        self._outputs = list(outputs or [])
        self._results_by_object_id = dict(results_by_object_id or {})
        self.calls: list[tuple[NormalizedActivityItem, AttentionContext]] = []

    def classify_activity(
        self,
        activity: NormalizedActivityItem,
        context: AttentionContext,
    ) -> AttentionTriageResult:
        self.calls.append((activity, context))

        if activity.object_id in self._results_by_object_id:
            return self._coerce(self._results_by_object_id[activity.object_id])

        if self._outputs:
            return self._coerce(self._outputs.pop(0))

        raise RuntimeError("MockAttentionTriageProvider has no output for activity")

    @staticmethod
    def _coerce(value: AttentionTriageResult | Mapping[str, Any] | str) -> AttentionTriageResult:
        if isinstance(value, AttentionTriageResult):
            return value
        return parse_attention_triage_result(value)


class AttentionTriageAgent:
    def __init__(
        self,
        provider: AttentionTriageProvider,
        *,
        fallback_provider: AttentionTriageProvider | None = None,
        min_confidence_to_hide: float = DEFAULT_ATTENTION_TRIAGE_MIN_CONFIDENCE_TO_HIDE,
        review_threshold: float = DEFAULT_ATTENTION_TRIAGE_REVIEW_THRESHOLD,
    ) -> None:
        self.provider = provider
        self.fallback_provider = fallback_provider or ConservativeFallbackAttentionTriageProvider()
        self.min_confidence_to_hide = min_confidence_to_hide
        self.review_threshold = review_threshold

    def classify_activity(
        self,
        activity: NormalizedActivityItem,
        context: AttentionContext,
    ) -> AttentionTriageResult:
        try:
            result = self.provider.classify_activity(activity, context)
        except Exception:
            result = self.fallback_provider.classify_activity(activity, context)

        return apply_attention_confidence_policy(
            result,
            min_confidence_to_hide=self.min_confidence_to_hide,
            review_threshold=self.review_threshold,
        )
