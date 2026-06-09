from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output
from scripts import report_ignored_file_cleanup_plan as planner

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "report_ignored_file_cleanup_plan.py"


def _unsafe_values() -> tuple[str, ...]:
    return (
        "https" + "://ignored.invalid/path",
        "operator" + "@" + "ignored.invalid",
        "bot_token ignored value",
        "a" * 64,
        "postgres" + "://ignored.invalid/db",
        "provider_payload ignored body",
        "source_object_id ignored body",
        "rendered_digest_text ignored body",
        "grouped_preview_text ignored body",
        "chunk_text ignored body",
        "item_title ignored body",
    )


def _assert_no_raw_unsafe_values(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for raw_value in _unsafe_values():
        assert raw_value not in serialized


def _assert_plan_safe(value: dict[str, Any]) -> None:
    assert value["status"] == "pass"
    assert value["no_send"] is True
    assert value["no_provider_calls"] is True
    assert value["no_source_of_truth_mutation"] is True
    assert value["scheduler_execution"] == "disabled"
    assert value["diagnostics"]["content_read_count"] == 0
    assert value["diagnostics"]["delete_operation_count"] == 0
    assert inspect_operator_output(value).safe is True
    _assert_no_raw_unsafe_values(value)


def test_ignored_file_cleanup_plan_classifies_synthetic_paths_counts_only() -> None:
    result = planner.ignored_file_cleanup_plan(
        ignored_paths=[
            ".env",
            ".env.local",
            "connectors.env",
            ".pytest_cache/state",
            "__pycache__/module.pyc",
            "node_modules/pkg/index.js",
            "dist/app.bundle.js",
            "operator_outputs/report.json",
            "tmp/run/output.txt",
            "logs/app.log",
            "local.sqlite3",
            "misc/local.file",
        ]
    )

    assert result["ignored_file_count"] == 12
    assert result["class_counts"]["env_secret_file"] == 3
    assert result["class_counts"]["cache_directory"] == 1
    assert result["class_counts"]["python_cache"] == 1
    assert result["class_counts"]["node_modules"] == 1
    assert result["class_counts"]["build_output"] == 1
    assert result["class_counts"]["test_artifact"] == 1
    assert result["class_counts"]["temp_artifact"] == 1
    assert result["class_counts"]["log_file"] == 1
    assert result["class_counts"]["local_database"] == 1
    assert result["class_counts"]["unknown_ignored"] == 1
    assert result["safe_relative_paths"] == {}
    _assert_plan_safe(result)


def test_ignored_file_cleanup_plan_never_prints_secret_like_paths() -> None:
    secret_path = "private/secret_token.env"
    result = planner.ignored_file_cleanup_plan(
        ignored_paths=[secret_path, "build/safe.js"],
        include_safe_relative_paths=True,
    )

    serialized = json.dumps(result, sort_keys=True)
    assert result["class_counts"]["env_secret_file"] == 1
    assert secret_path not in serialized
    assert result["safe_relative_paths"]["build_output"] == ["build/safe.js"]
    _assert_plan_safe(result)


def test_ignored_file_cleanup_plan_marks_raw_store_paths_without_printing() -> None:
    result = planner.ignored_file_cleanup_plan(
        ignored_paths=["raw_storage/local.env", "obsidian_vault/cache.txt"],
        include_safe_relative_paths=True,
    )

    serialized = json.dumps(result, sort_keys=True)
    assert result["diagnostics"]["source_of_truth_store_path_count"] == 2
    assert result["class_counts"]["raw_source_of_truth_store"] == 1
    assert result["class_counts"]["obsidian_vault_store"] == 1
    assert result["action_class_counts"]["source_of_truth_do_not_touch"] == 2
    assert "raw_storage/local.env" not in serialized
    assert "obsidian_vault/cache.txt" not in serialized
    _assert_plan_safe(result)


def test_ignored_file_cleanup_plan_source_does_not_read_or_delete_contents() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    blocked_markers = (
        ".read_text(",
        ".read_bytes(",
        "open(",
        "unlink(",
        "remove(",
        "rmtree(",
    )
    for marker in blocked_markers:
        assert marker not in source


def test_ignored_file_cleanup_plan_cli_outputs_strict_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["report_kind"] == "ignored_file_cleanup_plan"
    assert payload["safe_relative_paths_included"] is False
    assert payload["safe_relative_paths"] == {}
    _assert_plan_safe(payload)
