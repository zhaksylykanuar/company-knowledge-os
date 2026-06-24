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
