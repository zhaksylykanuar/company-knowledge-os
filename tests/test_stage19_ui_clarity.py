from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _html() -> str:
    return (ROOT / "app" / "static" / "founder_ui.html").read_text(
        encoding="utf-8"
    )


class _ButtonTooltipParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.missing: list[tuple[int, str | None, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "button":
            return
        values = dict(attrs)
        if "data-tip" not in values:
            line, _ = self.getpos()
            self.missing.append((line, values.get("id"), values.get("class")))


def test_stage20_command_center_is_russian_and_clear() -> None:
    html = _html()
    for marker in (
        "Центр управления FounderOS",
        "AI сравнивает заявленное состояние компании",
        "Пульс компании",
        "Что AI видит иначе",
        "Следующее лучшее действие",
        "Доверие к данным",
        "Obsidian Vault",
        "Настройка системы",
        "Главный следующий шаг",
        "actionProvenanceBadge",
        "UI fallback · not evidence-backed",
        "evidence-backed",
        "insufficient evidence",
    ):
        assert marker in html, marker


def test_stage20_navigation_and_explain_mode_are_russian() -> None:
    html = _html()
    for marker in (
        ">Центр управления</div>",
        ">Источники",
        ">Качество данных",
        ">Следующие действия",
        ">Obsidian-граф</div>",
        ">Решения",
        ">Апдейты",
        ">Метрики",
        ">Задачи",
        ">Команда</div>",
        ">Продукт</div>",
        ">Для инвестора</div>",
        "Просто",
        "Подробно",
        "fos_explain_mode",
    ):
        assert marker in html, marker


def test_stage20_sources_are_guided_setup_not_raw_table() -> None:
    html = _html()
    for marker in (
        "Источники данных",
        "FounderOS читает данные только в read-only режиме",
        "Мастер настройки",
        "Credentials",
        "Scope",
        "Проверка → Предпросмотр → Sync",
        "Безопасный режим: FounderOS не вызывает внешние API.",
        "Показать технические детали",
    ):
        assert marker in html, marker


def test_stage20_data_quality_is_grouped_issue_board() -> None:
    html = _html()
    for marker in (
        "Что мешает системе быть точной?",
        "Блокеры настройки",
        "Пробелы в evidence",
        "Гигиена графа",
        "Ошибки запусков",
        "Obsidian sync",
        "Что сделать:",
    ):
        assert marker in html, marker


def test_stage20_action_center_is_compact_decision_board() -> None:
    html = _html()
    for marker in (
        "Что решить дальше?",
        "Следующие решения",
        "Срочно сейчас",
        "Нужно решение",
        "Нужна настройка",
        "Ждём evidence",
        "Гигиена",
        "Позже",
        "Показать evidence и routing",
    ):
        assert marker in html, marker


def test_stage20_knowledge_tree_is_obsidian_bridge_first() -> None:
    html = _html()
    assert "Obsidian Bridge first" in html
    assert "FounderOS генерирует настоящий локальный Obsidian vault" in html
    assert "Открыть в Obsidian" in html
    assert "Web graph preview fallback / debug" in html
    assert "Граф строится из реальных wikilinks" in html
    assert "Резервный web-preview / debug" in html


def test_stage20_explain_mode_status_dictionary_and_tooltips_present() -> None:
    html = _html()
    for marker in (
        "Просто",
        "Подробно",
        "fos_explain_mode",
        "STATUS_HELP",
        "RU={",
        "missing_config",
        "real_disabled",
        "blocked_missing_scope",
        "watermark",
        "receipt",
        "technical-details",
        'id="global-tooltip"',
        "initTooltips",
        "mousemove",
        "focusin",
        "Escape",
    ):
        assert marker in html, marker


def test_stage20_every_button_has_russian_tooltip_hook() -> None:
    parser = _ButtonTooltipParser()
    parser.feed(_html())
    assert parser.missing == []


def test_stage20_founder_ui_does_not_restore_finance_surface() -> None:
    html = _html()
    for marker in (
        'data-nav="fi"',
        'data-sec="fi"',
        "fiRender",
        "MRR",
        "ARR",
        "runway",
        "Runway",
        "burn rate",
        "revenue forecast",
        "Finance",
    ):
        assert marker not in html, marker
