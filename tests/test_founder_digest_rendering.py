from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.founder_digest_rendering import (
    FOOTER_ACTIONS,
    NO_ACTIONS_LINE,
    STATUS_ACTION,
    STATUS_CALM,
    STATUS_URGENT,
    render_founder_attention_digest_text,
)

GENERATED_AT = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)

FORBIDDEN_TECH_MARKERS = (
    "evidence",
    "visible",
    "hidden_low_priority",
    "window",
    "Summary unavailable",
    "triage_result_id",
    "activity_item_id",
    "confidence",
    "show_in_digest",
)


def _item(
    *,
    title: str = "Клиент спросил про сроки",
    attention_class: str = "requires_my_attention",
    priority: str = "high",
    reason: str = "Клиент ждёт ответа сегодня",
    recommended_action: str = "Ответить до конца дня",
    source: str = "gmail",
    confidence: float = 0.9,
    project: str | None = None,
    safe_summary: str | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "attention_class": attention_class,
        "priority": priority,
        "reason": reason,
        "recommended_action": recommended_action,
        "source": source,
        "confidence": confidence,
        "project": project,
        "safe_summary": safe_summary,
        "evidence": "3 triage evidence refs",
        "evidence_refs": [{"kind": "source_event"}],
    }


def _digest(
    *,
    work_actions: list[dict[str, Any]] | None = None,
    manual_actions: list[dict[str, Any]] | None = None,
    waiting: list[dict[str, Any]] | None = None,
    work_info: list[dict[str, Any]] | None = None,
    review_optional: list[dict[str, Any]] | None = None,
    hidden_total: int = 0,
    hidden_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "groups": {
            "work_actions": work_actions or [],
            "manual_actions": manual_actions or [],
            "waiting_external_reply": waiting or [],
            "work_info": work_info or [],
            "review_optional": review_optional or [],
        },
        "hidden_low_priority_summary": {
            "total": hidden_total,
            "counts": hidden_counts or {},
        },
        "window": {"start_at": "2026-06-10T00:00:00+00:00"},
        "counts": {"visible": 99, "hidden": 99},
    }


def test_empty_digest_is_calm_and_explicit() -> None:
    text = render_founder_attention_digest_text(_digest(), generated_at=GENERATED_AT)

    assert "🧠 Дайджест внимания • 11.06.2026 09:00" in text
    assert STATUS_CALM in text
    assert NO_ACTIONS_LINE in text
    assert "🔥 Срочно\nНет" in text
    assert "📭 Ждут моего ответа\nНет" in text
    assert "Нет важных обновлений" in text
    assert "🗂 Скрыто как шум\nНет" in text
    assert FOOTER_ACTIONS in text


def test_urgent_item_has_what_why_action_source() -> None:
    text = render_founder_attention_digest_text(
        _digest(work_actions=[_item()]),
        generated_at=GENERATED_AT,
    )

    assert STATUS_URGENT in text
    assert "• Клиент спросил про сроки" in text
    assert "Почему: Клиент ждёт ответа сегодня" in text
    assert "Сделать: Ответить до конца дня" in text
    assert "Источник: gmail" in text


def test_main_items_capped_at_three_and_leftovers_grouped_as_noise() -> None:
    many = [_item(title=f"Срочное дело {i}") for i in range(5)]
    info = [
        _item(
            title=f"Инфо {i}",
            attention_class="important_info",
            priority="medium",
        )
        for i in range(4)
    ]
    text = render_founder_attention_digest_text(
        _digest(work_actions=many, work_info=info),
        generated_at=GENERATED_AT,
    )

    main_bullets = [
        line
        for line in text.splitlines()
        if line.startswith("• Срочное дело") or line.startswith("• Инфо")
    ]
    assert len(main_bullets) == 3
    assert "🗂 Скрыто как шум" in text
    assert "6 событий" in text  # 2 срочных + 4 инфо не показаны


def test_low_priority_actions_give_action_required_status() -> None:
    text = render_founder_attention_digest_text(
        _digest(manual_actions=[_item(priority="medium")]),
        generated_at=GENERATED_AT,
    )

    assert STATUS_ACTION in text
    assert NO_ACTIONS_LINE not in text


def test_waiting_section_lists_items_short_form() -> None:
    waiting = [
        _item(
            title=f"Жду ответа {i}",
            attention_class="waiting_on_external",
            priority="low",
        )
        for i in range(5)
    ]
    text = render_founder_attention_digest_text(
        _digest(waiting=waiting),
        generated_at=GENERATED_AT,
    )

    assert "📭 Ждут моего ответа" in text
    assert "• Жду ответа 0 (gmail)" in text
    assert "…и ещё 2" in text


def test_project_section_uses_project_field() -> None:
    info = [
        _item(
            title="Обновлён план запуска",
            attention_class="important_info",
            priority="low",
            confidence=0.5,
            project="QazTwin",
        )
    ]
    text = render_founder_attention_digest_text(
        _digest(work_info=info, work_actions=[_item(), _item(), _item()]),
        generated_at=GENERATED_AT,
    )

    assert "📌 Проекты" in text
    assert "• QazTwin: Обновлён план запуска" in text


def test_security_codes_are_masked_everywhere() -> None:
    item = _item(
        title="Код подтверждения 482913 для входа",
        reason="Verification code 482913",
        recommended_action="Введите код 482913",
    )
    text = render_founder_attention_digest_text(
        _digest(work_actions=[item]),
        generated_at=GENERATED_AT,
    )

    assert "482913" not in text
    assert "код скрыт" in text


def test_low_confidence_review_optional_is_noise_not_main() -> None:
    review = [
        _item(
            title="Непонятное событие",
            attention_class="review_optional",
            priority="low",
            confidence=0.5,
        )
    ]
    text = render_founder_attention_digest_text(
        _digest(review_optional=review, hidden_total=2, hidden_counts={"marketing": 2}),
        generated_at=GENERATED_AT,
    )

    assert "• Непонятное событие" not in text
    assert "3 событий (marketing)" in text


def test_no_technical_fields_or_placeholders_leak() -> None:
    item = _item(title="Subject unavailable", safe_summary="Summary unavailable")
    text = render_founder_attention_digest_text(
        _digest(work_actions=[item], hidden_total=1, hidden_counts={"noise": 1}),
        generated_at=GENERATED_AT,
    )

    for marker in FORBIDDEN_TECH_MARKERS:
        assert marker not in text
    assert "• Событие из gmail" in text  # placeholder title заменён


def test_fits_one_phone_screen_even_when_busy() -> None:
    busy = _digest(
        work_actions=[_item(title="Очень" + " длинно" * 40) for _ in range(10)],
        waiting=[
            _item(attention_class="waiting_on_external", title=f"Ожидание {i}")
            for i in range(10)
        ],
        work_info=[
            _item(
                attention_class="important_info",
                title=f"Инфо {i}",
                project="QazTwin",
            )
            for i in range(10)
        ],
        hidden_total=25,
        hidden_counts={"marketing": 20, "automated": 5},
    )
    text = render_founder_attention_digest_text(busy, generated_at=GENERATED_AT)

    assert len(text) < 2000
    assert text.count("Почему:") <= 3
