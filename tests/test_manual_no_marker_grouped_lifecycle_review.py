from __future__ import annotations

import inspect
import json
import re
import sys
from datetime import UTC, datetime
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


def _assert_contract_diagnostics(
    parsed: dict[str, Any],
    *,
    artifact_contract_status: str,
    artifact_presence: str = "present",
    artifact_schema_kind: str | None = None,
    child_exit_category: str | None = None,
    missing_required_field_names: list[str] | None = None,
) -> None:
    diagnostics = parsed["delegated_contract_diagnostics"]
    assert diagnostics["delegated_boundary_name"] == "manual_runner_to_report"
    assert diagnostics["artifact_presence"] == artifact_presence
    assert diagnostics["artifact_contract_status"] == artifact_contract_status
    assert diagnostics["validator_name"].startswith("_")
    if artifact_schema_kind is not None:
        assert diagnostics["artifact_schema_kind"] == artifact_schema_kind
    if child_exit_category is not None:
        assert diagnostics["child_exit_category"] == child_exit_category
    if missing_required_field_names is not None:
        assert diagnostics["missing_required_field_names"] == (
            missing_required_field_names
        )
    _assert_no_raw_hash_values(diagnostics)
    _assert_safe_output(json.dumps(diagnostics, sort_keys=True))


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


def _full_report_for_decision(decision: str) -> dict[str, Any]:
    review_payload = _review_payload_for_decision(decision)
    full_payload = {
        key: value
        for key, value in review_payload.items()
        if key not in {"artifact_schema", "output_format"}
    }
    return {
        **full_payload,
        "candidate": {},
        "grouped_preview": {},
        "duplicate_quality": {},
        "recommended_next_action": "inspect_review_artifact",
        "warnings": [],
        "limitations": [],
    }


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


def _lookback_args(tmp_path: Path) -> list[str]:
    return [
        "--allow-local-data-readonly",
        "--lookback-hours",
        "24",
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
    captured_report_args: list[list[str]] | None = None,
    stderr_text: str | None = None,
    stdout_text: str | None = None,
    write_artifact: bool = True,
    malformed_artifact: bool = False,
) -> None:
    payload = _review_payload_for_decision(decision)

    def fake_report_main(argv: list[str] | None = None) -> int:
        calls.append("report")
        assert argv is not None
        assert "--allow-local-data-readonly" in argv
        assert "--format" in argv
        assert argv[argv.index("--format") + 1] == "review-json"
        assert "--review-exit-code" in argv
        assert "--output-path" in argv
        if captured_report_args is not None:
            captured_report_args.append(list(argv))
        output_path = Path(argv[argv.index("--output-path") + 1])
        if write_artifact:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if malformed_artifact:
                output_path.write_text("{", encoding="utf-8")
            else:
                review_script._write_json_artifact(payload, output_path)
        if stderr_text is not None:
            print(stderr_text, file=sys.stderr)
        stdout_payload = (
            stdout_text
            if stdout_text is not None
            else json.dumps(payload, indent=2, sort_keys=True)
        )
        print(stdout_payload)
        return exit_code

    monkeypatch.setattr(manual_script.review_script, "main", fake_report_main)


def _patch_production_report_artifact(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calls: list[str],
    decision: str,
    exit_code: int,
    stderr_text: str | None = None,
    stdout_text: str | None = None,
    drop_diagnostics: bool = False,
    artifact_kind: str = "review-json",
    artifact_status: str | None = None,
) -> None:
    full_report = _full_report_for_decision(decision)

    def fake_report_main(argv: list[str] | None = None) -> int:
        calls.append("report")
        assert argv is not None
        assert "--allow-local-data-readonly" in argv
        assert "--format" in argv
        assert argv[argv.index("--format") + 1] == "review-json"
        assert "--review-exit-code" in argv
        assert "--output-path" in argv
        output_path = Path(argv[argv.index("--output-path") + 1])
        if artifact_kind == "full":
            artifact_payload = dict(full_report)
        else:
            artifact_payload = review_script.format_review_json_report(full_report)
            if artifact_kind == "legacy-review-json":
                artifact_payload.pop("artifact_schema", None)
                artifact_payload.pop("output_format", None)
            elif artifact_kind == "wrong-schema":
                artifact_payload["artifact_schema"] = "unsupported_review_json.v1"
        if artifact_status is not None:
            artifact_payload["status"] = artifact_status
        if drop_diagnostics:
            artifact_payload.pop("manual_review_diagnostics", None)
        review_script._write_json_artifact(artifact_payload, output_path)
        if stderr_text is not None:
            print(stderr_text, file=sys.stderr)
        print(
            stdout_text
            if stdout_text is not None
            else json.dumps(artifact_payload, indent=2, sort_keys=True)
        )
        return exit_code

    monkeypatch.setattr(manual_script.review_script, "main", fake_report_main)


