from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

FORBIDDEN_CI_STRINGS = (
    "/execute",
    "/repositories/issues/sync",
    "/repositories/pull-requests/sync",
    "/sync-execution-result",
    "/connections/provider-token",
    "/local-sync",
    "/normalize-local",
    "FOUNDEROS_SMOKE_API_KEY",
    "FOS_GITHUB_READONLY_TOKEN",
    "FOS_GITHUB_WRITE_ALLOWED_REPOS",
    "FOS_GITHUB_SYNC_ALLOWED_REPOS",
    "GITHUB_TOKEN:",
    '${{ secrets.',
)


def _ci_text() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def test_ci_has_separate_backend_and_frontend_deploy_readiness_jobs() -> None:
    workflow = _ci_text()

    assert "backend:" in workflow
    assert "name: Backend checks" in workflow
    assert "frontend:" in workflow
    assert "name: Frontend deploy-readiness checks" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow


def test_ci_preserves_backend_migration_lint_secret_and_pytest_gates() -> None:
    workflow = _ci_text()

    for command in (
        "bash scripts/check_no_secrets.sh --tracked",
        "uv sync --frozen",
        "uv run ruff check .",
        "uv run alembic upgrade head",
        "uv run pytest -q",
    ):
        assert command in workflow


def test_ci_runs_docs_smoke_and_cors_contract_tests_explicitly() -> None:
    workflow = _ci_text()

    assert "Docs and smoke contract tests" in workflow
    for test_path in (
        "tests/test_docs_navigation_integrity.py",
        "tests/test_private_beta_smoke.py",
        "tests/test_cors_config.py",
        "tests/test_ci_deploy_readiness.py",
    ):
        assert test_path in workflow


def test_ci_runs_frontend_test_build_typecheck_and_lint() -> None:
    workflow = _ci_text()

    assert "actions/setup-node@395ad3262231945c25e8478fd5baf05154b1d79f # v6.1.0" in workflow
    assert 'node-version: "22"' in workflow
    assert "cache-dependency-path: web/package-lock.json" in workflow
    assert "working-directory: web" in workflow
    for command in (
        "npm ci",
        "npm test",
        "npm run build",
        "npm run typecheck",
        "npm run lint",
    ):
        assert command in workflow


def test_ci_deploy_readiness_has_no_provider_write_or_live_smoke_commands() -> None:
    workflow = _ci_text()

    for forbidden in FORBIDDEN_CI_STRINGS:
        assert forbidden not in workflow
    assert "make smoke" not in workflow
    assert "scripts/smoke_private_beta.py" not in workflow
