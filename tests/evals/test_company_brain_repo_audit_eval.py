from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.repo_audit import load_repo_audit


def _write_discovery_snapshot(workspace: Path, repos: list[dict[str, Any]]) -> None:
    raw_dir = workspace / "discovery" / "github" / "20260620T000000Z" / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / "repos.json").write_text(json.dumps(repos), encoding="utf-8")


def test_company_brain_repo_audit_eval_keeps_repo_as_evidence_component(
    tmp_path: Path,
) -> None:
    raw_email = "founder" + "@" + "example.com"
    _write_discovery_snapshot(
        tmp_path,
        [
            {
                "name": "modern-agent-platform",
                "full_name": "qtwin-io/modern-agent-platform",
                "owner": {"login": "qtwin-io"},
                "description": "Agent platform",
                "archived": False,
                "fork": False,
                "private": True,
                "visibility": "private",
                "default_branch": "main",
                "pushed_at": "2026-06-19T00:00:00Z",
                "updated_at": "2026-06-19T00:00:00Z",
                "language": "Python",
                "_readme": "Architecture and operations",
                "_languages": {"Python": 1000},
                "_root_contents": [
                    {"name": "pyproject.toml"},
                    {"name": "Dockerfile"},
                    {"name": ".github"},
                    {"name": "tests"},
                ],
                "_branches": [{"name": "main"}],
                "_recent_commits": [
                    {
                        "author": {"login": "platform-owner"},
                        "commit": {"author": {"email": raw_email}},
                    }
                ],
            }
        ],
    )

    audit = load_repo_audit(
        workspace_path=tmp_path,
        now=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    serialized = json.dumps(audit, ensure_ascii=False)

    assert audit["status"] == "computed"
    assert audit["computed"] is True
    assert audit["preview_only"] is True
    assert audit["db_written"] is False
    assert audit["network_calls"] is False
    assert audit["provenance"]["mode"] == "computed_local_snapshot"
    assert audit["provenance"]["computed_facts"] is True
    assert audit["source_snapshot"]["available"] is True

    repo = audit["repo_facts"][0]
    assert repo["repo_role"] == "component_evidence"
    assert repo["repo_not_jira_project"] is True
    assert repo["jira_mapping_policy"] == "repo_is_component_or_evidence_not_jira_project"
    assert repo["needs_founder_confirm"] is True
    assert repo["owner_candidates"][0]["needs_founder_confirm"] is True
    assert repo["ci_detected"] is True
    assert repo["tests_detected"] is True
    assert "dockerfile" in repo["deploy_hints"]

    assert raw_email not in serialized
    assert audit["guardrails"]["raw_email_returned"] is False
    assert audit["guardrails"]["one_repo_one_jira_project"] is False