def _patch_malformed_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calls: list[str],
    exit_code: int,
) -> None:
    def fake_report_main(argv: list[str] | None = None) -> int:
        calls.append("report")
        assert argv is not None
        assert "--allow-local-data-readonly" in argv
        assert "--output-path" in argv
        output_path = Path(argv[argv.index("--output-path") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("{", encoding="utf-8")
        print("{")
        return exit_code

    monkeypatch.setattr(manual_script.review_script, "main", fake_report_main)


def _patch_unsafe_review_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calls: list[str],
) -> None:
    payload = _review_payload_for_decision("not_blocked")
    payload = dict(payload)
    summary = dict(payload["operator_review_summary"])
    summary["recommended_action"] = "item_title"
    payload["operator_review_summary"] = summary

    def fake_report_main(argv: list[str] | None = None) -> int:
        calls.append("report")
        assert argv is not None
        assert "--allow-local-data-readonly" in argv
        assert "--output-path" in argv
        output_path = Path(argv[argv.index("--output-path") + 1])
        review_script._write_json_artifact(payload, output_path)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    monkeypatch.setattr(manual_script.review_script, "main", fake_report_main)


def _patch_raw_hash_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calls: list[str],
    captured_report_args: list[list[str]] | None = None,
) -> None:
    payload = _full_report_for_decision("not_blocked")
    lifecycle = dict(payload["lifecycle_compatibility"])
    lifecycle["canonical_candidate_text_sha256"] = "a" * 64
    lifecycle["grouped_preview_text_sha256"] = "b" * 64
    payload["lifecycle_compatibility"] = lifecycle

    def fake_report_main(argv: list[str] | None = None) -> int:
        calls.append("report")
        assert argv is not None
        assert "--allow-local-data-readonly" in argv
        if captured_report_args is not None:
            captured_report_args.append(list(argv))
        assert "--output-path" in argv
        output_path = Path(argv[argv.index("--output-path") + 1])
        review_script._write_json_artifact(payload, output_path)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    monkeypatch.setattr(manual_script.review_script, "main", fake_report_main)


def _patch_report_builder(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calls: list[str],
    decision: str,
) -> None:
    async def fake_report_builder(*_args: object, **_kwargs: object) -> dict[str, Any]:
        calls.append("report_builder")
        return _full_report_for_decision(decision)

    monkeypatch.setattr(
        manual_script.review_script,
        "build_no_marker_grouped_lifecycle_compatibility_report",
        fake_report_builder,
    )


