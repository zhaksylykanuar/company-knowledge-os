"""Deterministic, offline MVP completion audit for FounderOS.

This module maps every ``founderOS_MASTER_PLAYBOOK.md`` MVP requirement (§1.5)
and every main end-to-end flow step (§1.4) to authoritative in-repository
evidence, and reports which implementation paths have repository evidence
versus which still require runtime or human proof: the local lifecycle, first
GitHub connection/read, and first real external action result.

It is a pure, read-only, offline check. It performs no provider calls, opens no
network connection, touches no database, and never reads or prints secrets,
tokens, env values, or credential contents. It only checks that specific tracked
files exist and contain specific structural markers, so a completion audit does
not have to be re-derived by hand every time.

The audit intentionally does not claim the full MVP is "done". File markers can
prove implementation presence, not that the runtime lifecycle or external
flows were actually exercised. Those acceptance gates require separate,
sanitized runtime evidence and explicit human approval where applicable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Minimum number of ``test_*.py`` files required to treat "basic tests" (§1.5)
# as satisfied. This is a deliberately low floor: the suite is far larger, but
# the audit only needs to prove the requirement is not empty.
MIN_TEST_FILES = 10


@dataclass(frozen=True)
class EvidenceCheck:
    """A single file-based evidence requirement.

    ``path`` is relative to the repository root. When ``marker`` is set the file
    must also contain that literal substring; otherwise mere existence is enough.
    """

    path: str
    marker: str | None = None


@dataclass(frozen=True)
class AuditItem:
    """One audited requirement or main-flow step."""

    key: str
    requirement: str
    category: str
    evidence: tuple[EvidenceCheck, ...]
    human_gated: bool = False
    human_note: str | None = None


@dataclass(frozen=True)
class AuditItemResult:
    key: str
    requirement: str
    category: str
    human_gated: bool
    evidence_present: bool
    missing_evidence: tuple[str, ...] = ()
    human_note: str | None = None

    @property
    def status(self) -> str:
        if not self.evidence_present:
            return "missing"
        if self.human_gated:
            return "code_ready_human_gated"
        return "complete_local"


# --- §1.5 "Что входит в MVP" (Must-have MVP requirements) --------------------

_MVP_REQUIREMENT_ITEMS: tuple[AuditItem, ...] = (
    AuditItem(
        key="auth",
        requirement="auth (email+password server-side sessions)",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/auth_routes.py", "/login"),
            EvidenceCheck("app/api/auth.py", "require_session"),
            EvidenceCheck("web/app/login/page.tsx"),
        ),
    ),
    AuditItem(
        key="workspace",
        requirement="workspace",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/workspaces.py", "bootstrap_workspace_for_owner"),
        ),
    ),
    AuditItem(
        key="ui_shell",
        requirement="UI shell",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("web/app/layout.tsx"),
            EvidenceCheck("web/components/Sidebar.tsx"),
        ),
    ),
    AuditItem(
        key="connector_framework",
        requirement="connector framework",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/connectors.py"),
            EvidenceCheck("web/app/connectors/page.tsx"),
        ),
    ),
    AuditItem(
        key="github_connector",
        requirement="GitHub connector",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/github.py", "/connections/app-installation"),
            EvidenceCheck("web/app/github/page.tsx"),
        ),
    ),
    AuditItem(
        key="jira_connector",
        requirement="Jira connector (minimal, local import)",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/jira.py", "/issues/import"),
            EvidenceCheck("web/app/jira/page.tsx"),
        ),
    ),
    AuditItem(
        key="gmail_connector",
        requirement="Gmail connector (minimal, local import)",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/gmail.py", "/messages/import"),
            EvidenceCheck("web/app/gmail/page.tsx"),
        ),
    ),
    AuditItem(
        key="drive_connector",
        requirement="Google Drive connector (minimal, local import)",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/drive.py", "/files/import"),
            EvidenceCheck("web/app/drive/page.tsx"),
        ),
    ),
    AuditItem(
        key="internal_documents",
        requirement="internal documents",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/documents.py"),
            EvidenceCheck("web/app/documents/page.tsx"),
        ),
    ),
    AuditItem(
        key="raw_source_records",
        requirement="raw source records",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/db/canonical_models.py", "class SourceRecord"),
        ),
    ),
    AuditItem(
        key="normalized_entities",
        requirement="normalized entities",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/workspace_company_brain.py", "/entities"),
            EvidenceCheck("web/components/NormalizedEntitiesPanel.tsx"),
        ),
    ),
    AuditItem(
        key="evidence_refs",
        requirement="evidence refs",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/db/canonical_models.py", "class EvidenceRef"),
        ),
    ),
    AuditItem(
        key="company_brain_view",
        requirement="Company Brain view",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("web/app/company-brain/page.tsx"),
            EvidenceCheck("app/api/workspace_company_brain.py"),
        ),
    ),
    AuditItem(
        key="founder_dashboard",
        requirement="Founder Dashboard",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("web/app/dashboard/page.tsx"),
        ),
    ),
    AuditItem(
        key="company_world_view",
        requirement="Company World operating map",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck(
                "web/components/CompanyWorldPanel.tsx",
                "export function CompanyWorldPanel",
            ),
            EvidenceCheck(
                "web/app/company-brain/page.tsx",
                "<CompanyWorldPanel",
            ),
            EvidenceCheck(
                "app/api/company_map.py",
                'prefix="/api/v1/workspaces/{workspace_id}/company-map"',
            ),
            EvidenceCheck(
                "app/main.py",
                "app.include_router(company_map_router",
            ),
            EvidenceCheck(
                "app/services/company_map_read_service.py",
                "async def build_workspace_company_map",
            ),
        ),
    ),
    AuditItem(
        key="manual_founder_briefing",
        requirement="manual Founder Briefing",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/briefings.py", "/manual"),
            EvidenceCheck("web/app/briefings/page.tsx"),
        ),
    ),
    AuditItem(
        key="action_proposals",
        requirement="action proposals",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/actions.py", "/proposals"),
            EvidenceCheck("web/app/actions/page.tsx"),
        ),
    ),
    AuditItem(
        key="human_approval_before_execution",
        requirement="human approval before execution",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/api/actions.py", "/execute"),
            EvidenceCheck(
                "app/services/github_issue_execution_service.py",
                "confirm_external_write",
            ),
        ),
    ),
    AuditItem(
        key="basic_logging",
        requirement="basic logging",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("app/core/logging.py", "RequestLoggingMiddleware"),
        ),
    ),
    AuditItem(
        key="basic_tests",
        requirement="basic tests",
        category="mvp_requirement",
        # Presence is validated dynamically (test-file count); the anchor file is
        # only a cheap existence check.
        evidence=(
            EvidenceCheck("tests/conftest.py"),
        ),
    ),
    AuditItem(
        key="local_full_stack_runtime",
        requirement="local full-stack runtime",
        category="mvp_requirement",
        evidence=(
            EvidenceCheck("Makefile", "local:"),
            EvidenceCheck("scripts/local_runtime.py", "supervise_local_runtime"),
            EvidenceCheck("scripts/local_runtime.py", "create_local_backup"),
            EvidenceCheck("docs/operations/local-runtime.md", "make local"),
        ),
        human_gated=True,
        human_note=(
            "The one-command local runtime is implemented, but repository marker "
            "checks cannot attest doctor/start/onboarding/smoke/restore/stop acceptance."
        ),
    ),
)


# --- §1.4 "Успешный результат MVP" (main end-to-end flow) --------------------

_MAIN_FLOW_ITEMS: tuple[AuditItem, ...] = (
    AuditItem(
        key="flow_login",
        requirement="Login",
        category="main_flow",
        evidence=(EvidenceCheck("app/api/auth_routes.py", "/login"),),
    ),
    AuditItem(
        key="flow_create_workspace",
        requirement="Create Workspace",
        category="main_flow",
        evidence=(
            EvidenceCheck("app/api/workspaces.py", "bootstrap_workspace_for_owner"),
        ),
    ),
    AuditItem(
        key="flow_connect_github",
        requirement="Connect GitHub",
        category="main_flow",
        evidence=(
            EvidenceCheck("app/api/github.py", "/connections/app-installation"),
        ),
        human_gated=True,
        human_note=(
            "The local connection flow exists, but the first real GitHub App "
            "installation requires founder-owned credentials and explicit approval."
        ),
    ),
    AuditItem(
        key="flow_sync_github",
        requirement="Sync GitHub",
        category="main_flow",
        evidence=(
            EvidenceCheck("app/api/github.py", "/repositories/issues/sync"),
        ),
        human_gated=True,
        human_note=(
            "The read-only sync path exists, but the first live provider read "
            "has not been proven and remains an explicitly approved operation."
        ),
    ),
    AuditItem(
        key="flow_see_dashboard",
        requirement="See Dashboard",
        category="main_flow",
        evidence=(EvidenceCheck("web/app/dashboard/page.tsx"),),
    ),
    AuditItem(
        key="flow_company_brain_entities",
        requirement="See Company Brain entities",
        category="main_flow",
        evidence=(
            EvidenceCheck("web/app/company-brain/page.tsx"),
            EvidenceCheck("app/api/workspace_company_brain.py", "/entities"),
        ),
    ),
    AuditItem(
        key="flow_generate_briefing",
        requirement="Generate Founder Briefing",
        category="main_flow",
        evidence=(EvidenceCheck("app/api/briefings.py", "/manual"),),
    ),
    AuditItem(
        key="flow_open_evidence",
        requirement="Open Evidence",
        category="main_flow",
        evidence=(EvidenceCheck("web/components/EvidenceDrawer.tsx"),),
    ),
    AuditItem(
        key="flow_approve_action_proposal",
        requirement="Approve Action Proposal",
        category="main_flow",
        evidence=(
            EvidenceCheck("app/api/actions.py", "/proposals/{proposal_id}/approve"),
            EvidenceCheck("web/app/actions/page.tsx"),
        ),
    ),
    AuditItem(
        key="flow_external_action_result",
        requirement="See External Action Result",
        category="main_flow",
        evidence=(
            EvidenceCheck("app/api/actions.py", "/execute"),
            EvidenceCheck("app/services/github_execution_result_sync_service.py"),
            EvidenceCheck("docs/deploy/external-action-result-smoke.md"),
        ),
        human_gated=True,
        human_note=(
            "The execute + result-sync code path and manual runbook exist, but "
            "a real external action result requires live provider credentials "
            "and one explicitly approved external write."
        ),
    ),
)


_ALL_ITEMS: tuple[AuditItem, ...] = _MVP_REQUIREMENT_ITEMS + _MAIN_FLOW_ITEMS


def _file_exists(root: Path, relpath: str) -> bool:
    return (root / relpath).is_file()


def _file_contains(root: Path, relpath: str, marker: str) -> bool:
    path = root / relpath
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return marker in text


def _count_test_files(root: Path) -> int:
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return 0
    return sum(1 for _ in tests_dir.glob("test_*.py"))


def _evaluate_item(root: Path, item: AuditItem) -> AuditItemResult:
    missing: list[str] = []
    for check in item.evidence:
        if check.marker is None:
            ok = _file_exists(root, check.path)
            label = check.path
        else:
            ok = _file_contains(root, check.path, check.marker)
            label = f"{check.path} :: {check.marker}"
        if not ok:
            missing.append(label)

    evidence_present = not missing
    if item.key == "basic_tests":
        test_count = _count_test_files(root)
        if test_count < MIN_TEST_FILES:
            evidence_present = False
            missing.append(f"tests/test_*.py >= {MIN_TEST_FILES} (found {test_count})")

    return AuditItemResult(
        key=item.key,
        requirement=item.requirement,
        category=item.category,
        human_gated=item.human_gated,
        evidence_present=evidence_present,
        missing_evidence=tuple(missing),
        human_note=item.human_note,
    )


@dataclass(frozen=True)
class MvpCompletionAudit:
    items: tuple[AuditItemResult, ...] = field(default_factory=tuple)

    def by_category(self, category: str) -> tuple[AuditItemResult, ...]:
        return tuple(item for item in self.items if item.category == category)

    @property
    def local_items(self) -> tuple[AuditItemResult, ...]:
        return tuple(item for item in self.items if not item.human_gated)

    @property
    def human_gated_items(self) -> tuple[AuditItemResult, ...]:
        return tuple(item for item in self.items if item.human_gated)

    @property
    def local_scope_complete(self) -> bool:
        """True when every non-human-gated requirement has evidence."""

        return all(item.evidence_present for item in self.local_items)

    @property
    def code_ready_for_human_gated(self) -> bool:
        """True when every human-gated item at least has its code path present."""

        return all(item.evidence_present for item in self.human_gated_items)

    @property
    def fully_complete(self) -> bool:
        """Whether this offline definition has no unresolved acceptance gates.

        Human/runtime-gated definitions are static in this repository-only
        audit, so it cannot transition them to accepted. A future receipt-backed
        audit may do that; until then this property intentionally remains false.
        """

        return self.local_scope_complete and not self.human_gated_items

    def to_dict(self) -> dict[str, object]:
        return {
            "check": "mvp_completion_audit",
            "assessment_scope": "repository_evidence_only",
            "offline": True,
            "provider_calls": False,
            "reads_secrets": False,
            "local_scope_complete": self.local_scope_complete,
            "repository_evidence_complete": (
                self.local_scope_complete and self.code_ready_for_human_gated
            ),
            "runtime_acceptance_assessed": False,
            "code_ready_for_human_gated": self.code_ready_for_human_gated,
            "fully_complete": self.fully_complete,
            "summary": {
                "total": len(self.items),
                "present": sum(1 for item in self.items if item.evidence_present),
                "local_total": len(self.local_items),
                "local_present": sum(
                    1 for item in self.local_items if item.evidence_present
                ),
                "human_gated_total": len(self.human_gated_items),
                "human_gated_present": sum(
                    1 for item in self.human_gated_items if item.evidence_present
                ),
            },
            "items": [
                {
                    "key": item.key,
                    "requirement": item.requirement,
                    "category": item.category,
                    "status": item.status,
                    "evidence_present": item.evidence_present,
                    "human_gated": item.human_gated,
                    "missing_evidence": list(item.missing_evidence),
                    "human_note": item.human_note,
                }
                for item in self.items
            ],
            "human_gated_next_steps": [
                {
                    "key": item.key,
                    "requirement": item.requirement,
                    "human_note": item.human_note,
                }
                for item in self.human_gated_items
            ],
        }


def run_mvp_completion_audit(root: Path | str | None = None) -> MvpCompletionAudit:
    """Evaluate every MVP requirement and main-flow step against repo evidence."""

    resolved_root = Path(root).resolve() if root is not None else REPO_ROOT
    results = tuple(_evaluate_item(resolved_root, item) for item in _ALL_ITEMS)
    return MvpCompletionAudit(items=results)
