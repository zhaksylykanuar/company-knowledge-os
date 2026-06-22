from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app.services.repo_audit as repo_audit_service
from app.services.repo_audit import load_repo_audit


def _write_raw_repos(workspace: Path, repos: list[dict[str, Any]]) -> Path:
    raw_dir = workspace / "discovery" / "github" / "20260618T000000Z" / "raw"
    raw_dir.mkdir(parents=True)
    raw_path = raw_dir / "repos.json"
    raw_path.write_text(json.dumps(repos), encoding="utf-8")
    return raw_path


def _repo(
    *,
    name: str,
    pushed_at: str | None,
    root_names: list[str],
    description: str | None = "service",
    readme: str = "readme",
    language: str = "Python",
    author_login: str | None = "maintainer",
) -> dict[str, Any]:
    raw_email = "person" + "@" + "example.com"
    return {
        "name": name,
        "full_name": f"qtwin-io/{name}",
        "owner": {"login": "qtwin-io"},
        "description": description,
        "archived": False,
        "fork": False,
        "private": False,
        "visibility": "public",
        "default_branch": "main",
        "pushed_at": pushed_at,
        "updated_at": pushed_at,
        "language": language,
        "license": {"key": "mit"} if readme else None,
        "_readme": readme,
        "_languages": {language: 1000, "Dockerfile": 100},
        "_root_contents": [{"name": item} for item in root_names],
        "_branches": [{"name": "main"}, {"name": "develop"}],
        "_recent_commits": [
            {
                "author": {"login": author_login} if author_login else None,
                "commit": {"author": {"email": raw_email}},
            }
        ],
    }


def test_repo_audit_reads_fixture_and_computes_repo_facts(tmp_path: Path) -> None:
    _write_raw_repos(
        tmp_path,
        [
            _repo(
                name="core-api",
                pushed_at="2026-06-10T00:00:00Z",
                root_names=["pyproject.toml", "Dockerfile", ".github", "tests"],
            ),
            _repo(
                name="ghost-repo",
                pushed_at="2025-01-01T00:00:00Z",
                root_names=["package.json"],
                description=None,
                readme="",
                language="TypeScript",
                author_login=None,
            ),
        ],
    )

    audit = load_repo_audit(
        workspace_path=tmp_path,
        now=datetime(2026, 6, 18, tzinfo=timezone.utc),
    )

    assert audit["status"] == "computed"
    assert audit["preview_only"] is True
    assert audit["computed"] is True
    assert audit["db_written"] is False
    assert audit["network_calls"] is False
    assert audit["repo_count"] == 2

    first = audit["repo_facts"][0]
    assert first["name"] == "core-api"
    assert first["repo_role"] == "component_evidence"
    assert first["repo_not_jira_project"] is True
    assert first["jira_component_candidate"] == "core-api"
    assert first["jira_mapping_policy"] == (
        "repo_is_component_or_evidence_not_jira_project"
    )
    assert first["needs_founder_confirm"] is True
    assert first["area_candidate"] in {"CORE", "PLAT", "OPS", "CORP", "RND"}
    assert first["owner_candidates"][0]["candidate"] == "maintainer"
    assert first["owner_candidates"][0]["needs_founder_confirm"] is True
    assert first["ci_detected"] is True
    assert first["tests_detected"] is True
    assert "Dockerfile" in first["detected_manifests"]
    assert "dockerfile" in first["deploy_hints"]
    assert first["activity_bucket"] == "active"
    assert first["evidence_refs"]
    assert audit["guardrails"]["active_area_count"] == 5
    assert audit["guardrails"]["active_area_keys"] == [
        "CORE",
        "PLAT",
        "OPS",
        "CORP",
        "RND",
    ]
    assert audit["guardrails"]["future_later_area_keys"] == ["GTM", "SALES"]
    assert audit["guardrails"]["future_later_area_status"] == "future_later_not_active"
    assert audit["guardrails"]["one_repo_one_jira_project"] is False

    second = audit["repo_facts"][1]
    assert second["activity_bucket"] == "stale"
    assert "description_missing" in second["risks"]
    assert "readme_missing" in second["risks"]
    assert "owner_candidate_unknown" in second["risks"]


def test_repo_audit_exposes_source_snapshot_freshness(tmp_path: Path) -> None:
    raw_path = _write_raw_repos(
        tmp_path,
        [
            _repo(
                name="core-api",
                pushed_at="2026-06-10T00:00:00Z",
                root_names=["pyproject.toml"],
            )
        ],
    )
    source_mtime = datetime(2026, 6, 14, tzinfo=timezone.utc)
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    os.utime(raw_path, (source_mtime.timestamp(), source_mtime.timestamp()))

    audit = load_repo_audit(workspace_path=tmp_path, now=now)
    snapshot = audit["source_snapshot"]

    assert snapshot["available"] is True
    assert snapshot["status"] == "available"
    assert snapshot["modified_at"] == source_mtime.isoformat()
    assert snapshot["snapshot_age_seconds"] == 4 * 24 * 60 * 60
    assert snapshot["as_of_source"] == "local_file_mtime"
    assert snapshot["freshness_status"] == "stale"
    assert snapshot["freshness_label_ru"] == "Локальный снимок discovery устарел"
    assert snapshot["repo_count"] == 1
    assert snapshot["path"].endswith("raw/repos.json")