def test_manual_runner_help_lists_lookback_and_preflight(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_doctor() -> dict[str, Any]:
        raise AssertionError("help must not run doctor")

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("help must not run report")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        forbidden_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    with pytest.raises(SystemExit) as exc_info:
        manual_script.main(["--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--allow-local-data-readonly" in captured.out
    assert "--lookback-hours" in captured.out
    assert "--preflight-only" in captured.out
    assert "review-json" in captured.out
    assert "--output-path" in captured.out
    assert "Without this flag" in captured.out
    assert "no report" in captured.out
    help_output = captured.out.casefold()
    assert "default-blocked" in help_output
    assert "doctor-gated" in help_output
    assert "sanitized output/artifact" in help_output
    assert "no send" in help_output
    assert "no enforcement" in help_output
    assert "no source-of-truth mutation" in help_output
    _assert_safe_output(captured.out)


def test_lookback_hours_resolves_with_deterministic_now(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    monkeypatch.setattr(
        manual_script,
        "_utc_now",
        lambda: datetime(2149, 1, 2, 12, 0, tzinfo=UTC),
    )
    artifact_path = tmp_path / "review" / "preflight.json"

    code = manual_script.main(
        [
            "--preflight-only",
            "--allow-local-data-readonly",
            "--lookback-hours",
            "24",
            "--output-path",
            str(artifact_path),
        ]
    )

    assert code == 0
    assert calls == ["doctor"]
    assert not artifact_path.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["mode"] == "manual_grouped_lifecycle_review_preflight"
    assert parsed["status"] == "pass"
    assert parsed["executed_report"] is False
    assert parsed["resolved_window"] == {
        "start_at": "2149-01-01T12:00:00+00:00",
        "end_at": "2149-01-02T12:00:00+00:00",
        "source": "lookback_hours",
        "lookback_hours": 24.0,
    }
    _assert_safe_output(captured.out)


def test_lookback_hours_with_explicit_end_at_resolves_window(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)

    code = manual_script.main(
        [
            "--preflight-only",
            "--allow-local-data-readonly",
            "--lookback-hours",
            "6",
            "--end-at",
            "2149-01-02T00:00:00+00:00",
            "--output-path",
            str(tmp_path / "review" / "preflight.json"),
        ]
    )

    assert code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["resolved_window"]["start_at"] == "2149-01-01T18:00:00+00:00"
    assert parsed["resolved_window"]["end_at"] == "2149-01-02T00:00:00+00:00"
    assert parsed["resolved_window"]["source"] == "lookback_hours"
    _assert_safe_output(captured.out)


@pytest.mark.parametrize("lookback_hours", ["0", "-1", "abc", "169"])
def test_lookback_hours_rejects_invalid_values_before_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    lookback_hours: str,
) -> None:
    def forbidden_doctor() -> dict[str, Any]:
        raise AssertionError("invalid window must not run doctor")

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("invalid window must not run report")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        forbidden_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    code = manual_script.main(
        [
            "--preflight-only",
            "--allow-local-data-readonly",
            "--lookback-hours",
            lookback_hours,
            "--output-path",
            str(tmp_path / "review" / "preflight.json"),
        ]
    )

    assert code == manual_script.EXIT_INVALID_WINDOW
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "fail"
    assert parsed["reason_code"] == "invalid_window"
    assert parsed["executed_report"] is False
    _assert_safe_output(captured.out)


def test_missing_window_without_lookback_fails_before_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def forbidden_doctor() -> dict[str, Any]:
        raise AssertionError("missing window must not run doctor")

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("missing window must not run report")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        forbidden_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    code = manual_script.main(
        [
            "--allow-local-data-readonly",
            "--output-path",
            str(tmp_path / "review" / "manual-review.json"),
        ]
    )

    assert code == manual_script.EXIT_INVALID_WINDOW
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "invalid_window"
    assert parsed["executed_report"] is False
    _assert_safe_output(captured.out)


def test_conflicting_start_at_and_lookback_fails_before_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def forbidden_doctor() -> dict[str, Any]:
        raise AssertionError("ambiguous window must not run doctor")

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("ambiguous window must not run report")

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
            "--lookback-hours",
            "24",
            "--end-at",
            "2149-01-02T00:00:00+00:00",
            "--output-path",
            str(tmp_path / "review" / "manual-review.json"),
        ]
    )

    assert code == manual_script.EXIT_INVALID_WINDOW
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["reason_code"] == "invalid_window"
    assert parsed["executed_report"] is False
    _assert_safe_output(captured.out)


def test_preflight_without_ack_blocks_without_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_doctor() -> dict[str, Any]:
        raise AssertionError("preflight without ack must not run doctor")

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("preflight must not run report")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        forbidden_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    code = manual_script.main(["--preflight-only"])

    assert code == manual_script.EXIT_LOCAL_DATA_ACK_REQUIRED
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["mode"] == "manual_grouped_lifecycle_review_preflight"
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "local_data_ack_required"
    assert parsed["executed_report"] is False
    assert parsed["resolved_window"] is None
    _assert_safe_output(captured.out)


def test_preflight_doctor_failure_stops_before_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def failing_doctor() -> dict[str, Any]:
        report = _doctor_pass_report()
        report["status"] = "fail"
        return report

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("preflight must not run report")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        failing_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    code = manual_script.main([*_lookback_args(tmp_path), "--preflight-only"])

    assert code == manual_script.EXIT_DOCTOR_FAILED
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "doctor_failed"
    assert parsed["executed_report"] is False
    _assert_safe_output(captured.out)


def test_preflight_unsafe_output_path_stops_before_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_doctor() -> dict[str, Any]:
        raise AssertionError("unsafe path preflight must not run doctor")

    def forbidden_report(_argv: list[str] | None = None) -> int:
        raise AssertionError("unsafe path preflight must not run report")

    monkeypatch.setattr(
        manual_script.doctor_script,
        "build_doctor_report",
        forbidden_doctor,
    )
    monkeypatch.setattr(manual_script.review_script, "main", forbidden_report)

    code = manual_script.main(
        [
            "--preflight-only",
            "--allow-local-data-readonly",
            "--lookback-hours",
            "24",
            "--output-path",
            "raw_storage/review.json",
        ]
    )

    assert code == manual_script.EXIT_UNSAFE_OUTPUT_PATH
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "unsafe_output_path"
    assert parsed["executed_report"] is False
    _assert_safe_output(captured.out)


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
    assert parsed["manual_review_diagnostics"]["diagnostic_status"] == "not_blocked"
    assert parsed["manual_review_diagnostics"]["enforced"] is False
    assert (
        parsed["manual_review_diagnostics"]["semantic_duplicate_claimed"]
        is False
    )
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)
    artifact_text = artifact_path.read_text(encoding="utf-8")
    _assert_no_raw_hash_values(artifact_payload)
    _assert_safe_output(artifact_text)


