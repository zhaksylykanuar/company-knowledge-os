"""Discovery package builder: turn local discovery outputs into 8 deliverables.

Deterministic, offline. Reads the latest local discovery summaries (Jira,
GitHub, local-repo) and assembles the founder-facing package:

1. current-jira-audit.md      5. migration-plan.md
2. github-repo-audit.md       6. dry-run-write-plan.json
3. target-jira-blueprint.md   7. decisions-needed.md
4. repo-to-jira-mapping.md    8. do-not-migrate.md

Nothing here calls a provider or executes a write. ``dry-run-write-plan.json``
lists *planned* Jira-creation actions only; every action is
``requires_approval: true`` / ``dry_run_only: true`` / ``executed: false`` and
names the ``write_action_guard`` it must pass through before any real execution.

Founder decisions (project names/keys, repo→project mapping, label policy,
board filter owner, migration scope) are supplied as a ``decisions`` mapping —
kept out of this module so no real org names live in tracked code. The defaults
here are neutral placeholders; real decisions come from a local
``.local/discovery/decisions.json`` the scripts load.
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
CONTROLLED_LABEL_VOCABULARY = (
    "client:<slug>",
    "risk:<type>",
    "source:<system>",
    "needs:<thing>",
    "tmp:<x>",
)

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

# Neutral defaults. Real values come from a local decisions file (gitignored);
# nothing company-specific is hardcoded here.
DEFAULT_DECISIONS: dict[str, Any] = {
    "projects": [{"key": f"<KEY{i}>", "name": slot} for i, slot in enumerate(TARGET_AREA_SLOTS, 1)],
    "legacy_policy": {
        "legacy_read_only": True,
        "preserve_legacy_keys": False,
        "key_strategy": "old_to_new_mapping",
    },
    "repo_mapping": [],
    "statuses": list(TARGET_STATUSES),
    "issue_types": list(TARGET_ISSUE_TYPES),
    "labels": {
        "controlled_vocabulary": list(CONTROLLED_LABEL_VOCABULARY),
        "quarantine_uncontrolled": True,
        "blind_migrate_legacy": False,
    },
    "migration_scope": {
        "pilot_open_issues_only": True,
        "recently_closed_only_if_reporting": True,
        "archive_old_closed": True,
        "do_not_migrate": [
            "old_boards",
            "uncontrolled_labels",
            "unused_custom_fields",
            "duplicate_issue_types",
        ],
    },
    "required_fields": {
        "always": ["component", "owner", "priority"],
        "story_task": ["acceptance_criteria"],
        "bug": ["repro_steps"],
        "blocked": ["blocker_reason"],
    },
    "board_filter_owner": "<service-or-admin-owner>",
}


def resolve_decisions(decisions: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge provided decisions over the neutral defaults (top-level replace)."""
    merged = json.loads(json.dumps(DEFAULT_DECISIONS))
    if isinstance(decisions, Mapping):
        for key, value in decisions.items():
            merged[key] = value
    return merged


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


def load_decisions(root: Path) -> dict[str, Any]:
    """Load local founder decisions from ``.local/discovery/decisions.json``."""
    path = Path(root) / DISCOVERY_LOCAL_DIRNAME / DISCOVERY_SUBDIR / "decisions.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _project_keys(decided: Mapping[str, Any]) -> list[str]:
    return [str(p.get("key", "")) for p in decided["projects"] if isinstance(p, Mapping)]


def _board_jql(board: str, project_keys_csv: str) -> str:
    if board == "product-roadmap":
        return f"project in ({project_keys_csv}) AND issuetype in (Epic, Story) ORDER BY Rank ASC"
    if board == "engineering-sprint":
        return f"project in ({project_keys_csv}) AND statusCategory != Done ORDER BY Rank ASC"
    if board == "support-incidents":
        return (
            f"project in ({project_keys_csv}) AND issuetype in (Bug, Incident) "
            "ORDER BY priority DESC, updated DESC"
        )
    if board == "infra-ops":
        # Label values contain ':' so they must be quoted in JQL.
        return (
            f'project in ({project_keys_csv}) AND labels in ("source:infra", "needs:infra") '
            "ORDER BY updated DESC"
        )
    return f"project in ({project_keys_csv}) ORDER BY updated DESC"


