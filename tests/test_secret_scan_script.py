from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_no_secrets.sh"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test User")


def _run_scan(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def test_secret_scan_tracked_scans_env_example_content(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    token = "sk-" + "A" * 24
    (tmp_path / ".env.example").write_text(
        f"OPENAI_API_KEY={token}\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".env.example")

    result = _run_scan(tmp_path, "--tracked")

    assert result.returncode == 1
    assert ".env.example" in result.stderr
    assert token not in result.stdout
    assert token not in result.stderr


def test_secret_scan_staged_does_not_print_matched_secret_value(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    token = "ghp_" + "B" * 32
    (tmp_path / "app.py").write_text(f"TOKEN = '{token}'\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")

    result = _run_scan(tmp_path)

    assert result.returncode == 1
    assert "staged diff" in result.stderr
    assert token not in result.stdout
    assert token not in result.stderr


def test_secret_scan_rejects_sensitive_tracked_paths(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / ".env").write_text("PLACEHOLDER=1\n", encoding="utf-8")
    _git(tmp_path, "add", ".env", "--force")

    result = _run_scan(tmp_path, "--tracked")

    assert result.returncode == 1
    assert "tracked secrets or raw data detected: .env" in result.stderr


def test_secret_scan_rejects_local_only_output_paths(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    output_path = tmp_path / "operator_outputs" / "review.json"
    output_path.parent.mkdir()
    output_path.write_text('{"status": "local-only"}\n', encoding="utf-8")
    vault_path = tmp_path / "obsidian_vault" / "note.md"
    vault_path.parent.mkdir()
    vault_path.write_text("local vault note\n", encoding="utf-8")
    _git(tmp_path, "add", "operator_outputs/review.json", "--force")

    staged_result = _run_scan(tmp_path)

    assert staged_result.returncode == 1
    assert "operator_outputs/review.json" in staged_result.stderr

    _git(tmp_path, "reset")
    _git(tmp_path, "add", "obsidian_vault/note.md", "--force")

    tracked_result = _run_scan(tmp_path, "--tracked")

    assert tracked_result.returncode == 1
    assert "obsidian_vault/note.md" in tracked_result.stderr


def test_secret_scan_rejects_invalid_mode(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    result = _run_scan(tmp_path, "--everything")

    assert result.returncode == 2
    assert "Usage:" in result.stderr