def test_manual_runner_acknowledged_run_accepts_lookback_hours(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    captured_report_args: list[list[str]] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_report(
        monkeypatch,
        calls=calls,
        decision="not_blocked",
        exit_code=0,
        captured_report_args=captured_report_args,
    )

    code = manual_script.main(_lookback_args(tmp_path))

    assert code == 0
    assert calls == ["doctor", "report"]
    assert len(captured_report_args) == 1
    report_args = captured_report_args[0]
    assert report_args[report_args.index("--start-at") + 1] == (
        "2149-01-01T00:00:00+00:00"
    )
    assert report_args[report_args.index("--end-at") + 1] == (
        "2149-01-02T00:00:00+00:00"
    )
    assert "--format" in report_args
    assert report_args[report_args.index("--format") + 1] == "review-json"
    assert "--review-exit-code" in report_args
    assert "--output-path" in report_args
    assert Path(report_args[report_args.index("--output-path") + 1]) == (
        tmp_path / "review" / "manual-review.json"
    )
    assert "--allow-local-data-readonly" in report_args
    assert "--preflight-only" not in report_args
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["operator_review_summary"]["decision"] == "not_blocked"
    assert parsed["operator_review_summary"]["enforced"] is False
    assert parsed["manual_review_diagnostics"]["enforced"] is False
    assert parsed["manual_review_diagnostics"]["read_only"] is True
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)


