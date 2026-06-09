#!/usr/bin/env python3
"""Safe local operator runtime health check.

The check reports key presence and readiness metadata only. It never prints
environment values, credential paths, token paths, database URLs, queries, IDs,
or raw content.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any


OPERATOR_ENV_FILE = ".env"

BOOLEAN_KEYS = {
    "API_AUTH_ENABLED",
    "ENABLE_LLM",
    "ENABLE_OBSIDIAN_EXPORT",
    "ENABLE_WRITE_ACTIONS",
    "GOOGLE_DRIVE_BACKFILL_ENABLED",
    "GOOGLE_GMAIL_BACKFILL_ENABLED",
    "REQUIRE_APPROVAL_FOR_WRITES",
}

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}

PATH_KEY_TYPES = {
    "GOOGLE_CLIENT_SECRETS_FILE": "file",
    "GOOGLE_GMAIL_TOKEN_FILE": "file",
    "GOOGLE_TOKEN_FILE": "file",
    "OBSIDIAN_VAULT_PATH": "dir",
    "RAW_STORAGE_DIR": "dir",
}

BROAD_GMAIL_QUERY = "in:inbox OR in:sent"

MODE_CONFIG: dict[str, dict[str, Any]] = {
    "fos036": {
        "required": [
            "API_BASE_URL",
            "API_AUTH_ENABLED",
            "API_AUTH_KEY",
            "API_AUTH_HEADER_NAME",
            "GOOGLE_GMAIL_BACKFILL_ENABLED",
            "GOOGLE_GMAIL_BACKFILL_QUERY",
        ],
        "optional": [
            "DATABASE_URL",
            "RAW_STORAGE_DIR",
            "GOOGLE_CLIENT_SECRETS_FILE",
            "GOOGLE_GMAIL_TOKEN_FILE",
        ],
        "expected_booleans": {
            "API_AUTH_ENABLED": True,
            "GOOGLE_GMAIL_BACKFILL_ENABLED": True,
        },
        "required_existing_paths": [],
    },
    "google": {
        "required": [
            "API_BASE_URL",
            "API_AUTH_ENABLED",
            "API_AUTH_KEY",
            "API_AUTH_HEADER_NAME",
            "DATABASE_URL",
            "RAW_STORAGE_DIR",
            "GOOGLE_CLIENT_SECRETS_FILE",
            "GOOGLE_GMAIL_TOKEN_FILE",
            "GOOGLE_TOKEN_FILE",
            "GOOGLE_GMAIL_BACKFILL_ENABLED",
            "GOOGLE_GMAIL_BACKFILL_QUERY",
            "GOOGLE_DRIVE_BACKFILL_ENABLED",
            "GOOGLE_DRIVE_AI_INBOX_FOLDER_ID",
        ],
        "optional": [
            "GOOGLE_PUBSUB_TOPIC",
            "GOOGLE_PUBSUB_SUBSCRIPTION",
            "OBSIDIAN_VAULT_PATH",
        ],
        "expected_booleans": {
            "API_AUTH_ENABLED": True,
            "GOOGLE_GMAIL_BACKFILL_ENABLED": True,
            "GOOGLE_DRIVE_BACKFILL_ENABLED": True,
        },
        "required_existing_paths": [
            "GOOGLE_CLIENT_SECRETS_FILE",
            "GOOGLE_GMAIL_TOKEN_FILE",
            "GOOGLE_TOKEN_FILE",
        ],
    },
    "full": {
        "required": [
            "API_BASE_URL",
            "API_AUTH_ENABLED",
            "API_AUTH_KEY",
            "API_AUTH_HEADER_NAME",
            "DATABASE_URL",
            "RAW_STORAGE_DIR",
            "GOOGLE_CLIENT_SECRETS_FILE",
            "GOOGLE_GMAIL_TOKEN_FILE",
            "GOOGLE_TOKEN_FILE",
            "GOOGLE_GMAIL_BACKFILL_ENABLED",
            "GOOGLE_GMAIL_BACKFILL_QUERY",
            "GOOGLE_DRIVE_BACKFILL_ENABLED",
            "GOOGLE_DRIVE_AI_INBOX_FOLDER_ID",
            "ENABLE_LLM",
            "OPENAI_API_KEY",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
        ],
        "optional": [
            "ENABLE_OBSIDIAN_EXPORT",
            "ENABLE_WRITE_ACTIONS",
            "GOOGLE_PUBSUB_TOPIC",
            "GOOGLE_PUBSUB_SUBSCRIPTION",
            "MODEL_CONFIG",
            "OBSIDIAN_VAULT_PATH",
            "REDIS_URL",
            "REQUIRE_APPROVAL_FOR_WRITES",
            "TELEGRAM_WEBHOOK_SECRET_TOKEN",
        ],
        "expected_booleans": {
            "API_AUTH_ENABLED": True,
            "ENABLE_LLM": True,
            "GOOGLE_GMAIL_BACKFILL_ENABLED": True,
            "GOOGLE_DRIVE_BACKFILL_ENABLED": True,
        },
        "required_existing_paths": [
            "GOOGLE_CLIENT_SECRETS_FILE",
            "GOOGLE_GMAIL_TOKEN_FILE",
            "GOOGLE_TOKEN_FILE",
        ],
    },
}


def _parse_operator_env_file(path: Path) -> tuple[dict[str, str], bool, bool]:
    if not path.exists():
        return {}, False, True

    values: dict[str, str] = {}
    parse_ok = True
    key_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        try:
            tokens = shlex.split(raw_line, comments=True, posix=True)
        except ValueError:
            parse_ok = False
            continue

        if not tokens:
            continue

        if tokens[0] == "export":
            tokens = tokens[1:]

        if len(tokens) != 1 or "=" not in tokens[0]:
            parse_ok = False
            continue

        key, value = tokens[0].split("=", 1)
        if not key_pattern.match(key):
            parse_ok = False
            continue

        values[key] = value

    return values, True, parse_ok


def _configured_value(key: str, file_values: dict[str, str]) -> str | None:
    if key in os.environ:
        value = os.environ.get(key)
    else:
        value = file_values.get(key)

    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


def _is_present(key: str, file_values: dict[str, str]) -> bool:
    return _configured_value(key, file_values) is not None


def _parse_bool(value: str | None) -> tuple[bool, bool | None]:
    if value is None:
        return False, None

    normalized = value.strip().casefold()
    if normalized in TRUE_VALUES:
        return True, True
    if normalized in FALSE_VALUES:
        return True, False
    return False, None


def _looks_like_placeholder(value: str | None) -> bool:
    if value is None:
        return False

    normalized = value.strip().casefold()
    return (
        normalized.startswith("<")
        or "placeholder" in normalized
        or "replace" in normalized
        or "change-me" in normalized
        or "changeme" in normalized
        or "yyyy/" in normalized
        or "example.com" in normalized
    )


def _normalized_query(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _path_exists(key: str, value: str | None) -> bool:
    if value is None:
        return False

    try:
        path = Path(value).expanduser()
        path_type = PATH_KEY_TYPES[key]
        if path_type == "file":
            return path.is_file()
        if path_type == "dir":
            return path.is_dir()
    except (OSError, RuntimeError, ValueError):
        return False

    return False


def _build_report(mode: str) -> dict[str, Any]:
    config = MODE_CONFIG[mode]
    env_path = Path(OPERATOR_ENV_FILE)
    file_values, operator_env_file_present, operator_env_file_parse_ok = _parse_operator_env_file(
        env_path
    )

    required_keys: list[str] = config["required"]
    optional_keys: list[str] = config["optional"]
    all_reported_keys = sorted(set(required_keys) | set(optional_keys))

    required_presence = {key: _is_present(key, file_values) for key in required_keys}
    optional_presence = {key: _is_present(key, file_values) for key in optional_keys}
    missing_required_keys = [key for key, present in required_presence.items() if not present]

    boolean_parse_status = {}
    invalid_boolean_keys = []
    boolean_expectations = {}
    boolean_expectation_failures = []
    expected_booleans: dict[str, bool] = config["expected_booleans"]

    for key in sorted(BOOLEAN_KEYS & set(all_reported_keys)):
        value = _configured_value(key, file_values)
        valid, parsed = _parse_bool(value)
        present = value is not None
        boolean_parse_status[key] = {
            "present": present,
            "valid": valid if present else False,
        }
        if present and not valid:
            invalid_boolean_keys.append(key)

        if key in expected_booleans:
            expected_value = expected_booleans[key]
            matches = valid and parsed is expected_value
            boolean_expectations[key] = {
                "expected": expected_value,
                "matches": matches,
            }
            if not matches:
                boolean_expectation_failures.append(key)

    placeholder_value_keys = [
        key for key in required_keys if _looks_like_placeholder(_configured_value(key, file_values))
    ]

    path_checks = {}
    path_failures = []
    required_existing_paths: list[str] = config["required_existing_paths"]
    for key in sorted(PATH_KEY_TYPES.keys() & set(all_reported_keys)):
        value = _configured_value(key, file_values)
        configured = value is not None
        exists = _path_exists(key, value)
        path_checks[key] = {
            "configured": configured,
            "exists": exists,
            "required_to_exist": key in required_existing_paths,
            "type": PATH_KEY_TYPES[key],
        }
        if key in required_existing_paths and not exists:
            path_failures.append(key)

    gmail_query_value = _configured_value("GOOGLE_GMAIL_BACKFILL_QUERY", file_values)
    gmail_query_checks = {
        "configured": gmail_query_value is not None,
        "not_known_broad_query": _normalized_query(gmail_query_value)
        != _normalized_query(BROAD_GMAIL_QUERY),
    }
    unsafe_query_keys = []
    if "GOOGLE_GMAIL_BACKFILL_QUERY" in required_keys and (
        not gmail_query_checks["configured"] or not gmail_query_checks["not_known_broad_query"]
    ):
        unsafe_query_keys.append("GOOGLE_GMAIL_BACKFILL_QUERY")

    blocked = (
        bool(missing_required_keys)
        or not operator_env_file_parse_ok
        or bool(invalid_boolean_keys)
        or bool(boolean_expectation_failures)
        or bool(placeholder_value_keys)
        or bool(path_failures)
        or bool(unsafe_query_keys)
    )

    return {
        "mode": mode,
        "operator_env_file_present": operator_env_file_present,
        "operator_env_file_parse_ok": operator_env_file_parse_ok,
        "required": required_presence,
        "optional": optional_presence,
        "missing_required_keys": missing_required_keys,
        "boolean_parse_status": boolean_parse_status,
        "boolean_expectations": boolean_expectations,
        "invalid_boolean_keys": invalid_boolean_keys,
        "boolean_expectation_failures": boolean_expectation_failures,
        "placeholder_value_keys": placeholder_value_keys,
        "path_checks": path_checks,
        "path_failures": path_failures,
        "safe_value_checks": {
            "GOOGLE_GMAIL_BACKFILL_QUERY": gmail_query_checks,
        },
        "unsafe_value_keys": unsafe_query_keys,
        "status": "blocked" if blocked else "ready",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(MODE_CONFIG), default="fos036")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = _build_report(args.mode)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
