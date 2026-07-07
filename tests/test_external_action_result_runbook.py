from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "deploy" / "external-action-result-smoke.md"

REQUIRED_TERMS = (
    "Approve Action Proposal -> See External Action Result",
    "manual, human-approved",
    "One explicitly approved external write only",
    "FOS_GITHUB_WRITE_ALLOWED_REPOS",
    "ENABLE_WRITE_ACTIONS=true",
    "REQUIRE_APPROVAL_FOR_WRITES=true",
    "evidence_refs",
    "execution-preview",
    "/execute",
    "sync-execution-result",
    "idempotency_key",
    "ActionExecution",
    "SourceRecord",
    "Task",
    "Company Brain",
    "ENABLE_WRITE_ACTIONS is disabled again",
)

FORBIDDEN_STRINGS = (
    "workflow_dispatch:",
    "on:\n  push",
    "railway up",
    "vercel --prod",
    "fly deploy",
    "render deploy",
    "kubectl apply",
    "terraform apply",
    "docker/login-action",
    "/connections/provider-token",
    "/local-sync",
    "/normalize-local",
    "openai api",
    "call openai",
    "invoke llm",
)

SECRET_SHAPED_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
    re.compile(r"postgres(?:ql)?://[^<\s]+:[^<\s]+@"),
    re.compile(r"redis://[^<\s]+:[^<\s]+@"),
)


def _runbook_text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_external_action_result_runbook_exists_and_is_linked() -> None:
    assert RUNBOOK.exists()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert "docs/deploy/external-action-result-smoke.md" in readme
    assert "deploy/external-action-result-smoke.md" in docs_readme


def test_external_action_result_runbook_documents_required_boundaries() -> None:
    runbook = _runbook_text()

    for term in REQUIRED_TERMS:
        assert term in runbook


def test_external_action_result_runbook_is_not_read_only_smoke_or_auto_deploy() -> None:
    runbook = _runbook_text().casefold()
    normalized = " ".join(runbook.split())

    assert "not be run as part of normal read-only private-beta smoke" in runbook
    assert "not referenced by ci" in runbook
    assert "not add automation" in runbook
    assert (
        "it does not add automation, ci, workflow dispatch, provider writes, "
        "deploy commands, secret reads, or llm calls"
    ) in normalized
    for forbidden in FORBIDDEN_STRINGS:
        assert forbidden.casefold() not in runbook


def test_external_action_result_runbook_has_no_secret_shaped_values() -> None:
    runbook = _runbook_text()

    for pattern in SECRET_SHAPED_PATTERNS:
        assert pattern.search(runbook) is None


def test_existing_read_only_smoke_does_not_reference_external_action_runbook() -> None:
    smoke_script = (ROOT / "scripts" / "smoke_private_beta.py").read_text(
        encoding="utf-8"
    )
    private_beta_runbook = (ROOT / "docs" / "deploy" / "private-beta.md").read_text(
        encoding="utf-8"
    )

    assert "external-action-result-smoke" not in smoke_script
    assert "external-action-result-smoke" not in private_beta_runbook
    assert "/actions/proposals/{proposal_id}/execute" not in private_beta_runbook
