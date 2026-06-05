from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from scripts import manual_no_marker_grouped_lifecycle_review as manual_script
from scripts import manual_no_marker_grouped_lifecycle_review_sweep as sweep_script
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
RAW_HASH_VALUE_RE = re.compile(r"(?i)(?:sha256[:=_-]?)?[a-f0-9]{64}")


def _safe_serialized(value: str) -> str:
    return value.replace("grouped_preview_text_sha256", "").replace(
        "grouped_preview_text_included",
        "",
    )


def _assert_safe_output(output: str) -> None:
    lowered = _safe_serialized(output).casefold()
    for pattern in UNSAFE_OUTPUT_PATTERNS:
        assert pattern not in lowered


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


def _review_payload_for_decision(decision: str) -> dict[str, Any]:
    smoke_report = review_script.build_synthetic_review_smoke_report()
    for scenario in smoke_report["scenarios"]:
        if scenario["operator_review_summary"]["decision"] == decision:
            return dict(scenario)
    raise AssertionError(f"missing synthetic scenario for {decision}")


def _doctor_pass() -> dict[str, Any]:
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


def _patch_doctor_pass(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    def fake_doctor() -> dict[str, Any]:
        calls.append("doctor")
        return _doctor_pass()

    monkeypatch.setattr(sweep_script, "_run_doctor", fake_doctor)


def _patch_delegate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calls: list[str],
    decisions: list[str],
    exit_codes: list[int] | None = None,
) -> None:
    state = {"index": 0}

    def fake_delegate(
        _args: object,
        *,
        lookback_hours: float,
        output_path: Path,
    ) -> manual_script.DelegatedReportResult:
        index = state["index"]
        state["index"] += 1
        decision = decisions[index]
        payload = _review_payload_for_decision(
            decision if decision in review_script.REVIEW_DECISION_EXIT_CODES else "not_blocked"
        )
        if decision not in review_script.REVIEW_DECISION_EXIT_CODES:
            payload = dict(payload)
            summary = dict(payload["operator_review_summary"])
            summary["decision"] = decision
            payload["operator_review_summary"] = summary
        exit_code = (
            exit_codes[index]
            if exit_codes is not None
            else review_script.REVIEW_DECISION_EXIT_CODES.get(decision, 30)
        )
        calls.append(f"delegate:{lookback_hours:g}")
        review_script._write_json_artifact(payload, output_path)
        return manual_script.DelegatedReportResult(
            exit_code=exit_code,
            payload=payload,
        )

    monkeypatch.setattr(sweep_script, "_delegate_window_review", fake_delegate)


def _ack_args(tmp_path: Path, *, lookbacks: str = "6,24,72") -> list[str]:
    return [
        "--allow-local-data-readonly",
        "--lookback-hours-list",
        lookbacks,
        "--output-dir",
        str(tmp_path / "sweep"),
    ]


def _parse_stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    captured = capsys.readouterr()
    assert captured.err == ""
    _assert_safe_output(captured.out)
    parsed = json.loads(captured.out)
    _assert_no_raw_hash_values(parsed)
    return parsed


