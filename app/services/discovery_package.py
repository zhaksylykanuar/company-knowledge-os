"""Discovery package builder: turn local discovery outputs into 8 deliverables.

Deterministic, offline. Reads the latest local discovery summaries (Jira,
GitHub, local-repo) and assembles the founder-facing package:

1. current-jira-audit.md      5. migration-plan.md
2. github-repo-audit.md       6. dry-run-write-plan.json
3. target-jira-blueprint.md   7. decisions-needed.md
4. repo-to-jira-mapping.md    8. do-not-migrate.md

Nothing here calls a provider or executes a write. ``dry-run-write-plan.json``
lists *planned* Jira-creation actions only; every action is
``requires_approval: true`` / ``status: dry_run_only`` and names the
``write_action_guard`` it must pass through before any real execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.discovery_core import DISCOVERY_LOCAL_DIRNAME, DISCOVERY_SUBDIR
from app.services.secret_patterns import contains_secret_value
from app.services.write_action_guard import (
    JIRA_CREATE_COMPONENT,
    JIRA_CREATE_ISSUE,
    JIRA_CREATE_PROJECT,
)

# Target model classes (kept in sync with docs/ops/jira-target-blueprint.md).
TARGET_AREA_SLOTS = (
    "area-product-core",
    "area-product-platform",
    "area-rnd",
    "area-corporate",
    "area-ops-support",
)
TARGET_ISSUE_TYPES = ("Epic", "Story", "Task", "Bug", "Subtask", "Incident", "Tech Debt", "Spike")
TARGET_STATUSES = (
    "Backlog",
    "Ready",
    "In Progress",
    "Code Review",
    "Validation",
    "Ready for Release",
    "Done",
    "Blocked",
)
TARGET_BOARDS = ("product-roadmap", "engineering-sprint", "support-incidents", "infra-ops")

PACKAGE_FILES = (
    "current-jira-audit.md",
    "github-repo-audit.md",
    "target-jira-blueprint.md",
    "repo-to-jira-mapping.md",
    "migration-plan.md",
    "dry-run-write-plan.json",
    "decisions-needed.md",
    "do-not-migrate.md",
)

DRY_RUN_ONLY = "dry_run_only"
WRITE_GUARDRAIL = "write_action_guard"


def find_latest_run(root: Path, source: str) -> Path | None:
    base = Path(root) / DISCOVERY_LOCAL_DIRNAME / DISCOVERY_SUBDIR / source
    if not base.is_dir():
        return None
    runs = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)
    return runs[-1] if runs else None


def load_latest_summary(root: Path, source: str) -> dict[str, Any]:
    run = find_latest_run(root, source)
    if run is None:
        return {}
    summary_file = run / "summary.json"
    if not summary_file.is_file():
        return {}
    try:
        data = json.loads(summary_file.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def build_dry_run_write_plan(
    jira_summary: Mapping[str, Any], github_summary: Mapping[str, Any]
) -> dict[str, Any]:
    """Planned-only Jira creation actions. No execution, ever."""
    actions: list[dict[str, Any]] = []

    for slot in TARGET_AREA_SLOTS:
        actions.append(
            _action(
                JIRA_CREATE_PROJECT,
                target=slot,
                payload={"name": "<decide-from-discovery>", "key": "<decide>"},
                reason="Clean product-area project (product_area_model).",
                risk="medium",
            )
        )

    repos = github_summary.get("repos", []) if isinstance(github_summary, Mapping) else []
    for repo in repos:
        name = repo.get("name", "") if isinstance(repo, Mapping) else ""
        if not name:
            continue
        actions.append(
            _action(
                JIRA_CREATE_COMPONENT,
                target=name,
                payload={"component": name, "owning_area": "<decide-from-discovery>"},
                reason="repo_as_component: map repository to a component.",
                risk="low",
            )
        )

    actions.append(
        _action(
            "jira_create_workflow_scheme",
            target="shared-workflow",
            payload={"statuses": list(TARGET_STATUSES)},
            reason="Single clean workflow; replaces proliferated legacy statuses.",
            risk="high",
        )
    )
    actions.append(
        _action(
            "jira_create_issue_type_scheme",
            target="shared-issue-types",
            payload={"issue_types": list(TARGET_ISSUE_TYPES)},
            reason="Closed issue-type set.",
            risk="medium",
        )
    )
    for board in TARGET_BOARDS:
        actions.append(
            _action(
                "jira_create_board",
                target=board,
                payload={"board": board, "filter": "<owned-jql>"},
                reason="View over product/engineering/support work.",
                risk="low",
            )
        )

    return {
        "report_kind": "jira_dry_run_write_plan",
        "execution": "none",
        "executed": False,
        "guardrail": WRITE_GUARDRAIL,
        "manual_approval_required": True,
        "source_inventory": {
            "legacy_project_count": _count(jira_summary, "project_count"),
            "legacy_status_count": _count(jira_summary, "status_count"),
            "discovered_repo_count": _count(github_summary, "repo_count"),
        },
        "planned_actions": actions,
        "planned_action_count": len(actions),
        "example_issue_boundary": JIRA_CREATE_ISSUE,
    }


def _action(
    action_type: str, *, target: str, payload: Mapping[str, Any], reason: str, risk: str
) -> dict[str, Any]:
    return {
        "action_type": action_type,
        "target": target,
        "payload": dict(payload),
        "reason": reason,
        "risk": risk,
        "requires_approval": True,
        "guardrail": WRITE_GUARDRAIL,
        "status": DRY_RUN_ONLY,
    }


def build_target_jira_blueprint(
    jira_summary: Mapping[str, Any],
    github_summary: Mapping[str, Any],
    *,
    base_text: str = "",
) -> str:
    counts = jira_summary.get("counts", {}) if isinstance(jira_summary, Mapping) else {}
    mess = jira_summary.get("mess_indicators", {}) if isinstance(jira_summary, Mapping) else {}
    derived = [
        "",
        "---",
        "",
        "## Discovery-derived inputs",
        "",
        "Filled from the latest read-only discovery run (legacy/reference only):",
        "",
        f"- Legacy projects: {counts.get('project_count', 'n/a')}",
        f"- Legacy statuses: {counts.get('status_count', 'n/a')} (target {len(TARGET_STATUSES)})",
        f"- Legacy issue types: {counts.get('issue_type_count', 'n/a')} "
        f"(target {len(TARGET_ISSUE_TYPES)})",
        f"- Legacy custom fields: {counts.get('custom_field_count', 'n/a')}",
        f"- Discovered repos: {_count(github_summary, 'repo_count')} → components",
        "",
        "Mess indicators driving the rebuild:",
        f"- Status proliferation: {mess.get('status_proliferation', 'n/a')}",
        f"- Issue-type proliferation: {mess.get('issue_type_proliferation', 'n/a')}",
        f"- Custom-field heavy: {mess.get('custom_field_heavy', 'n/a')}",
        "",
        "Target structure (see sections above for the full model):",
        f"- Area projects: {', '.join(TARGET_AREA_SLOTS)}",
        f"- Issue types: {', '.join(TARGET_ISSUE_TYPES)}",
        f"- Statuses: {', '.join(TARGET_STATUSES)}",
        f"- Boards: {', '.join(TARGET_BOARDS)}",
        "",
    ]
    header = (
        base_text.strip()
        or "# Jira Target Blueprint\n\n(See docs/ops/jira-target-blueprint.md for the full model.)"
    )
    return header + "\n" + "\n".join(derived)


def build_repo_to_jira_mapping(github_summary: Mapping[str, Any]) -> str:
    repos = github_summary.get("repos", []) if isinstance(github_summary, Mapping) else []
    lines = [
        "# Repo → Jira Mapping",
        "",
        "Strategy: `repo_as_component`. Each repo becomes one component in its",
        "owning area project. Owning area is a founder decision (see decisions-needed).",
        "",
        "| Repo | Domain hints | Suggested area | Component | Decision |",
        "|---|---|---|---|---|",
    ]
    for repo in repos:
        if not isinstance(repo, Mapping):
            continue
        name = repo.get("name", "")
        hints = ", ".join(repo.get("domain_hints", []) or []) or "—"
        suggested = _suggest_area(repo.get("domain_hints", []) or [])
        lines.append(f"| {name} | {hints} | {suggested} | {name} | needs founder confirm |")
    if not repos:
        lines.append("| (no repos discovered yet) | — | — | — | run github discovery |")
    lines += [
        "",
        "Future repositories (≈19) map the same way once migrated into the org.",
        "",
    ]
    return "\n".join(lines)


def _suggest_area(domain_hints: list[str]) -> str:
    mapping = {
        "frontend": "area-product-core",
        "backend": "area-product-core",
        "service": "area-product-platform",
        "infrastructure": "area-product-platform",
        "data": "area-product-platform",
        "rnd": "area-rnd",
        "mobile": "area-product-core",
    }
    for hint in domain_hints:
        if hint in mapping:
            return mapping[hint]
    return "<decide-from-discovery>"


def build_migration_plan(jira_summary: Mapping[str, Any], github_summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Migration Plan",
            "",
            "Read-only discovery is done; this plan stays no-write until approval.",
            "",
            "## Sequence",
            "",
            "1. Create the clean target structure (dry-run-write-plan.json) — "
            "approval-gated via write_action_guard.",
            "2. Pilot: wire one current frontend repo as a component; verify "
            "repo ↔ project ↔ task linkage end to end.",
            "3. Validate pilot (status snapshots, Jira↔GitHub reality check).",
            "4. Onboard remaining repos (≈19) into the org as components, in batches.",
            "5. Enable the Jira source-agent on the clean structure.",
            "",
            "## What to migrate",
            "",
            "- Active/open issues mapped to target project/type/status.",
            "- Recently closed issues only where reporting continuity needs them.",
            "",
            "## What to archive (not migrate)",
            "",
            "- Old closed/archive issues — leave in the read-only legacy projects.",
            "- See do-not-migrate.md for legacy noise.",
            "",
            "## Manual decisions required",
            "",
            "- Area names/keys, repo→area ownership, label slugs, key-preservation "
            "policy. See decisions-needed.md.",
            "",
            f"## Scale context: legacy projects "
            f"{_count(jira_summary, 'project_count')}, discovered repos "
            f"{_count(github_summary, 'repo_count')}, future repos ~19.",
            "",
        ]
    )


def build_decisions_needed(
    jira_summary: Mapping[str, Any], github_summary: Mapping[str, Any]
) -> str:
    return "\n".join(
        [
            "# Decisions Needed",
            "",
            "Founder decisions required before any write step:",
            "",
            "## Projects & keys",
            "- [ ] Real name + key for each area slot: " + ", ".join(TARGET_AREA_SLOTS),
            "- [ ] Preserve legacy keys or map old→new?",
            "",
            "## Repo ownership",
            "- [ ] Owning area/component for each repo (see repo-to-jira-mapping.md).",
            "- [ ] Which repo is the pilot?",
            "",
            "## Workflow & types",
            f"- [ ] Confirm target statuses ({len(TARGET_STATUSES)}) map legacy "
            f"statuses ({_count(jira_summary, 'status_count')}).",
            "- [ ] Confirm closed issue-type set; map legacy duplicates.",
            "",
            "## Governance",
            "- [ ] Label vocabulary (client:/risk:/source:/needs:).",
            "- [ ] Required fields + Definition of Ready/Done.",
            "",
            "## Migration scope",
            "- [ ] Active-issue migration scope; closed-issue scope.",
            "- [ ] Approval to create the clean structure (separate write-enabled run).",
            "",
        ]
    )


def build_do_not_migrate(jira_summary: Mapping[str, Any]) -> str:
    mess = jira_summary.get("mess_indicators", {}) if isinstance(jira_summary, Mapping) else {}
    counts = jira_summary.get("counts", {}) if isinstance(jira_summary, Mapping) else {}
    return "\n".join(
        [
            "# Do Not Migrate",
            "",
            "Legacy patterns to leave behind in the read-only archive:",
            "",
            f"- Proliferated statuses beyond the target {len(TARGET_STATUSES)} "
            f"(legacy has {_count(jira_summary, 'status_count')}; "
            f"over-target {mess.get('status_over_target', 0)}).",
            f"- Near-duplicate statuses: {mess.get('near_duplicate_status_count', 0)} "
            "(e.g. To Do / Todo / Doing).",
            f"- Issue types beyond the target {len(TARGET_ISSUE_TYPES)} "
            f"(over-target {mess.get('issue_type_over_target', 0)}).",
            f"- Unused/one-off custom fields ({counts.get('custom_field_count', 0)} total; "
            "review before recreating any).",
            "- Personal/stale board filters and abandoned boards.",
            "- Duplicate issue types created by habit.",
            "- Old labels with no controlled-vocabulary prefix.",
            "",
            "None of the above is recreated in the target model.",
            "",
        ]
    )


def build_discovery_package(
    *,
    jira_summary: Mapping[str, Any],
    github_summary: Mapping[str, Any],
    local_summary: Mapping[str, Any] | None = None,
    jira_audit_md: str = "",
    github_audit_md: str = "",
    blueprint_base_text: str = "",
) -> dict[str, Any]:
    """Assemble all 8 deliverables as {filename: content}. JSON for the plan."""
    package: dict[str, Any] = {
        "current-jira-audit.md": jira_audit_md
        or "# Current Jira Audit\n\n(no discovery run found)\n",
        "github-repo-audit.md": github_audit_md
        or "# GitHub Repo Audit\n\n(no discovery run found)\n",
        "target-jira-blueprint.md": build_target_jira_blueprint(
            jira_summary, github_summary, base_text=blueprint_base_text
        ),
        "repo-to-jira-mapping.md": build_repo_to_jira_mapping(github_summary),
        "migration-plan.md": build_migration_plan(jira_summary, github_summary),
        "dry-run-write-plan.json": build_dry_run_write_plan(jira_summary, github_summary),
        "decisions-needed.md": build_decisions_needed(jira_summary, github_summary),
        "do-not-migrate.md": build_do_not_migrate(jira_summary),
    }
    _assert_package_safe(package)
    return package


def _assert_package_safe(package: Mapping[str, Any]) -> None:
    for name, content in package.items():
        text = content if isinstance(content, str) else json.dumps(content)
        if contains_secret_value(text):
            raise ValueError(f"secret_value_in_package:{name}")


def _count(summary: Mapping[str, Any], key: str) -> Any:
    counts = summary.get("counts", {}) if isinstance(summary, Mapping) else {}
    return counts.get(key, "n/a")
