from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTING_DOC = ROOT / "docs" / "deploy" / "railway-private-beta.md"
TEMPLATE_DIR = ROOT / "docs" / "deploy" / "templates"

TEMPLATE_FILES = (
    TEMPLATE_DIR / "railway-backend.env.example",
    TEMPLATE_DIR / "railway-frontend.env.example",
    TEMPLATE_DIR / "private-beta-smoke.env.example",
)

REQUIRED_HOSTING_TERMS = (
    "Railway-only split-service private-beta baseline",
    "Backend service",
    "Frontend service",
    "Managed Postgres service",
    "Managed Redis service",
    "Domain, CORS, and API-base mapping",
    "Migration dry run",
    "Smoke dry run",
    "Rollback dry run",
    "Later live provider smoke",
    "Do not create a Railway project",
    "Do not provision Postgres or Redis",
)

REQUIRED_ENV_NAMES = (
    "APP_ENV",
    "API_BASE_URL",
    "DATABASE_URL",
    "REDIS_URL",
    "API_AUTH_ENABLED",
    "API_AUTH_KEY",
    "API_AUTH_HEADER_NAME",
    "FOUNDEROS_SECRET_ENCRYPTION_KEY",
    "FOUNDEROS_CORS_ALLOWED_ORIGINS",
    "FOUNDEROS_CORS_ALLOW_CREDENTIALS",
    "ENABLE_WRITE_ACTIONS",
    "FOS_GITHUB_WRITE_ALLOWED_REPOS",
    "FOS_GITHUB_SYNC_ALLOWED_REPOS",
    "FOUNDEROS_GITHUB_APP_ID",
    "FOUNDEROS_GITHUB_APP_SLUG",
    "FOUNDEROS_GITHUB_APP_PRIVATE_KEY",
    "FOUNDEROS_GITHUB_APP_PRIVATE_KEY_PATH",
    "FOUNDEROS_GITHUB_APP_WEBHOOK_SECRET",
    "FOUNDEROS_GITHUB_APP_SETUP_URL",
    "FOUNDEROS_GITHUB_APP_CALLBACK_URL",
    "NEXT_PUBLIC_API_BASE_URL",
    "FOUNDEROS_SMOKE_API_BASE_URL",
    "FOUNDEROS_SMOKE_API_KEY",
    "FOUNDEROS_SMOKE_WORKSPACE_ID",
)

REQUIRED_COMMANDS = (
    "uv sync --frozen",
    "uv run uvicorn app.main:app",
    "uv run alembic heads",
    "uv run alembic current",
    "uv run alembic upgrade head",
    "npm ci && npm run build",
    "npm run start",
    "make smoke",
)

FORBIDDEN_HOSTING_STRINGS = (
    "railway up",
    "railway login",
    "railway link",
    "railway variables",
    "vercel --prod",
    "fly deploy",
    "render deploy",
    "kubectl apply",
    "terraform apply",
    "docker/login-action",
    "on:\n  push",
    "workflow_dispatch:",
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
    re.compile(r"redis://[^<\s]+:[^<\s]+@"),
)


def _hosting_text() -> str:
    return HOSTING_DOC.read_text(encoding="utf-8")


def test_railway_hosting_plan_exists_and_is_linked() -> None:
    assert HOSTING_DOC.exists()
    for path in (
        ROOT / "README.md",
        ROOT / "web" / "README.md",
        ROOT / "docs" / "README.md",
        ROOT / "docs" / "deploy" / "private-beta.md",
    ):
        assert "railway-private-beta.md" in path.read_text(encoding="utf-8")


def test_railway_hosting_plan_documents_required_sections_and_commands() -> None:
    hosting = _hosting_text()

    for term in REQUIRED_HOSTING_TERMS:
        assert term in hosting
    for env_name in REQUIRED_ENV_NAMES:
        assert env_name in hosting
    for command in REQUIRED_COMMANDS:
        assert command in hosting


def test_railway_hosting_plan_documents_security_boundaries() -> None:
    hosting = _hosting_text().casefold()

    for phrase in (
        "dry-run preparation only",
        "does not create a railway project",
        "do not use the railway cli",
        "enable_write_actions disabled by default",
        "live provider smoke is not part of this dry-run plan",
        "requires a separate human approval",
        "provider write endpoints",
        "openai/llm apis",
        "restore-from-backup is the rollback boundary",
    ):
        assert phrase in hosting


def test_railway_hosting_plan_has_no_auto_deploy_or_live_write_commands() -> None:
    hosting = _hosting_text().casefold()

    for forbidden in FORBIDDEN_HOSTING_STRINGS:
        assert forbidden.casefold() not in hosting


def test_railway_templates_exist_and_are_placeholder_only() -> None:
    for path in TEMPLATE_FILES:
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assignments = [
            line
            for line in text.splitlines()
            if line and not line.startswith("#") and "=" in line
        ]
        assert assignments
        for line in assignments:
            _key, value = line.split("=", 1)
            assert value.startswith("<") and value.endswith(">")


def test_railway_docs_and_templates_have_no_secret_shaped_values() -> None:
    paths = [HOSTING_DOC, *TEMPLATE_FILES]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for pattern in SECRET_SHAPED_PATTERNS:
            assert pattern.search(text) is None, path


def test_no_auto_deploy_workflow_added_for_hosting_target() -> None:
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows

    forbidden = (
        "railway up",
        "railway login",
        "railway variables",
        "vercel --prod",
        "fly deploy",
        "render deploy",
        "kubectl apply",
        "terraform apply",
        "docker/login-action",
        "make smoke",
        "scripts/smoke_private_beta.py",
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
