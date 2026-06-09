from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Any

from app.services.external_connector_config import (
    ATLASSIAN_ADMIN_ENV_KEYS,
    GITHUB_ENV_KEYS,
    JIRA_ENV_KEYS,
    JIRA_WRITE_ENV_KEYS,
    is_configured_environment_value,
)

PROJECT_LOCAL_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
USER_CONFIG_CONNECTOR_ENV_PATH = (
    Path.home() / ".config" / "company-knowledge-os" / "connectors.env"
)
DEFAULT_CONNECTOR_ENV_PATH = PROJECT_LOCAL_ENV_PATH
CANONICAL_CONNECTOR_ENV_SECTIONS = (
    ("GitHub read-only", GITHUB_ENV_KEYS),
    ("Jira read-only", JIRA_ENV_KEYS),
    ("Jira write dry-run", JIRA_WRITE_ENV_KEYS),
    ("Atlassian Admin dry-run", ATLASSIAN_ADMIN_ENV_KEYS),
    ("OpenAI", ("FOS_OPENAI_API_KEY",)),
    (
        "Telegram delivery",
        (
            "FOS_TELEGRAM_BOT_TOKEN",
            "FOS_TELEGRAM_CHAT_ID",
        ),
    ),
    (
        "Slack delivery",
        (
            "FOS_SLACK_BOT_TOKEN",
            "FOS_SLACK_CHANNEL_ID",
        ),
    ),
    (
        "Gmail read-only",
        (
            "FOS_GMAIL_READONLY_CLIENT_ID",
            "FOS_GMAIL_READONLY_CLIENT_SECRET",
        ),
    ),
    (
        "Google Drive read-only",
        (
            "FOS_GOOGLE_DRIVE_READONLY_CLIENT_ID",
            "FOS_GOOGLE_DRIVE_READONLY_CLIENT_SECRET",
        ),
    ),
)
CANONICAL_CONNECTOR_ENV_KEYS = tuple(
    key for _, keys in CANONICAL_CONNECTOR_ENV_SECTIONS for key in keys
)
REQUIRED_CONNECTOR_ENV_KEYS = (*GITHUB_ENV_KEYS, *JIRA_ENV_KEYS)
OPTIONAL_CONNECTOR_ENV_KEYS = tuple(
    key for key in CANONICAL_CONNECTOR_ENV_KEYS if key not in REQUIRED_CONNECTOR_ENV_KEYS
)
ALLOWLISTED_CONNECTOR_ENV_KEYS = CANONICAL_CONNECTOR_ENV_KEYS

ENV_FILE_STATUS_DISABLED = "disabled"
ENV_FILE_STATUS_LOADED = "loaded"
ENV_FILE_STATUS_MALFORMED = "malformed"
ENV_FILE_STATUS_NOT_FOUND = "not_found"
ENV_FILE_STATUS_UNSAFE_PERMISSIONS = "unsafe_permissions"
ENV_FILE_STATUS_UNSUPPORTED_LINES = "unsupported_lines"

PATH_LABEL_DEFAULT = "default_connector_env_file"
PATH_LABEL_EXPLICIT = "explicit_connector_env_file"
PATH_LABEL_DISABLED = "disabled"
SOURCE_CLASS_EXPLICIT_OVERRIDE = "explicit_override"
SOURCE_CLASS_NONE = "none"
SOURCE_CLASS_PROJECT_LOCAL = "project_local"
SOURCE_CLASS_USER_CONFIG = "user_config"


@dataclass(frozen=True)
class LocalConnectorEnvResult:
    environment: Mapping[str, str]
    diagnostics: Mapping[str, Any]


@dataclass(frozen=True)
class LocalConnectorEnvReconcileResult:
    diagnostics: Mapping[str, Any]


