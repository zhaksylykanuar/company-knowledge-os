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


OPENAI_ATTENTION_TRIAGE_SYSTEM_PROMPT = (
    "You are an AI attention triage agent for a professional work operating system.\n"
    "Your job is to decide whether a source activity item deserves the user's attention.\n\n"
    "Do not classify based only on keywords.\n"
    "Use the whole context: sender, participants, source, thread history, message content, "
    "project relevance, known contacts, deadlines, requests, and prior user feedback.\n\n"
    "Do not invent facts.\n"
    "If uncertain, classify as review_optional.\n"
    "Never hide something that could reasonably require a work action.\n"
    "Return strict JSON only."
)


def _json_dump(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _truncate_text(value: Any, max_chars: int) -> Any:
    if isinstance(value, str):
        if max_chars <= 0:
            return ""
        return value[:max_chars]
    if isinstance(value, list):
        return [_truncate_text(item, max_chars) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _truncate_text(item, max_chars)
            for key, item in value.items()
            if item is not None
        }
    return value


def _activity_prompt_payload(
    activity: NormalizedActivityItem,
    *,
    max_text_chars: int,
) -> dict[str, Any]:
    payload = activity.model_dump(mode="json")
    payload["clean_text_preview"] = _truncate_text(
        payload.get("clean_text_preview"),
        max_text_chars,
    )
    payload["thread_summary"] = _truncate_text(payload.get("thread_summary"), max_text_chars)
    payload["source_metadata"] = _truncate_text(payload.get("source_metadata"), max_text_chars)
    payload["link_count"] = len(activity.links)
    payload.pop("links", None)
    return payload


def _context_prompt_payload(
    context: AttentionContext,
    *,
    max_text_chars: int,
) -> dict[str, Any]:
    return _truncate_text(context.model_dump(mode="json"), max_text_chars)


def _response_output_text(response: Any) -> str | bytes | Mapping[str, Any]:
    if isinstance(response, str | bytes):
        return response
    if isinstance(response, Mapping):
        for key in ("output_text", "text", "content"):
            value = response.get(key)
            if isinstance(value, str | bytes | Mapping):
                return value
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str | bytes):
        return output_text
    raise ValueError("provider response did not include output text")


def _call_openai_compatible_client(client: Any, payload: Mapping[str, Any]) -> Any:
    if callable(client):
        return client(dict(payload))

    responses = getattr(client, "responses", None)
    create = getattr(responses, "create", None)
    if callable(create):
        return create(**payload)

    raise RuntimeError("OpenAI-compatible client must be callable or expose responses.create")


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


class OpenAIAttentionTriageProvider:
    """OpenAI-compatible scaffold with injected-client execution only."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        enabled: bool = False,
        model: str | None = None,
        max_text_chars: int = 6000,
        min_confidence_to_hide: float = DEFAULT_ATTENTION_TRIAGE_MIN_CONFIDENCE_TO_HIDE,
        review_threshold: float = DEFAULT_ATTENTION_TRIAGE_REVIEW_THRESHOLD,
        fallback_provider: AttentionTriageProvider | None = None,
    ) -> None:
        self.client = client
        self.enabled = enabled
        self.model = model or "gpt-4o-mini"
        self.max_text_chars = max(0, int(max_text_chars))
        self.min_confidence_to_hide = min_confidence_to_hide
        self.review_threshold = review_threshold
        self.fallback_provider = fallback_provider or ConservativeFallbackAttentionTriageProvider()

    def classify_activity(
        self,
        activity: NormalizedActivityItem,
        context: AttentionContext,
    ) -> AttentionTriageResult:
        if not self.enabled or self.client is None:
            return self.fallback_provider.classify_activity(activity, context)

        payload = self._request_payload(activity, context)
        for _attempt in range(2):
            try:
                response = _call_openai_compatible_client(self.client, payload)
                result = parse_attention_triage_result(_response_output_text(response))
            except Exception:
                continue

            return apply_attention_confidence_policy(
                result,
                min_confidence_to_hide=self.min_confidence_to_hide,
                review_threshold=self.review_threshold,
            )

        return self.fallback_provider.classify_activity(activity, context)

    def _request_payload(
        self,
        activity: NormalizedActivityItem,
        context: AttentionContext,
    ) -> dict[str, Any]:
        activity_json = _json_dump(
            _activity_prompt_payload(activity, max_text_chars=self.max_text_chars)
        )
        context_json = _json_dump(
            _context_prompt_payload(context, max_text_chars=self.max_text_chars)
        )
        return {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": OPENAI_ATTENTION_TRIAGE_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "Activity item:\n"
                        f"{activity_json}\n\n"
                        "User/work context:\n"
                        f"{context_json}\n\n"
                        "Return only JSON matching the schema."
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "attention_triage_result",
                    "strict": True,
                    "schema": AttentionTriageResult.model_json_schema(),
                }
            },
        }


def build_attention_triage_provider(
    settings: Any,
    *,
    client: Any | None = None,
) -> AttentionTriageProvider:
    fallback = ConservativeFallbackAttentionTriageProvider()
    if getattr(settings, "attention_triage_enabled", False) is not True:
        return fallback

    provider_name = str(getattr(settings, "attention_triage_provider", "openai")).casefold()
    if provider_name != "openai":
        return fallback

    if client is None:
        return fallback

    return OpenAIAttentionTriageProvider(
        client=client,
        enabled=True,
        model=getattr(settings, "attention_triage_model", None),
        max_text_chars=getattr(settings, "attention_triage_max_text_chars", 6000),
        min_confidence_to_hide=getattr(
            settings,
            "attention_triage_min_confidence_to_hide",
            DEFAULT_ATTENTION_TRIAGE_MIN_CONFIDENCE_TO_HIDE,
        ),
        review_threshold=getattr(
            settings,
            "attention_triage_review_threshold",
            DEFAULT_ATTENTION_TRIAGE_REVIEW_THRESHOLD,
        ),
        fallback_provider=fallback,
    )


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
