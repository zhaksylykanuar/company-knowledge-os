#!/usr/bin/env python
"""Read-only ignored/local file cleanup planner."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Mapping
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.operator_output_sanitizer import inspect_operator_output  # noqa: E402

REPORT_KIND = "ignored_file_cleanup_plan"
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
SCHEDULER_DISABLED = "disabled"

CLASS_ENV_SECRET_FILE = "env_secret_file"
CLASS_CACHE_DIRECTORY = "cache_directory"
CLASS_PYTHON_CACHE = "python_cache"
CLASS_NODE_MODULES = "node_modules"
CLASS_BUILD_OUTPUT = "build_output"
CLASS_TEST_ARTIFACT = "test_artifact"
CLASS_TEMP_ARTIFACT = "temp_artifact"
CLASS_LOG_FILE = "log_file"
CLASS_LOCAL_DATABASE = "local_database"
CLASS_RAW_SOURCE_OF_TRUTH_STORE = "raw_source_of_truth_store"
CLASS_OBSIDIAN_VAULT_STORE = "obsidian_vault_store"
CLASS_UNKNOWN_IGNORED = "unknown_ignored"

ACTION_KEEP_LOCAL_SECRET = "keep_local_secret"
ACTION_SAFE_TO_DELETE_CANDIDATE = "safe_to_delete_candidate"
ACTION_REVIEW_BEFORE_DELETE = "review_before_delete"
ACTION_KEEP_CACHE = "keep_cache"
ACTION_IGNORE_RULE_REVIEW = "ignore_rule_review"
ACTION_SOURCE_OF_TRUTH_DO_NOT_TOUCH = "source_of_truth_do_not_touch"

SECRET_MARKERS = ("env", "secret", "token", "credential", "password", "key")
RAW_STORE_PREFIXES = ("raw_storage/", "obsidian_vault/")


def ignored_file_cleanup_plan(
    *,
    ignored_paths: Iterable[str] | None = None,
    repo_root: Path | None = None,
    include_safe_relative_paths: bool = False,
) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    paths = list(ignored_paths) if ignored_paths is not None else _git_local_paths(root)
    classifications = [_classify_ignored_path(path) for path in paths]
    class_counts = Counter(item["ignored_file_class"] for item in classifications)
    action_counts = Counter(item["recommended_action_class"] for item in classifications)

    result = {
        "status": STATUS_PASS,
        "reason_code": None,
        "report_kind": REPORT_KIND,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_DISABLED,
        "ignored_file_count": len(classifications),
        "class_counts": _ordered_counts(class_counts, _ignored_file_classes()),
        "action_class_counts": _ordered_counts(
            action_counts,
            _recommended_action_classes(),
        ),
        "safe_relative_paths_included": include_safe_relative_paths,
        "safe_relative_paths": _safe_relative_paths(classifications)
        if include_safe_relative_paths
        else {},
        "diagnostics": {
            "planner_mode": "metadata_only",
            "content_read_count": 0,
            "delete_operation_count": 0,
            "source_of_truth_store_path_count": sum(
                1 for item in classifications if item["raw_store_related"] is True
            ),
            "secret_like_path_count": class_counts.get(CLASS_ENV_SECRET_FILE, 0),
            "unknown_ignored_count": class_counts.get(CLASS_UNKNOWN_IGNORED, 0),
        },
    }
    if inspect_operator_output(result).safe is not True:
        return _failure_report("ignored_file_cleanup_plan_output_unsafe")
    return result


def _git_local_paths(repo_root: Path) -> list[str]:
    visible_untracked = _git_path_list(
        repo_root,
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
    )
    ignored = _git_path_list(
        repo_root,
        [
            "git",
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
            "--",
            ":!raw_storage/**",
            ":!obsidian_vault/**",
        ],
    )
    source_of_truth_markers = [
        "raw_storage/"
        if (repo_root / "raw_storage").exists()
        else "",
        "obsidian_vault/"
        if (repo_root / "obsidian_vault").exists()
        else "",
    ]
    return sorted(
        {
            path
            for path in [*visible_untracked, *ignored, *source_of_truth_markers]
            if path
        }
    )


def _git_path_list(repo_root: Path, command: list[str]) -> list[str]:
    completed = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return []
    return [
        item.decode("utf-8", errors="ignore")
        for item in completed.stdout.split(b"\0")
        if item
    ]


def _classify_ignored_path(path: str) -> dict[str, Any]:
    normalized = path.replace("\\", "/").strip("/")
    lowered = normalized.casefold()
    raw_store_related = lowered.startswith(RAW_STORE_PREFIXES)
    if lowered.startswith("raw_storage/"):
        file_class = CLASS_RAW_SOURCE_OF_TRUTH_STORE
        action = ACTION_SOURCE_OF_TRUTH_DO_NOT_TOUCH
    elif lowered.startswith("obsidian_vault/"):
        file_class = CLASS_OBSIDIAN_VAULT_STORE
        action = ACTION_SOURCE_OF_TRUTH_DO_NOT_TOUCH
    elif _is_env_or_secret_like(lowered):
        file_class = CLASS_ENV_SECRET_FILE
        action = ACTION_KEEP_LOCAL_SECRET
    elif "__pycache__" in lowered or lowered.endswith(".pyc"):
        file_class = CLASS_PYTHON_CACHE
        action = ACTION_SAFE_TO_DELETE_CANDIDATE
    elif "node_modules/" in lowered or lowered == "node_modules":
        file_class = CLASS_NODE_MODULES
        action = ACTION_KEEP_CACHE
    elif _is_cache_like(lowered):
        file_class = CLASS_CACHE_DIRECTORY
        action = ACTION_KEEP_CACHE
    elif _is_build_like(lowered):
        file_class = CLASS_BUILD_OUTPUT
        action = ACTION_SAFE_TO_DELETE_CANDIDATE
    elif _is_test_artifact_like(lowered):
        file_class = CLASS_TEST_ARTIFACT
        action = ACTION_SAFE_TO_DELETE_CANDIDATE
    elif _is_temp_artifact_like(lowered):
        file_class = CLASS_TEMP_ARTIFACT
        action = ACTION_SAFE_TO_DELETE_CANDIDATE
    elif lowered.endswith(".log"):
        file_class = CLASS_LOG_FILE
        action = ACTION_REVIEW_BEFORE_DELETE
    elif _is_local_database_like(lowered):
        file_class = CLASS_LOCAL_DATABASE
        action = ACTION_REVIEW_BEFORE_DELETE
    else:
        file_class = CLASS_UNKNOWN_IGNORED
        action = ACTION_IGNORE_RULE_REVIEW
    return {
        "ignored_file_class": file_class,
        "recommended_action_class": action,
        "safe_relative_path": normalized
        if _can_include_safe_relative_path(normalized, file_class, raw_store_related)
        else None,
        "raw_store_related": raw_store_related,
    }


def _is_env_or_secret_like(value: str) -> bool:
    name = value.rsplit("/", 1)[-1]
    return (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith(".env")
        or name in {"connectors.env", "local.env", "secrets.env"}
        or any(marker in name for marker in SECRET_MARKERS)
    )


def _is_cache_like(value: str) -> bool:
    return (
        ".cache/" in value
        or value.startswith(".cache/")
        or ".pytest_cache/" in value
        or ".ruff_cache/" in value
        or ".venv/" in value
        or value.startswith(".venv/")
    )


def _is_build_like(value: str) -> bool:
    return value.startswith(("dist/", "build/", "target/")) or "/dist/" in value


def _is_test_artifact_like(value: str) -> bool:
    return "coverage" in value or value.startswith("operator_outputs/")


def _is_temp_artifact_like(value: str) -> bool:
    return value.startswith(("tmp/", "temp/")) or "/tmp/" in value or "/temp/" in value


def _is_local_database_like(value: str) -> bool:
    return value.endswith((".sqlite", ".sqlite3", ".db"))


def _can_include_safe_relative_path(
    path: str,
    file_class: str,
    raw_store_related: bool,
) -> bool:
    if raw_store_related or file_class == CLASS_ENV_SECRET_FILE:
        return False
    return inspect_operator_output({"safe_relative_path": path}).safe is True


def _safe_relative_paths(classifications: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    by_class: dict[str, list[str]] = {class_name: [] for class_name in _ignored_file_classes()}
    for item in classifications:
        path = item.get("safe_relative_path")
        file_class = str(item.get("ignored_file_class", CLASS_UNKNOWN_IGNORED))
        if isinstance(path, str) and path:
            by_class.setdefault(file_class, []).append(path)
    return {key: sorted(values) for key, values in by_class.items() if values}


def _ordered_counts(counter: Counter[str], keys: tuple[str, ...]) -> dict[str, int]:
    return {key: int(counter.get(key, 0)) for key in keys}


def _ignored_file_classes() -> tuple[str, ...]:
    return (
        CLASS_ENV_SECRET_FILE,
        CLASS_CACHE_DIRECTORY,
        CLASS_PYTHON_CACHE,
        CLASS_NODE_MODULES,
        CLASS_BUILD_OUTPUT,
        CLASS_TEST_ARTIFACT,
        CLASS_TEMP_ARTIFACT,
        CLASS_LOG_FILE,
        CLASS_LOCAL_DATABASE,
        CLASS_RAW_SOURCE_OF_TRUTH_STORE,
        CLASS_OBSIDIAN_VAULT_STORE,
        CLASS_UNKNOWN_IGNORED,
    )


def _recommended_action_classes() -> tuple[str, ...]:
    return (
        ACTION_KEEP_LOCAL_SECRET,
        ACTION_SAFE_TO_DELETE_CANDIDATE,
        ACTION_REVIEW_BEFORE_DELETE,
        ACTION_KEEP_CACHE,
        ACTION_IGNORE_RULE_REVIEW,
        ACTION_SOURCE_OF_TRUTH_DO_NOT_TOUCH,
    )


def _failure_report(reason_code: str) -> dict[str, Any]:
    return {
        "status": STATUS_FAIL,
        "reason_code": _safe_reason_code(reason_code),
        "report_kind": REPORT_KIND,
        "no_send": True,
        "no_provider_calls": True,
        "no_source_of_truth_mutation": True,
        "scheduler_execution": SCHEDULER_DISABLED,
        "ignored_file_count": 0,
        "class_counts": _ordered_counts(Counter(), _ignored_file_classes()),
        "action_class_counts": _ordered_counts(
            Counter(),
            _recommended_action_classes(),
        ),
        "safe_relative_paths_included": False,
        "safe_relative_paths": {},
        "diagnostics": {
            "planner_mode": "metadata_only",
            "content_read_count": 0,
            "delete_operation_count": 0,
            "raw_store_path_count": 0,
            "source_of_truth_store_path_count": 0,
            "secret_like_path_count": 0,
            "unknown_ignored_count": 0,
        },
    }


def _safe_reason_code(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in value.casefold()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "ignored_file_cleanup_plan_failed"


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), indent=2, sort_keys=True) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--include-safe-relative-paths", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = ignored_file_cleanup_plan(
        include_safe_relative_paths=args.include_safe_relative_paths,
    )
    print(_json_text(result), end="")
    return 0 if result["status"] == STATUS_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