def test_manual_runner_report_argv_requests_review_json_artifact_contract(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "review" / "delegated-report.json"
    args = manual_script._parse_args(_lookback_args(tmp_path))
    resolved_window = manual_script.ResolvedWindow(
        start_at="2149-01-01T00:00:00+00:00",
        end_at="2149-01-02T00:00:00+00:00",
        source="lookback_hours",
        lookback_hours=24.0,
    )

    report_args = manual_script._report_args(
        args,
        resolved_window,
        artifact_path=artifact_path,
    )

    assert report_args[report_args.index("--start-at") + 1] == (
        "2149-01-01T00:00:00+00:00"
    )
    assert report_args[report_args.index("--end-at") + 1] == (
        "2149-01-02T00:00:00+00:00"
    )
    assert report_args[report_args.index("--format") + 1] == "review-json"
    assert report_args[report_args.index("--output-path") + 1] == str(
        artifact_path
    )
    assert "--review-exit-code" in report_args
    assert "--allow-local-data-readonly" in report_args
    assert "--preflight-only" not in report_args
    parsed_report_args = review_script._parse_args(report_args)
    assert parsed_report_args.allow_local_data_readonly is True
    assert parsed_report_args.format == "review-json"
    assert parsed_report_args.output_path == str(artifact_path)


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
    _assert_no_raw_hash_values(parsed)
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
def test_manual_runner_accepts_production_report_artifact_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    decision: str,
    exit_code: int,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_production_report_artifact(
        monkeypatch,
        calls=calls,
        decision=decision,
        exit_code=exit_code,
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == exit_code
    assert calls == ["doctor", "report"]
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert parsed == artifact_payload
    assert parsed["artifact_schema"] == review_script.REVIEW_JSON_ARTIFACT_SCHEMA
    assert parsed["output_format"] == "review-json"
    assert parsed["operator_review_summary"]["decision"] == decision
    assert parsed["manual_review_diagnostics"]["diagnostic_status"] == decision
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)


def test_manual_runner_accepts_real_report_entrypoint_artifact_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_report_builder(
        monkeypatch,
        calls=calls,
        decision="manual_review_needed",
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == 30
    assert calls == ["doctor", "report_builder"]
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert parsed == artifact_payload
    assert parsed["artifact_schema"] == review_script.REVIEW_JSON_ARTIFACT_SCHEMA
    assert parsed["output_format"] == "review-json"
    assert parsed["operator_review_summary"]["decision"] == (
        "manual_review_needed"
    )
    assert parsed["manual_review_diagnostics"]["diagnostic_status"] == (
        "manual_review_needed"
    )
    assert "delegated_contract_diagnostics" not in parsed
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)
    _assert_safe_output(artifact_path.read_text(encoding="utf-8"))


def test_manual_runner_accepts_legacy_review_json_artifact_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_production_report_artifact(
        monkeypatch,
        calls=calls,
        decision="manual_review_needed",
        exit_code=30,
        artifact_kind="legacy-review-json",
        stderr_text="synthetic delegated stderr",
        stdout_text="synthetic delegated stdout",
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == 30
    assert calls == ["doctor", "report"]
    captured = capsys.readouterr()
    assert captured.err == ""
    parsed = json.loads(captured.out)
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert parsed == artifact_payload
    assert parsed["artifact_schema"] == review_script.REVIEW_JSON_ARTIFACT_SCHEMA
    assert parsed["output_format"] == "review-json"
    assert parsed["operator_review_summary"]["decision"] == (
        "manual_review_needed"
    )
    assert parsed["manual_review_diagnostics"]["diagnostic_status"] == (
        "manual_review_needed"
    )
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)
    _assert_safe_output(artifact_path.read_text(encoding="utf-8"))


def test_manual_runner_accepts_legacy_review_json_with_safe_status_drift(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_production_report_artifact(
        monkeypatch,
        calls=calls,
        decision="manual_review_needed",
        exit_code=30,
        artifact_kind="legacy-review-json",
        artifact_status="pass",
        stderr_text="synthetic delegated stderr",
        stdout_text="synthetic delegated stdout",
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == 30
    assert calls == ["doctor", "report"]
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert parsed == artifact_payload
    assert parsed["artifact_schema"] == review_script.REVIEW_JSON_ARTIFACT_SCHEMA
    assert parsed["output_format"] == "review-json"
    assert parsed["status"] == "pass"
    assert parsed["operator_review_summary"]["decision"] == (
        "manual_review_needed"
    )
    assert "delegated_contract_diagnostics" not in parsed
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)
    _assert_safe_output(artifact_path.read_text(encoding="utf-8"))


def test_manual_runner_delegated_report_boundary_does_not_check_nonzero_outcomes() -> None:
    source = inspect.getsource(manual_script._delegate_report)

    assert "check=True" not in source
    assert "CalledProcessError" not in source
    assert "delegated_report_stderr" not in source
    assert "json.loads(delegated_stdout" not in source


def test_manual_runner_accepts_valid_manual_review_with_delegated_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_report(
        monkeypatch,
        calls=calls,
        decision="manual_review_needed",
        exit_code=30,
        stderr_text="synthetic delegated stderr",
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == 30
    assert calls == ["doctor", "report"]
    captured = capsys.readouterr()
    assert captured.err == ""
    parsed = json.loads(captured.out)
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert parsed == artifact_payload
    assert parsed["operator_review_summary"]["decision"] == "manual_review_needed"
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)
    _assert_safe_output(artifact_path.read_text(encoding="utf-8"))


def test_manual_runner_accepts_artifact_backed_report_runtime_review_outcome(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)

    async def runtime_report(*_args: object, **_kwargs: object) -> dict[str, Any]:
        calls.append("report_builder")
        raise review_script.NoMarkerGroupedLifecycleRuntimeError(
            "synthetic construction error"
        )

    monkeypatch.setattr(
        manual_script.review_script,
        "build_no_marker_grouped_lifecycle_compatibility_report",
        runtime_report,
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == 30
    assert calls == ["doctor", "report_builder"]
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert parsed == artifact_payload
    assert parsed["operator_review_summary"]["decision"] == "manual_review_needed"
    assert "local_review_source_unavailable" in parsed[
        "operator_review_summary"
    ]["reason_codes"]
    assert "delegated_contract_diagnostics" not in parsed
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)
    _assert_safe_output(artifact_path.read_text(encoding="utf-8"))


def test_manual_runner_uses_delegated_report_artifact_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_production_report_artifact(
        monkeypatch,
        calls=calls,
        decision="manual_review_needed",
        exit_code=30,
        stderr_text="synthetic delegated stderr",
        stdout_text="synthetic delegated stdout",
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == 30
    assert calls == ["doctor", "report"]
    captured = capsys.readouterr()
    assert captured.err == ""
    parsed = json.loads(captured.out)
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert parsed == artifact_payload
    assert parsed["artifact_schema"] == review_script.REVIEW_JSON_ARTIFACT_SCHEMA
    assert parsed["operator_review_summary"]["decision"] == "manual_review_needed"
    assert parsed["manual_review_diagnostics"]["diagnostic_status"] == (
        "manual_review_needed"
    )
    _assert_no_raw_hash_values(parsed)
    _assert_safe_output(captured.out)
    _assert_safe_output(artifact_path.read_text(encoding="utf-8"))


def test_manual_runner_rejects_unexpected_delegated_exit_before_artifact(
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
        exit_code=99,
        write_artifact=False,
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == manual_script.EXIT_INVALID_USAGE
    assert calls == ["doctor", "report"]
    assert not artifact_path.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "delegated_report_failed"
    assert parsed["executed_report"] is False
    _assert_contract_diagnostics(
        parsed,
        artifact_presence="missing",
        artifact_contract_status="not_observed",
        artifact_schema_kind="malformed",
        child_exit_category="unexpected_exit",
    )
    _assert_safe_output(captured.out)


def test_manual_runner_fos127_shape_reports_artifact_not_written_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)

    def fake_report_main(argv: list[str] | None = None) -> int:
        calls.append("report")
        assert argv is not None
        assert "--allow-local-data-readonly" in argv
        assert "--review-exit-code" in argv
        assert "--output-path" in argv
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_code": "runtime_error",
                    "safety": {"read_only": True},
                },
                sort_keys=True,
            )
        )
        return manual_script.EXIT_INVALID_USAGE

    monkeypatch.setattr(manual_script.review_script, "main", fake_report_main)
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == manual_script.EXIT_INVALID_USAGE
    assert calls == ["doctor", "report"]
    assert not artifact_path.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "delegated_report_failed"
    _assert_contract_diagnostics(
        parsed,
        artifact_presence="missing",
        artifact_contract_status="not_observed",
        artifact_schema_kind="malformed",
        child_exit_category="artifact_not_written",
    )
    assert parsed["delegated_contract_diagnostics"]["cli_contract_status"] == (
        "unexpected_exit"
    )
    _assert_safe_output(captured.out)


