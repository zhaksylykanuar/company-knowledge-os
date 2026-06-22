from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import founder_overview
from app.services.project_status_view import RepoActivity

NOW = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)


class _FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


class _FakeSessionFactory:
    def __init__(self) -> None:
        self.session = _FakeSession()

    async def __aenter__(self) -> _FakeSession:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_founder_overview_is_read_only_by_default(monkeypatch) -> None:
    factory = _FakeSessionFactory()
    captured: dict[str, Any] = {}

    async def fake_project_blocks(*args: object, **kwargs: object) -> list[dict]:
        captured.update(kwargs)
        return []

    async def fake_recent_decisions(*args: object, **kwargs: object) -> list[dict]:
        return []

    async def fake_activity_block(*args: object, **kwargs: object) -> dict:
        return {"window_days": 14, "by_source": {}, "by_day": []}

    async def fake_counts_block(*args: object, **kwargs: object) -> dict[str, int]:
        return {"documents": 0, "tasks": 0, "risks": 0, "decisions": 0}

    async def fake_attention_dashboard(*args: object, **kwargs: object) -> dict:
        return {"top_items": []}

    monkeypatch.setattr(founder_overview, "AsyncSessionLocal", lambda: factory)
    monkeypatch.setattr(founder_overview, "_project_blocks", fake_project_blocks)
    monkeypatch.setattr(founder_overview, "_recent_decisions", fake_recent_decisions)
    monkeypatch.setattr(founder_overview, "_activity_block", fake_activity_block)
    monkeypatch.setattr(founder_overview, "_counts_block", fake_counts_block)
    monkeypatch.setattr(
        founder_overview, "get_attention_dashboard", fake_attention_dashboard
    )

    result = await founder_overview.build_founder_overview()

    assert result["schema_version"] == "founder_overview.v2"
    assert result["status"]["level"] == "unknown"
    assert result["provenance"]["source"] == "server_read_model"
    assert result["provenance"]["cache_policy"] == {
        "browser_cache_key": "fos_overview_cache",
        "cache_is_client_side_only": True,
        "stale_on_read": True,
    }
    assert captured["persist_status_snapshots"] is False
    assert factory.session.commit_count == 0


@pytest.mark.asyncio
async def test_founder_overview_persists_only_when_explicit(monkeypatch) -> None:
    factory = _FakeSessionFactory()
    captured: dict[str, Any] = {}

    async def fake_project_blocks(*args: object, **kwargs: object) -> list[dict]:
        captured.update(kwargs)
        return []

    async def fake_recent_decisions(*args: object, **kwargs: object) -> list[dict]:
        return []

    async def fake_activity_block(*args: object, **kwargs: object) -> dict:
        return {"window_days": 14, "by_source": {}, "by_day": []}

    async def fake_counts_block(*args: object, **kwargs: object) -> dict[str, int]:
        return {"documents": 0, "tasks": 0, "risks": 0, "decisions": 0}

    async def fake_attention_dashboard(*args: object, **kwargs: object) -> dict:
        return {"top_items": []}

    monkeypatch.setattr(founder_overview, "AsyncSessionLocal", lambda: factory)
    monkeypatch.setattr(founder_overview, "_project_blocks", fake_project_blocks)
    monkeypatch.setattr(founder_overview, "_recent_decisions", fake_recent_decisions)
    monkeypatch.setattr(founder_overview, "_activity_block", fake_activity_block)
    monkeypatch.setattr(founder_overview, "_counts_block", fake_counts_block)
    monkeypatch.setattr(
        founder_overview, "get_attention_dashboard", fake_attention_dashboard
    )

    await founder_overview.build_founder_overview(persist_status_snapshots=True)

    assert captured["persist_status_snapshots"] is True
    assert factory.session.commit_count == 1


