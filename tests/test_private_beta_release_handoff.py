from __future__ import annotations

import json
from pathlib import Path

from scripts.private_beta_release_handoff import build_release_handoff


def test_release_handoff_reports_current_repo_without_side_effects() -> None:
    report = build_release_handoff()

    assert report["check"] == "private_beta_release_handoff"
    assert report["offline"] is True
    assert report["provider_calls"] is False
    assert report["provider_writes"] is False
    assert report["deploy_started"] is False
    assert report["external_write_started"] is False
    assert report["reads_secrets"] is False
    assert report["mvp_audit"]["local_scope_complete"] is True
    assert report["mvp_audit"]["fully_complete"] is False
    assert report["github_real_read_preflight"]["provider_read_started"] is False
    assert report["github_real_read_preflight"]["requires_human_approval"] is True
    assert "docs/deploy/external-action-result-smoke.md" in " ".join(
        report["recommended_handoff_order"]
    )


def test_release_handoff_is_exposed_through_make_and_docs() -> None:
    root = Path(__file__).resolve().parents[1]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    docs_readme = (root / "docs" / "README.md").read_text(encoding="utf-8")

    assert "release-handoff:" in makefile
    assert "scripts/private_beta_release_handoff.py" in makefile
    assert "make release-handoff" in readme
    assert "private_beta_release_handoff.py" in docs_readme


def test_release_handoff_json_contains_no_secret_values() -> None:
    report = build_release_handoff()
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


def test_release_handoff_handles_non_git_tree(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_text("", encoding="utf-8")
    repos_file = tmp_path / "repos.json"
    repos_file.write_text("[]", encoding="utf-8")

    report = build_release_handoff(root=tmp_path, repos_file=repos_file)

    assert report["git"]["branch_line"] is None
    assert report["git"]["commit"] is None
    assert report["git"]["ahead_count"] is None
    assert report["git"]["dirty"] is False
    assert report["mvp_audit"]["local_scope_complete"] is False
    assert report["github_real_read_preflight"]["local_repository_count"] == 0
