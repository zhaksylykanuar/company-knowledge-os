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
    build_repo_to_jira_mapping,
    build_target_jira_blueprint,
    load_decisions,
    load_latest_summary,
    resolve_decisions,
)
from scripts.build_jira_blueprint import run as build_blueprint
from scripts.export_discovery_package import run as export_package

_DECISIONS = {
    "projects": [
        {"key": "CORE", "name": "Product Core"},
        {"key": "PLAT", "name": "Product Platform"},
        {"key": "RND", "name": "R&D"},
        {"key": "CORP", "name": "Corporate"},
        {"key": "OPS", "name": "Ops & Support"},
    ],
    "repo_mapping": [
        {
            "repo": "repo-alpha-web",
            "project_key": "CORE",
            "component": "repo-alpha-web",
            "pilot": True,
        }
    ],
    "board_filter_owner": "jira-automation-service",
}

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
    assert plan["dry_run_only"] is True
    assert plan["manual_approval_required"] is True
    assert plan["planned_actions"], "expected planned actions"
    for action in plan["planned_actions"]:
        assert action["requires_approval"] is True
        assert action["dry_run_only"] is True
        assert action["executed"] is False
        assert action["status"] == DRY_RUN_ONLY
        assert action["guardrail"] == WRITE_GUARDRAIL
    # No execution flag anywhere in the serialized plan.
    blob = json.dumps(plan)
    assert '"executed": true' not in blob
    assert '"status": "executed"' not in blob


def test_resolve_decisions_merges_over_defaults() -> None:
    default = resolve_decisions(None)
    assert len(default["projects"]) == 5
    assert default["board_filter_owner"] == "<service-or-admin-owner>"
    merged = resolve_decisions({"board_filter_owner": "svc"})
    assert merged["board_filter_owner"] == "svc"
    assert len(merged["projects"]) == 5  # untouched default


def test_decisions_apply_project_keys_repo_mapping_and_jql() -> None:
    plan = build_dry_run_write_plan(_JIRA, _GITHUB, _DECISIONS)
    project_actions = [
        a for a in plan["planned_actions"] if a["action_type"] == "jira_create_project"
    ]
    assert {a["payload"]["key"] for a in project_actions} == {"CORE", "PLAT", "RND", "CORP", "OPS"}
    component_actions = [
        a for a in plan["planned_actions"] if a["action_type"] == "jira_create_component"
    ]
    pilot = next(a for a in component_actions if a["target"] == "repo-alpha-web")
    assert pilot["payload"]["owning_project_key"] == "CORE"
    assert pilot["payload"]["pilot"] is True
    # Board actions carry concrete JQL referencing the decided keys + service owner.
    boards = [a for a in plan["planned_actions"] if a["action_type"] == "jira_create_board"]
    roadmap = next(a for a in boards if a["target"] == "product-roadmap")
    assert "CORE" in roadmap["payload"]["jql"]
    assert roadmap["payload"]["filter_owner"] == "jira-automation-service"
    # Legacy policy and label policy echoed.
    assert plan["legacy_policy"]["preserve_legacy_keys"] is False


def test_infra_ops_board_quotes_colon_labels() -> None:
    plan = build_dry_run_write_plan(_JIRA, _GITHUB, _DECISIONS)
    boards = [a for a in plan["planned_actions"] if a["action_type"] == "jira_create_board"]
    infra = next(a for a in boards if a["target"] == "infra-ops")
    jql = infra["payload"]["jql"]
    # Colon-bearing label values must be quoted, not bare.
    assert '"source:infra"' in jql
    assert '"needs:infra"' in jql
    assert "(source:infra," not in jql


def test_decisions_reflected_in_markdown() -> None:
    mapping = build_repo_to_jira_mapping(_GITHUB, _DECISIONS)
    assert "| repo-alpha-web |" in mapping
    assert "CORE" in mapping and "yes" in mapping  # pilot marked
    blueprint = build_target_jira_blueprint(_JIRA, _GITHUB, decisions=_DECISIONS)
    assert "Product Core" in blueprint
    assert "old_to_new_mapping" in blueprint


def test_load_decisions_from_local_file(tmp_path) -> None:
    assert load_decisions(tmp_path) == {}
    target = tmp_path / ".local" / "discovery"
    target.mkdir(parents=True)
    (target / "decisions.json").write_text(json.dumps(_DECISIONS), encoding="utf-8")
    loaded = load_decisions(tmp_path)
    assert loaded["projects"][0]["key"] == "CORE"


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
    assert "Applied decisions" in blueprint.read_text()
