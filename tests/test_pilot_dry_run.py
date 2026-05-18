from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.services.attention_triage import AttentionContext, DigestSection
from scripts import pilot_dry_run

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "pilot_dry_run.py"


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_json_command_exits_successfully_with_expected_sections() -> None:
    completed = _run_script("--format", "json")

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert set(payload) == {
        "attention_policy_sample",
        "digest_sections_sample",
        "source_normalization_sample",
        "meeting_draft_sample",
        "feedback_context_shape_sample",
        "deferred_boundaries",
        "safety",
    }


def test_text_command_exits_successfully() -> None:
    completed = _run_script("--format", "text")

    assert completed.returncode == 0
    assert "FOS-049A Manual Pilot Dry Run" in completed.stdout
    assert "attention_policy_sample:" in completed.stdout
    assert "safety:" in completed.stdout


def test_output_uses_synthetic_sample_ids_and_titles_only() -> None:
    report = pilot_dry_run.build_report()
    dumped = json.dumps(report, sort_keys=True)

    assert "synthetic" in dumped
    assert "PRIVATE" not in dumped
    assert "YOUR_API_KEY" not in dumped
    assert ".env" not in dumped
    assert "raw://synthetic/" in dumped


def test_attention_policy_sample_forces_medium_and_low_hidden_visible() -> None:
    report = pilot_dry_run.build_report()
    samples = {sample["case"]: sample for sample in report["attention_policy_sample"]}

    medium = samples["medium_confidence_hidden"]["after_policy"]
    low = samples["low_confidence_hidden"]["after_policy"]

    assert medium["attention_class"] == "review_optional"
    assert medium["show_in_digest"] is True
    assert "medium confidence" in medium["reason"]
    assert low["attention_class"] == "review_optional"
    assert low["show_in_digest"] is True
    assert "low confidence" in low["reason"]


def test_digest_sample_includes_all_sections_and_counts_only_hidden_summary() -> None:
    report = pilot_dry_run.build_report()
    digest = report["digest_sections_sample"]
    hidden_summary = digest["sections"]["Hidden low-priority summary"]

    assert digest["section_order"] == list(DigestSection.__args__)
    assert set(digest["sections"]) == set(DigestSection.__args__)
    assert hidden_summary == {
        "count": 2,
        "by_attention_class": {"no_action_required": 2},
        "details_included": False,
    }
    assert "items" not in hidden_summary
    assert digest["hidden_summary_counts_only"] is True


def test_source_normalization_sample_includes_github_jira_and_drive_outputs() -> None:
    sample = pilot_dry_run.build_report()["source_normalization_sample"]

    assert sample["github"]["source"] == "github"
    assert sample["github"]["activity_type"] == "pull_request.review_requested"
    assert sample["github"]["related_prs"]
    assert sample["jira"]["source"] == "jira"
    assert sample["jira"]["activity_type"] == "issue.blocked"
    assert sample["jira"]["related_jira_keys"] == ["PILOT-49"]
    assert sample["drive"]["source"] == "drive"
    assert sample["drive"]["activity_type"] == "document.changed"
    assert sample["drive"]["related_files"]


def test_meeting_draft_sample_reports_draft_only_counts() -> None:
    sample = pilot_dry_run.build_report()["meeting_draft_sample"]

    assert sample["summary"] == "Team reviewed the synthetic pilot dry-run boundary."
    assert sample["decisions_count"] == 1
    assert sample["action_items_count"] == 1
    assert sample["risks_count"] == 1
    assert sample["open_questions_count"] == 1
    assert sample["jira_draft_count"] == 1
    assert sample["kb_draft_count"] == 3
    assert sample["evidence_refs_count"] >= 6
    assert sample["all_statuses"] == ["draft"]
    assert sample["jira_and_kb_are_draft_only"] is True


def test_feedback_context_shape_sample_is_non_persistent_and_context_ready() -> None:
    sample = pilot_dry_run.build_report()["feedback_context_shape_sample"]
    context = AttentionContext.model_validate(
        {"recent_feedback": sample["recent_feedback"]}
    )

    assert sample["synthetic"] is True
    assert sample["persisted"] is False
    assert sample["suitable_for_attention_context"] is True
    assert sample["recent_feedback_count"] == 1
    assert context.recent_feedback[0].feedback_id == "synthetic-feedback-049a"
    assert context.recent_feedback[0].user_action == "marked_important"


def test_safety_section_reports_no_writes_or_live_calls() -> None:
    safety = pilot_dry_run.build_report()["safety"]

    assert safety == {
        "provider_free": True,
        "external_api_calls": False,
        "db_writes": False,
        "ingestion": False,
        "migrations": False,
        "jira_writes": False,
        "kb_obsidian_writes": False,
        "uses_synthetic_data_only": True,
    }


def test_script_source_avoids_live_clients_and_db_session_factories() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden_tokens = [
        "AsyncSessionLocal",
        "create_async_engine",
        "requests",
        "httpx",
        "googleapiclient",
        "slack_sdk",
        "telegram",
        "openai",
        ".env",
        "write_text(",
        "alembic",
        "ingest_text",
        "run_ingestion",
        "export_obsidian",
    ]

    for token in forbidden_tokens:
        assert token not in source
