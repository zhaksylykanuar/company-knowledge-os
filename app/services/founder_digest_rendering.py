"""Founder digest v2 renderer (product contract in docs/features/telegram-digest.md).

Pure presentation over the persisted attention digest read model. Saves the
founder's attention instead of enumerating events: one-line status, at most
three main items, grouped noise, no technical fields, security codes masked,
Russian output sized for one phone screen.

This renderer does not change the existing draft renderer, draft hashes, or
delivery behavior; callers opt in explicitly.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

MAX_MAIN_ITEMS = 3
MAX_WAITING_ITEMS = 3
MAX_PROJECT_ITEMS = 2
MAX_FIELD_CHARS = 110
HIGH_CONFIDENCE_REVIEW_THRESHOLD = 0.8
FOOTER_ACTIONS = "[Открыть главное] [Показать всё] [Скрыть похожее]"

STATUS_URGENT = "Срочно: есть пункты, требующие действия сейчас."
STATUS_ACTION = "Требуется действие: есть задачи на сегодня."
STATUS_CALM = "Спокойно: можно не отвлекаться."
NO_ACTIONS_LINE = "Действий не требуется."

_SECURITY_KEYWORDS = (
    "код",
    "code",
    "otp",
    "verification",
    "verify",
    "подтвержден",
    "одноразов",
    "2fa",
    "two-factor",
)
_CODE_DIGITS_RE = re.compile(r"\b\d{4,8}\b")
_PLACEHOLDER_TEXTS = ("summary unavailable", "subject unavailable")


def _items(digest: Mapping[str, Any], group_key: str) -> list[dict[str, Any]]:
    groups = digest.get("groups")
    if not isinstance(groups, Mapping):
        return []
    raw_items = groups.get(group_key)
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, Mapping)]


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.strip().split())
    if cleaned.casefold() in _PLACEHOLDER_TEXTS:
        return ""
    if len(cleaned) > MAX_FIELD_CHARS:
        cleaned = cleaned[: MAX_FIELD_CHARS - 1].rstrip() + "…"
    return cleaned


def _item_security_sensitive(item: Mapping[str, Any]) -> bool:
    combined = " ".join(
        str(item.get(field) or "")
        for field in ("title", "safe_summary", "reason", "recommended_action")
    ).casefold()
    return any(keyword in combined for keyword in _SECURITY_KEYWORDS) and bool(
        _CODE_DIGITS_RE.search(combined)
    )


def _mask_codes(text: str) -> str:
    return _CODE_DIGITS_RE.sub("••••", text)


def _confidence(item: Mapping[str, Any]) -> float:
    value = item.get("confidence")
    return float(value) if isinstance(value, int | float) else 0.0


def _item_title(item: Mapping[str, Any]) -> str:
    title = _clean_text(item.get("title"))
    if title:
        return title
    source = _clean_text(item.get("source")) or "источник неизвестен"
    return f"Событие из {source}"


def _render_main_item(item: Mapping[str, Any]) -> list[str]:
    sensitive = _item_security_sensitive(item)
    title = _item_title(item)
    reason = _clean_text(item.get("reason"))
    action = _clean_text(item.get("recommended_action"))
    source = _clean_text(item.get("source"))
    if sensitive:
        title = _mask_codes(title)
        reason = "Пришёл код подтверждения — сам код скрыт."
        action = _mask_codes(action)

    lines = [f"• {title}"]
    if reason:
        lines.append(f"  Почему: {reason}")
    if action:
        lines.append(f"  Сделать: {action}")
    if source:
        lines.append(f"  Источник: {source}")
    return lines


def _render_short_item(item: Mapping[str, Any]) -> str:
    title = _item_title(item)
    if _item_security_sensitive(item):
        title = _mask_codes(title)
    source = _clean_text(item.get("source"))
    return f"• {title}" + (f" ({source})" if source else "")


def _noise_summary(digest: Mapping[str, Any], leftover_count: int) -> str:
    hidden = digest.get("hidden_low_priority_summary")
    hidden_total = 0
    categories: list[str] = []
    if isinstance(hidden, Mapping):
        total = hidden.get("total")
        hidden_total = int(total) if isinstance(total, int) else 0
        counts = hidden.get("counts")
        if isinstance(counts, Mapping):
            categories = [str(key) for key in list(counts)[:3]]

    total = hidden_total + max(leftover_count, 0)
    if total < 1:
        return "Нет"
    suffix = f" ({', '.join(categories)})" if categories else ""
    return f"{total} событий{suffix}"


def render_founder_attention_digest_text(
    digest: Mapping[str, Any],
    *,
    generated_at: datetime,
    max_main_items: int = MAX_MAIN_ITEMS,
) -> str:
    """Render the founder digest v2 text from a persisted attention read model."""

    work_actions = _items(digest, "work_actions")
    manual_actions = _items(digest, "manual_actions")
    waiting = _items(digest, "waiting_external_reply")
    work_info = _items(digest, "work_info")
    review_optional = _items(digest, "review_optional")

    actionable = work_actions + manual_actions
    urgent = [item for item in actionable if item.get("priority") == "high"]
    non_urgent_actions = [item for item in actionable if item.get("priority") != "high"]
    watch_pool = non_urgent_actions + work_info + [
        item
        for item in review_optional
        if _confidence(item) >= HIGH_CONFIDENCE_REVIEW_THRESHOLD
    ]

    safe_cap = max(1, int(max_main_items))
    urgent_shown = urgent[:safe_cap]
    watch_shown = watch_pool[: max(safe_cap - len(urgent_shown), 0)]
    shown_ids = {id(item) for item in urgent_shown + watch_shown}

    waiting_shown = waiting[:MAX_WAITING_ITEMS]
    project_pool = [
        item
        for item in work_info
        if _clean_text(item.get("project")) and id(item) not in shown_ids
    ]
    project_shown = project_pool[:MAX_PROJECT_ITEMS]

    leftover_count = (
        len(urgent) - len(urgent_shown)
        + len(watch_pool) - len(watch_shown)
        + len(waiting) - len(waiting_shown)
        + len([item for item in review_optional if _confidence(item) < HIGH_CONFIDENCE_REVIEW_THRESHOLD])
    )

    if urgent_shown:
        status = STATUS_URGENT
    elif non_urgent_actions or waiting:
        status = STATUS_ACTION
    else:
        status = STATUS_CALM

    lines: list[str] = [
        f"🧠 Дайджест внимания • {generated_at.strftime('%d.%m.%Y %H:%M')}",
        "",
        status,
        "",
        "🔥 Срочно",
    ]
    if urgent_shown:
        for item in urgent_shown:
            lines.extend(_render_main_item(item))
    else:
        lines.append("Нет")

    lines.extend(["", "🟡 Стоит посмотреть"])
    if watch_shown:
        for item in watch_shown:
            lines.extend(_render_main_item(item))
    else:
        lines.append("Нет")

    lines.extend(["", "📭 Ждут моего ответа"])
    if waiting_shown:
        lines.extend(_render_short_item(item) for item in waiting_shown)
        remaining_waiting = len(waiting) - len(waiting_shown)
        if remaining_waiting > 0:
            lines.append(f"…и ещё {remaining_waiting}")
    else:
        lines.append("Нет")

    lines.extend(["", "📌 Проекты"])
    if project_shown:
        for item in project_shown:
            project = _clean_text(item.get("project"))
            lines.append(f"• {project}: {_item_title(item)}")
    else:
        lines.append("Нет важных обновлений")

    lines.extend(["", "🗂 Скрыто как шум", _noise_summary(digest, leftover_count)])

    if not urgent_shown and not non_urgent_actions and not waiting:
        lines.extend(["", NO_ACTIONS_LINE])

    lines.extend(["", FOOTER_ACTIONS])
    return "\n".join(lines) + "\n"
