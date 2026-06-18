from __future__ import annotations

import json
import socket
from pathlib import Path

from scripts.bootstrap_local_workspace import (
    LOCAL_DIRS,
    MANAGED_START,
    bootstrap_local_workspace,
    parse_env_values,
)
from scripts.start_local import port_in_use


def test_bootstrap_creates_directories_and_env_local(tmp_path: Path) -> None:
    result = bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    assert result["status"] == "applied"
    for relative in LOCAL_DIRS:
        assert (tmp_path / relative).is_dir()
    env_text = (tmp_path / ".env.local").read_text(encoding="utf-8")
    assert env_text.count(MANAGED_START) == 1
    values = parse_env_values(env_text)
    assert values["APP_ENV"] == "local"
    assert values["FOUNDEROS_LOCAL_WORKSPACE_PATH"] == str(tmp_path / ".local")
    assert (
        values["FOUNDEROS_OBSIDIAN_VAULT_PATH"]
        == str(tmp_path / ".local" / "obsidian" / "FounderOS Knowledge Vault")
    )
    assert (tmp_path / ".local" / "migration-log.json").is_file()


def test_bootstrap_preserves_existing_secrets_and_masks_output(tmp_path: Path) -> None:
    secret_value = "CUSTOM-SHOULD-STAY-PRIVATE"
    (tmp_path / ".env.local").write_text(
        "\n".join(
            [
                "GITHUB_TOKEN=" + secret_value,
                "FOUNDEROS_DEV_API_KEY=custom-dev-key",
                "FOUNDEROS_API_KEYS=existing-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    env_text = (tmp_path / ".env.local").read_text(encoding="utf-8")
    assert "GITHUB_TOKEN=" + secret_value in env_text
    values = parse_env_values(env_text)
    assert values["FOUNDEROS_DEV_API_KEY"] == "custom-dev-key"
    assert "existing-key" in values["FOUNDEROS_API_KEYS"]
    assert "custom-dev-key" in values["FOUNDEROS_API_KEYS"]
    assert "local-dev-key" in values["FOUNDEROS_API_KEYS"]
    assert secret_value not in json.dumps(result)
    assert result["env_updates"]["FOUNDEROS_DEV_API_KEY"] == "***redacted***"


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    first = (tmp_path / ".env.local").read_text(encoding="utf-8")
    bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    second = (tmp_path / ".env.local").read_text(encoding="utf-8")
    assert second.count(MANAGED_START) == 1
    assert parse_env_values(second) == parse_env_values(first)


def test_bootstrap_dry_run_writes_nothing(tmp_path: Path) -> None:
    result = bootstrap_local_workspace(repo_root=tmp_path, apply=False)
    assert result["status"] == "dry_run"
    assert not (tmp_path / ".local").exists()
    assert not (tmp_path / ".env.local").exists()


def test_bootstrap_migrates_existing_vault_with_conflicts(tmp_path: Path) -> None:
    old_vault = tmp_path / "old vault"
    old_vault.mkdir()
    (old_vault / "Existing.md").write_text("old content\n", encoding="utf-8")
    (old_vault / "Same.md").write_text("same\n", encoding="utf-8")
    new_vault = tmp_path / ".local" / "obsidian" / "FounderOS Knowledge Vault"
    new_vault.mkdir(parents=True)
    (new_vault / "Existing.md").write_text("new content\n", encoding="utf-8")
    (new_vault / "Same.md").write_text("same\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text(
        f"FOUNDEROS_OBSIDIAN_VAULT_PATH={old_vault}\n",
        encoding="utf-8",
    )
    result = bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    assert (old_vault / "Existing.md").exists()
    log = json.loads((tmp_path / ".local" / "migration-log.json").read_text())
    assert log["migrated_from"] == str(old_vault)
    assert "Same.md" in log["skipped_files"]
    assert log["conflicts"]
    conflict_path = new_vault / log["conflicts"][0]["conflict"]
    assert conflict_path.read_text(encoding="utf-8") == "old content\n"
    assert result["migration"]["conflicts"]


def test_gitignore_and_env_example_local_workspace_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".local/" in gitignore
    assert ".env.local" in gitignore
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    assert "FOUNDEROS_LOCAL_WORKSPACE_PATH=<project local workspace path>" in env_example
    assert "/Users/anuarzh/Projects/company-knowledge-os/.local" not in env_example


def test_start_local_port_in_use_helper() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        assert port_in_use("127.0.0.1", port) is True
    assert port_in_use("127.0.0.1", port) is False
