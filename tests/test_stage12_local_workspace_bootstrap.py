from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from app.core.config import Settings
import scripts.bootstrap_local_workspace as bootstrap_module
from scripts.bootstrap_local_workspace import (
    LOCAL_DIRS,
    MANAGED_END,
    MANAGED_START,
    LocalWorkspaceBootstrapError,
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
    assert values["RAW_STORAGE_DIR"] == str(tmp_path / ".local" / "raw_storage")
    assert values["FOUNDEROS_SECRET_ENCRYPTION_KEY"]
    assert values["FOUNDEROS_DEV_API_KEY"] != "local-dev-key"
    assert values["FOUNDEROS_ENABLE_BROWSER_DEV_CONFIG"] == "false"
    assert values["FOUNDEROS_OBSIDIAN_VAULT_PATH"] == str(
        tmp_path / ".local" / "obsidian" / "FounderOS Knowledge Vault"
    )
    assert (tmp_path / ".local" / "migration-log.json").is_file()
    assert (tmp_path / ".env.local").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / ".local").stat().st_mode & 0o777 == 0o700
    assert all((tmp_path / relative).stat().st_mode & 0o777 == 0o700 for relative in LOCAL_DIRS)


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
    assert "local-dev-key" not in values["FOUNDEROS_API_KEYS"]
    assert values["FOUNDEROS_ENABLE_BROWSER_DEV_CONFIG"] == "false"
    assert secret_value not in json.dumps(result)
    assert result["env_updates"]["FOUNDEROS_DEV_API_KEY"] == "***redacted***"
    assert result["env_updates"]["FOUNDEROS_SECRET_ENCRYPTION_KEY"] == "***redacted***"


def test_bootstrap_cli_prints_only_public_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_marker = "private-path-and-secret-marker"

    def fake_bootstrap(*, apply: bool) -> dict[str, object]:
        assert apply is True
        return {
            "status": "applied",
            "repo_root": f"/private/{private_marker}",
            "env_updates": {"SECRET": private_marker},
        }

    monkeypatch.setattr(
        bootstrap_module,
        "bootstrap_local_workspace",
        fake_bootstrap,
    )

    assert bootstrap_module.main(["--apply"]) == 0
    captured = capsys.readouterr()

    assert json.loads(captured.out) == {"status": "applied"}
    assert private_marker not in captured.out
    assert captured.err == ""


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    first = (tmp_path / ".env.local").read_text(encoding="utf-8")
    bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    second = (tmp_path / ".env.local").read_text(encoding="utf-8")
    assert second.count(MANAGED_START) == 1
    assert parse_env_values(second) == parse_env_values(first)


@pytest.mark.parametrize(
    "marker_lines",
    (
        (MANAGED_START, "OLD_MANAGED_VALUE=1"),
        (MANAGED_END,),
        (MANAGED_START, MANAGED_START, MANAGED_END),
        (MANAGED_START, MANAGED_END, MANAGED_END),
        (MANAGED_END, "OLD_MANAGED_VALUE=1", MANAGED_START),
        (MANAGED_START, MANAGED_END, MANAGED_START, MANAGED_END),
    ),
    ids=(
        "unmatched-start",
        "unmatched-end",
        "duplicate-start",
        "duplicate-end",
        "out-of-order",
        "duplicate-pairs",
    ),
)
def test_bootstrap_rejects_invalid_managed_markers_without_touching_env_local(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    marker_lines: tuple[str, ...],
) -> None:
    secret_value = "after-value-that-must-survive"
    original = (
        "USER_SETTING_BEFORE=preserve\r\n"
        + "\r\n".join(marker_lines)
        + f"\r\nUSER_SECRET_AFTER={secret_value}\r\n"
    ).encode()
    env_path = tmp_path / ".env.local"
    env_path.write_bytes(original)

    with pytest.raises(LocalWorkspaceBootstrapError, match="managed block markers") as exc_info:
        bootstrap_local_workspace(repo_root=tmp_path, apply=True)

    captured = capsys.readouterr()
    assert env_path.read_bytes() == original
    assert not (tmp_path / ".local").exists()
    assert "USER_SECRET_AFTER" not in str(exc_info.value)
    assert secret_value not in str(exc_info.value)
    assert "USER_SECRET_AFTER" not in captured.out
    assert "USER_SECRET_AFTER" not in captured.err
    assert secret_value not in captured.out
    assert secret_value not in captured.err


