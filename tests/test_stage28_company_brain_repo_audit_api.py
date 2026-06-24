from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

import app.services.repo_audit as repo_audit_service
from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.main import app

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _write_raw_repos(workspace: Path) -> None:
    raw_dir = workspace / "discovery" / "github" / "20260618T010000Z" / "raw"
    raw_dir.mkdir(parents=True)
    raw_email = "person" + "@" + "example.com"
    repos = [
        {
            "name": "computed-api",
            "full_name": "qtwin-io/computed-api",
            "owner": {"login": "qtwin-io"},
            "description": "api",
            "archived": False,
            "fork": False,
            "private": False,
            "visibility": "public",
            "default_branch": "main",
            "pushed_at": "2026-06-10T00:00:00Z",
            "updated_at": "2026-06-10T00:00:00Z",
            "language": "Python",
            "license": {"key": "mit"},
            "_readme": "readme",
            "_languages": {"Python": 1000},
            "_root_contents": [
                {"name": "pyproject.toml"},
                {"name": "Dockerfile"},
                {"name": ".github"},
                {"name": "tests"},
            ],
            "_branches": [{"name": "main"}],
            "_recent_commits": [
                {
                    "author": {"login": "maintainer"},
                    "commit": {"author": {"email": raw_email}},
                }
            ],
        }
    ]
    (raw_dir / "repos.json").write_text(json.dumps(repos), encoding="utf-8")


async def test_company_brain_repo_audit_api_shape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_raw_repos(tmp_path)
    monkeypatch.setattr(
        repo_audit_service.settings,
        "founderos_local_workspace_path",
        str(tmp_path),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/founder/company-brain/repo-audit")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "computed"
    assert body["preview_only"] is True
    assert body["computed"] is True
    assert body["provenance"]["mode_label_ru"] == "Вычисленные факты"
    assert body["provenance"]["preview_label_ru"] == "Предпросмотр"
    assert body["provenance"]["production_graph"] is False
    assert body["db_written"] is False
    assert body["network_calls"] is False
    assert body["repo_count"] == 1
    assert body["catalog_count"] >= 0
    assert body["source_snapshot"]["available"] is True
    assert body["source_snapshot"]["modified_at"]
    assert body["source_snapshot"]["snapshot_age_seconds"] is not None
    assert body["source_snapshot"]["as_of_source"] == "local_file_mtime"
    assert body["source_snapshot"]["freshness_status"] in {"fresh", "stale"}
    assert body["source_snapshot"]["freshness_label_ru"]
    assert body["summary_cards"]
    assert body["guardrails"]["external_writes"] is False
    assert body["guardrails"]["repo_is_component_not_project"] is True
    assert body["repo_facts"][0]["needs_founder_confirm"] is True
    assert body["repo_facts"][0]["repo_not_jira_project"] is True
    assert _EMAIL_RE.search(response.text) is None


async def test_company_brain_preview_includes_computed_repo_audit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_raw_repos(tmp_path)
    monkeypatch.setattr(
        repo_audit_service.settings,
        "founderos_local_workspace_path",
        str(tmp_path),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/founder/company-brain/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["repo_audit"]["computed"] is True
    assert body["provenance"]["mode_label_ru"] == "Предпросмотр"
    assert body["provenance"]["computed_facts_label_ru"] == "Вычисленные факты"
    assert body["provenance"]["production_graph"] is False
    assert body["repo_audit"]["repo_count"] == 1
    assert body["repo_audit"]["guardrails"]["repo_is_component_not_project"] is True
    assert _EMAIL_RE.search(response.text) is None


async def test_company_brain_repo_audit_requires_api_key_when_auth_enabled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", "test-api-key")
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/founder/company-brain/repo-audit")

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}


def test_founder_ui_contains_repo_audit_section() -> None:
    with TestClient(app) as client:
        response = client.get("/ui")

    assert response.status_code == 200
    for marker in (
        "Аудит репозиториев",
        "renderCbSourceProvenance",
        "Источник preview",
        "source_label_ru",
        "snapshot:",
        "as-of:",
        "source_snapshot.modified_at",
        "snapshot_age_seconds",
        "as-of source",
        "Локальный discovery устарел",
        "cb-repo-audit-badge",
        "Discovery не найден",
        "Вычислено из discovery",
        "Предпросмотр, не production graph",
        "Вычисленные факты",
        "repo ≠ Jira project",
        "Показано ",
        "Показать детали",
        "technical-details simple-hidden",
        "renderCompanyBrainRepoAudit",
    ):
        assert marker in response.text
    assert _EMAIL_RE.search(response.text) is None