def build_dry_run_write_plan(
    jira_summary: Mapping[str, Any],
    github_summary: Mapping[str, Any],
    decisions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Planned-only Jira creation actions. No execution, ever."""
    decided = resolve_decisions(decisions)
    actions: list[dict[str, Any]] = []

    for project in decided["projects"]:
        if not isinstance(project, Mapping):
            continue
        actions.append(
            _action(
                JIRA_CREATE_PROJECT,
                target=str(project.get("key", "")),
                payload={"key": project.get("key", ""), "name": project.get("name", "")},
                reason="Clean product-area project (product_area_model).",
                risk="medium",
            )
        )

    mapping_index = {
        str(m.get("repo", "")): m for m in decided["repo_mapping"] if isinstance(m, Mapping)
    }
    repos = github_summary.get("repos", []) if isinstance(github_summary, Mapping) else []
    for repo in repos:
        name = repo.get("name", "") if isinstance(repo, Mapping) else ""
        if not name:
            continue
        decided_map = mapping_index.get(name, {})
        actions.append(
            _action(
                JIRA_CREATE_COMPONENT,
                target=str(decided_map.get("component", name)),
                payload={
                    "component": decided_map.get("component", name),
                    "owning_project_key": decided_map.get("project_key", "<decide>"),
                    "pilot": bool(decided_map.get("pilot", False)),
                },
                reason="repo_as_component: map repository to a component.",
                risk="low",
            )
        )

    actions.append(
        _action(
            "jira_create_workflow_scheme",
            target="shared-workflow",
            payload={"statuses": list(decided["statuses"])},
            reason="Single clean workflow; replaces proliferated legacy statuses.",
            risk="high",
        )
    )
    actions.append(
        _action(
            "jira_create_issue_type_scheme",
            target="shared-issue-types",
            payload={"issue_types": list(decided["issue_types"])},
            reason="Closed issue-type set.",
            risk="medium",
        )
    )
    keys_csv = ", ".join(k for k in _project_keys(decided) if k)
    owner = decided.get("board_filter_owner", "<service-or-admin-owner>")
    for board in TARGET_BOARDS:
        actions.append(
            _action(
                "jira_create_board",
                target=board,
                payload={"board": board, "jql": _board_jql(board, keys_csv), "filter_owner": owner},
                reason="View over product/engineering/support work; owned filter.",
                risk="low",
            )
        )

    return {
        "report_kind": "jira_dry_run_write_plan",
        "execution": "none",
        "executed": False,
        "dry_run_only": True,
        "guardrail": WRITE_GUARDRAIL,
        "manual_approval_required": True,
        "legacy_policy": decided["legacy_policy"],
        "migration_scope": decided["migration_scope"],
        "label_policy": decided["labels"],
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
        "dry_run_only": True,
        "executed": False,
        "guardrail": WRITE_GUARDRAIL,
        "status": DRY_RUN_ONLY,
    }


def build_target_jira_blueprint(
    jira_summary: Mapping[str, Any],
    github_summary: Mapping[str, Any],
    *,
    base_text: str = "",
    decisions: Mapping[str, Any] | None = None,
) -> str:
    decided = resolve_decisions(decisions)
    counts = jira_summary.get("counts", {}) if isinstance(jira_summary, Mapping) else {}
    mess = jira_summary.get("mess_indicators", {}) if isinstance(jira_summary, Mapping) else {}
    keys_csv = ", ".join(k for k in _project_keys(decided) if k)
    legacy = decided["legacy_policy"]
    required = decided["required_fields"]

    derived = [
        "",
        "---",
        "",
        "## Applied decisions + discovery inputs",
        "",
        "### Target projects (decided)",
        "",
        "| Key | Name |",
        "|---|---|",
        *(
            f"| {p.get('key', '')} | {p.get('name', '')} |"
            for p in decided["projects"]
            if isinstance(p, Mapping)
        ),
        "",
        "### Legacy policy",
        "",
        f"- Legacy Jira read-only: {legacy.get('legacy_read_only')}",
        f"- Preserve legacy keys: {legacy.get('preserve_legacy_keys')} "
        f"(strategy: {legacy.get('key_strategy')})",
        "",
        "### Workflow statuses (decided)",
        "",
        f"- {', '.join(decided['statuses'])}",
        "",
        "### Issue types (decided)",
        "",
        f"- {', '.join(decided['issue_types'])}",
        "",
        "### Label vocabulary (controlled)",
        "",
        f"- {', '.join(decided['labels'].get('controlled_vocabulary', []))}",
        f"- Quarantine uncontrolled: {decided['labels'].get('quarantine_uncontrolled')}; "
        f"blind-migrate legacy: {decided['labels'].get('blind_migrate_legacy')}",
        "",
        "### Required fields / hygiene",
        "",
        f"- Always: {', '.join(required.get('always', []))}",
        f"- Story/Task: {', '.join(required.get('story_task', []))}",
        f"- Bug: {', '.join(required.get('bug', []))}",
        f"- Blocked: {', '.join(required.get('blocked', []))}",
        "",
        "### Board filters (proposed JQL)",
        "",
        f"Filter owner: {decided.get('board_filter_owner')}",
        "",
        *(f"- `{board}`: `{_board_jql(board, keys_csv)}`" for board in TARGET_BOARDS),
        "",
        "### Discovery inputs (legacy/reference only)",
        "",
        f"- Legacy projects: {counts.get('project_count', 'n/a')}",
        f"- Legacy statuses: {counts.get('status_count', 'n/a')} (target {len(TARGET_STATUSES)})",
        f"- Legacy issue types: {counts.get('issue_type_count', 'n/a')} "
        f"(target {len(TARGET_ISSUE_TYPES)})",
        f"- Legacy custom fields: {counts.get('custom_field_count', 'n/a')}",
        f"- Discovered repos: {_count(github_summary, 'repo_count')} → components",
        f"- Mess indicators: status_proliferation={mess.get('status_proliferation', 'n/a')}, "
        f"issue_type_proliferation={mess.get('issue_type_proliferation', 'n/a')}, "
        f"custom_field_heavy={mess.get('custom_field_heavy', 'n/a')}",
        "",
    ]
    header = (
        base_text.strip()
        or "# Jira Target Blueprint\n\n(See docs/ops/jira-target-blueprint.md for the full model.)"
    )
    return header + "\n" + "\n".join(derived)


def build_repo_to_jira_mapping(
    github_summary: Mapping[str, Any], decisions: Mapping[str, Any] | None = None
) -> str:
    decided = resolve_decisions(decisions)
    mapping_index = {
        str(m.get("repo", "")): m for m in decided["repo_mapping"] if isinstance(m, Mapping)
    }
    repos = github_summary.get("repos", []) if isinstance(github_summary, Mapping) else []
    lines = [
        "# Repo → Jira Mapping",
        "",
        "Strategy: `repo_as_component`. Each repo becomes one component in its",
        "owning area project.",
        "",
        "| Repo | Domain hints | Project | Component | Pilot | Status |",
        "|---|---|---|---|---|---|",
    ]
    for repo in repos:
        if not isinstance(repo, Mapping):
            continue
        name = repo.get("name", "")
        hints = ", ".join(repo.get("domain_hints", []) or []) or "—"
        decided_map = mapping_index.get(name)
        if decided_map:
            project = decided_map.get("project_key", "<decide>")
            component = decided_map.get("component", name)
            pilot = "yes" if decided_map.get("pilot") else "—"
            status = "decided"
        else:
            project = _suggest_area(repo.get("domain_hints", []) or [])
            component = name
            pilot = "—"
            status = "needs founder confirm"
        lines.append(f"| {name} | {hints} | {project} | {component} | {pilot} | {status} |")
    if not repos:
        lines.append("| (no repos discovered yet) | — | — | — | — | run github discovery |")
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


def build_migration_plan(
    jira_summary: Mapping[str, Any],
    github_summary: Mapping[str, Any],
    decisions: Mapping[str, Any] | None = None,
) -> str:
    decided = resolve_decisions(decisions)
    scope = decided["migration_scope"]
    pilot = _pilot_repo(decided)
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
            f"2. Pilot: wire `{pilot}` as a component; verify repo ↔ project ↔ task "
            "linkage end to end.",
            "3. Validate pilot (status snapshots, Jira↔GitHub reality check).",
            "4. Onboard remaining repos (≈19) into the org as components, in batches.",
            "5. Enable the Jira source-agent on the clean structure.",
            "",
            "## What to migrate",
            "",
            f"- Pilot: active/open issues only = {scope.get('pilot_open_issues_only')}.",
            "- Recently closed issues only where reporting continuity needs them = "
            f"{scope.get('recently_closed_only_if_reporting')}.",
            "",
            "## What to archive (not migrate)",
            "",
            f"- Archive old closed/stale issues = {scope.get('archive_old_closed')}.",
            f"- Do not migrate: {', '.join(scope.get('do_not_migrate', []))}.",
            "- See do-not-migrate.md.",
            "",
            f"## Scale context: legacy projects {_count(jira_summary, 'project_count')}, "
            f"discovered repos {_count(github_summary, 'repo_count')}, future repos ~19.",
            "",
        ]
    )


def _pilot_repo(decided: Mapping[str, Any]) -> str:
    for m in decided["repo_mapping"]:
        if isinstance(m, Mapping) and m.get("pilot"):
            return str(m.get("repo", "<pilot-repo>"))
    return "<pilot-repo>"


def build_decisions_needed(
    jira_summary: Mapping[str, Any],
    github_summary: Mapping[str, Any],
    decisions: Mapping[str, Any] | None = None,
) -> str:
    decided = resolve_decisions(decisions)
    applied = [
        "# Decisions",
        "",
        "## Applied (defaults from founder)",
        "",
        "- Projects: "
        + ", ".join(
            f"{p.get('key', '')}={p.get('name', '')}"
            for p in decided["projects"]
            if isinstance(p, Mapping)
        ),
        f"- Legacy: read-only={decided['legacy_policy'].get('legacy_read_only')}, "
        f"preserve_keys={decided['legacy_policy'].get('preserve_legacy_keys')}, "
        f"{decided['legacy_policy'].get('key_strategy')}",
        f"- Statuses: {', '.join(decided['statuses'])}",
        f"- Issue types: {', '.join(decided['issue_types'])}",
        f"- Labels controlled: {', '.join(decided['labels'].get('controlled_vocabulary', []))}",
        f"- Board filter owner: {decided.get('board_filter_owner')}",
        "",
        "## Still open / to confirm before write",
        "",
        "- [ ] Confirm exact board JQL (see target-jira-blueprint.md).",
        "- [ ] Owning project for any repo still marked `needs founder confirm` "
        "(repo-to-jira-mapping.md).",
        "- [ ] Any hard external dependency that forces a legacy key to be preserved.",
        "- [ ] Legacy issue-type → target mapping for habit/duplicate types "
        f"(legacy has {_count(jira_summary, 'issue_type_count')}).",
        "- [ ] Final approval to create the clean structure (separate write-enabled run).",
        "",
    ]
    return "\n".join(applied)


def build_do_not_migrate(
    jira_summary: Mapping[str, Any], decisions: Mapping[str, Any] | None = None
) -> str:
    decided = resolve_decisions(decisions)
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
            f"- Near-duplicate statuses: {mess.get('near_duplicate_status_count', 0)}.",
            f"- Issue types beyond the target {len(TARGET_ISSUE_TYPES)} "
            f"(over-target {mess.get('issue_type_over_target', 0)}) — map into the closed set.",
            f"- Unused/one-off custom fields ({counts.get('custom_field_count', 0)} total; "
            "review before recreating any).",
            "- Uncontrolled legacy labels — quarantine, do not blind-migrate "
            f"(quarantine={decided['labels'].get('quarantine_uncontrolled')}).",
            "- Personal/stale board filters and abandoned boards.",
            "- Duplicate issue types created by habit.",
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
    decisions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble all 8 deliverables as {filename: content}. JSON for the plan."""
    package: dict[str, Any] = {
        "current-jira-audit.md": jira_audit_md
        or "# Current Jira Audit\n\n(no discovery run found)\n",
        "github-repo-audit.md": github_audit_md
        or "# GitHub Repo Audit\n\n(no discovery run found)\n",
        "target-jira-blueprint.md": build_target_jira_blueprint(
            jira_summary, github_summary, base_text=blueprint_base_text, decisions=decisions
        ),
        "repo-to-jira-mapping.md": build_repo_to_jira_mapping(github_summary, decisions),
        "migration-plan.md": build_migration_plan(jira_summary, github_summary, decisions),
        "dry-run-write-plan.json": build_dry_run_write_plan(
            jira_summary, github_summary, decisions
        ),
        "decisions-needed.md": build_decisions_needed(jira_summary, github_summary, decisions),
        "do-not-migrate.md": build_do_not_migrate(jira_summary, decisions),
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