def load_local_connector_environment(
    *,
    environ: Mapping[str, str] | None = None,
    connector_env_file: str | Path | None = None,
    project_env_file: str | Path | None = None,
    user_config_env_file: str | Path | None = None,
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
                source_class=SOURCE_CLASS_NONE,
                environment=shell_environment,
            ),
        )

    env_path = _resolve_env_path(
        connector_env_file=connector_env_file,
        project_env_file=project_env_file,
        user_config_env_file=user_config_env_file,
    )
    if env_path is None:
        return LocalConnectorEnvResult(
            environment=shell_environment,
            diagnostics=_diagnostics(
                status=ENV_FILE_STATUS_NOT_FOUND,
                path_label=PATH_LABEL_DEFAULT,
                source_class=SOURCE_CLASS_NONE,
                environment=shell_environment,
            ),
        )
    path, path_label, source_class = env_path
    if not path.exists():
        return LocalConnectorEnvResult(
            environment=shell_environment,
            diagnostics=_diagnostics(
                status=ENV_FILE_STATUS_NOT_FOUND,
                path_label=path_label,
                source_class=source_class,
                environment=shell_environment,
            ),
        )
    if not path.is_file():
        return LocalConnectorEnvResult(
            environment=shell_environment,
            diagnostics=_diagnostics(
                status=ENV_FILE_STATUS_MALFORMED,
                path_label=path_label,
                source_class=source_class,
                environment=shell_environment,
                malformed_line_count=1,
            ),
        )
    if _has_unsafe_permissions(path):
        return LocalConnectorEnvResult(
            environment=shell_environment,
            diagnostics=_diagnostics(
                status=ENV_FILE_STATUS_UNSAFE_PERMISSIONS,
                path_label=path_label,
                source_class=source_class,
                environment=shell_environment,
            ),
        )

    parsed = _parse_connector_env_file(path)
    configured_shell_keys = {
        key
        for key, value in shell_environment.items()
        if is_configured_environment_value(value)
    }
    file_environment = {
        key: value
        for key, value in parsed.allowed_values.items()
        if key not in configured_shell_keys
    }
    merged_environment = {**file_environment, **shell_environment}
    for key, value in file_environment.items():
        if not is_configured_environment_value(shell_environment.get(key)):
            merged_environment[key] = value
    shell_precedence_count = sum(
        1 for key in parsed.allowed_values if key in configured_shell_keys
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
            source_class=source_class,
            environment=merged_environment,
            loaded_allowed_key_count=len(file_environment),
            skipped_key_count=parsed.unsupported_line_count,
            shell_precedence_count=shell_precedence_count,
            malformed_line_count=parsed.malformed_line_count,
            unsupported_line_count=parsed.unsupported_line_count,
        ),
    )


def reconcile_project_local_env_file(
    *,
    project_env_file: str | Path,
    fallback_env_files: Iterable[str | Path] = (),
    remove_redundant_files: bool = False,
) -> LocalConnectorEnvReconcileResult:
    """Rebuild a project-local env file without exposing values in diagnostics."""

    project_path = Path(project_env_file).expanduser()
    source_paths = [project_path, *(Path(path).expanduser() for path in fallback_env_files)]
    merged_supported: dict[str, str] = {}
    merged_unsupported: dict[str, str] = {}
    env_like_files_seen_count = 0
    malformed_env_file_count = 0

    parsed_by_path: dict[Path, _ParsedLocalEnvFile] = {}
    for path in source_paths:
        parsed = _parse_local_env_assignments(path)
        parsed_by_path[path] = parsed
        if parsed.present:
            env_like_files_seen_count += 1
        if parsed.malformed_line_count:
            malformed_env_file_count += 1
        for key in ALLOWLISTED_CONNECTOR_ENV_KEYS:
            if (
                key not in merged_supported
                and key in parsed.supported_values
                and is_configured_environment_value(parsed.supported_values[key])
            ):
                merged_supported[key] = parsed.supported_values[key]
        for key in sorted(parsed.unsupported_values):
            if key not in merged_unsupported:
                merged_unsupported[key] = parsed.unsupported_values[key]

    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(
        _project_local_env_text(
            supported_values=merged_supported,
            unsupported_values=merged_unsupported,
        ),
        encoding="utf-8",
    )
    try:
        project_path.chmod(0o600)
    except OSError:
        pass

    redundant_removed_count = 0
    review_required_count = 0
    if remove_redundant_files:
        for path in source_paths[1:]:
            parsed = parsed_by_path[path]
            if not parsed.present:
                continue
            if parsed.malformed_line_count:
                review_required_count += 1
                continue
            path.unlink()
            redundant_removed_count += 1

    diagnostics = {
        "local_env_rebuilt": True,
        "canonical_key_count": len(ALLOWLISTED_CONNECTOR_ENV_KEYS),
        "env_like_files_seen_count": env_like_files_seen_count,
        "supported_value_count": sum(
            1 for key in ALLOWLISTED_CONNECTOR_ENV_KEYS if key in merged_supported
        ),
        "supported_missing_count": sum(
            1 for key in ALLOWLISTED_CONNECTOR_ENV_KEYS if key not in merged_supported
        ),
        "unsupported_local_key_count": len(merged_unsupported),
        "redundant_env_file_removed_count": redundant_removed_count,
        "env_cleanup_review_required_count": review_required_count,
        "malformed_env_file_count": malformed_env_file_count,
        "values_visibility": "hidden",
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
    }
    return LocalConnectorEnvReconcileResult(diagnostics=diagnostics)


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
        help="Load allowlisted connector variables from an explicit local env file.",
    )
    parser.add_argument(
        "--no-connector-env-file",
        action="store_true",
        help="Do not load the default local connector env file.",
    )