def test_repo_audit_never_returns_raw_email(tmp_path: Path) -> None:
    raw_path = _write_raw_repos(
        tmp_path,
        [
            _repo(
                name="core-api",
                pushed_at="2026-06-10T00:00:00Z",
                root_names=["pyproject.toml"],
            )
        ],
    )
    raw_text = raw_path.read_text(encoding="utf-8")
    assert "@" in raw_text

    audit = load_repo_audit(workspace_path=tmp_path)
    serialized = json.dumps(audit, ensure_ascii=False)

    assert "@" not in serialized
    assert audit["guardrails"]["raw_email_returned"] is False


def test_repo_audit_drops_email_shaped_owner_logins(tmp_path: Path) -> None:
    email_like_login = "owner" + "@" + "example.com"
    _write_raw_repos(
        tmp_path,
        [
            _repo(
                name="core-api",
                pushed_at="2026-06-10T00:00:00Z",
                root_names=["pyproject.toml"],
                author_login=email_like_login,
            )
        ],
    )

    audit = load_repo_audit(workspace_path=tmp_path)
    repo = audit["repo_facts"][0]

    assert repo["owner_candidates"] == []
    assert "owner_candidate_unknown" in repo["risks"]
    assert "owner_unknown" in repo["unknowns"]


def test_repo_audit_reconciles_live_and_static_catalog(tmp_path: Path) -> None:
    _write_raw_repos(
        tmp_path,
        [
            _repo(
                name="core-api",
                pushed_at="2026-06-10T00:00:00Z",
                root_names=["pyproject.toml"],
            ),
            _repo(
                name="qaztwin-ssap-frontend",
                pushed_at="2026-06-10T00:00:00Z",
                root_names=["package.json"],
            ),
        ],
    )

    audit = load_repo_audit(workspace_path=tmp_path)
    reconciliation = audit["reconciliation"]

    assert reconciliation["status"] == "computed"
    assert reconciliation["live_count"] == 2
    assert reconciliation["catalog_count"] == 19
    assert reconciliation["matched_count"] == 1
    assert reconciliation["live_repos"] == ["core-api", "qaztwin-ssap-frontend"]
    assert "qaztwin-ssap-frontend" in reconciliation["catalog_repos"]
    assert "core-api" in reconciliation["in_live_not_in_catalog"]
    assert "qaztwin-ssap-frontend" in reconciliation["matched"]
    assert reconciliation["repo_mapping_policy"] == (
        "repo_is_component_or_evidence_not_jira_project"
    )


def test_repo_audit_reports_catalog_unavailable(tmp_path: Path, monkeypatch) -> None:
    _write_raw_repos(
        tmp_path,
        [
            _repo(
                name="core-api",
                pushed_at="2026-06-10T00:00:00Z",
                root_names=["pyproject.toml"],
            ),
        ],
    )

    def unavailable_catalog() -> tuple[dict[str, Any], ...]:
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(
        repo_audit_service,
        "repository_portfolio_catalog",
        unavailable_catalog,
    )

    audit = load_repo_audit(workspace_path=tmp_path)

    assert audit["catalog_count"] == 0
    assert audit["reconciliation"]["status"] == "catalog_unavailable"
    assert audit["reconciliation"]["catalog_repos"] == []
    assert audit["reconciliation"]["live_repos"] == ["core-api"]


def test_repo_audit_keeps_gtm_sales_out_of_active_areas(tmp_path: Path) -> None:
    _write_raw_repos(
        tmp_path,
        [
            _repo(
                name="sales-portal",
                pushed_at="2026-06-10T00:00:00Z",
                root_names=["package.json"],
                language="TypeScript",
            ),
            _repo(
                name="gtm-landing",
                pushed_at="2026-06-10T00:00:00Z",
                root_names=["package.json"],
                language="TypeScript",
            ),
        ],
    )

    audit = load_repo_audit(workspace_path=tmp_path)
    candidates = {fact["area_candidate"] for fact in audit["repo_facts"]}

    assert candidates <= {"CORE", "PLAT", "OPS", "CORP", "RND"}
    assert "GTM" not in candidates
    assert "SALES" not in candidates


def test_repo_audit_makes_no_network_calls_or_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_raw_repos(
        tmp_path,
        [
            _repo(
                name="core-api",
                pushed_at="2026-06-10T00:00:00Z",
                root_names=["pyproject.toml"],
            )
        ],
    )
    network_calls: list[object] = []

    def blocked_connect(self, address) -> None:  # noqa: ANN001
        network_calls.append(address)
        raise AssertionError("repo audit must not call the network")

    def blocked_write_text(self, *args, **kwargs) -> None:  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("repo audit must not write files")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    monkeypatch.setattr(Path, "write_text", blocked_write_text)

    audit = load_repo_audit(workspace_path=tmp_path)

    assert network_calls == []
    assert audit["network_calls"] is False
    assert audit["db_written"] is False
    assert audit["guardrails"]["external_writes"] is False
    assert audit["guardrails"]["github_writes"] is False
    assert audit["guardrails"]["jira_writes"] is False
    assert audit["guardrails"]["obsidian_written"] is False


def test_repo_audit_missing_raw_file_is_graceful(tmp_path: Path) -> None:
    audit = load_repo_audit(workspace_path=tmp_path)

    assert audit["status"] == "raw_discovery_missing"
    assert audit["preview_only"] is True
    assert audit["computed"] is False
    assert audit["db_written"] is False
    assert audit["network_calls"] is False
    assert audit["repo_count"] == 0
    assert audit["repo_facts"] == []
    assert audit["source_snapshot"]["available"] is False