def test_bootstrap_preserves_user_secret_after_well_formed_managed_block(
    tmp_path: Path,
) -> None:
    secret_value = "after-value-that-must-survive"
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            (
                "USER_SETTING_BEFORE=preserve",
                MANAGED_START,
                "OLD_MANAGED_VALUE=1",
                MANAGED_END,
                f"USER_SECRET_AFTER={secret_value}",
                "",
            )
        ),
        encoding="utf-8",
    )

    result = bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    rewritten = env_path.read_text(encoding="utf-8")

    assert rewritten.count(MANAGED_START) == 1
    assert rewritten.count(MANAGED_END) == 1
    assert f"USER_SECRET_AFTER={secret_value}" in rewritten
    assert secret_value not in json.dumps(result)


def test_bootstrap_persists_ambient_encryption_key_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ambient = "ambient-local-encryption-key"
    monkeypatch.setenv("FOUNDEROS_SECRET_ENCRYPTION_KEY", ambient)
    bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    first = parse_env_values((tmp_path / ".env.local").read_text(encoding="utf-8"))
    assert first["FOUNDEROS_SECRET_ENCRYPTION_KEY"] == ambient

    monkeypatch.delenv("FOUNDEROS_SECRET_ENCRYPTION_KEY")
    bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    second = parse_env_values((tmp_path / ".env.local").read_text(encoding="utf-8"))
    assert second["FOUNDEROS_SECRET_ENCRYPTION_KEY"] == ambient


@pytest.mark.parametrize(
    "secret_value",
    (
        "key with spaces # suffix",
        'key-with-"double"-and-\'single\'-quotes',
        "key-with-backslash\\suffix",
        "key-with-line-one\nline-two",
    ),
    ids=("spaces-and-hash", "quotes", "backslash", "newline"),
)
def test_bootstrap_round_trips_special_encryption_keys_through_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    secret_value: str,
) -> None:
    monkeypatch.setenv("FOUNDEROS_SECRET_ENCRYPTION_KEY", secret_value)

    result = bootstrap_local_workspace(repo_root=tmp_path, apply=True)
    monkeypatch.delenv("FOUNDEROS_SECRET_ENCRYPTION_KEY")
    loaded = Settings(_env_file=tmp_path / ".env.local").secret_encryption_key
    effective = loaded.get_secret_value() if hasattr(loaded, "get_secret_value") else loaded
    captured = capsys.readouterr()

    assert effective == secret_value
    assert secret_value not in json.dumps(result)
    assert secret_value not in captured.out
    assert secret_value not in captured.err


def test_bootstrap_rejects_interpolating_secret_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_path = tmp_path / ".env.local"
    original = b"USER_SETTING=preserve-byte-for-byte\n"
    env_path.write_bytes(original)
    secret_value = "literal-${HOME}-must-not-change"
    monkeypatch.setenv("FOUNDEROS_SECRET_ENCRYPTION_KEY", secret_value)

    with pytest.raises(LocalWorkspaceBootstrapError, match="stable dotenv semantics"):
        bootstrap_local_workspace(repo_root=tmp_path, apply=True)

    captured = capsys.readouterr()
    assert env_path.read_bytes() == original
    assert not (tmp_path / ".local").exists()
    assert secret_value not in captured.out
    assert secret_value not in captured.err


def test_bootstrap_promotes_local_api_auth_key_for_existing_ciphertext(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env.local").write_text(
        "API_AUTH_KEY=legacy-local-key\n",
        encoding="utf-8",
    )

    bootstrap_local_workspace(repo_root=tmp_path, apply=True)

    values = parse_env_values((tmp_path / ".env.local").read_text(encoding="utf-8"))
    assert values["FOUNDEROS_SECRET_ENCRYPTION_KEY"] == "legacy-local-key"


def test_bootstrap_refuses_legacy_api_auth_key_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env.local").write_text(
        "API_AUTH_KEY=file-legacy-key\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("API_AUTH_KEY", "different-shell-key")

    with pytest.raises(LocalWorkspaceBootstrapError, match="API_AUTH_KEY differs"):
        bootstrap_local_workspace(repo_root=tmp_path, apply=True)


def test_bootstrap_refuses_ambient_encryption_key_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env.local").write_text(
        "FOUNDEROS_SECRET_ENCRYPTION_KEY=file-key\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FOUNDEROS_SECRET_ENCRYPTION_KEY", "different-shell-key")

    with pytest.raises(LocalWorkspaceBootstrapError, match="differs"):
        bootstrap_local_workspace(repo_root=tmp_path, apply=True)


def test_bootstrap_preserves_legacy_raw_storage_without_moving_it(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "raw_storage"
    legacy.mkdir()
    (legacy / "evidence.json").write_text("{}\n", encoding="utf-8")

    bootstrap_local_workspace(repo_root=tmp_path, apply=True)

    values = parse_env_values((tmp_path / ".env.local").read_text(encoding="utf-8"))
    assert values["RAW_STORAGE_DIR"] == str(legacy)
    assert (legacy / "evidence.json").is_file()
    assert legacy.stat().st_mode & 0o777 == 0o700


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
