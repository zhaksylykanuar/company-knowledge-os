from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import (
    PullRequest,
    Repository,
    SourceRecord,
    Task,
)
from app.db.event_models import SourceEvent
from app.db.identity_models import Membership, User, Workspace
from app.db.models import IngestedEvent
from app.main import app


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _bootstrap_payload(marker: str) -> dict[str, str]:
    return {
        "owner_email": f"company-brain-{marker}@example.test",
        "owner_name": "Company Brain Owner",
        "workspace_name": f"Company Brain {marker}",
        "workspace_slug": f"company-brain-{marker}",
    }


async def _bootstrap_workspace(marker: str) -> dict:
    async with _async_client() as client:
        response = await client.post(
            "/api/v1/workspaces/bootstrap",
            headers=_headers(),
            json=_bootstrap_payload(marker),
        )
    assert response.status_code == 201, response.text
    return response.json()


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"company-brain-{marker}%"))
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(User.email.like(f"company-brain-{marker}%"))
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(delete(Task).where(Task.workspace_id.in_(workspace_ids)))
            await session.execute(
                delete(PullRequest).where(PullRequest.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(Repository).where(Repository.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(SourceRecord).where(SourceRecord.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
            )
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.execute(
            delete(SourceEvent).where(SourceEvent.source_event_id.like(f"%{marker}%"))
        )
        await session.execute(
            delete(IngestedEvent).where(IngestedEvent.event_id.like(f"%{marker}%"))
        )
        await session.commit()


async def _seed_company_brain_rows(workspace_id: str, marker: str) -> None:
    now = datetime(2026, 6, 24, 10, 0, tzinfo=timezone.utc)
    async with AsyncSessionLocal() as session:
        repo_record = SourceRecord(
            workspace_id=UUID(workspace_id),
            provider="github",
            external_id="qtwin-io/founderos-api",
            record_type="repository",
            source_url="https://github.com/qtwin-io/founderos-api",
            payload={
                "evidence_refs": [
                    {
                        "kind": "repository_inventory_snapshot",
                        "source": "canonical_source_record",
                        "ref": "repo-snapshot-1",
                        "url": "https://github.com/qtwin-io/founderos-api",
                    }
                ]
            },
            payload_hash=f"repo-hash-{marker}",
            observed_at=now,
            source_updated_at=now,
        )
        issue_record = SourceRecord(
            workspace_id=UUID(workspace_id),
            provider="github",
            external_id="qtwin-io/founderos-api#issue/42",
            record_type="issue",
            source_url="https://github.com/qtwin-io/founderos-api/issues/42",
            payload={
                "evidence_refs": [
                    {
                        "kind": "github_issue",
                        "source": "github",
                        "ref": "qtwin-io/founderos-api#issue/42",
                        "url": "https://github.com/qtwin-io/founderos-api/issues/42",
                    }
                ]
            },
            payload_hash=f"issue-hash-{marker}",
            observed_at=now,
            source_updated_at=now,
        )
        closed_issue_record = SourceRecord(
            workspace_id=UUID(workspace_id),
            provider="github",
            external_id="qtwin-io/founderos-api#issue/43",
            record_type="issue",
            source_url="https://github.com/qtwin-io/founderos-api/issues/43",
            payload={"evidence_refs": []},
            payload_hash=f"closed-issue-hash-{marker}",
            observed_at=now,
            source_updated_at=now,
        )
        pr_record = SourceRecord(
            workspace_id=UUID(workspace_id),
            provider="github",
            external_id="qtwin-io/founderos-api#pull/7",
            record_type="pull_request",
            source_url="https://github.com/qtwin-io/founderos-api/pull/7",
            payload={
                "evidence_refs": [
                    {
                        "kind": "github_pull_request",
                        "source": "github",
                        "ref": "qtwin-io/founderos-api#pull/7",
                        "url": "https://github.com/qtwin-io/founderos-api/pull/7",
                    }
                ]
            },
            payload_hash=f"pr-hash-{marker}",
            observed_at=now,
            source_updated_at=now,
        )
        merged_pr_record = SourceRecord(
            workspace_id=UUID(workspace_id),
            provider="github",
            external_id="qtwin-io/founderos-api#pull/8",
            record_type="pull_request",
            source_url="https://github.com/qtwin-io/founderos-api/pull/8",
            payload={"evidence_refs": []},
            payload_hash=f"merged-pr-hash-{marker}",
            observed_at=now,
            source_updated_at=now,
        )
        session.add_all(
            [repo_record, issue_record, closed_issue_record, pr_record, merged_pr_record]
        )
        await session.flush()

        repository = Repository(
            workspace_id=UUID(workspace_id),
            provider="github",
            external_id="qtwin-io/founderos-api",
            name="founderos-api",
            full_name="qtwin-io/founderos-api",
            default_branch="main",
            visibility="private",
            archived=False,
            source_url="https://github.com/qtwin-io/founderos-api",
            repo_metadata={"repo_not_jira_project": True},
            last_activity_at=now,
        )
        session.add(repository)
        await session.flush()

        session.add_all(
            [
                Task(
                    workspace_id=UUID(workspace_id),
                    source_provider="github",
                    source_record_id=issue_record.id,
                    external_id="qtwin-io/founderos-api#issue/42",
                    title="Investigate issue 42",
                    status="open",
                    source_url="https://github.com/qtwin-io/founderos-api/issues/42",
                    task_metadata={
                        "github_object_type": "issue",
                        "number": 42,
                        "repository_full_name": "qtwin-io/founderos-api",
                        "repository_external_id": "qtwin-io/founderos-api",
                    },
                    source_updated_at=now,
                ),
                Task(
                    workspace_id=UUID(workspace_id),
                    source_provider="github",
                    source_record_id=closed_issue_record.id,
                    external_id="qtwin-io/founderos-api#issue/43",
                    title="Close issue 43",
                    status="closed",
                    source_url="https://github.com/qtwin-io/founderos-api/issues/43",
                    task_metadata={
                        "github_object_type": "issue",
                        "number": 43,
                        "repository_full_name": "qtwin-io/founderos-api",
                        "repository_external_id": "qtwin-io/founderos-api",
                    },
                    source_updated_at=now,
                ),
                PullRequest(
                    workspace_id=UUID(workspace_id),
                    repository_id=repository.id,
                    external_id="qtwin-io/founderos-api#pull/7",
                    number=7,
                    title="Ship PR 7",
                    state="open",
                    source_url="https://github.com/qtwin-io/founderos-api/pull/7",
                    created_at_source=now,
                    updated_at_source=now,
                    pr_metadata={"github_object_type": "pull_request"},
                ),
                PullRequest(
                    workspace_id=UUID(workspace_id),
                    repository_id=repository.id,
                    external_id="qtwin-io/founderos-api#pull/8",
                    number=8,
                    title="Merge PR 8",
                    state="merged",
                    source_url="https://github.com/qtwin-io/founderos-api/pull/8",
                    created_at_source=now,
                    updated_at_source=now,
                    merged_at_source=now,
                    pr_metadata={"github_object_type": "pull_request"},
                ),
            ]
        )
        session.add(
            IngestedEvent(
                event_id=f"ie-company-brain-{marker}",
                event_type="github.repository",
                source_system="github",
                source_object_id=f"legacy-only-company-brain-{marker}",
                idempotency_key=f"company-brain-{marker}",
                correlation_id=f"corr-company-brain-{marker}",
                trace_id=f"trace-company-brain-{marker}",
                raw_object_ref=f"raw://company-brain/{marker}",
                payload={},
                status="received",
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=f"sevt-company-brain-{marker}",
                source_event_key=f"sevt-key-company-brain-{marker}",
                ingested_event_id=f"ie-company-brain-{marker}",
                event_type="github.repository",
                source_system="github",
                source_object_type="repository",
                source_object_id=f"legacy-only-company-brain-{marker}",
                title=f"legacy-only-company-brain-{marker}",
                raw_object_ref=f"raw://company-brain/{marker}",
                evidence_refs=[],
                metadata_json={},
            )
        )
        await session.commit()


async def test_workspace_company_brain_returns_empty_canonical_state(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/company-brain",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["mode"] == "github_first_canonical"
        assert body["source"] == "canonical_github_company_brain"
        assert body["summary"] == {
            "repositories": 0,
            "open_issues": 0,
            "open_pull_requests": 0,
            "closed_issues": 0,
            "merged_pull_requests": 0,
        }
        assert body["repositories"] == []
        assert body["work"] == {"issues": [], "pull_requests": [], "recent": []}
        assert body["evidence"] == []
        assert body["is_live"] is False
        assert body["llm_used"] is False
        assert body["capabilities"] == {
            "live_github_oauth": False,
            "live_provider_sync": False,
            "local_sync": True,
            "llm_briefing": False,
        }
        assert any("No canonical GitHub records" in warning for warning in body["warnings"])
    finally:
        await _cleanup(marker)


async def test_workspace_company_brain_reads_canonical_github_evidence(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        await _seed_company_brain_rows(workspace_id, marker)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/company-brain",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["summary"] == {
            "repositories": 1,
            "open_issues": 1,
            "open_pull_requests": 1,
            "closed_issues": 1,
            "merged_pull_requests": 1,
        }
        assert body["repositories"][0]["full_name"] == "qtwin-io/founderos-api"
        assert body["repositories"][0]["source_refs"][0]["label"] == "repo-snapshot-1"
        assert body["work"]["issues"][0]["title"] == "Investigate issue 42"
        assert body["work"]["issues"][0]["source_refs"][0]["kind"] == "github_issue"
        assert body["work"]["pull_requests"][0]["title"] == "Ship PR 7"
        assert body["work"]["pull_requests"][0]["source_refs"][0]["kind"] == (
            "github_pull_request"
        )
        recent_titles = {item["title"] for item in body["work"]["recent"]}
        assert {"Close issue 43", "Merge PR 8"}.issubset(recent_titles)
        evidence_labels = {ref["label"] for ref in body["evidence"]}
        assert {
            "repo-snapshot-1",
            "qtwin-io/founderos-api#issue/42",
            "qtwin-io/founderos-api#pull/7",
        }.issubset(evidence_labels)
        serialized = json.dumps(body, sort_keys=True)
        assert f"legacy-only-company-brain-{marker}" not in serialized
        assert "source_events" not in serialized
        assert body["is_live"] is False
        assert body["llm_used"] is False
        assert body["capabilities"]["live_provider_sync"] is False
        assert body["capabilities"]["llm_briefing"] is False
    finally:
        await _cleanup(marker)
