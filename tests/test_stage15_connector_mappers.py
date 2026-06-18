from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.source_control_models import SourceRunRequest
from app.services.connector_clients import (
    GitHubReadOnlyConnectorClient,
    JiraReadOnlyConnectorClient,
    ReadOnlyRecord,
    map_github_commit,
    map_github_issue,
    map_github_pull_request,
    map_jira_issue,
)
from app.services.source_connectors import NoopSourceConnector
from app.services.source_run_orchestrator import run_source_request
from tests.test_stage11_connector_ingestion import (
    _cleanup,
    _ensure_tables,
    _request,
    _restore_state,
    _state_snapshot,
)


def test_jira_issue_mapper_is_deterministic_and_safe() -> None:
    raw = {
        "key": "ALPHA-101",
        "fields": {
            "summary": "Fix SCADA export",
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "Person A"},
            "updated": "2026-06-14T10:00:00.000+0000",
            "project": {"key": "ALPHA"},
        },
    }
    a = map_jira_issue(raw, base_url="https://example.atlassian.net")
    b = map_jira_issue(raw, base_url="https://example.atlassian.net")
    assert a.external_id == "ALPHA-101"
    assert a.object_type == "issue"
    assert a.event_type == "jira.issue.updated"
    assert a.url == "https://example.atlassian.net/browse/ALPHA-101"
    assert a.occurred_at == datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc)
    assert a.metadata["project"] == "ALPHA"
    # Deterministic + no raw-body field.
    assert not hasattr(a, "body")
    assert a == b


def test_github_mappers_cover_pr_issue_commit() -> None:
    pr = map_github_pull_request(
        {
            "number": 7,
            "title": "PR title",
            "state": "open",
            "user": {"login": "octocat"},
            "updated_at": "2026-06-14T10:00:00Z",
            "html_url": "https://github.com/o/r/pull/7",
        },
        repo="o/r",
    )
    assert pr.object_type == "pull_request"
    assert pr.external_id == "o/r#pull/7"
    assert pr.occurred_at == datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc)

    issue = map_github_issue(
        {"number": 3, "title": "Bug", "state": "closed", "html_url": "u"}, repo="o/r"
    )
    assert issue.object_type == "issue"
    assert issue.external_id == "o/r#issue/3"

    commit = map_github_commit(
        {
            "sha": "abc123",
            "commit": {
                "message": "fix: thing\n\nbody",
                "author": {"name": "Dev", "date": "2026-06-14T10:00:00Z"},
            },
            "html_url": "https://github.com/o/r/commit/abc123",
        },
        repo="o/r",
    )
    assert commit.object_type == "commit"
    assert commit.title == "fix: thing"  # first line only


def test_real_mappers_emit_contract_valid_events() -> None:
    from app.integrations.source_registry import validate_source_event_contract
    from app.services.connector_clients import _record_to_event

    samples = [
        ("jira", map_jira_issue(
            {"key": "ALPHA-9", "fields": {"summary": "x", "updated": "2026-06-14T10:00:00Z"}},
            base_url="https://example.atlassian.net",
        )),
        ("github", map_github_pull_request(
            {"number": 1, "title": "p", "state": "open", "html_url": "https://gh/o/r/pull/1"},
            repo="o/r",
        )),
        ("github", map_github_pull_request(
            {"number": 2, "title": "p", "state": "closed", "merged_at": "2026-06-14T10:00:00Z",
             "html_url": "https://gh/o/r/pull/2"},
            repo="o/r",
        )),
        ("github", map_github_issue(
            {"number": 3, "title": "i", "state": "closed", "html_url": "https://gh/o/r/issues/3"},
            repo="o/r",
        )),
        ("github", map_github_commit(
            {"sha": "abc", "commit": {"message": "m", "author": {"name": "d", "date": "2026-06-14T10:00:00Z"}},
             "html_url": "https://gh/o/r/commit/abc"},
            repo="o/r",
        )),
    ]
    for source_type, record in samples:
        event = _record_to_event(source_type, record)
        payload = event.to_connector_payload()
        errors = validate_source_event_contract(
            source_system=payload["source_system"],
            source_object_type=payload["source_object_type"],
            event_type=payload["event_type"],
            payload=payload["payload"],
        )
        assert errors == [], (source_type, record.event_type, errors)


