from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import manual_no_marker_grouped_lifecycle_review as manual_script
from scripts import (
    report_no_marker_persisted_attention_grouped_lifecycle_compatibility as review_script,
)

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


def _safe_serialized(value: str) -> str:
    return value.replace("grouped_preview_text_sha256", "").replace(
        "grouped_preview_text_included",
        "",
    )


def _assert_safe_output(output: str) -> None:
    lowered = _safe_serialized(output).casefold()
    for pattern in UNSAFE_OUTPUT_PATTERNS:
        assert pattern not in lowered


def _doctor_pass_report() -> dict[str, Any]:
    return {
        "mode": "grouped_lifecycle_review_doctor",
        "status": "pass",
        "read_only": True,
        "provider_free": True,
        "local_synthetic_only": True,
        "uses_real_local_data": False,
        "enforced": False,
        "semantic_duplicate_claimed": False,
        "checks": [],
        "summary": {
            "check_count": 0,
            "passed_count": 0,
            "failed_count": 0,
        },
    }


def _review_payload_for_decision(decision: str) -> dict[str, Any]:
    smoke_report = review_script.build_synthetic_review_smoke_report()
    for scenario in smoke_report["scenarios"]:
        if scenario["operator_review_summary"]["decision"] == decision:
            return dict(scenario)
    raise AssertionError(f"missing synthetic scenario for {decision}")


def _base_args(tmp_path: Path) -> list[str]:
    return [
        "--allow-local-data-readonly",
        "--start-at",
        "2149-01-01T00:00:00+00:00",
        "--end-at",
        "2149-01-02T00:00:00+00:00",
        "--output-path",
        str(tmp_path / "review" / "manual-review.json"),
    ]


def _patch_doctor_pass(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    def fake_doctor() -> dict[str, Any]:
        calls.append("doctor")
        return _doctor_pass_report()

    monkeypatch.setattr(manual_script.doctor_script, "build_doctor_report", fake_doctor)


def _patch_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calls: list[str],
    decision: str,
    exit_code: int,
) -> None:
    payload = _review_payload_for_decision(decision)

    def fake_report_main(argv: list[str] | None = None) -> int:
        calls.append("report")
        assert argv is not None
        assert "--format" in argv
        assert argv[argv.index("--format") + 1] == "review-json"
        assert "--review-exit-code" in argv
        assert "--output-path" not in argv
        print(json.dumps(payload, indent=2, sort_keys=True))
        return exit_code

    monkeypatch.setattr(manual_script.review_script, "main", fake_report_main)


def test_manual_runner_without_ack_blocks_before_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_doctor() -> dict[str, Any]:
        raise AssertionError("doctor must not run without acknowledgement")

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("report must not run without acknowledgement")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        forbidden_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    code = manual_script.main([])

    assert code == manual_script.EXIT_LOCAL_DATA_ACK_REQUIRED
    captured = capsys.readouterr()
    assert captured.err == ""
    parsed = json.loads(captured.out)
    assert parsed == {
        "mode": "manual_grouped_lifecycle_review",
        "status": "blocked",
        "reason_code": "local_data_ack_required",
        "read_only": True,
        "provider_free": False,
        "local_synthetic_only": False,
        "uses_real_local_data": False,
        "local_data_acknowledged": False,
        "executed_report": False,
        "output_format": "review-json",
        "enforced": False,
        "semantic_duplicate_claimed": False,
    }
    _assert_safe_output(captured.out)


def test_manual_runner_runs_doctor_before_delegating_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_report(
        monkeypatch,
        calls=calls,
        decision="not_blocked",
        exit_code=0,
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == 0
    assert calls == ["doctor", "report"]
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert parsed == artifact_payload
    assert parsed["operator_review_summary"]["decision"] == "not_blocked"
    assert parsed["operator_review_summary"]["enforced"] is False
    assert parsed["operator_review_summary"]["semantic_duplicate_claimed"] is False
    _assert_safe_output(captured.out)
    _assert_safe_output(artifact_path.read_text(encoding="utf-8"))


def test_manual_runner_doctor_failure_stops_before_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def failing_doctor() -> dict[str, Any]:
        calls.append("doctor")
        report = _doctor_pass_report()
        report["status"] = "fail"
        return report

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("report must not run when doctor fails")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        failing_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    code = manual_script.main(_base_args(tmp_path))

    assert code == manual_script.EXIT_DOCTOR_FAILED
    assert calls == ["doctor"]
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "doctor_failed"
    assert parsed["local_data_acknowledged"] is True
    assert parsed["executed_report"] is False
    _assert_safe_output(captured.out)


@pytest.mark.parametrize(
    "unsafe_path",
    (
        "raw_storage/review.json",
        "obsidian_vault/review.json",
        ".git/review.json",
        ".config/review.json",
        "credentials.json",
        "token-review.json",
    ),
)
def test_manual_runner_rejects_unsafe_output_paths_before_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    unsafe_path: str,
) -> None:
    def forbidden_doctor() -> dict[str, Any]:
        raise AssertionError("doctor must not run for unsafe path")

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("report must not run for unsafe path")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        forbidden_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    code = manual_script.main(
        [
            "--allow-local-data-readonly",
            "--start-at",
            "2149-01-01T00:00:00+00:00",
            "--end-at",
            "2149-01-02T00:00:00+00:00",
            "--output-path",
            unsafe_path,
        ]
    )

    assert code == manual_script.EXIT_UNSAFE_OUTPUT_PATH
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "unsafe_output_path"
    assert parsed["executed_report"] is False
    _assert_safe_output(captured.out)


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_manual_runner_rejects_unsafe_output_modes_before_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    output_format: str,
) -> None:
    def forbidden_doctor() -> dict[str, Any]:
        raise AssertionError("doctor must not run for unsafe output mode")

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("report must not run for unsafe output mode")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        forbidden_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    code = manual_script.main([*_base_args(tmp_path), "--format", output_format])

    assert code == manual_script.EXIT_INVALID_USAGE
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "safe_review_json_required"
    assert parsed["executed_report"] is False
    _assert_safe_output(captured.out)


def test_manual_runner_requires_output_path_before_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_doctor() -> dict[str, Any]:
        raise AssertionError("doctor must not run without output path")

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("report must not run without output path")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        forbidden_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    code = manual_script.main(
        [
            "--allow-local-data-readonly",
            "--start-at",
            "2149-01-01T00:00:00+00:00",
            "--end-at",
            "2149-01-02T00:00:00+00:00",
        ]
    )

    assert code == manual_script.EXIT_UNSAFE_OUTPUT_PATH
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["reason_code"] == "output_path_required"
    assert parsed["executed_report"] is False
    _assert_safe_output(captured.out)


@pytest.mark.parametrize(
    ("decision", "exit_code"),
    (
        ("not_blocked", 0),
        ("already_sent_by_current_hash", 10),
        ("blocked_by_linked_canonical_hash", 20),
        ("manual_review_needed", 30),
    ),
)
def test_manual_runner_maps_delegated_decision_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    decision: str,
    exit_code: int,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_report(
        monkeypatch,
        calls=calls,
        decision=decision,
        exit_code=exit_code,
    )

    code = manual_script.main(_base_args(tmp_path))

    assert code == exit_code
    assert calls == ["doctor", "report"]
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["operator_review_summary"]["decision"] == decision
    _assert_safe_output(captured.out)
