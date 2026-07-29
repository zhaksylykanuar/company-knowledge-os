from __future__ import annotations

from pathlib import Path
import stat


ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_private_repository_governance_files_are_present() -> None:
    for relative in (
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        ".github/CODEOWNERS",
        ".githooks/pre-commit",
    ):
        assert (ROOT / relative).is_file(), relative

    license_text = _text("LICENSE").casefold()
    assert "private and proprietary" in license_text
    assert "no license is granted" in license_text

    security = _text("SECURITY.md").casefold()
    assert "do not open a public issue" in security
    assert "private, verified channel" in security

    assert _text(".github/CODEOWNERS").splitlines()[-1] == "* @zhaksylykanuar"


def test_pre_commit_hook_enforces_local_quality_and_secret_gates() -> None:
    hook_path = ROOT / ".githooks/pre-commit"
    assert hook_path.stat().st_mode & stat.S_IXUSR
    hook = _text(".githooks/pre-commit")
    for required in (
        "scripts/check_no_secrets.sh --staged",
        "git diff --cached --check",
        "uv run ruff check .",
        "uv run mypy app",
        "npm run typecheck",
        "npm run lint",
    ):
        assert required in hook


def test_makefile_exposes_governance_and_disaster_recovery_controls() -> None:
    makefile = _text("Makefile")
    for target in (
        "hooks-install:",
        "offsite-recovery-key-init:",
        "offsite-target-init:",
        "offsite-backup:",
        "offsite-restore-drill:",
        "offsite-retention-dry-run:",
        "offsite-retention-apply:",
    ):
        assert target in makefile
