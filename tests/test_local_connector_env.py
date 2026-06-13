from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.services.external_connector_config import GITHUB_ENV_KEYS, JIRA_ENV_KEYS
from app.services.local_connector_env import (
    ALLOWLISTED_CONNECTOR_ENV_KEYS,
    CANONICAL_CONNECTOR_ENV_KEYS,
    ENV_FILE_STATUS_DISABLED,
    ENV_FILE_STATUS_LOADED,
    ENV_FILE_STATUS_MALFORMED,
    ENV_FILE_STATUS_NOT_FOUND,
    ENV_FILE_STATUS_UNSUPPORTED_LINES,
    OPTIONAL_CONNECTOR_ENV_KEYS,
    REQUIRED_CONNECTOR_ENV_KEYS,
    SOURCE_CLASS_EXPLICIT_OVERRIDE,
    SOURCE_CLASS_NONE,
    SOURCE_CLASS_PROJECT_LOCAL,
    SOURCE_CLASS_USER_CONFIG,
    load_local_connector_environment,
    reconcile_project_local_env_file,
)
from app.services.operator_output_sanitizer import inspect_operator_output


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://local-env.invalid/path",
        "operator" + "@" + "local-env.invalid",
        "bot_token local env value",
        "a" * 64,
        "postgres" + "://local-env.invalid/db",
        "provider_payload local env body",
        "source_object_id local env body",
        "rendered_digest_text local env body",
        "grouped_preview_text local env body",
        "chunk_text local env body",
        "item_title local env body",
    )


