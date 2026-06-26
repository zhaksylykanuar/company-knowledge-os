from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.services.github_issue_execution_service as github_issue_execution_service
import app.services.github_selected_issue_sync_service as selected_issue_sync_service
from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import PullRequest, Repository, SourceRecord, Task
from app.db.identity_models import Membership, User, Workspace
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GITHUB,
    IntegrationConnection,
    SyncJob,
)
from app.main import app

pytestmark = pytest.mark.anyio


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
        "owner_email": f"github-selected-sync-{marker}@example.test",
        "owner_name": "GitHub Selected Sync Owner",
        "workspace_name": f"GitHub Selected Sync {marker}",
        "workspace_slug": f"github-selected-sync-{marker}",
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
                    select(Workspace.id).where(
                        Workspace.slug.like(f"github-selected-sync-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"github-selected-sync-{marker}%")
                    )
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
            await session.execute(delete(SyncJob).where(SyncJob.workspace_id.in_(workspace_ids)))
            await session.execute(
                delete(IntegrationConnection).where(
                    IntegrationConnection.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
            )
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def _seed_connection(workspace_id: str) -> UUID:
    async with AsyncSessionLocal() as session:
        connection = IntegrationConnection(
            workspace_id=UUID(workspace_id),
            provider=INTEGRATION_PROVIDER_GITHUB,
            status=INTEGRATION_CONNECTION_STATUS_CONNECTED,
            display_name="GitHub selected sync",
            external_account_id="selected-sync-account",
            scopes=["repo"],
            encrypted_access_token="encrypted-access-placeholder",
            provider_metadata={"connection_method": "test"},
        )
        session.add(connection)
        await session.commit()
        return connection.id


async def _count_workspace(model: type, workspace_id: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
            )
            or 0
        )


async def _workspace_tasks(workspace_id: str) -> list[Task]:
    async with AsyncSessionLocal() as session:
        return list(
            (
                await session.execute(
                    select(Task)
                    .where(Task.workspace_id == UUID(workspace_id))
                    .order_by(Task.external_id)
                )
            ).scalars()
        )


async def _seed_alternate_issue_identifier_task(workspace_id: str) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            Task(
                workspace_id=UUID(workspace_id),
                source_provider="github",
                external_id="qtwin-io/founderos-smoke#issue/1",
                title="Closed smoke issue alternate id",
                status="closed",
                source_url=None,
                source_updated_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
                task_metadata={
                    "github_object_type": "issue",
                    "repository_full_name": "qtwin-io/founderos-smoke",
                    "repository_external_id": "qtwin-io/founderos-smoke",
                    "number": 1,
                },
            )
        )
        await session.commit()


def _issue(number: int, *, state: str, title: str) -> dict:
    return {
        "id": 1000 + number,
        "number": number,
        "title": title,
        "state": state,
        "html_url": f"https://github.com/qtwin-io/founderos-smoke/issues/{number}",
        "created_at": "2026-06-26T01:00:00Z",
        "updated_at": f"2026-06-26T01:{number:02d}:00Z",
    }


async def test_selected_issue_sync_requires_allowlist_before_provider_call(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "github_sync_allowed_repos", None)
    monkeypatch.setattr(settings, "github_repos", None)
    await _cleanup(marker)

    async def fail_list_issues(**_kwargs):
        raise AssertionError("provider read must not be called without allowlist")

    monkeypatch.setattr(
        selected_issue_sync_service.github_issue_client,
        "list_issues",
        fail_list_issues,
    )
    monkeypatch.setattr(
        selected_issue_sync_service,
        "decrypt_secret",
        lambda _value: (_ for _ in ()).throw(
            AssertionError("token decrypt must not happen without allowlist")
        ),
    )

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories/issues/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": str(connection_id),
                    "repositories": ["qtwin-io/founderos-smoke"],
                    "states": ["open", "closed"],
                },
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "github selected issue sync allowed repositories are not configured"
        }
    finally:
        await _cleanup(marker)


async def test_selected_issue_sync_blocks_non_allowlisted_repo_before_provider_call(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "github_sync_allowed_repos", "qtwin-io/founderos-smoke")
    await _cleanup(marker)

    async def fail_list_issues(**_kwargs):
        raise AssertionError("provider read must not be called for blocked repo")

    monkeypatch.setattr(
        selected_issue_sync_service.github_issue_client,
        "list_issues",
        fail_list_issues,
    )
    monkeypatch.setattr(
        selected_issue_sync_service,
        "decrypt_secret",
        lambda _value: (_ for _ in ()).throw(
            AssertionError("token decrypt must not happen for blocked repo")
        ),
    )

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories/issues/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": str(connection_id),
                    "repositories": ["qtwin-io/not-approved"],
                    "states": ["all"],
                },
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "github repository is not allowed for selected issue sync"
        }
    finally:
        await _cleanup(marker)