def test_sweep_help_describes_gates_and_non_delivery_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sweep_script,
        "_run_doctor",
        lambda: (_ for _ in ()).throw(AssertionError("help must not run doctor")),
    )
    monkeypatch.setattr(
        sweep_script,
        "_delegate_window_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("help must not delegate")
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        sweep_script.main(["--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    help_output = captured.out.casefold()
    assert "--allow-local-data-readonly" in captured.out
    assert "--lookback-hours-list" in captured.out
    assert "--preflight-only" in captured.out
    assert "default-blocked" in help_output
    assert "doctor-gated" in help_output
    assert "sanitized output/artifact" in help_output
    assert "no send" in help_output
    assert "no enforcement" in help_output
    assert "no source-of-truth mutation" in help_output
    _assert_safe_output(captured.out)


def test_sweep_without_ack_blocks_before_delegation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sweep_script,
        "_run_doctor",
        lambda: (_ for _ in ()).throw(AssertionError("doctor must not run")),
    )
    monkeypatch.setattr(
        sweep_script,
        "_delegate_window_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("delegate must not run")
        ),
    )

    code = sweep_script.main([])

    assert code == sweep_script.EXIT_LOCAL_DATA_ACK_REQUIRED
    parsed = _parse_stdout(capsys)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "local_data_ack_required"
    assert parsed["executed_report_count"] == 0
    assert parsed["enforced"] is False
    assert parsed["semantic_duplicate_claimed"] is False


def test_default_window_list_is_deterministic_and_bounded() -> None:
    args = sweep_script._parse_args(
        ["--allow-local-data-readonly", "--output-dir", "/tmp/fos108_sweep"]
    )

    assert sweep_script.parse_lookback_hours_list(args.lookback_hours_list) == (
        6.0,
        24.0,
        72.0,
    )


def test_lookback_hours_list_parses_valid_values() -> None:
    assert sweep_script.parse_lookback_hours_list("6,24,72") == (6.0, 24.0, 72.0)


@pytest.mark.parametrize("value", ("0", "-1", "abc", "6,,24", "6,6", "169"))
def test_lookback_hours_list_rejects_invalid_values(value: str) -> None:
    with pytest.raises(sweep_script.SweepRunnerError) as exc_info:
        sweep_script.parse_lookback_hours_list(value)

    assert exc_info.value.reason_code == "invalid_window"
    assert exc_info.value.exit_code == sweep_script.EXIT_INVALID_WINDOW


def test_preflight_without_ack_blocks_without_delegation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sweep_script,
        "_delegate_window_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("delegate must not run")
        ),
    )

    code = sweep_script.main(["--preflight-only"])

    assert code == sweep_script.EXIT_LOCAL_DATA_ACK_REQUIRED
    parsed = _parse_stdout(capsys)
    assert parsed["mode"] == "manual_grouped_lifecycle_review_sweep"
    assert parsed["status"] == "blocked"
    assert parsed["executed_report_count"] == 0


def test_preflight_with_ack_passes_without_report_execution(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    monkeypatch.setattr(
        sweep_script,
        "_delegate_window_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preflight must not delegate")
        ),
    )

    code = sweep_script.main([*_ack_args(tmp_path), "--preflight-only"])

    assert code == 0
    assert calls == ["doctor"]
    parsed = _parse_stdout(capsys)
    assert parsed["status"] == "pass"
    assert parsed["executed_report_count"] == 0
    assert parsed["window_count"] == 3
    assert all(window["status"] == "preflight_only" for window in parsed["windows"])


def test_preflight_doctor_failure_returns_blocked_without_delegation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def failing_doctor() -> None:
        raise sweep_script.SweepRunnerError(
            "doctor_failed",
            sweep_script.EXIT_DOCTOR_FAILED,
        )

    monkeypatch.setattr(sweep_script, "_run_doctor", failing_doctor)
    monkeypatch.setattr(
        sweep_script,
        "_delegate_window_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("delegate must not run")
        ),
    )

    code = sweep_script.main([*_ack_args(tmp_path), "--preflight-only"])

    assert code == sweep_script.EXIT_DOCTOR_FAILED
    parsed = _parse_stdout(capsys)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "doctor_failed"
    assert parsed["executed_report_count"] == 0


def test_unsafe_output_dir_rejected_before_delegation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sweep_script,
        "_delegate_window_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("delegate must not run")
        ),
    )

    code = sweep_script.main(
        [
            "--allow-local-data-readonly",
            "--output-dir",
            "raw_storage/sweep",
        ]
    )

    assert code == sweep_script.EXIT_UNSAFE_OUTPUT_PATH
    parsed = _parse_stdout(capsys)
    assert parsed["status"] == "blocked"
    assert parsed["reason_code"] == "unsafe_output_path"
    assert parsed["executed_report_count"] == 0


def test_acknowledged_sweep_runs_doctor_once_before_window_delegations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_delegate(
        monkeypatch,
        calls=calls,
        decisions=["not_blocked", "blocked_by_linked_canonical_hash"],
    )

    code = sweep_script.main(_ack_args(tmp_path, lookbacks="6,24"))

    assert code == 20
    assert calls == ["doctor", "delegate:6", "delegate:24"]
    parsed = _parse_stdout(capsys)
    assert parsed["executed_report_count"] == 2
    assert parsed["aggregate_decision"] == "blocked_by_linked_canonical_hash"