def _resolve_env_path(
    *,
    connector_env_file: str | Path | None,
    project_env_file: str | Path | None,
    user_config_env_file: str | Path | None,
) -> tuple[Path, str, str] | None:
    if connector_env_file is not None:
        path = Path(connector_env_file).expanduser()
        return path, PATH_LABEL_EXPLICIT, SOURCE_CLASS_EXPLICIT_OVERRIDE

    project_path = (
        Path(project_env_file).expanduser()
        if project_env_file is not None
        else PROJECT_LOCAL_ENV_PATH
    )
    if project_path.exists():
        return project_path, PATH_LABEL_DEFAULT, SOURCE_CLASS_PROJECT_LOCAL

    user_config_path = (
        Path(user_config_env_file).expanduser()
        if user_config_env_file is not None
        else USER_CONFIG_CONNECTOR_ENV_PATH
    )
    if user_config_path.exists():
        return user_config_path, PATH_LABEL_DEFAULT, SOURCE_CLASS_USER_CONFIG
    return None


@dataclass(frozen=True)
class _ParsedConnectorEnvFile:
    allowed_values: Mapping[str, str]
    unsupported_line_count: int
    malformed_line_count: int


@dataclass(frozen=True)
class _ParsedLocalEnvFile:
    supported_values: Mapping[str, str]
    unsupported_values: Mapping[str, str]
    malformed_line_count: int
    present: bool


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
        stripped_value = _strip_optional_quotes(value.strip())
        if is_configured_environment_value(stripped_value):
            allowed_values[key] = stripped_value
    return _ParsedConnectorEnvFile(
        allowed_values=allowed_values,
        unsupported_line_count=unsupported_line_count,
        malformed_line_count=malformed_line_count,
    )


def _parse_local_env_assignments(path: Path) -> _ParsedLocalEnvFile:
    supported_values: dict[str, str] = {}
    unsupported_values: dict[str, str] = {}
    malformed_line_count = 0
    if not path.exists() or not path.is_file():
        return _ParsedLocalEnvFile(
            supported_values=supported_values,
            unsupported_values=unsupported_values,
            malformed_line_count=0,
            present=False,
        )
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            malformed_line_count += 1
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "A").isalnum() or key[0].isdigit():
            malformed_line_count += 1
            continue
        stripped_value = _strip_optional_quotes(value.strip())
        if _is_supported_key(key):
            supported_values[key] = stripped_value
        else:
            unsupported_values[key] = stripped_value
    return _ParsedLocalEnvFile(
        supported_values=supported_values,
        unsupported_values=unsupported_values,
        malformed_line_count=malformed_line_count,
        present=True,
    )


def _project_local_env_text(
    *,
    supported_values: Mapping[str, str],
    unsupported_values: Mapping[str, str],
) -> str:
    lines = [
        "# FounderOS project-local operator configuration.",
        "# Values in this file stay local and must never be committed or printed.",
        "# Blank values are treated as missing. Shell environment values override this file.",
        "",
    ]
    for section_name, keys in CANONICAL_CONNECTOR_ENV_SECTIONS:
        lines.append(f"# {section_name}")
        lines.extend(f"{key}={supported_values.get(key, '')}" for key in keys)
        lines.append("")
    lines.append("# Legacy/local extra keys")
    lines.append("# Preserved from older local env files. Keep only if still needed locally.")
    lines.extend(f"{key}={unsupported_values[key]}" for key in sorted(unsupported_values))
    lines.append("")
    return "\n".join(lines)


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
    source_class: str,
    environment: Mapping[str, str],
    loaded_allowed_key_count: int = 0,
    skipped_key_count: int = 0,
    shell_precedence_count: int = 0,
    malformed_line_count: int = 0,
    unsupported_line_count: int = 0,
) -> dict[str, Any]:
    required_present_count = sum(
        1
        for key in REQUIRED_CONNECTOR_ENV_KEYS
        if is_configured_environment_value(environment.get(key))
    )
    optional_present_count = sum(
        1
        for key in OPTIONAL_CONNECTOR_ENV_KEYS
        if is_configured_environment_value(environment.get(key))
    )
    return {
        "env_file_status": status,
        "env_file_path_label": path_label,
        "env_file_source_class": source_class,
        "allowlisted_key_count": len(ALLOWLISTED_CONNECTOR_ENV_KEYS),
        "loaded_allowed_key_count": max(0, loaded_allowed_key_count),
        "skipped_key_count": max(0, skipped_key_count),
        "shell_precedence_count": max(0, shell_precedence_count),
        "required_present_count": required_present_count,
        "required_missing_count": len(REQUIRED_CONNECTOR_ENV_KEYS)
        - required_present_count,
        "optional_present_count": optional_present_count,
        "optional_missing_count": len(OPTIONAL_CONNECTOR_ENV_KEYS)
        - optional_present_count,
        "malformed_line_count": max(0, malformed_line_count),
        "unsupported_line_count": max(0, unsupported_line_count),
        "values_visibility": "hidden",
        "no_send": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": "disabled",
    }
