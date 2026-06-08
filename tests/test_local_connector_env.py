from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.external_connector_config import GITHUB_ENV_KEYS, JIRA_ENV_KEYS
from app.services.local_connector_env import (
    ALLOWLISTED_CONNECTOR_ENV_KEYS,
    ENV_FILE_STATUS_DISABLED,
    ENV_FILE_STATUS_LOADED,
    ENV_FILE_STATUS_MALFORMED,
    ENV_FILE_STATUS_NOT_FOUND,
    ENV_FILE_STATUS_UNSUPPORTED_LINES,
    load_local_connector_environment,
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
    assert result.diagnostics["loaded_allowed_key_count"] == 0
    _assert_diagnostics_safe(result.diagnostics)


def test_env_file_loading_can_be_disabled() -> None:
    result = load_local_connector_environment(
        environ={GITHUB_ENV_KEYS[0]: _unsafe_values()[0]},
        use_connector_env_file=False,
    )

    assert result.environment[GITHUB_ENV_KEYS[0]] == _unsafe_values()[0]
    assert result.diagnostics["env_file_status"] == ENV_FILE_STATUS_DISABLED
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
    assert result.diagnostics["loaded_allowed_key_count"] == len(
        ALLOWLISTED_CONNECTOR_ENV_KEYS
    )
    for key in ALLOWLISTED_CONNECTOR_ENV_KEYS:
        assert key in result.environment
    serialized_diagnostics = json.dumps(result.diagnostics, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized_diagnostics
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
    assert file_value not in json.dumps(result.diagnostics, sort_keys=True)
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