def test_acknowledged_sweep_writes_one_artifact_per_window(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_delegate(
        monkeypatch,
        calls=calls,
        decisions=["not_blocked", "manual_review_needed", "not_blocked"],
    )

    code = sweep_script.main(_ack_args(tmp_path))

    assert code == 30
    assert calls == ["doctor", "delegate:6", "delegate:24", "delegate:72"]
    parsed = _parse_stdout(capsys)
    assert parsed["status"] == "pass"
    assert parsed["executed_report_count"] == 3
    assert parsed["window_count"] == 3
    assert all(window["status"] == "completed" for window in parsed["windows"])
    artifact_paths = sorted((tmp_path / "sweep").glob("*.json"))
    assert len(artifact_paths) == 3
    for artifact_path in artifact_paths:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert "operator_review_summary" in payload
        assert "manual_review_diagnostics" in payload
        _assert_no_raw_hash_values(payload)
        _assert_safe_output(artifact_path.read_text(encoding="utf-8"))


def test_sweep_aggregate_summary_contains_only_safe_fields(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_delegate(
        monkeypatch,
        calls=calls,
        decisions=["not_blocked", "already_sent_by_current_hash"],
    )

    code = sweep_script.main(_ack_args(tmp_path, lookbacks="6,24"))

    assert code == 10
    parsed = _parse_stdout(capsys)
    assert parsed["read_only"] is True
    assert parsed["enforced"] is False
    assert parsed["semantic_duplicate_claimed"] is False
    assert parsed["window_count"] == 2
    assert parsed["aggregate_decision"] == "already_sent_by_current_hash"
    for window in parsed["windows"]:
        assert set(window) == {
            "lookback_hours",
            "status",
            "exit_code",
            "decision",
            "diagnostic_status",
            "reason_codes",
            "safe_next_step",
            "recommended_operator_action",
            "artifact_written",
        }
        assert window["artifact_written"] is True
        assert isinstance(window["reason_codes"], list)
    _assert_no_raw_hash_values(parsed)


@pytest.mark.parametrize(
    ("exit_code", "expected_decision"),
    (
        (0, "not_blocked"),
        (10, "already_sent_by_current_hash"),
        (20, "blocked_by_linked_canonical_hash"),
        (30, "manual_review_needed"),
    ),
)
def test_sweep_accepts_each_valid_delegated_exit_code_as_window_outcome(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    exit_code: int,
    expected_decision: str,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_delegate(
        monkeypatch,
        calls=calls,
        decisions=["not_blocked"],
        exit_codes=[exit_code],
    )

    code = sweep_script.main(_ack_args(tmp_path, lookbacks="6"))

    assert code == exit_code
    assert calls == ["doctor", "delegate:6"]
    parsed = _parse_stdout(capsys)
    assert parsed["status"] == "pass"
    assert parsed["executed_report_count"] == 1
    assert parsed["aggregate_decision"] == expected_decision
    assert len(parsed["windows"]) == 1
    window = parsed["windows"][0]
    assert window["lookback_hours"] == 6.0
    assert window["status"] == "completed"
    assert window["exit_code"] == exit_code
    assert window["decision"] == expected_decision
    assert window["diagnostic_status"] == "not_blocked"
    assert window["artifact_written"] is True
    assert isinstance(window["reason_codes"], list)


@pytest.mark.parametrize(
    ("decisions", "expected_decision", "expected_exit_code"),
    (
        (["not_blocked", "not_blocked"], "not_blocked", 0),
        (
            ["already_sent_by_current_hash", "not_blocked"],
            "already_sent_by_current_hash",
            10,
        ),
        (
            ["blocked_by_linked_canonical_hash", "already_sent_by_current_hash"],
            "blocked_by_linked_canonical_hash",
            20,
        ),
        (["manual_review_needed", "not_blocked"], "manual_review_needed", 30),
        (["unknown", "not_blocked"], "manual_review_needed", 30),
    ),
)
def test_aggregate_decision_precedence_and_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    decisions: list[str],
    expected_decision: str,
    expected_exit_code: int,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_delegate(monkeypatch, calls=calls, decisions=decisions)

    code = sweep_script.main(_ack_args(tmp_path, lookbacks="6,24"))

    assert code == expected_exit_code
    parsed = _parse_stdout(capsys)
    assert parsed["aggregate_decision"] == expected_decision
    assert parsed["recommended_operator_action"]
    _assert_safe_output(json.dumps(parsed, sort_keys=True))


def test_unexpected_delegated_exit_code_fails_safely(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _patch_doctor_pass(monkeypatch, calls)
    _patch_delegate(
        monkeypatch,
        calls=calls,
        decisions=["not_blocked"],
        exit_codes=[99],
    )

    code = sweep_script.main(_ack_args(tmp_path, lookbacks="6"))

    assert code == sweep_script.EXIT_INVALID_USAGE
    assert calls == ["doctor", "delegate:6"]
    parsed = _parse_stdout(capsys)
    assert parsed["status"] == "fail"
    assert parsed["reason_code"] == "delegated_report_failed"
    assert parsed["executed_report_count"] == 0
    assert parsed["windows"] == []
