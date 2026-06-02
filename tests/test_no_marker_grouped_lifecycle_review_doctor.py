from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import doctor_no_marker_grouped_lifecycle_review as doctor_script
from scripts import (
    report_no_marker_persisted_attention_grouped_lifecycle_compatibility as review_script,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "doctor_no_marker_grouped_lifecycle_review.py"
EXPECTED_CHECK_NAMES = {
    "help_contract",
    "synthetic_smoke_contract",
    "review_json_contract",
    "review_exit_codes",
    "sanitized_artifact_output",
    "unsafe_artifact_rejection",
}
UNSAFE_OUTPUT_PATTERNS = (
    "rendered_digest_text",
    "rendered digest text",
    "grouped_preview_text",
    "grouped preview text",
    '"chunk_text":',
    "chunk text",
    "raw_payload",
    "raw payload",
    "provider_payload",
    '"credentials":',
    '"credential":',
    "credential value",
    "webhook",
    "bot_token",
    "chat_id",
    '"source_object_id":',
    "source object id",
    "item_title",
    "item_summary",
    "item_action",
    "author_email",
    "author_name",
    '"evidence_refs": [',
    "remote_url",
    "repository_name",
    "http://",
    "https://",
)


def _assert_safe_output(output: str) -> None:
    lowered = output.casefold()
    for pattern in UNSAFE_OUTPUT_PATTERNS:
        assert pattern not in lowered


RAW_HASH_VALUE_RE = re.compile(r"(?i)(?:sha256[:=_-]?)?[a-f0-9]{64}")


def _raw_hash_value_paths(value: object, path: str = "$") -> list[str]:
    if isinstance(value, str):
        return [path] if RAW_HASH_VALUE_RE.search(value) else []
    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            paths.extend(_raw_hash_value_paths(child, f"{path}.{key}"))
        return paths
    if isinstance(value, list):
        paths = []
        for index, child in enumerate(value):
            paths.extend(_raw_hash_value_paths(child, f"{path}[{index}]"))
        return paths
    return []


def _assert_no_raw_hash_values(value: object) -> None:
    assert _raw_hash_value_paths(value) == []


def _assert_top_level_contract(parsed: dict[str, Any]) -> None:
    assert parsed["mode"] == "grouped_lifecycle_review_doctor"
    assert parsed["status"] in {"pass", "fail"}
    assert parsed["read_only"] is True
    assert parsed["provider_free"] is True
    assert parsed["local_synthetic_only"] is True
    assert parsed["uses_real_local_data"] is False
    assert parsed["enforced"] is False
    assert parsed["semantic_duplicate_claimed"] is False
    assert isinstance(parsed["checks"], list)
    assert isinstance(parsed["summary"], dict)


def _check_by_name(parsed: dict[str, Any], name: str) -> dict[str, Any]:
    for check in parsed["checks"]:
        if check["name"] == name:
            return check
    raise AssertionError(f"missing doctor check: {name}")


def _assert_check_contract(parsed: dict[str, Any]) -> None:
    assert {check["name"] for check in parsed["checks"]} == EXPECTED_CHECK_NAMES
    for check in parsed["checks"]:
        assert set(check) == {"name", "status", "reason_code"}
        assert check["name"] in EXPECTED_CHECK_NAMES
        assert check["status"] in {"pass", "fail"}
        assert check["reason_code"] is None or isinstance(check["reason_code"], str)


def test_doctor_cli_exits_zero_and_outputs_valid_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def forbidden_report(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("doctor must not execute real report building")

    monkeypatch.setattr(
        review_script,
        "build_no_marker_grouped_lifecycle_compatibility_report",
        forbidden_report,
    )

    code = doctor_script.main([])

    assert code == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    parsed = json.loads(captured.out)
    _assert_top_level_contract(parsed)
    assert parsed["status"] == "pass"
    assert parsed["summary"] == {
        "check_count": len(EXPECTED_CHECK_NAMES),
        "passed_count": len(EXPECTED_CHECK_NAMES),
        "failed_count": 0,
    }
    _assert_check_contract(parsed)
    for check_name in EXPECTED_CHECK_NAMES:
        assert _check_by_name(parsed, check_name)["status"] == "pass"
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)


def test_doctor_script_subprocess_exits_zero_with_json_output() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    parsed = json.loads(result.stdout)
    _assert_top_level_contract(parsed)
    assert parsed["status"] == "pass"
    _assert_check_contract(parsed)
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(result.stdout)


def test_doctor_uses_tmp_path_for_sanitized_artifact_check(tmp_path: Path) -> None:
    report = doctor_script.build_doctor_report(artifact_dir=tmp_path)

    assert report["status"] == "pass"
    _assert_top_level_contract(report)
    _assert_check_contract(report)
    artifact_path = tmp_path / "grouped-lifecycle-review-doctor.json"
    assert artifact_path.exists()
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert "lifecycle_compatibility" in artifact_payload
    assert "canonical_hash_guard_evaluation" in artifact_payload
    assert "operator_review_summary" in artifact_payload
    assert artifact_payload["canonical_hash_guard_evaluation"]["enforced"] is False
    assert artifact_payload["operator_review_summary"]["enforced"] is False
    assert (
        artifact_payload["canonical_hash_guard_evaluation"][
            "semantic_duplicate_claimed"
        ]
        is False
    )
    assert (
        artifact_payload["operator_review_summary"]["semantic_duplicate_claimed"]
        is False
    )
    _assert_no_raw_hash_values(report)
    _assert_no_raw_hash_values(artifact_payload)
    _assert_safe_output(json.dumps(report, sort_keys=True))
    artifact_output = (
        artifact_path.read_text(encoding="utf-8")
        .replace("grouped_preview_text_sha256", "")
        .replace("grouped_preview_text_included", "")
    )
    _assert_safe_output(artifact_output)


def test_doctor_check_output_covers_operator_workflow_affordances() -> None:
    report = doctor_script.build_doctor_report()

    assert report["status"] == "pass"
    for check_name in (
        "help_contract",
        "synthetic_smoke_contract",
        "review_json_contract",
        "review_exit_codes",
        "sanitized_artifact_output",
        "unsafe_artifact_rejection",
    ):
        assert _check_by_name(report, check_name) == {
            "name": check_name,
            "status": "pass",
            "reason_code": None,
        }
    _assert_no_raw_hash_values(report)
    _assert_safe_output(json.dumps(report, sort_keys=True))


def test_doctor_failure_path_returns_safe_nonzero_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failing_check(_context: doctor_script.DoctorContext) -> None:
        raise doctor_script.DoctorCheckError("synthetic_failure")

    monkeypatch.setattr(
        doctor_script,
        "DOCTOR_CHECKS",
        (doctor_script.DoctorCheck("help_contract", failing_check),),
    )

    code = doctor_script.main([])

    assert code == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    parsed = json.loads(captured.out)
    _assert_top_level_contract(parsed)
    assert parsed["status"] == "fail"
    assert parsed["checks"] == [
        {
            "name": "help_contract",
            "status": "fail",
            "reason_code": "synthetic_failure",
        }
    ]
    assert parsed["summary"] == {
        "check_count": 1,
        "passed_count": 0,
        "failed_count": 1,
    }
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)


def test_doctor_unexpected_runtime_failure_returns_generic_safe_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken_report() -> dict[str, Any]:
        raise RuntimeError("unexpected synthetic test failure")

    monkeypatch.setattr(doctor_script, "build_doctor_report", broken_report)

    code = doctor_script.main([])

    assert code == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    parsed = json.loads(captured.out)
    _assert_top_level_contract(parsed)
    assert parsed["status"] == "fail"
    assert parsed["checks"] == [
        {
            "name": "doctor_runtime",
            "status": "fail",
            "reason_code": "unexpected_exception",
        }
    ]
    _assert_safe_output(captured.out)