async def test_selected_issue_sync_persists_canonical_issues_and_read_models(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "github_sync_allowed_repos", "qtwin-io/founderos-smoke")
    monkeypatch.setattr(selected_issue_sync_service, "decrypt_secret", lambda _value: "token")
    await _cleanup(marker)

    async def fail_create_issue(**_kwargs):
        raise AssertionError("selected repository sync must not create GitHub issues")

    async def fake_list_issues(**kwargs):
        assert kwargs["access_token"] == "token"
        assert kwargs["repository_full_name"] == "qtwin-io/founderos-smoke"
        assert kwargs["state"] == "all"
        return [
            _issue(1, state="closed", title="Closed smoke issue"),
            _issue(2, state="open", title="Open follow-up"),
            {
                "id": 2003,
                "number": 3,
                "title": "PR-shaped issue record",
                "state": "open",
                "html_url": "https://github.com/qtwin-io/founderos-smoke/pull/3",
                "pull_request": {"url": "https://api.github.test/pulls/3"},
            },
        ]

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fail_create_issue)
    monkeypatch.setattr(
        selected_issue_sync_service.github_issue_client,
        "list_issues",
        fake_list_issues,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection_id = await _seed_connection(workspace_id)

        async with _async_client() as client:
            first = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/repositories/issues/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": str(connection_id),
                    "repositories": ["qtwin-io/founderos-smoke"],
                    "states": ["open", "closed"],
                },
            )
            second = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/repositories/issues/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": str(connection_id),
                    "repositories": ["qtwin-io/founderos-smoke"],
                    "states": ["all"],
                },
            )

        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body["capabilities"] == {
            "read_only_sync": True,
            "external_writes": False,
        }
        assert first_body["external_write_performed"] is False
        assert first_body["totals"] == {
            "repositories": 1,
            "issues": 2,
            "open_issues": 1,
            "closed_issues": 1,
            "skipped_pull_requests": 1,
        }
        assert first_body["repositories"] == [
            {
                "full_name": "qtwin-io/founderos-smoke",
                "synced_issues": 2,
                "open_issues": 1,
                "closed_issues": 1,
                "skipped_pull_requests": 1,
            }
        ]
        assert first_body["counts"] == {
            "repositories": 1,
            "issues": 2,
            "pull_requests": 0,
        }
        assert first_body["sync_job"]["records_created"] == 3
        assert second.status_code == 200, second.text
        assert second.json()["sync_job"]["records_created"] == 0
        assert second.json()["sync_job"]["records_updated"] == 3

        assert await _count_workspace(Repository, workspace_id) == 1
        assert await _count_workspace(Task, workspace_id) == 2
        assert await _count_workspace(PullRequest, workspace_id) == 0
        assert await _count_workspace(SourceRecord, workspace_id) == 3

        await _seed_alternate_issue_identifier_task(workspace_id)

        async with _async_client() as client:
            open_work = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/operational-work",
                headers=_headers(),
                params={
                    "owner_email": _bootstrap_payload(marker)["owner_email"],
                    "state": "open",
                },
            )
            closed_work = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/operational-work",
                headers=_headers(),
                params={
                    "owner_email": _bootstrap_payload(marker)["owner_email"],
                    "state": "closed",
                },
            )
            company_brain = await client.get(
                f"/api/v1/workspaces/{workspace_id}/company-brain",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )
            briefing = await client.post(
                f"/api/v1/workspaces/{workspace_id}/briefings/manual",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert await _count_workspace(Task, workspace_id) == 3

        tasks = await _workspace_tasks(workspace_id)
        canonical_tasks = [
            task
            for task in tasks
            if not str(task.external_id).startswith("qtwin-io/founderos-smoke#issue/")
        ]
        assert [task.status for task in canonical_tasks] == ["closed", "open"]
        assert [task.external_id for task in canonical_tasks] == ["1001", "1002"]
        assert all(
            task.task_metadata["repository_full_name"] == "qtwin-io/founderos-smoke"
            for task in tasks
        )

        assert open_work.status_code == 200, open_work.text
        assert open_work.json()["counts"] == {"issues": 1, "pull_requests": 0}
        assert open_work.json()["issues"][0]["title"] == "Open follow-up"
        assert closed_work.status_code == 200, closed_work.text
        assert closed_work.json()["counts"] == {"issues": 1, "pull_requests": 0}
        assert closed_work.json()["issues"][0]["title"] == "Closed smoke issue"

        assert company_brain.status_code == 200, company_brain.text
        assert company_brain.json()["summary"]["repositories"] == 1
        assert company_brain.json()["summary"]["open_issues"] == 1
        assert company_brain.json()["summary"]["closed_issues"] == 1
        assert company_brain.json()["evidence"]

        assert briefing.status_code == 200, briefing.text
        briefing_body = briefing.json()["briefing"]
        assert briefing_body["llm_used"] is False
        assert briefing_body["persistence"] == "transient"
        assert any(item["evidence_refs"] for item in briefing_body["items"])
        assert any(
            "No external write occurred" in warning
            for warning in first_body["warnings"]
        )
    finally:
        await _cleanup(marker)
