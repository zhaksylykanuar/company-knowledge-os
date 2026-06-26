from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.services.github_issue_execution_service as github_issue_execution_service
import app.services.github_selected_issue_sync_service as selected_issue_sync_service
import app.services.github_selected_pr_sync_service as selected_pr_sync_service
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
        "owner_email": f"github-selected-pr-sync-{marker}@example.test",
        "owner_name": "GitHub Selected PR Sync Owner",
        "workspace_name": f"GitHub Selected PR Sync {marker}",
        "workspace_slug": f"github-selected-pr-sync-{marker}",
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
                        Workspace.slug.like(f"github-selected-pr-sync-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"github-selected-pr-sync-{marker}%")
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
            display_name="GitHub selected PR sync",
            external_account_id="selected-pr-sync-account",
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


async def _workspace_pull_requests(workspace_id: str) -> list[PullRequest]:
    async with AsyncSessionLocal() as session:
        return list(
            (
                await session.execute(
                    select(PullRequest)
                    .where(PullRequest.workspace_id == UUID(workspace_id))
                    .order_by(PullRequest.number)
                )
            ).scalars()
        )


async def _seed_alternate_pull_request_identifier(workspace_id: str) -> None:
    async with AsyncSessionLocal() as session:
        repository = await session.scalar(
            select(Repository)
            .where(Repository.workspace_id == UUID(workspace_id))
            .where(Repository.full_name == "qtwin-io/founderos-smoke")
        )
        assert repository is not None
        session.add(
            PullRequest(
                workspace_id=UUID(workspace_id),
                repository_id=repository.id,
                external_id="legacy-provider-pr-2002",
                number=2,
                title="Closed PR alternate id",
                state="closed",
                source_url=None,
                updated_at_source=datetime(2026, 6, 25, 2, 2, tzinfo=timezone.utc),
                pr_metadata={
                    "github_object_type": "pull_request",
                    "repository_full_name": "qtwin-io/founderos-smoke",
                    "repository_external_id": "qtwin-io/founderos-smoke",
                    "number": 2,
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
        "html_url": f"https://example.invalid/qtwin-io/founderos-smoke/issues/{number}",
        "created_at": "2026-06-26T01:00:00Z",
        "updated_at": f"2026-06-26T01:{number:02d}:00Z",
    }


def _pull_request(
    number: int,
    *,
    state: str,
    title: str,
    merged_at: str | None = None,
) -> dict:
    return {
        "id": 2000 + number,
        "number": number,
        "title": title,
        "state": state,
        "html_url": f"https://example.invalid/qtwin-io/founderos-smoke/pull/{number}",
        "created_at": "2026-06-26T02:00:00Z",
        "updated_at": f"2026-06-26T02:{number:02d}:00Z",
        "merged_at": merged_at,
        "body": "raw provider body must not be returned by selected sync response",
        "head": {"secret_token": "must-not-leak"},
        "draft": False,
    }


async def _run_issue_sync(workspace_id: str, connection_id: UUID, marker: str) -> None:
    async with _async_client() as client:
        response = await client.post(
            f"/api/v1/workspaces/{workspace_id}/github/repositories/issues/sync",
            headers=_headers(),
            params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            json={
                "connection_id": str(connection_id),
                "repositories": ["qtwin-io/founderos-smoke"],
                "states": ["all"],
            },
        )
    assert response.status_code == 200, response.text


async def test_selected_pr_sync_requires_allowlist_before_provider_call(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "github_sync_allowed_repos", None)
    monkeypatch.setattr(settings, "github_repos", None)
    await _cleanup(marker)

    async def fail_list_pull_requests(**_kwargs):
        raise AssertionError("provider read must not be called without allowlist")

    monkeypatch.setattr(
        selected_pr_sync_service.github_pull_request_client,
        "list_pull_requests",
        fail_list_pull_requests,
    )
    monkeypatch.setattr(
        selected_pr_sync_service,
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
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories/pull-requests/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": str(connection_id),
                    "repositories": ["qtwin-io/founderos-smoke"],
                    "states": ["open", "closed", "merged"],
                },
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "github selected pull request sync allowed repositories are not configured"
        }
    finally:
        await _cleanup(marker)


async def test_selected_pr_sync_blocks_non_allowlisted_repo_before_provider_call(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "github_sync_allowed_repos", "qtwin-io/founderos-smoke")
    await _cleanup(marker)

    async def fail_list_pull_requests(**_kwargs):
        raise AssertionError("provider read must not be called for blocked repo")

    monkeypatch.setattr(
        selected_pr_sync_service.github_pull_request_client,
        "list_pull_requests",
        fail_list_pull_requests,
    )
    monkeypatch.setattr(
        selected_pr_sync_service,
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
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories/pull-requests/sync",
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
            "detail": "github repository is not allowed for selected pull request sync"
        }
    finally:
        await _cleanup(marker)


async def test_selected_pr_sync_persists_canonical_prs_and_read_models(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "github_sync_allowed_repos", "qtwin-io/founderos-smoke")
    monkeypatch.setattr(selected_issue_sync_service, "decrypt_secret", lambda _value: "token")
    monkeypatch.setattr(selected_pr_sync_service, "decrypt_secret", lambda _value: "token")
    await _cleanup(marker)

    async def fake_list_issues(**kwargs):
        assert kwargs["access_token"] == "token"
        assert kwargs["repository_full_name"] == "qtwin-io/founderos-smoke"
        return [_issue(1, state="closed", title="Closed smoke issue")]

    async def fake_list_pull_requests(**kwargs):
        assert kwargs["access_token"] == "token"
        assert kwargs["repository_full_name"] == "qtwin-io/founderos-smoke"
        assert kwargs["state"] == "all"
        return [
            _pull_request(1, state="open", title="Open smoke PR"),
            _pull_request(2, state="closed", title="Closed smoke PR"),
            _pull_request(
                3,
                state="closed",
                title="Merged smoke PR",
                merged_at="2026-06-26T03:03:00Z",
            ),
        ]

    async def fail_create_issue(**_kwargs):
        raise AssertionError("selected PR sync must not create GitHub issues")

    monkeypatch.setattr(github_issue_execution_service, "create_issue", fail_create_issue)
    monkeypatch.setattr(
        selected_issue_sync_service.github_issue_client,
        "list_issues",
        fake_list_issues,
    )
    monkeypatch.setattr(
        selected_pr_sync_service.github_pull_request_client,
        "list_pull_requests",
        fake_list_pull_requests,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection_id = await _seed_connection(workspace_id)
        await _run_issue_sync(workspace_id, connection_id, marker)
        assert await _count_workspace(Repository, workspace_id) == 1
        assert await _count_workspace(Task, workspace_id) == 1

        async with _async_client() as client:
            first = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": str(connection_id),
                    "repositories": ["qtwin-io/founderos-smoke"],
                    "states": ["open", "closed", "merged"],
                },
            )
            second = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync",
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
            "pull_requests": 3,
            "open_pull_requests": 1,
            "closed_pull_requests": 1,
            "merged_pull_requests": 1,
        }
        assert first_body["repositories"] == [
            {
                "full_name": "qtwin-io/founderos-smoke",
                "synced_pull_requests": 3,
                "open_pull_requests": 1,
                "closed_pull_requests": 1,
                "merged_pull_requests": 1,
            }
        ]
        assert first_body["counts"] == {
            "repositories": 1,
            "issues": 0,
            "pull_requests": 3,
        }
        assert first_body["sync_job"]["records_created"] == 3
        assert first_body["sync_job"]["records_updated"] == 1
        assert second.status_code == 200, second.text
        assert second.json()["sync_job"]["records_created"] == 0
        assert second.json()["sync_job"]["records_updated"] == 4

        assert await _count_workspace(Repository, workspace_id) == 1
        assert await _count_workspace(Task, workspace_id) == 1
        assert await _count_workspace(PullRequest, workspace_id) == 3
        assert await _count_workspace(SourceRecord, workspace_id) == 5

        pull_requests = await _workspace_pull_requests(workspace_id)
        assert [pull_request.external_id for pull_request in pull_requests] == [
            "qtwin-io/founderos-smoke#pull/1",
            "qtwin-io/founderos-smoke#pull/2",
            "qtwin-io/founderos-smoke#pull/3",
        ]
        assert [pull_request.state for pull_request in pull_requests] == [
            "open",
            "closed",
            "merged",
        ]
        assert all(
            pull_request.pr_metadata["repository_full_name"]
            == "qtwin-io/founderos-smoke"
            for pull_request in pull_requests
        )

        await _seed_alternate_pull_request_identifier(workspace_id)
        assert await _count_workspace(PullRequest, workspace_id) == 4

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
            merged_work = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/operational-work",
                headers=_headers(),
                params={
                    "owner_email": _bootstrap_payload(marker)["owner_email"],
                    "state": "merged",
                },
            )
            all_work = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/operational-work",
                headers=_headers(),
                params={
                    "owner_email": _bootstrap_payload(marker)["owner_email"],
                    "state": "all",
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

        assert open_work.status_code == 200, open_work.text
        assert open_work.json()["counts"] == {"issues": 0, "pull_requests": 1}
        assert open_work.json()["pull_requests"][0]["title"] == "Open smoke PR"
        assert closed_work.status_code == 200, closed_work.text
        assert closed_work.json()["counts"] == {"issues": 1, "pull_requests": 1}
        assert closed_work.json()["pull_requests"][0]["title"] == "Closed smoke PR"
        assert merged_work.status_code == 200, merged_work.text
        assert merged_work.json()["counts"] == {"issues": 0, "pull_requests": 1}
        assert merged_work.json()["pull_requests"][0]["title"] == "Merged smoke PR"
        assert all_work.status_code == 200, all_work.text
        assert all_work.json()["counts"] == {"issues": 1, "pull_requests": 3}

        assert company_brain.status_code == 200, company_brain.text
        assert company_brain.json()["summary"]["repositories"] == 1
        assert company_brain.json()["summary"]["open_pull_requests"] == 1
        assert company_brain.json()["summary"]["merged_pull_requests"] == 1
        assert company_brain.json()["evidence"]

        assert briefing.status_code == 200, briefing.text
        briefing_body = briefing.json()["briefing"]
        assert briefing_body["llm_used"] is False
        assert briefing_body["persistence"] == "transient"
        assert any(item["evidence_refs"] for item in briefing_body["items"])

        serialized_response = str(first_body)
        assert "raw provider body must not be returned" not in serialized_response
        assert "must-not-leak" not in serialized_response
        assert any(
            "No external write occurred" in warning for warning in first_body["warnings"]
        )
    finally:
        await _cleanup(marker)
