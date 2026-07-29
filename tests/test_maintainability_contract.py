from __future__ import annotations

from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
LINE_BUDGETS = {
    "app/services/headquarters_read_service.py": 3100,
    "web/components/ActionProposalsPanel.tsx": 3150,
    "web/app/globals.css": 7050,
    "app/api/github.py": 1500,
    "app/api/actions.py": 1250,
    "app/api/action_schemas.py": 350,
    "app/api/assistant.py": 200,
    "app/api/ai_settings.py": 210,
    "app/api/documents.py": 500,
    "app/services/assistant_query_service.py": 1000,
    "app/services/assistant_llm_service.py": 350,
    "app/services/ai_settings_service.py": 525,
    "app/services/document_service.py": 575,
    "web/app/settings/ai/page.tsx": 450,
    "web/app/settings/memory/page.tsx": 425,
    "scripts/disaster_recovery.py": 1250,
}


def test_audited_large_modules_cannot_grow_without_an_explicit_budget_change() -> None:
    offenders: list[str] = []
    for relative, budget in LINE_BUDGETS.items():
        line_count = len((ROOT / relative).read_text(encoding="utf-8").splitlines())
        if line_count > budget:
            offenders.append(f"{relative}: {line_count} > {budget}")
    assert offenders == []


def test_durable_job_is_the_only_live_github_repository_read_route() -> None:
    route_methods = {
        (route.path, method)
        for route in app.routes
        for method in (route.methods or set())
    }
    prefix = "/api/v1/workspaces/{workspace_id}/github"
    assert (f"{prefix}/connections/app-installation/sync", "POST") in route_methods
    assert (f"{prefix}/repositories/issues/sync", "POST") not in route_methods
    assert (f"{prefix}/repositories/pull-requests/sync", "POST") not in route_methods

    assert not (ROOT / "app/services/github_selected_issue_sync_service.py").exists()
    assert not (ROOT / "app/services/github_selected_pr_sync_service.py").exists()