class _FakeJiraProvider:
    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.calls = 0

    async def test_connection(self) -> dict:
        self.calls += 1
        return {"status": "ok", "checked": "jira"}

    async def list_updated_issues(self, *, since=None, limit=50):
        self.calls += 1
        return [
            ReadOnlyRecord(
                external_id=f"ALPHA-{self.marker}",
                object_type="issue",
                event_type="jira.issue.updated",
                occurred_at=datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc),
                title="Fix SCADA export",
                summary="status=In Progress",
                actor="Person A",
                url="https://example.atlassian.net/browse/ALPHA",
                metadata={
                    "project": "ALPHA",
                    "leak_token": "ghp_" + "z" * 30,
                },
            )
        ]

    async def list_project_issues(self, *, project=None, since=None, limit=200):
        return await self.list_updated_issues()


async def test_fake_jira_sync_ingests_idempotently_without_secrets(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "stage15-fake-token-value")
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("jira")
    provider = _FakeJiraProvider(marker)
    client = JiraReadOnlyConnectorClient(provider)
    try:
        async with AsyncSessionLocal() as session:
            first_req = _request(marker, action_type="sync")
            first_req.source_type = "jira"
            first_req.request_key = f"jira-sync-{marker}"
            session.add(first_req)
            await session.flush()
            first = await run_source_request(
                session,
                request=first_req,
                connectors={
                    "jira": NoopSourceConnector("jira", session=session, client=client)
                },
                run_id=f"src_run_{marker}",
            )
            await session.commit()
        assert first["status"] == "succeeded"
        assert provider.calls >= 1

        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(func.count(SourceEvent.id)).where(
                    SourceEvent.source_object_id == f"ALPHA-{marker}"
                )
            )
            event = await session.scalar(
                select(SourceEvent).where(
                    SourceEvent.source_object_id == f"ALPHA-{marker}"
                )
            )
        assert count == 1
        # The secret-shaped metadata value must never reach a stored event.
        blob = json.dumps(
            {
                "metadata": event.metadata_json,
                "evidence": event.evidence_refs,
                "title": event.title,
                "summary": event.summary,
            }
        )
        assert "ghp_zzzz" not in blob

        # Repeated sync is idempotent (same content hash → no new event).
        async with AsyncSessionLocal() as session:
            second_req = _request(f"{marker}-2", action_type="sync")
            second_req.source_type = "jira"
            second_req.request_key = f"jira-sync-{marker}-2"
            session.add(second_req)
            await session.flush()
            await run_source_request(
                session,
                request=second_req,
                connectors={
                    "jira": NoopSourceConnector(
                        "jira", session=session, client=JiraReadOnlyConnectorClient(provider)
                    )
                },
                run_id=f"src_run_{marker}_2",
            )
            await session.commit()
            count2 = await session.scalar(
                select(func.count(SourceEvent.id)).where(
                    SourceEvent.source_object_id == f"ALPHA-{marker}"
                )
            )
        assert count2 == 1
    finally:
        await _cleanup(marker)
        await _restore_state("jira", snapshot)


class _FailingProvider:
    async def test_connection(self) -> dict:
        raise RuntimeError("boom ghp_" + "q" * 30)

    async def list_repo_activity(self, *, since=None, limit=50):
        raise RuntimeError("boom")

    async def list_pull_requests(self, *, since=None, limit=50):
        raise RuntimeError("boom")

    async def list_commits(self, *, since=None, limit=50):
        raise RuntimeError("boom")


async def test_github_adapter_exception_is_sanitized(monkeypatch) -> None:
    await _ensure_tables()
    monkeypatch.setenv("GITHUB_TOKEN", "stage15-fake-token-value")
    marker = uuid4().hex[:8]
    snapshot = await _state_snapshot("github")
    client = GitHubReadOnlyConnectorClient(_FailingProvider())
    try:
        async with AsyncSessionLocal() as session:
            req = _request(marker, action_type="test")
            req.source_type = "github"
            req.request_key = f"github-test-{marker}"
            session.add(req)
            await session.flush()
            result = await run_source_request(
                session,
                request=req,
                connectors={
                    "github": NoopSourceConnector(
                        "github", session=session, client=client
                    )
                },
                run_id=f"src_run_{marker}",
            )
            await session.commit()
            row = await session.scalar(
                select(SourceRunRequest).where(
                    SourceRunRequest.request_key == f"github-test-{marker}"
                )
            )
        assert result["status"] == "failed"
        blob = json.dumps({"r": row.result_summary, "e": row.error_summary})
        assert "ghp_" not in blob
        assert row.error_summary.get("message") == "connector adapter failed"
    finally:
        await _cleanup(marker)
        await _restore_state("github", snapshot)
