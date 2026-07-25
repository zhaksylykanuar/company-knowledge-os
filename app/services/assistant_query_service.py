"""Bounded deterministic assistant over the exact Headquarters snapshot.

The service classifies an allowlisted intent and formats only already-sanitized
Headquarters facts. It never logs the question, calls a provider/LLM, persists
chat, or invokes a mutation service.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from math import ceil
from threading import Lock
from time import monotonic
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.services.headquarters_read_service import (
    read_workspace_headquarters,
    sanitize_headquarters_evidence_url,
)


ASSISTANT_CONTRACT_VERSION = "assistant.v1"
ASSISTANT_QUERY_MAX_CHARS = 500
ASSISTANT_RESPONSE_TEXT_MAX_CHARS = 600
ASSISTANT_CITATION_LIMIT = 8
ASSISTANT_SUGGESTION_LIMIT = 4
ASSISTANT_WARNING_LIMIT = 8
ASSISTANT_RESPONSE_MAX_BYTES = 16_384

ASSISTANT_INTENTS = frozenset(
    {
        "action_request",
        "briefing",
        "company_person",
        "current_priority",
        "decision_status",
        "evidence",
        "owners",
        "sources",
        "unsupported",
        "waiting_decisions",
        "why_now",
    }
)

_UNSAFE_INSTRUCTION_MARKERS = (
    "api key",
    "developer message",
    "ignore all",
    "ignore previous",
    "raw body",
    "show secret",
    "system prompt",
    "token value",
    "игнорируй все",
    "игнорируй предыдущ",
    "покажи ключ",
    "покажи секрет",
    "системный промпт",
)
_ACTION_REQUEST_MARKERS = (
    "approve it",
    "do it",
    "execute it",
    "reject it",
    "выполни",
    "одобри",
    "отклони",
    "отправь",
    "сделай сам",
    "сделай это",
    "создай задачу",
)
_WHY_MARKERS = ("why now", "почему сейчас", "почему этот", "почему главный")
_OWNER_MARKERS = ("owner", "ответствен", "владелец", "кто делает", "кто вед")
_EVIDENCE_MARKERS = (
    "citation",
    "evidence",
    "доказ",
    "на чём основан",
    "основани",
    "подтвержден",
)
_DECISION_STATUS_MARKERS = (
    "decision status",
    "статус решения",
    "что решили",
    "решение принято",
)
_WAITING_DECISION_MARKERS = (
    "waiting decision",
    "ждут реш",
    "какие реш",
    "очередь реш",
    "сколько реш",
)
_SOURCE_MARKERS = ("source", "источник")
_BRIEFING_MARKERS = ("briefing", "brief", "брифинг", "сводк")
_PERSON_MARKERS = (
    "company",
    "customer",
    "employee",
    "person",
    "заказчик",
    "компани",
    "клиент",
    "сотрудник",
    "человек",
)
_PRIORITY_MARKERS = (
    "current priority",
    "main move",
    "priority",
    "главный ход",
    "приоритет",
    "что главное",
)

_ALLOWED_PROVENANCE = frozenset(
    {
        "briefing_item",
        "canonical_evidence_ref",
        "canonical_repository",
        "canonical_source_record",
        "company_world_projection",
        "headquarters_aggregate",
        "integration_connection",
    }
)
_ALLOWED_REFERENCE_TYPES = frozenset(
    {
        "briefing_item",
        "company_world_candidate",
        "evidence_ref",
        "headquarters_snapshot",
        "integration_connection",
        "repository",
        "source_record",
        "sync_job",
    }
)
_ALLOWED_TRUST = frozenset({"aggregate", "verified"})
_SAFE_NAVIGATION_PREFIXES = (
    "/actions",
    "/briefings",
    "/company-brain",
    "/dashboard",
    "/documents",
    "/settings",
)


class AssistantRateLimitedError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("assistant query rate limit exceeded")
        self.retry_after_seconds = max(1, retry_after_seconds)


class AssistantSnapshotChangedError(RuntimeError):
    """The requested screen snapshot is no longer the current projection."""


class AssistantResponseTooLargeError(RuntimeError):
    """A bounded response invariant was violated."""


@dataclass(frozen=True)
class AssistantFlightKey:
    workspace_id: UUID
    user_id: UUID
    expected_snapshot_id: str
    normalized_query: str


class AssistantQueryController:
    """Process-local rate limit plus identical-query single-flight."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts: dict[tuple[UUID, UUID], deque[float]] = defaultdict(deque)
        self._in_flight: dict[
            AssistantFlightKey,
            asyncio.Task[dict[str, Any]],
        ] = {}

    async def run(
        self,
        *,
        key: AssistantFlightKey,
        operation: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        with self._lock:
            existing = self._in_flight.get(key)
            if existing is not None:
                task = existing
            else:
                self._admit(key.user_id, key.workspace_id)
                task = asyncio.create_task(operation())
                self._in_flight[key] = task
                task.add_done_callback(
                    lambda completed, flight_key=key: self._complete(
                        flight_key,
                        completed,
                    )
                )
        return await asyncio.shield(task)

    def _admit(self, user_id: UUID, workspace_id: UUID) -> None:
        now = monotonic()
        window = settings.assistant_query_rate_limit_window_seconds
        window_start = now - window
        rate_key = (user_id, workspace_id)

        for stale_key in tuple(self._attempts):
            attempts = self._attempts[stale_key]
            self._prune(attempts, window_start)
            if not attempts:
                del self._attempts[stale_key]

        attempts = self._attempts[rate_key]
        self._prune(attempts, window_start)
        if len(attempts) >= settings.assistant_query_rate_limit_per_user_workspace:
            retry_after = ceil(max(1.0, attempts[0] + window - now))
            raise AssistantRateLimitedError(retry_after)
        attempts.append(now)

    def _complete(
        self,
        key: AssistantFlightKey,
        task: asyncio.Task[dict[str, Any]],
    ) -> None:
        with self._lock:
            if self._in_flight.get(key) is task:
                del self._in_flight[key]

    def reset(self) -> None:
        """Clear process-local state for deterministic tests only."""

        with self._lock:
            tasks = tuple(self._in_flight.values())
            self._in_flight.clear()
            self._attempts.clear()
        for task in tasks:
            if not task.done():
                task.cancel()

    @staticmethod
    def _prune(attempts: deque[float], window_start: float) -> None:
        while attempts and attempts[0] <= window_start:
            attempts.popleft()


assistant_query_controller = AssistantQueryController()


async def query_workspace_assistant(
    *,
    workspace_id: UUID,
    user_id: UUID,
    query: str,
    expected_snapshot_id: str,
) -> dict[str, Any]:
    normalized_query = _normalize_query(query)
    key = AssistantFlightKey(
        workspace_id=workspace_id,
        user_id=user_id,
        expected_snapshot_id=expected_snapshot_id,
        normalized_query=normalized_query,
    )

    async def operation() -> dict[str, Any]:
        async with asyncio.timeout(settings.assistant_query_timeout_seconds):
            snapshot = await read_workspace_headquarters(
                workspace_id=workspace_id,
                user_id=user_id,
            )
            if snapshot["snapshot"]["id"] != expected_snapshot_id:
                raise AssistantSnapshotChangedError("headquarters snapshot changed")
            return build_assistant_response(snapshot, normalized_query)

    return await assistant_query_controller.run(key=key, operation=operation)


def build_assistant_response(
    snapshot: Mapping[str, Any],
    normalized_query: str,
) -> dict[str, Any]:
    intent, intent_warning = _classify_intent(normalized_query)
    text, citations, action = _answer(intent, normalized_query, snapshot)
    warnings = _warnings(snapshot, intent_warning)
    result: dict[str, Any] = {
        "contract_version": ASSISTANT_CONTRACT_VERSION,
        "intent": intent,
        "text": text[:ASSISTANT_RESPONSE_TEXT_MAX_CHARS],
        "citations": citations[:ASSISTANT_CITATION_LIMIT],
        "suggestions": _suggestions(intent)[:ASSISTANT_SUGGESTION_LIMIT],
        "action": action,
        "snapshot_id": snapshot["snapshot"]["id"],
        "as_of": snapshot["snapshot"]["as_of"],
        "partial": bool(snapshot["snapshot"]["partial"]),
        "warnings": warnings[:ASSISTANT_WARNING_LIMIT],
        "is_live": True,
        "llm_used": False,
    }
    encoded = json.dumps(
        result,
        default=str,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > ASSISTANT_RESPONSE_MAX_BYTES:
        raise AssistantResponseTooLargeError("assistant response exceeded bounded size")
    return result


def _normalize_query(query: str) -> str:
    return " ".join(query.casefold().split())


def _classify_intent(query: str) -> tuple[str, str | None]:
    if _contains_any(query, _UNSAFE_INSTRUCTION_MARKERS):
        return "unsupported", "unsafe_instruction_ignored"
    if _contains_any(query, _ACTION_REQUEST_MARKERS):
        return "action_request", None
    if _contains_any(query, _WHY_MARKERS):
        return "why_now", None
    if _contains_any(query, _OWNER_MARKERS):
        return "owners", None
    if _contains_any(query, _EVIDENCE_MARKERS):
        return "evidence", None
    if _contains_any(query, _DECISION_STATUS_MARKERS):
        return "decision_status", None
    if _contains_any(query, _WAITING_DECISION_MARKERS):
        return "waiting_decisions", None
    if _contains_any(query, _SOURCE_MARKERS):
        return "sources", None
    if _contains_any(query, _BRIEFING_MARKERS):
        return "briefing", None
    if _contains_any(query, _PERSON_MARKERS):
        return "company_person", None
    if _contains_any(query, _PRIORITY_MARKERS):
        return "current_priority", None
    return "unsupported", "unsupported_intent"


def _answer(
    intent: str,
    query: str,
    snapshot: Mapping[str, Any],
) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
    if intent == "unsupported":
        return (
            "Я отвечаю только о текущем подтверждённом снимке компании. Выберите один из безопасных вопросов ниже.",
            [],
            None,
        )
    if intent == "action_request":
        can_review = _capability(snapshot, "can_review_proposal")
        return (
            (
                "Я не выполняю действия сам. Откройте очередь решений, проверьте последствия и подтвердите нужный шаг лично."
                if can_review
                else "Я не выполняю действия сам, а у вашей роли нет права подтверждать решения."
            ),
            [_snapshot_citation(snapshot, "decisions", "/actions?status=proposed")],
            (
                _navigation_action("Открыть подтверждение", "/actions?status=proposed")
                if can_review
                else None
            ),
        )
    if intent in {"current_priority", "why_now"}:
        priority = _mapping(snapshot.get("priority"))
        if priority is None:
            return _insufficient()
        citations = _evidence(priority.get("evidence_refs"))
        if not citations:
            return _insufficient()
        if intent == "why_now":
            text = f"Почему сейчас: {_safe_text(priority.get('why_now'), 420)}"
        else:
            text = (
                f"Главный ход: {_safe_text(priority.get('title'), 180)}. "
                f"{_safe_text(priority.get('summary'), 320)}"
            )
        return text, citations, _mission_action(priority)
    if intent == "owners":
        priority = _mapping(snapshot.get("priority"))
        if priority is None:
            return _insufficient()
        provenance = _mapping(priority.get("fact_provenance"))
        citations = _evidence(provenance.get("owner") if provenance else None)
        if not citations:
            return _insufficient()
        return (
            "У текущей ситуации есть подтверждённое основание для владельца. Откройте решение, чтобы проверить точную связь.",
            citations,
            _mission_action(priority),
        )
    if intent == "sources":
        sources = _mapping(snapshot.get("sources")) or {}
        total = _safe_count(sources.get("total"))
        healthy = _safe_count(sources.get("healthy"))
        attention = _safe_count(sources.get("attention_count"))
        if total is None or healthy is None or attention is None:
            return _insufficient()
        return (
            f"Источники: всего {total}, работают {healthy}, требуют внимания {attention}.",
            [_snapshot_citation(snapshot, "sources", "/settings/integrations")],
            _navigation_action("Открыть настройки источников", "/settings/integrations"),
        )
    if intent == "briefing":
        briefing_count = _onboarding_count(snapshot, "briefings")
        if briefing_count is None:
            return _insufficient()
        text = (
            "Подтверждённых брифингов пока нет."
            if briefing_count == 0
            else f"В текущем снимке подтверждено брифингов: {briefing_count}."
        )
        return (
            text,
            [_snapshot_citation(snapshot, "briefing", "/briefings")],
            _navigation_action("Открыть брифинги", "/briefings"),
        )
    if intent == "waiting_decisions":
        metric = _pulse_metric(snapshot, "waiting_decisions")
        if metric is None or _safe_count(metric.get("value")) is None:
            return _insufficient()
        count = _safe_count(metric.get("value")) or 0
        precision = "не менее " if metric.get("precision") == "at_least" else ""
        return (
            f"Решений с проверяемыми основаниями ждёт: {precision}{count}.",
            [_snapshot_citation(snapshot, "decisions", "/actions?status=proposed")],
            _navigation_action("Открыть решения", "/actions?status=proposed"),
        )
    if intent == "evidence":
        priority = _mapping(snapshot.get("priority"))
        citations = _evidence(priority.get("evidence_refs") if priority else None)
        if not citations:
            return _insufficient()
        return (
            f"Для текущего приоритета разрешено подтверждённых ссылок: {len(citations)}.",
            citations,
            _mission_action(priority) if priority else None,
        )
    if intent == "decision_status":
        missions = [
            mission
            for mission in _missions(snapshot)
            if mission.get("kind") == "review_proposal"
        ]
        if not missions:
            return (
                "В текущем снимке нет подтверждённого решения на проверке.",
                [_snapshot_citation(snapshot, "decisions", "/actions?status=proposed")],
                _navigation_action("Открыть историю решений", "/actions"),
            )
        selected = missions[0]
        citations = _evidence(selected.get("evidence_refs"))
        if not citations:
            return _insufficient()
        return (
            f"Статус решения «{_safe_text(selected.get('title'), 180)}»: {_safe_text(selected.get('status'), 80)}.",
            citations,
            _mission_action(selected),
        )
    if intent == "company_person":
        if _contains_any(query, ("customer", "employee", "person", "заказчик", "клиент", "сотрудник", "человек")):
            priority = _mapping(snapshot.get("priority"))
            provenance = _mapping(priority.get("fact_provenance")) if priority else None
            citations = _evidence(
                [
                    *(_mapping_list(provenance.get("owner")) if provenance else []),
                    *(_mapping_list(provenance.get("customer")) if provenance else []),
                ]
            )
            if not citations:
                return _insufficient()
            return (
                "В текущей ситуации есть подтверждённая связь с человеком или заказчиком. Откройте профиль для точной проверки.",
                citations,
                _navigation_action("Открыть компанию", "/company-brain"),
            )
        workspace = _mapping(snapshot.get("workspace")) or {}
        name = _safe_text(workspace.get("name"), 180)
        if not name:
            return _insufficient()
        return (
            f"Текущая компания: {name}. Ответ собран только из её workspace-снимка.",
            [_snapshot_citation(snapshot, "identity", "/dashboard")],
            _navigation_action("Открыть компанию", "/dashboard"),
        )
    return _insufficient()


def _insufficient() -> tuple[str, list[dict[str, Any]], None]:
    return "Недостаточно подтверждённых данных.", [], None


def _mission_action(mission: Mapping[str, Any]) -> dict[str, Any] | None:
    action = _mapping(mission.get("action"))
    if action is None or not bool(action.get("enabled")):
        return None
    target = action.get("target")
    if not isinstance(target, str):
        return None
    return _navigation_action(_safe_text(action.get("label"), 100), target)


def _navigation_action(label: str, target: str) -> dict[str, Any] | None:
    if not label or not _safe_internal_target(target):
        return None
    return {
        "kind": "navigate",
        "label": label[:100],
        "target": target,
        "enabled": True,
        "disabled_reason": None,
    }


def _snapshot_citation(
    snapshot: Mapping[str, Any],
    section: str,
    target: str,
) -> dict[str, Any]:
    snapshot_meta = _mapping(snapshot.get("snapshot")) or {}
    snapshot_id = _safe_text(snapshot_meta.get("id"), 80)
    return {
        "id": f"headquarters_snapshot:{snapshot_id}:{section}",
        "kind": "headquarters_snapshot",
        "source_key": "internal",
        "label": f"Картина компании · {section}"[:160],
        "target": target if _safe_internal_target(target) else "/dashboard",
        "provenance": "headquarters_aggregate",
        "trust": "aggregate",
        "reference_type": "headquarters_snapshot",
        "reference_id": snapshot_id,
        "workspace_scoped": True,
    }


def _evidence(value: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _mapping_list(value):
        evidence_id = _safe_text(item.get("id"), 180)
        provenance = _safe_text(item.get("provenance"), 80)
        trust = _safe_text(item.get("trust"), 40)
        reference_type = _safe_text(item.get("reference_type"), 80)
        if (
            not evidence_id
            or evidence_id in seen
            or provenance not in _ALLOWED_PROVENANCE
            or trust not in _ALLOWED_TRUST
            or reference_type not in _ALLOWED_REFERENCE_TYPES
            or item.get("workspace_scoped") is not True
        ):
            continue
        target = item.get("target")
        safe_target = (
            target
            if isinstance(target, str)
            and (
                _safe_internal_target(target)
                or sanitize_headquarters_evidence_url(target) == target
            )
            else None
        )
        normalized.append(
            {
                "id": evidence_id,
                "kind": _safe_text(item.get("kind"), 80),
                "source_key": _safe_text(item.get("source_key"), 80),
                "label": _safe_text(item.get("label"), 180),
                "target": safe_target,
                "provenance": provenance,
                "trust": trust,
                "reference_type": reference_type,
                "reference_id": _safe_text(item.get("reference_id"), 180),
                "workspace_scoped": True,
            }
        )
        seen.add(evidence_id)
        if len(normalized) == ASSISTANT_CITATION_LIMIT:
            break
    return normalized


def _suggestions(intent: str) -> list[dict[str, str]]:
    pool = [
        ("priority", "Какой сейчас главный приоритет?"),
        ("why", "Почему этот ход главный?"),
        ("sources", "Что с источниками?"),
        ("decisions", "Какие решения ждут?"),
    ]
    intent_to_key = {
        "current_priority": "priority",
        "why_now": "why",
        "sources": "sources",
        "waiting_decisions": "decisions",
    }
    current_key = intent_to_key.get(intent)
    return [
        {"id": key, "label": label, "query": label}
        for key, label in pool
        if key != current_key
    ]


def _warnings(snapshot: Mapping[str, Any], intent_warning: str | None) -> list[str]:
    snapshot_meta = _mapping(snapshot.get("snapshot")) or {}
    raw = snapshot_meta.get("warnings")
    warnings = [
        warning[:160]
        for warning in raw
        if isinstance(warning, str) and warning
    ] if isinstance(raw, list) else []
    if intent_warning:
        warnings.append(intent_warning)
    return list(dict.fromkeys(warnings))


def _onboarding_count(snapshot: Mapping[str, Any], key: str) -> int | None:
    onboarding = _mapping(snapshot.get("onboarding"))
    for step in _mapping_list(onboarding.get("steps") if onboarding else None):
        for fact in _mapping_list(step.get("evidence")):
            if fact.get("key") == key:
                return _safe_count(fact.get("value"))
    return None


def _pulse_metric(snapshot: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    for metric in _mapping_list(snapshot.get("pulse")):
        if metric.get("key") == key:
            return metric
    return None


def _missions(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    missions: list[Mapping[str, Any]] = []
    priority = _mapping(snapshot.get("priority"))
    if priority is not None:
        missions.append(priority)
    missions.extend(_mapping_list(snapshot.get("queue")))
    return missions


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _safe_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _capability(snapshot: Mapping[str, Any], key: str) -> bool:
    capabilities = _mapping(snapshot.get("capabilities"))
    return bool(capabilities and capabilities.get(key) is True)


def _safe_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.split())
    return cleaned[:limit]


def _safe_internal_target(value: str) -> bool:
    return (
        any(
            value == prefix
            or value.startswith(f"{prefix}/")
            or value.startswith(f"{prefix}?")
            for prefix in _SAFE_NAVIGATION_PREFIXES
        )
        and not value.startswith("//")
        and "\\" not in value
        and not any(character.isspace() or ord(character) < 32 for character in value)
    )


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)
