from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _html() -> str:
    return (ROOT / "app" / "static" / "founder_ui.html").read_text(
        encoding="utf-8"
    )


def test_stage19_command_center_clarity_cards_present() -> None:
    html = _html()
    for marker in (
        "AI second opinion for your company",
        "Company Pulse",
        "What AI sees differently",
        "Next Best Actions",
        "Data Trust",
        "Obsidian Vault",
        "Setup Progress",
        "Main next action",
    ):
        assert marker in html, marker


def test_stage19_sources_are_guided_setup_not_raw_table() -> None:
    html = _html()
    for marker in (
        "Connect your company data",
        "Guided setup steps",
        "Add credentials",
        "Add scope",
        "Enable safe real reads",
        "Test, preview, sync",
        "Safe mode: FounderOS will not call external APIs.",
        "Show technical details",
    ):
        assert marker in html, marker


def test_stage19_data_quality_is_grouped_issue_board() -> None:
    html = _html()
    for marker in (
        "What blocks accurate answers?",
        "Setup blockers",
        "Evidence gaps",
        "Graph hygiene",
        "Run issues",
        "Obsidian sync",
        "What to do next:",
    ):
        assert marker in html, marker


def test_stage19_action_center_is_compact_decision_board() -> None:
    html = _html()
    for marker in (
        "What should I decide next?",
        "Next decisions",
        "Simple mode shows the top few",
        "Show evidence and routing",
    ):
        assert marker in html, marker


def test_stage19_knowledge_tree_is_obsidian_bridge_first() -> None:
    html = _html()
    assert "Obsidian Bridge first" in html
    assert "Use Obsidian for Graph View, Local Graph, backlinks" in html
    assert "Web graph preview fallback / debug" in html
    assert "The graph is built from real wikilinks" in html


def test_stage19_explain_mode_and_status_dictionary_present() -> None:
    html = _html()
    for marker in (
        "Explain mode: Simple hides technical details",
        "fos_explain_mode",
        "STATUS_HELP",
        "missing_config",
        "real_disabled",
        "blocked_missing_scope",
        "watermark",
        "receipt",
        "technical-details",
    ):
        assert marker in html, marker


def test_stage19_founder_ui_does_not_restore_finance_surface() -> None:
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
