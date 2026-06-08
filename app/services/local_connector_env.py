from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Any

from app.services.external_connector_config import GITHUB_ENV_KEYS, JIRA_ENV_KEYS

DEFAULT_CONNECTOR_ENV_PATH = (
    Path.home() / ".config" / "company-knowledge-os" / "connectors.env"
)
ALLOWLISTED_CONNECTOR_ENV_KEYS = tuple(sorted((*GITHUB_ENV_KEYS, *JIRA_ENV_KEYS)))

ENV_FILE_STATUS_DISABLED = "disabled"
ENV_FILE_STATUS_LOADED = "loaded"
ENV_FILE_STATUS_MALFORMED = "malformed"
ENV_FILE_STATUS_NOT_FOUND = "not_found"
ENV_FILE_STATUS_UNSAFE_PERMISSIONS = "unsafe_permissions"
ENV_FILE_STATUS_UNSUPPORTED_LINES = "unsupported_lines"

PATH_LABEL_DEFAULT = "default_connector_env_file"
PATH_LABEL_EXPLICIT = "explicit_connector_env_file"
PATH_LABEL_DISABLED = "disabled"


@dataclass(frozen=True)
class LocalConnectorEnvResult:
    environment: Mapping[str, str]
    diagnostics: Mapping[str, Any]


def load_local_connector_environment(
    *,
    environ: Mapping[str, str] | None = None,
    connector_env_file: str | Path | None = None,
    use_connector_env_file: bool = True,
) -> LocalConnectorEnvResult:
    """Merge allowlisted connector env-file values with shell env.

    Returned diagnostics intentionally expose only safe statuses and counts.
    Shell-provided values take precedence over file-provided values.
    """

    shell_environment = dict(environ if environ is not None else os.environ)
    if not use_connector_env_file:
        return LocalConnectorEnvResult(
            environment=shell_environment,
            diagnostics=_diagnostics(
                status=ENV_FILE_STATUS_DISABLED,
                path_label=PATH_LABEL_DISABLED,
            ),
        )

    path = Path(connector_env_file).expanduser() if connector_env_file else DEFAULT_CONNECTOR_ENV_PATH
    path_label = PATH_LABEL_EXPLICIT if connector_env_file else PATH_LABEL_DEFAULT
    if not path.exists():
        return LocalConnectorEnvResult(
            environment=shell_environment,
            diagnostics=_diagnostics(
                status=ENV_FILE_STATUS_NOT_FOUND,
                path_label=path_label,
            ),
        )
    if not path.is_file():
        return LocalConnectorEnvResult(
            environment=shell_environment,
            diagnostics=_diagnostics(
                status=ENV_FILE_STATUS_MALFORMED,
                path_label=path_label,
                malformed_line_count=1,
            ),
        )
    if _has_unsafe_permissions(path):
        return LocalConnectorEnvResult(
            environment=shell_environment,
            diagnostics=_diagnostics(
                status=ENV_FILE_STATUS_UNSAFE_PERMISSIONS,
                path_label=path_label,
            ),
        )

    parsed = _parse_connector_env_file(path)
    file_environment = {
        key: value for key, value in parsed.allowed_values.items() if key not in shell_environment
    }
    merged_environment = {**file_environment, **shell_environment}
    shell_precedence_count = sum(
        1 for key in parsed.allowed_values if key in shell_environment
    )

    status = ENV_FILE_STATUS_LOADED
    if parsed.malformed_line_count:
        status = ENV_FILE_STATUS_MALFORMED
    elif parsed.unsupported_line_count:
        status = ENV_FILE_STATUS_UNSUPPORTED_LINES

    return LocalConnectorEnvResult(
        environment=merged_environment,
        diagnostics=_diagnostics(
            status=status,
            path_label=path_label,
            loaded_allowed_key_count=len(file_environment),
            skipped_key_count=parsed.unsupported_line_count,
            shell_precedence_count=shell_precedence_count,
            malformed_line_count=parsed.malformed_line_count,
            unsupported_line_count=parsed.unsupported_line_count,
        ),
    )


def connector_env_cli_kwargs(args: Any) -> dict[str, Any]:
    return {
        "connector_env_file": getattr(args, "connector_env_file", None),
        "use_connector_env_file": not bool(
            getattr(args, "no_connector_env_file", False)
        ),
    }


def add_connector_env_file_arguments(parser: Any) -> None:
    parser.add_argument(
        "--connector-env-file",
        help="Load allowlisted connector variables from a local env file.",
    )
    parser.add_argument(
        "--no-connector-env-file",
        action="store_true",
        help="Do not load the default local connector env file.",
    )


@dataclass(frozen=True)
class _ParsedConnectorEnvFile:
    allowed_values: Mapping[str, str]
    unsupported_line_count: int
    malformed_line_count: int


def _parse_connector_env_file(path: Path) -> _ParsedConnectorEnvFile:
    allowed_values: dict[str, str] = {}
    unsupported_line_count = 0
    malformed_line_count = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            malformed_line_count += 1
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not _is_supported_key(key):
            unsupported_line_count += 1
            continue
        allowed_values[key] = _strip_optional_quotes(value.strip())
    return _ParsedConnectorEnvFile(
        allowed_values=allowed_values,
        unsupported_line_count=unsupported_line_count,
        malformed_line_count=malformed_line_count,
    )


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _is_supported_key(key: str) -> bool:
    return key in ALLOWLISTED_CONNECTOR_ENV_KEYS


def _has_unsafe_permissions(path: Path) -> bool:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return True
    return bool(mode & 0o022)


def _diagnostics(
    *,
    status: str,
    path_label: str,
    loaded_allowed_key_count: int = 0,
    skipped_key_count: int = 0,
    shell_precedence_count: int = 0,
    malformed_line_count: int = 0,
    unsupported_line_count: int = 0,
) -> dict[str, Any]:
    return {
        "env_file_status": status,
        "env_file_path_label": path_label,
        "allowlisted_key_count": len(ALLOWLISTED_CONNECTOR_ENV_KEYS),
        "loaded_allowed_key_count": max(0, loaded_allowed_key_count),
        "skipped_key_count": max(0, skipped_key_count),
        "shell_precedence_count": max(0, shell_precedence_count),
        "malformed_line_count": max(0, malformed_line_count),
        "unsupported_line_count": max(0, unsupported_line_count),
        "values_visibility": "hidden",
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
    }
