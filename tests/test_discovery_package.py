"""Discovery package: 8 deliverables, dry-run-only write plan, no leaks."""

from __future__ import annotations

import json

import pytest

from app.services.discovery_package import (
    DRY_RUN_ONLY,
    PACKAGE_FILES,
    WRITE_GUARDRAIL,
    build_discovery_package,
    build_dry_run_write_plan,
    load_latest_summary,
)
from scripts.build_jira_blueprint import run as build_blueprint
from scripts.export_discovery_package import run as export_package

_JIRA = {
    "counts": {
        "project_count": 12,
        "status_count": 15,
        "issue_type_count": 11,
        "custom_field_count": 40,
    },
    "mess_indicators": {
        "status_proliferation": True,
        "status_over_target": 7,
        "near_duplicate_status_count": 3,
        "issue_type_proliferation": True,
        "issue_type_over_target": 3,
    },
}
_GITHUB = {
    "counts": {"repo_count": 1},
    "repos": [{"name": "repo-alpha-web", "domain_hints": ["frontend"]}],
}


def test_package_has_all_eight_deliverables() -> None:
    package = build_discovery_package(jira_summary=_JIRA, github_summary=_GITHUB)
    assert set(package) == set(PACKAGE_FILES)
    assert len(PACKAGE_FILES) == 8


def test_dry_run_plan_is_never_executable() -> None:
    plan = build_dry_run_write_plan(_JIRA, _GITHUB)
    assert plan["execution"] == "none"
    assert plan["executed"] is False
    assert plan["manual_approval_required"] is True
    assert plan["planned_actions"], "expected planned actions"
    for action in plan["planned_actions"]:
        assert action["requires_approval"] is True
        assert action["status"] == DRY_RUN_ONLY
        assert action["guardrail"] == WRITE_GUARDRAIL
    # No execution flag anywhere in the serialized plan.
    blob = json.dumps(plan)
    assert '"executed": true' not in blob
    assert '"status": "executed"' not in blob


def test_repo_mapping_and_do_not_migrate_reflect_inputs() -> None:
    package = build_discovery_package(jira_summary=_JIRA, github_summary=_GITHUB)
    assert "repo-alpha-web" in package["repo-to-jira-mapping.md"]
    assert "area-product-core" in package["repo-to-jira-mapping.md"]
    assert "proliferat" in package["do-not-migrate.md"].lower()


def test_package_rejects_secret_values() -> None:
    leaky_github = {"counts": {"repo_count": 1}, "repos": [{"name": "ghp_" + "a" * 36}]}
    with pytest.raises(ValueError):
        build_discovery_package(jira_summary=_JIRA, github_summary=leaky_github)


def _seed_run(root, source, stamp, summary, audit_name=None):
    run_dir = root / ".local" / "discovery" / source / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    if audit_name:
        (run_dir / audit_name).write_text(f"# {source} audit\n", encoding="utf-8")
    return run_dir


def test_load_latest_summary_picks_newest(tmp_path) -> None:
    _seed_run(tmp_path, "jira", "20260101T000000Z", {"counts": {"project_count": 1}})
    _seed_run(tmp_path, "jira", "20260615T000000Z", {"counts": {"project_count": 99}})
    summary = load_latest_summary(tmp_path, "jira")
    assert summary["counts"]["project_count"] == 99


def test_export_writes_eight_files_and_safe_stdout(tmp_path) -> None:
    _seed_run(tmp_path, "jira", "20260615T000000Z", _JIRA, audit_name="current-jira-audit.md")
    _seed_run(tmp_path, "github", "20260615T000000Z", _GITHUB, audit_name="github-repo-audit.md")
    result = export_package(root=tmp_path, timestamp="20260615T120000Z")
    assert result["status"] == "ok"
    assert result["deliverables_created"] == 8
    pkg = tmp_path / ".local" / "discovery" / "package" / "20260615T120000Z"
    for filename in PACKAGE_FILES:
        assert (pkg / filename).exists()
    # dry-run plan landed as valid JSON with no execution.
    plan = json.loads((pkg / "dry-run-write-plan.json").read_text())
    assert plan["executed"] is False
    for artifact in result["artifacts"]:
        assert artifact["relative_path"].startswith(".local/discovery/package/")


def test_build_blueprint_writes_blueprint(tmp_path) -> None:
    _seed_run(tmp_path, "jira", "20260615T000000Z", _JIRA)
    _seed_run(tmp_path, "github", "20260615T000000Z", _GITHUB)
    result = build_blueprint(root=tmp_path, timestamp="20260615T120000Z")
    assert result["status"] == "ok"
    blueprint = (
        tmp_path
        / ".local"
        / "discovery"
        / "package"
        / "20260615T120000Z"
        / "target-jira-blueprint.md"
    )
    assert blueprint.exists()
    assert "Discovery-derived inputs" in blueprint.read_text()
