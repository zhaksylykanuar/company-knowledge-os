from __future__ import annotations

import json
from pathlib import Path

from scripts.local_readiness_report import build_local_readiness_report
from scripts.private_beta_release_handoff import build_release_handoff


def test_local_readiness_reports_current_repo_without_side_effects() -> None:
    report = build_local_readiness_report()

    assert report["check"] == "local_runtime_readiness"
    assert report["offline"] is True
    assert report["provider_calls"] is False
    assert report["provider_writes"] is False
    assert report["local_runtime_started"] is False
    assert report["external_write_started"] is False
    assert report["env_configuration_loaded"] is False
    assert report["secret_presence_checked"] is False
    assert report["secret_values_emitted"] is False
    assert report["referenced_credential_files_read"] is False
    assert report["mvp_audit"]["local_scope_complete"] is True
    assert report["mvp_audit"]["repository_evidence_complete"] is True
    assert report["mvp_audit"]["runtime_acceptance_assessed"] is False
    assert report["mvp_audit"]["fully_complete"] is False
    assert report["provider_configuration"]["source_of_truth"] == (
        "workspace_settings_ui"
    )
    assert report["provider_configuration"]["provider_calls_started"] is False
    assert "docs/deploy/external-action-result-smoke.md" in " ".join(
        report["recommended_handoff_order"]
    )


def test_compatibility_entrypoint_delegates_to_local_readiness() -> None:
    root = Path(__file__).resolve().parents[1]
    compatibility_script = (
        root / "scripts" / "private_beta_release_handoff.py"
    ).read_text(encoding="utf-8")

    assert "scripts.local_readiness_report" in compatibility_script
    assert "the canonical local report has no cloud-deploy state" in compatibility_script
    assert build_release_handoff()["deploy_started"] is False


def test_local_readiness_json_contains_no_secret_values() -> None:
    report = build_local_readiness_report()
    blob = json.dumps(report)

    # Env names and next-step text are allowed; concrete secret values, URLs
    # with credentials, and provider/API token shapes are not.
    assert "/secrets/" not in blob
    assert "postgresql://" not in blob
    assert "postgres://" not in blob
    assert "redis://" not in blob
    assert "ghp_" not in blob
    assert "github_pat_" not in blob
    assert "sk-" not in blob
    assert "provider_payload" not in blob


def test_local_readiness_handles_non_git_tree(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_text("", encoding="utf-8")
    report = build_local_readiness_report(root=tmp_path)

    assert report["git"]["branch_line"] is None
    assert report["git"]["commit"] is None
    assert report["git"]["ahead_count"] is None
    assert report["git"]["dirty"] is False
    assert report["mvp_audit"]["local_scope_complete"] is False
