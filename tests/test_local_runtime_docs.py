from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "operations" / "local-runtime.md"
COMPOSE = ROOT / "docker-compose.yml"

REQUIRED_COMMANDS = (
    "make local",
    "make local-doctor",
    "make local-backup",
    "make local-stop",
    "make local-smoke",
)

FORBIDDEN_ACTIVE_RUNBOOK_STRINGS = (
    "railway",
    "fly deploy",
    "vercel --prod",
    "render deploy",
    "kubectl apply",
    "terraform apply",
    "/repositories/issues/sync",
    "/repositories/pull-requests/sync",
    "/actions/proposals/{proposal_id}/execute",
    "/connections/provider-token",
    "/sync-execution-result",
)

SECRET_SHAPED_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"postgres(?:ql)?://[^<\s]+:[^<\s]+@"),
    re.compile(r"redis://[^<\s]+:[^<\s]+@"),
)


def _runbook_text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_local_runtime_runbook_exists_and_is_canonically_linked() -> None:
    assert RUNBOOK.exists()
    for path in (
        ROOT / "README.md",
        ROOT / "docs" / "README.md",
        ROOT / "web" / "README.md",
    ):
        assert "operations/local-runtime.md" in path.read_text(encoding="utf-8")


def test_local_runtime_runbook_documents_one_command_operator_path() -> None:
    runbook = _runbook_text()
    normalized = runbook.casefold()

    for command in REQUIRED_COMMANDS:
        assert command in runbook
    for term in (
        "local runtime",
        "http://127.0.0.1:3000",
        "postgres",
        "backup",
        "restore",
        "bounded local smoke",
        "provider writes",
        "llm",
    ):
        assert term in normalized


def test_local_runtime_runbook_has_no_hosting_or_live_write_contract() -> None:
    runbook = _runbook_text().casefold()

    for forbidden in FORBIDDEN_ACTIVE_RUNBOOK_STRINGS:
        assert forbidden.casefold() not in runbook


def test_local_runtime_runbook_has_no_secret_shaped_values() -> None:
    runbook = _runbook_text()

    for pattern in SECRET_SHAPED_PATTERNS:
        assert pattern.search(runbook) is None


def test_no_github_actions_workflow_starts_runtime_or_provider_actions() -> None:
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows

    forbidden = (
        "make local",
        "make local-smoke",
        "scripts/smoke_local.py",
        "/execute",
        "/repositories/issues/sync",
        "/repositories/pull-requests/sync",
    )
    offenders: list[str] = []
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8").casefold()
        for item in forbidden:
            if item.casefold() in text:
                offenders.append(f"{workflow.relative_to(ROOT)}:{item}")

    assert offenders == []


def test_compose_datastores_bind_to_loopback_only() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert '"127.0.0.1:5432:5432"' in compose
    assert '"127.0.0.1:6379:6379"' in compose
    assert '- "5432:5432"' not in compose
    assert '- "6379:6379"' not in compose