def _assert_no_raw_unsafe_values(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized


def _assert_diagnostics_safe(value: Any) -> None:
    assert inspect_operator_output(value).safe is True
    _assert_no_raw_unsafe_values(value)


def _write_connector_env(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_missing_env_file_is_safe_and_does_not_fail(tmp_path: Path) -> None:
    result = load_local_connector_environment(
        environ={},
        connector_env_file=tmp_path / "missing.env",
    )

    assert result.environment == {}
    assert result.diagnostics["env_file_status"] == ENV_FILE_STATUS_NOT_FOUND
    assert result.diagnostics["env_file_source_class"] == SOURCE_CLASS_EXPLICIT_OVERRIDE
    assert result.diagnostics["loaded_allowed_key_count"] == 0
    _assert_diagnostics_safe(result.diagnostics)


def test_env_file_loading_can_be_disabled() -> None:
    result = load_local_connector_environment(
        environ={GITHUB_ENV_KEYS[0]: _unsafe_values()[0]},
        use_connector_env_file=False,
    )

    assert result.environment[GITHUB_ENV_KEYS[0]] == _unsafe_values()[0]
    assert result.diagnostics["env_file_status"] == ENV_FILE_STATUS_DISABLED
    assert result.diagnostics["env_file_source_class"] == SOURCE_CLASS_NONE
    _assert_diagnostics_safe(result.diagnostics)


def test_missing_project_and_user_env_files_are_safe(tmp_path: Path) -> None:
    result = load_local_connector_environment(
        environ={},
        project_env_file=tmp_path / ".env",
        user_config_env_file=tmp_path / "connectors.env",
    )

    assert result.environment == {}
    assert result.diagnostics["env_file_status"] == ENV_FILE_STATUS_NOT_FOUND
    assert result.diagnostics["env_file_source_class"] == SOURCE_CLASS_NONE
    assert result.diagnostics["required_missing_count"] == len(REQUIRED_CONNECTOR_ENV_KEYS)
    assert result.diagnostics["optional_missing_count"] == len(OPTIONAL_CONNECTOR_ENV_KEYS)
    _assert_diagnostics_safe(result.diagnostics)


def test_synthetic_env_file_loads_allowed_keys_without_value_diagnostics(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "connectors.env"
    _write_connector_env(
        env_file,
        [
            f"{key}={_unsafe_values()[index % len(_unsafe_values())]}"
            for index, key in enumerate(ALLOWLISTED_CONNECTOR_ENV_KEYS)
        ],
    )

    result = load_local_connector_environment(environ={}, connector_env_file=env_file)

    assert result.diagnostics["env_file_status"] == ENV_FILE_STATUS_LOADED
    assert result.diagnostics["env_file_source_class"] == SOURCE_CLASS_EXPLICIT_OVERRIDE
    assert result.diagnostics["loaded_allowed_key_count"] == len(
        ALLOWLISTED_CONNECTOR_ENV_KEYS
    )
    assert result.diagnostics["required_present_count"] == len(REQUIRED_CONNECTOR_ENV_KEYS)
    assert result.diagnostics["optional_present_count"] == len(OPTIONAL_CONNECTOR_ENV_KEYS)
    for key in ALLOWLISTED_CONNECTOR_ENV_KEYS:
        assert key in result.environment
    serialized_diagnostics = json.dumps(result.diagnostics, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized_diagnostics
    _assert_diagnostics_safe(result.diagnostics)


def test_synthetic_project_env_is_preferred_over_user_config(tmp_path: Path) -> None:
    project_env = tmp_path / ".env"
    user_env = tmp_path / "connectors.env"
    _write_connector_env(project_env, [f"{GITHUB_ENV_KEYS[0]}=project_value"])
    _write_connector_env(user_env, [f"{JIRA_ENV_KEYS[0]}=user_value"])

    result = load_local_connector_environment(
        environ={},
        project_env_file=project_env,
        user_config_env_file=user_env,
    )

    assert result.diagnostics["env_file_status"] == ENV_FILE_STATUS_LOADED
    assert result.diagnostics["env_file_source_class"] == SOURCE_CLASS_PROJECT_LOCAL
    assert GITHUB_ENV_KEYS[0] in result.environment
    assert JIRA_ENV_KEYS[0] not in result.environment
    assert "project_value" not in json.dumps(result.diagnostics, sort_keys=True)
    _assert_diagnostics_safe(result.diagnostics)


def test_user_config_fallback_still_loads_when_project_env_missing(
    tmp_path: Path,
) -> None:
    user_env = tmp_path / "connectors.env"
    _write_connector_env(user_env, [f"{JIRA_ENV_KEYS[0]}=user_value"])

    result = load_local_connector_environment(
        environ={},
        project_env_file=tmp_path / ".env",
        user_config_env_file=user_env,
    )

    assert result.diagnostics["env_file_status"] == ENV_FILE_STATUS_LOADED
    assert result.diagnostics["env_file_source_class"] == SOURCE_CLASS_USER_CONFIG
    assert JIRA_ENV_KEYS[0] in result.environment
    assert "user_value" not in json.dumps(result.diagnostics, sort_keys=True)
    _assert_diagnostics_safe(result.diagnostics)


def test_shell_environment_values_override_file_values(tmp_path: Path) -> None:
    env_file = tmp_path / "connectors.env"
    shell_value = "shell_hidden_value"
    file_value = _unsafe_values()[0]
    _write_connector_env(env_file, [f"{GITHUB_ENV_KEYS[0]}={file_value}"])

    result = load_local_connector_environment(
        environ={GITHUB_ENV_KEYS[0]: shell_value},
        connector_env_file=env_file,
    )

    assert result.environment[GITHUB_ENV_KEYS[0]] == shell_value
    assert result.diagnostics["loaded_allowed_key_count"] == 0
    assert result.diagnostics["shell_precedence_count"] == 1
    assert result.diagnostics["required_present_count"] == 1
    assert file_value not in json.dumps(result.diagnostics, sort_keys=True)
    _assert_diagnostics_safe(result.diagnostics)


def test_placeholder_and_blank_values_are_treated_as_missing(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _write_connector_env(
        env_file,
        [
            f"{GITHUB_ENV_KEYS[0]}=",
            f"{GITHUB_ENV_KEYS[1]}=<set locally>",
            f"{JIRA_ENV_KEYS[0]}=placeholder",
            f"{JIRA_ENV_KEYS[1]}=<missing>",
            f"{JIRA_ENV_KEYS[2]}=change-me",
        ],
    )

    result = load_local_connector_environment(environ={}, connector_env_file=env_file)

    assert result.diagnostics["env_file_status"] == ENV_FILE_STATUS_LOADED
    assert result.diagnostics["loaded_allowed_key_count"] == 0
    assert result.diagnostics["required_present_count"] == 0
    assert result.diagnostics["required_missing_count"] == len(REQUIRED_CONNECTOR_ENV_KEYS)
    _assert_diagnostics_safe(result.diagnostics)


def test_placeholder_shell_value_does_not_hide_configured_file_value(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    _write_connector_env(env_file, [f"{GITHUB_ENV_KEYS[0]}=configured_file_value"])

    result = load_local_connector_environment(
        environ={GITHUB_ENV_KEYS[0]: "<set locally>"},
        connector_env_file=env_file,
    )

    assert result.environment[GITHUB_ENV_KEYS[0]] == "configured_file_value"
    assert result.diagnostics["loaded_allowed_key_count"] == 1
    assert result.diagnostics["shell_precedence_count"] == 0
    assert result.diagnostics["required_present_count"] == 1
    _assert_diagnostics_safe(result.diagnostics)


def test_unsupported_keys_are_skipped_without_echoing_values(tmp_path: Path) -> None:
    env_file = tmp_path / "connectors.env"
    _write_connector_env(
        env_file,
        [
            f"{GITHUB_ENV_KEYS[0]}=hidden",
            "UNSUPPORTED_CONNECTOR_SECRET=" + _unsafe_values()[1],
        ],
    )

    result = load_local_connector_environment(environ={}, connector_env_file=env_file)

    assert result.diagnostics["env_file_status"] == ENV_FILE_STATUS_UNSUPPORTED_LINES
    assert result.diagnostics["loaded_allowed_key_count"] == 1
    assert result.diagnostics["skipped_key_count"] == 1
    assert "UNSUPPORTED_CONNECTOR_SECRET" not in result.environment
    _assert_diagnostics_safe(result.diagnostics)


def test_malformed_lines_fail_safely_with_counts_only(tmp_path: Path) -> None:
    env_file = tmp_path / "connectors.env"
    _write_connector_env(
        env_file,
        [
            f"{JIRA_ENV_KEYS[0]}=hidden",
            "malformed connector line",
        ],
    )

    result = load_local_connector_environment(environ={}, connector_env_file=env_file)

    assert result.diagnostics["env_file_status"] == ENV_FILE_STATUS_MALFORMED
    assert result.diagnostics["malformed_line_count"] == 1
    assert result.diagnostics["loaded_allowed_key_count"] == 1
    _assert_diagnostics_safe(result.diagnostics)


def test_reconcile_project_env_merges_redundant_env_files_safely(
    tmp_path: Path,
) -> None:
    project_env = tmp_path / ".env"
    local_env = tmp_path / ".env.local"
    operator_env = tmp_path / ".env.operator"
    _write_connector_env(
        project_env,
        [
            f"{GITHUB_ENV_KEYS[0]}=project_wins",
            "LEGACY_LOCAL_KEY=project_legacy_wins",
        ],
    )
    _write_connector_env(
        local_env,
        [
            f"{GITHUB_ENV_KEYS[0]}=local_loses",
            f"{GITHUB_ENV_KEYS[1]}=local_token",
            "LEGACY_LOCAL_KEY=local_legacy_loses",
            "LOCAL_ONLY_KEY=local_only",
        ],
    )
    _write_connector_env(
        operator_env,
        [
            f"{JIRA_ENV_KEYS[0]}=operator_site",
            f"{JIRA_ENV_KEYS[1]}=operator_user",
            f"{JIRA_ENV_KEYS[2]}=operator_token",
        ],
    )

    result = reconcile_project_local_env_file(
        project_env_file=project_env,
        fallback_env_files=[local_env, operator_env],
        remove_redundant_files=True,
    )

    text = project_env.read_text(encoding="utf-8")
    assert local_env.exists() is False
    assert operator_env.exists() is False
    assert "FOS_GITHUB_READONLY_ACCOUNT=project_wins" in text
    assert "FOS_GITHUB_READONLY_TOKEN=local_token" in text
    assert "FOS_JIRA_READONLY_SITE=operator_site" in text
    assert "LEGACY_LOCAL_KEY=project_legacy_wins" in text
    assert "LOCAL_ONLY_KEY=local_only" in text
    assert result.diagnostics["canonical_key_count"] == len(CANONICAL_CONNECTOR_ENV_KEYS)
    assert result.diagnostics["redundant_env_file_removed_count"] == 2
    assert result.diagnostics["env_cleanup_review_required_count"] == 0
    _assert_diagnostics_safe(result.diagnostics)


def test_env_example_contains_placeholders_only() -> None:
    env_example = Path(__file__).resolve().parents[1] / ".env.example"
    text = env_example.read_text(encoding="utf-8")

    assert "<set locally>" in text
    for key in REQUIRED_CONNECTOR_ENV_KEYS:
        assert key in text
    for key in OPTIONAL_CONNECTOR_ENV_KEYS:
        assert key in text
    for raw_value in _unsafe_values():
        assert raw_value not in text
    assert inspect_operator_output(text).safe is True


def test_redundant_env_templates_are_not_present() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / ".env.example").is_file()
    assert not (root / ".env.operator.example").exists()
    assert not (root / "docs" / "examples" / "connectors.env.example").exists()


def test_gitignore_ignores_real_env_files_but_allows_template() -> None:
    root = Path(__file__).resolve().parents[1]
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")

    assert ".env" in gitignore
    assert ".env.*" in gitignore
    assert "*.env" in gitignore
    assert "local.env" in gitignore
    assert "secrets.env" in gitignore
    assert "!.env.example" in gitignore
    assert "!.env.operator.example" not in gitignore
    ignored_files = [
        ".env",
        ".env.local",
        ".env.operator",
        "connectors.env",
        "local.env",
        "secrets.env",
    ]
    for path in ignored_files:
        assert (
            subprocess.run(
                ["git", "check-ignore", "-q", path],
                cwd=root,
                check=False,
            ).returncode
            == 0
        )
    assert (
        subprocess.run(
            ["git", "check-ignore", "-q", ".env.example"],
            cwd=root,
            check=False,
        ).returncode
        != 0
    )


def test_markdown_docs_use_project_env_as_primary_workflow() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    markdown_paths = [
        root / line
        for line in completed.stdout.splitlines()
        if line and line not in {"NOTES.md", "docs/dev-env.md"}
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in markdown_paths)

    assert ".env.operator" not in combined
    assert ".env.local" not in combined
    assert "docs/examples/connectors.env.example" not in combined
    assert "examples/connectors.env.example" not in combined

    operator_setup = (root / "docs" / "operator_runtime_setup.md").read_text(
        encoding="utf-8"
    )
    assert "project root `.env`" in operator_setup
    assert ".env.example" in operator_setup