def test_repo_activity_provenance_keeps_window_and_source_event_metadata() -> None:
    activity = RepoActivity(
        repo_names=("repo-alpha-api",),
        open_prs=(),
        merged_prs=(),
        commit_count_7d=2,
        commit_jira_keys_7d=frozenset({"ALPHA-1"}),
        pr_jira_keys=frozenset(),
        source_event_count=4,
        last_source_event_at=NOW - timedelta(hours=2),
        source_run_ids=("run-a", "run-b"),
        window_start=NOW - timedelta(days=7),
        window_end=NOW,
    )

    provenance = founder_overview._repo_activity_provenance(activity, now=NOW)

    assert provenance["computed"] is True
    assert provenance["source"] == "github_source_events"
    assert provenance["window_days"] == 7
    assert provenance["window_start"] == "2026-06-05T12:00:00+00:00"
    assert provenance["window_end"] == "2026-06-12T12:00:00+00:00"
    assert provenance["source_event_count"] == 4
    assert provenance["last_source_event_at"] == "2026-06-12T10:00:00+00:00"
    assert provenance["source_run_ids"] == ["run-a", "run-b"]
    assert provenance["scope"] == "mapped_repositories_only"


@pytest.mark.asyncio
async def test_project_blocks_include_code_metric_provenance(monkeypatch) -> None:
    class _FakeResult:
        def scalars(self) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(
                    entity_id="project:alpha",
                    canonical_name="Project Alpha",
                )
            ]

    class _FakeProjectSession:
        async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
            return _FakeResult()

    async def fake_jira_keys(*args: object, **kwargs: object) -> list[str]:
        return ["ALPHA"]

    async def fake_issue_snapshots(*args: object, **kwargs: object) -> list:
        return []

    async def fake_repos(*args: object, **kwargs: object) -> list[dict[str, str]]:
        return [{"org": "org", "repo": "repo-alpha-api"}]

    async def fake_repo_activity(*args: object, **kwargs: object) -> RepoActivity:
        return RepoActivity(
            repo_names=("repo-alpha-api",),
            open_prs=(),
            merged_prs=(),
            commit_count_7d=3,
            commit_jira_keys_7d=frozenset(),
            pr_jira_keys=frozenset(),
            source_event_count=5,
            last_source_event_at=NOW,
            source_run_ids=("github-run-1",),
            window_start=NOW - timedelta(days=7),
            window_end=NOW,
        )

    async def fake_latest_snapshot(*args: object, **kwargs: object) -> None:
        return None

    def fake_status_snapshot(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            status_color="green",
            confidence=1.0,
            summary="Fresh work",
            blockers=(),
            conflicts=(),
            risks=(),
            recommendations=(),
            last_meaningful_update_at=NOW,
        )

    async def fail_save_snapshot(*args: object, **kwargs: object) -> None:
        raise AssertionError("UI GET project block should not persist snapshots")

    monkeypatch.setattr(founder_overview, "jira_keys_for_project", fake_jira_keys)
    monkeypatch.setattr(
        founder_overview, "load_project_issue_snapshots", fake_issue_snapshots
    )
    monkeypatch.setattr(founder_overview, "repos_for_project", fake_repos)
    monkeypatch.setattr(founder_overview, "load_repo_activity", fake_repo_activity)
    monkeypatch.setattr(founder_overview, "get_latest_status_snapshot", fake_latest_snapshot)
    monkeypatch.setattr(
        founder_overview, "build_project_status_snapshot", fake_status_snapshot
    )
    monkeypatch.setattr(founder_overview, "save_status_snapshot", fail_save_snapshot)

    projects = await founder_overview._project_blocks(
        _FakeProjectSession(),
        now=NOW,
        organization_id="org-default",
        persist_status_snapshots=False,
    )

    code = projects[0]["code"]
    assert code["commits_7d"] == 3
    assert code["provenance"]["source"] == "github_source_events"
    assert code["provenance"]["source_event_count"] == 5
    assert code["provenance"]["source_run_ids"] == ["github-run-1"]
