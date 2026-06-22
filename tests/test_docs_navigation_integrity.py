from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
BACKTICKED_MD_RE = re.compile(r"`([^`]+\.md)`")


def _referenced_markdown_paths(path: Path) -> set[Path]:
    text = path.read_text(encoding="utf-8")
    refs: set[Path] = set()
    for pattern in (MARKDOWN_LINK_RE, BACKTICKED_MD_RE):
        for raw in pattern.findall(text):
            if "://" in raw or raw.startswith("#"):
                continue
            if not raw.endswith(".md"):
                continue
            refs.add((path.parent / raw).resolve())
    return refs


def _collapsed_markdown_text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_docs_index_markdown_references_exist() -> None:
    missing = sorted(
        str(ref.relative_to(ROOT))
        for ref in _referenced_markdown_paths(ROOT / "docs" / "index.md")
        if not ref.exists()
    )

    assert missing == []


def test_readme_markdown_references_exist() -> None:
    missing = sorted(
        str(ref.relative_to(ROOT))
        for ref in _referenced_markdown_paths(ROOT / "README.md")
        if not ref.exists()
    )

    assert missing == []


def test_tracked_files_do_not_include_local_desktop_artifacts() -> None:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    offenders = [
        path
        for path in result.stdout.splitlines()
        if path.endswith(".DS_Store") or "/.DS_Store/" in path
    ]

    assert offenders == []


def test_feature_docs_separate_current_contract_from_history() -> None:
    attention = (ROOT / "docs" / "features" / "attention.md").read_text(encoding="utf-8")
    telegram = (ROOT / "docs" / "features" / "telegram-digest.md").read_text(
        encoding="utf-8"
    )
    collapsed_attention = _collapsed_markdown_text(
        ROOT / "docs" / "features" / "attention.md"
    )
    collapsed_telegram = _collapsed_markdown_text(
        ROOT / "docs" / "features" / "telegram-digest.md"
    )

    assert "## Historical Implementation Ledger (Archived)" in attention
    assert "not the current feature contract" in collapsed_attention
    assert "## Historical Implementation Ledger (Archived)" in telegram
    assert "not the current status source" in collapsed_telegram
    assert "\n## Current Status\n" not in telegram
    assert "Historical implemented slices:" in telegram


def test_docs_make_current_vs_target_boundaries_explicit() -> None:
    docs_index = _collapsed_markdown_text(ROOT / "docs" / "index.md")
    manual_pilot = _collapsed_markdown_text(ROOT / "docs" / "runbooks" / "manual-pilot.md")
    attention = _collapsed_markdown_text(ROOT / "docs" / "features" / "attention.md")
    telegram = _collapsed_markdown_text(
        ROOT / "docs" / "features" / "telegram-digest.md"
    )
    knowledge_graph = _collapsed_markdown_text(
        ROOT / "docs" / "features" / "knowledge-graph.md"
    )
    gmail = _collapsed_markdown_text(ROOT / "docs" / "features" / "gmail.md")
    drive = _collapsed_markdown_text(ROOT / "docs" / "features" / "drive.md")

    assert "Current Truth vs Target Direction" in docs_index
    assert "Historical traceability" in docs_index
    assert "Synthetic dry run" in manual_pilot
    assert "Current daily founder digest v2 loop" in manual_pilot
    assert "not a production scheduler" in manual_pilot
    assert "Production target gaps" in attention
    assert "Legacy manual text MVP still supported" in telegram
    assert "Source Inputs: Current vs Target" in telegram
    assert "Current Implementation Status" in knowledge_graph
    assert "does not wire a real Gmail client" in gmail
    assert "does not wire a real Drive client" in drive