def test_manual_runner_rejects_malformed_delegated_review_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_malformed_report(monkeypatch, calls=calls, exit_code=30)
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == manual_script.EXIT_INVALID_USAGE
    assert calls == ["doctor", "report"]
    assert artifact_path.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "delegated_report_invalid_json"
    assert parsed["executed_report"] is False
    _assert_contract_diagnostics(
        parsed,
        artifact_contract_status="malformed",
        artifact_schema_kind="malformed",
    )
    _assert_safe_output(captured.out)


def test_manual_runner_rejects_delegated_exit_decision_mismatch(
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
        exit_code=30,
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == manual_script.EXIT_INVALID_USAGE
    assert calls == ["doctor", "report"]
    assert artifact_path.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "delegated_report_failed"
    assert parsed["executed_report"] is False
    _assert_contract_diagnostics(
        parsed,
        artifact_contract_status="decision_exit_code_mismatch",
        artifact_schema_kind="review_json_marked",
    )
    _assert_safe_output(captured.out)


def test_manual_runner_rejects_missing_delegated_report_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_production_report_artifact(
        monkeypatch,
        calls=calls,
        decision="manual_review_needed",
        exit_code=30,
        drop_diagnostics=True,
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == manual_script.EXIT_INVALID_USAGE
    assert calls == ["doctor", "report"]
    assert artifact_path.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "delegated_report_failed"
    assert parsed["executed_report"] is False
    _assert_contract_diagnostics(
        parsed,
        artifact_contract_status="missing_required_fields",
        artifact_schema_kind="unknown",
        missing_required_field_names=["manual_review_diagnostics"],
    )
    _assert_safe_output(captured.out)


def test_manual_runner_rejects_wrong_delegated_report_schema(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_production_report_artifact(
        monkeypatch,
        calls=calls,
        decision="manual_review_needed",
        exit_code=30,
        artifact_kind="wrong-schema",
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == manual_script.EXIT_INVALID_USAGE
    assert calls == ["doctor", "report"]
    assert artifact_path.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "delegated_report_failed"
    assert parsed["executed_report"] is False
    _assert_contract_diagnostics(
        parsed,
        artifact_contract_status="wrong_schema",
        artifact_schema_kind="unknown",
    )
    _assert_safe_output(captured.out)


def test_manual_runner_rejects_wrong_delegated_report_artifact_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)

    def fake_report_main(argv: list[str] | None = None) -> int:
        calls.append("report")
        assert argv is not None
        assert "--allow-local-data-readonly" in argv
        assert "--format" in argv
        assert argv[argv.index("--format") + 1] == "review-json"
        assert "--output-path" in argv
        requested_path = Path(argv[argv.index("--output-path") + 1])
        wrong_path = requested_path.with_name("delegated-report-wrong-path.json")
        review_script._write_json_artifact(
            review_script.format_review_json_report(
                _full_report_for_decision("manual_review_needed")
            ),
            wrong_path,
        )
        print("synthetic delegated stdout")
        return 30

    monkeypatch.setattr(manual_script.review_script, "main", fake_report_main)
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == manual_script.EXIT_INVALID_USAGE
    assert calls == ["doctor", "report"]
    assert not artifact_path.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "delegated_report_invalid_json"
    assert parsed["executed_report"] is False
    _assert_contract_diagnostics(
        parsed,
        artifact_presence="missing",
        artifact_contract_status="wrong_path",
        artifact_schema_kind="malformed",
    )
    _assert_safe_output(captured.out)


def test_manual_runner_rejects_unsafe_delegated_review_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_unsafe_review_report(monkeypatch, calls=calls)
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == manual_script.EXIT_INVALID_USAGE
    assert calls == ["doctor", "report"]
    assert artifact_path.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "delegated_report_failed"
    assert parsed["executed_report"] is False
    _assert_contract_diagnostics(
        parsed,
        artifact_contract_status="unsafe",
        artifact_schema_kind="review_json_marked",
    )
    _assert_safe_output(captured.out)


def test_manual_runner_artifact_includes_sanitized_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_report(
        monkeypatch,
        calls=calls,
        decision="manual_review_needed",
        exit_code=30,
    )
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == 30
    captured = capsys.readouterr()
    stdout_payload = json.loads(captured.out)
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert stdout_payload == artifact_payload
    diagnostics = artifact_payload["manual_review_diagnostics"]
    assert diagnostics["diagnostic_status"] == "manual_review_needed"
    assert diagnostics["requires_human_review"] is True
    assert diagnostics["read_only"] is True
    assert diagnostics["enforced"] is False
    assert diagnostics["semantic_duplicate_claimed"] is False
    assert "manual_review_needed" in diagnostics["reason_codes"]
    assert diagnostics["safe_next_step"] == "verify_canonical_linkage"
    _assert_no_raw_hash_values(stdout_payload)
    _assert_no_raw_hash_values(artifact_payload)
    _assert_safe_output(captured.out)
    _assert_safe_output(artifact_path.read_text(encoding="utf-8"))


def test_manual_runner_artifact_redacts_delegated_raw_hash_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_raw_hash_report(monkeypatch, calls=calls)
    artifact_path = tmp_path / "review" / "manual-review.json"

    code = manual_script.main(_base_args(tmp_path))

    assert code == 0
    assert calls == ["doctor", "report"]
    captured = capsys.readouterr()
    stdout_payload = json.loads(captured.out)
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert stdout_payload == artifact_payload
    lifecycle = artifact_payload["lifecycle_compatibility"]
    assert "canonical_candidate_text_sha256" not in lifecycle
    assert "grouped_preview_text_sha256" not in lifecycle
    assert lifecycle["hash_relationship_status"] == "distinct_explicitly_linked_hashes"
    _assert_no_raw_hash_values(stdout_payload)
    _assert_no_raw_hash_values(artifact_payload)
    _assert_safe_output(captured.out)
    _assert_safe_output(artifact_path.read_text(encoding="utf-8"))
