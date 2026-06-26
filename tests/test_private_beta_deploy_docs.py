from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "deploy" / "private-beta.md"

REQUIRED_ENV_NAMES = (
    "APP_ENV",
    "API_BASE_URL",
    "DATABASE_URL",
    "REDIS_URL",
    "API_AUTH_ENABLED",
    "API_AUTH_KEY",
    "API_AUTH_HEADER_NAME",
    "FOUNDEROS_API_KEYS",
    "FOUNDEROS_SECRET_ENCRYPTION_KEY",
    "FOUNDEROS_CORS_ALLOWED_ORIGINS",
    "FOUNDEROS_CORS_ALLOW_CREDENTIALS",
    "ENABLE_WRITE_ACTIONS",
    "REQUIRE_APPROVAL_FOR_WRITES",
    "FOS_GITHUB_WRITE_ALLOWED_REPOS",
    "FOS_GITHUB_SYNC_ALLOWED_REPOS",
    "NEXT_PUBLIC_API_BASE_URL",
    "FOUNDEROS_SMOKE_API_BASE_URL",
    "FOUNDEROS_SMOKE_API_KEY",
    "FOUNDEROS_SMOKE_API_KEY_HEADER_NAME",
    "FOUNDEROS_SMOKE_OWNER_EMAIL",
    "FOUNDEROS_SMOKE_WORKSPACE_ID",
)

REQUIRED_COMMANDS = (
    "uv sync --frozen",
    "uv run alembic upgrade head",
    "uv run alembic heads",
    "uv run alembic current",
    "uv run uvicorn app.main:app",
    "npm ci",
    "npm test",
    "npm run build",
    "npm run typecheck",
    "npm run lint",
    "npm run start",
    "make smoke",
)

FORBIDDEN_RUNBOOK_STRINGS = (
    "pull_request_target",
    "workflow_dispatch:",
    "on:\n  push",
    "uses: docker/login-action",
    "railway up",
    "fly deploy",
    "vercel --prod",
    "render deploy",
    "kubectl apply",
    "terraform apply",
    "/repositories/issues/sync",
    "/repositories/pull-requests/sync",
    "/actions/proposals/{proposal_id}/execute",
    "/connections/provider-token",
    "/local-sync",
    "/normalize-local",
    "/sync-execution-result",
)

SECRET_SHAPED_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xoxb-[A-Za-z0-9-]{10,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
    re.compile(r"postgres(?:ql)?://[^<\s]+:[^<\s]+@"),
)


def _runbook_text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_private_beta_deploy_runbook_exists_and_is_linked() -> None:
    assert RUNBOOK.exists()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    web_readme = (ROOT / "web" / "README.md").read_text(encoding="utf-8")

    assert "docs/deploy/private-beta.md" in readme
    assert "deploy/private-beta.md" in docs_readme
    assert "docs/deploy/private-beta.md" in web_readme


def test_private_beta_runbook_documents_required_env_names_and_commands() -> None:
    runbook = _runbook_text()

    for env_name in REQUIRED_ENV_NAMES:
        assert env_name in runbook
    for command in REQUIRED_COMMANDS:
        assert command in runbook


def test_private_beta_runbook_documents_db_migration_backup_and_rollback() -> None:
    runbook = _runbook_text().casefold()

    for required in (
        "managed postgres",
        "managed redis",
        "database backup",
        "restore-from-backup",
        "rollback",
        "alembic upgrade head",
        "alembic heads",
        "alembic current",
        "known retained-substrate alembic drift",
    ):
        assert required in runbook


def test_private_beta_runbook_documents_read_only_smoke_and_provider_write_boundary() -> None:
    runbook = _runbook_text().casefold()

    for required in (
        "make smoke",
        "read-only",
        "does not call",
        "actionproposal execute",
        "selected repository issue sync",
        "selected repository pr sync",
        "provider-token setup",
        "provider write endpoints",
        "openai or other llm apis",
        "enable_write_actions remains disabled",
    ):
        assert required in runbook


def test_private_beta_runbook_has_no_auto_deploy_or_live_write_commands() -> None:
    runbook = _runbook_text()

    for forbidden in FORBIDDEN_RUNBOOK_STRINGS:
        assert forbidden not in runbook


def test_private_beta_runbook_has_no_secret_shaped_values() -> None:
    runbook = _runbook_text()

    for pattern in SECRET_SHAPED_PATTERNS:
        assert pattern.search(runbook) is None


def test_no_github_actions_workflow_auto_deploys() -> None:
    workflow_dir = ROOT / ".github" / "workflows"
    workflows = sorted(workflow_dir.glob("*.yml"))
    assert workflows

    forbidden = (
        "railway up",
        "fly deploy",
        "vercel --prod",
        "render deploy",
        "kubectl apply",
        "terraform apply",
        "docker/login-action",
        "scripts/smoke_private_beta.py",
        "make smoke",
        "/execute",
        "/repositories/issues/sync",
        "/repositories/pull-requests/sync",
    )
    offenders: list[str] = []
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        for value in forbidden:
            if value in text:
                offenders.append(f"{path.relative_to(ROOT)}:{value}")

    assert offenders == []
