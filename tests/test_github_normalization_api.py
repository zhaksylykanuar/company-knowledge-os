from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.services.github_repository_read_service as github_repository_read_service
from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import (
    EvidenceRef,
    PullRequest,
    Repository,
    SourceRecord,
    Task,
)
from app.db.event_models import SourceEvent
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GITHUB,
    INTEGRATION_PROVIDER_JIRA,
    SYNC_JOB_STATUS_PARTIAL,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_STATUS_SUCCEEDED,
    SYNC_JOB_TYPE_INITIAL,
    SYNC_JOB_TYPE_MANUAL,
    IntegrationConnection,
    SyncJob,
)
from app.main import app
from app.services.github_repository_read_service import GitHubRepositoryListResult
from app.services.repository_source_inventory import INVENTORY_DISCOVERY_SNAPSHOT


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch, *, enabled: bool = True) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _bootstrap_payload(marker: str, *, suffix: str = "") -> dict[str, str]:
    return {
        "owner_email": f"github-normalize-{marker}{suffix}@example.test",
        "owner_name": "GitHub Normalize Owner",
        "workspace_name": f"GitHub Normalize {marker}{suffix}",
        "workspace_slug": f"github-normalize-{marker}{suffix}",
    }


async def _cleanup_normalization_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"github-normalize-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"github-normalize-{marker}%@example.test")
                    )
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(
                delete(EvidenceRef).where(EvidenceRef.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(Task).where(Task.workspace_id.in_(workspace_ids))
            )
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
                delete(SyncJob).where(SyncJob.workspace_id.in_(workspace_ids))
            )
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


async def _bootstrap_workspace(marker: str, *, suffix: str = "") -> dict:
    async with _async_client() as client:
        response = await client.post(
            "/api/v1/workspaces/bootstrap",
            headers=_headers(),
            json=_bootstrap_payload(marker, suffix=suffix),
        )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_workspace_user(
    workspace_id: str,
    marker: str,
    *,
    role: str,
    suffix: str,
) -> str:
    email = f"github-normalize-{marker}-{suffix}@example.test"
    async with AsyncSessionLocal() as session:
        user = User(email=email, name=f"GitHub Normalize {role}")
        session.add(user)
        await session.flush()
        session.add(
            Membership(
                workspace_id=UUID(workspace_id),
                user_id=user.id,
                role=role,
            )
        )
        await session.commit()
    return email


async def _seed_connection(
    workspace_id: str,
    *,
    provider: str = INTEGRATION_PROVIDER_GITHUB,
    suffix: str = "primary",
) -> UUID:
    async with AsyncSessionLocal() as session:
        connection = IntegrationConnection(
            workspace_id=UUID(workspace_id),
            provider=provider,
            status=INTEGRATION_CONNECTION_STATUS_CONNECTED,
            display_name=f"GitHub Normalize {suffix}",
            external_account_id=f"normalize-account-{suffix}",
            scopes=["repo:read"],
            encrypted_access_token="encrypted-access-placeholder",
            provider_metadata={"login": f"founderos-normalize-{suffix}"},
        )
        session.add(connection)
        await session.commit()
        return connection.id


async def _seed_sync_job(
    workspace_id: str,
    connection_id: UUID,
    *,
    provider: str = INTEGRATION_PROVIDER_GITHUB,
    status: str = SYNC_JOB_STATUS_QUEUED,
    sync_type: str = SYNC_JOB_TYPE_MANUAL,
    cursor_before: dict | None = None,
) -> UUID:
    async with AsyncSessionLocal() as session:
        sync_job = SyncJob(
            workspace_id=UUID(workspace_id),
            connection_id=connection_id,
            provider=provider,
            status=status,
            sync_type=sync_type,
            cursor_before=cursor_before,
            logs=[{"note": "manual sync job record only"}],
        )
        session.add(sync_job)
        await session.commit()
        return sync_job.id


async def _stored_sync_job(sync_job_id: str) -> SyncJob:
    async with AsyncSessionLocal() as session:
        sync_job = await session.scalar(
            select(SyncJob).where(SyncJob.id == UUID(sync_job_id))
        )
        assert sync_job is not None
        return sync_job


async def _count(model: type) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def _count_workspace(model: type, workspace_id: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.workspace_id == UUID(workspace_id))
            )
            or 0
        )


async def _stored_canonical_repo_rows(
    workspace_id: str,
    external_id: str,
) -> tuple[SourceRecord, Repository]:
    async with AsyncSessionLocal() as session:
        source_record = await session.scalar(
            select(SourceRecord)
            .where(SourceRecord.workspace_id == UUID(workspace_id))
            .where(SourceRecord.provider == "github")
            .where(SourceRecord.external_id == external_id)
        )
        repository = await session.scalar(
            select(Repository)
            .where(Repository.workspace_id == UUID(workspace_id))
            .where(Repository.external_id == external_id)
        )
        assert source_record is not None
        assert repository is not None
        return source_record, repository


async def _stored_source_record(
    workspace_id: str,
    external_id: str,
) -> SourceRecord:
    async with AsyncSessionLocal() as session:
        source_record = await session.scalar(
            select(SourceRecord)
            .where(SourceRecord.workspace_id == UUID(workspace_id))
            .where(SourceRecord.provider == "github")
            .where(SourceRecord.external_id == external_id)
        )
        assert source_record is not None
        return source_record


async def _stored_task(workspace_id: str, external_id: str) -> Task:
    async with AsyncSessionLocal() as session:
        task = await session.scalar(
            select(Task)
            .where(Task.workspace_id == UUID(workspace_id))
            .where(Task.source_provider == "github")
            .where(Task.external_id == external_id)
        )
        assert task is not None
        return task


async def _stored_pull_request(workspace_id: str, external_id: str) -> PullRequest:
    async with AsyncSessionLocal() as session:
        pull_request = await session.scalar(
            select(PullRequest)
            .where(PullRequest.workspace_id == UUID(workspace_id))
            .where(PullRequest.external_id == external_id)
        )
        assert pull_request is not None
        return pull_request


def _repository_result(
    repositories: list[dict],
    *,
    warnings: list[str] | None = None,
) -> GitHubRepositoryListResult:
    return GitHubRepositoryListResult(
        repositories=repositories,
        count=len(repositories),
        source="repository_inventory",
        is_live=False,
        warnings=warnings or [],
    )


def _repo_payload() -> dict:
    return {
        "id": "qtwin-io/founderos-api",
        "name": "founderos-api",
        "full_name": "qtwin-io/founderos-api",
        "default_branch": "main",
        "visibility": "private",
        "archived": False,
        "source_url": "https://github.com/qtwin-io/founderos-api",
        "last_activity_at": "2026-06-20T00:00:00+00:00",
        "source": "repository_inventory",
        "evidence_refs": [
            {
                "kind": "repository_inventory_snapshot",
                "source": INVENTORY_DISCOVERY_SNAPSHOT,
                "ref": "local-snap-1",
                "url": None,
            }
        ],
        "metadata": {
            "source_class": INVENTORY_DISCOVERY_SNAPSHOT,
            "repo_not_jira_project": True,
            "access_token_hint": "must-not-leak",
            "nested": {"webhook_secret": "must-not-leak"},
        },
    }


def _issue_payload(*, number: int = 42, state: str = "open") -> dict:
    return {
        "external_id": f"qtwin-io/founderos-api#issue/{number}",
        "number": number,
        "title": f"Investigate issue {number}",
        "state": state,
        "source_url": f"https://github.com/qtwin-io/founderos-api/issues/{number}",
        "repository_full_name": "qtwin-io/founderos-api",
        "created_at": "2026-06-21T00:00:00+00:00",
        "updated_at": "2026-06-21T01:00:00+00:00",
        "evidence_refs": [
            {
                "kind": "github_issue",
                "source": "github",
                "ref": f"qtwin-io/founderos-api#issue/{number}",
                "url": f"https://github.com/qtwin-io/founderos-api/issues/{number}",
            }
        ],
        "metadata": {
            "label_names": ["bug"],
            "access_token_hint": "must-not-leak",
            "nested": {"webhook_secret": "must-not-leak"},
        },
    }


def _pull_request_payload(*, number: int = 7, state: str = "open") -> dict:
    payload = {
        "external_id": f"qtwin-io/founderos-api#pull/{number}",
        "number": number,
        "title": f"Ship PR {number}",
        "state": state,
        "source_url": f"https://github.com/qtwin-io/founderos-api/pull/{number}",
        "repository_full_name": "qtwin-io/founderos-api",
        "created_at": "2026-06-21T02:00:00+00:00",
        "updated_at": "2026-06-21T03:00:00+00:00",
        "evidence_refs": [
            {
                "kind": "github_pull_request",
                "source": "github",
                "ref": f"qtwin-io/founderos-api#pull/{number}",
                "url": f"https://github.com/qtwin-io/founderos-api/pull/{number}",
            }
        ],
        "metadata": {
            "base_branch": "main",
            "access_token_hint": "must-not-leak",
        },
    }
    if state == "merged":
        payload["merged_at"] = "2026-06-21T04:00:00+00:00"
    return payload


def _work_item_cursor(
    *,
    issues: list[dict] | None = None,
    pull_requests: list[dict] | None = None,
) -> dict:
    return {
        "local_github": {
            "issues": issues or [],
            "pull_requests": pull_requests or [],
        }
    }


async def test_normalize_local_requires_api_key(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}/normalize-local",
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert response.status_code == 401
        assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_normalize_local_requires_owner_email_context(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                json={},
            )

        assert response.status_code == 403
        assert response.json() == {
            "detail": "owner_email is required for operator workspace access"
        }
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_owner_can_run_local_normalization_projection(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([_repo_payload()])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["is_live"] is False
        assert body["provider_sync_started"] is False
        assert body["local_normalization_performed"] is True
        assert body["persistence_mode"] == "projection"
        assert body["counts"] == {"repositories": 1, "issues": 0, "pull_requests": 0}
        assert body["sync_job"]["status"] == "partial"
        assert body["sync_job"]["records_seen"] == 1
        assert body["sync_job"]["records_created"] == 0
        assert body["sync_job"]["records_updated"] == 0
        assert body["sync_job"]["started_at"] is not None
        assert body["sync_job"]["finished_at"] is not None
        assert any("compatibility projection" in warning for warning in body["warnings"])
        assert any("issues were not available" in warning for warning in body["warnings"])
        assert any("pull requests were not available" in warning for warning in body["warnings"])

        repo = body["normalized"]["repositories"][0]
        assert repo["entity_type"] == "repository"
        assert repo["provider"] == "github"
        assert repo["external_id"] == "qtwin-io/founderos-api"
        assert repo["name"] == "founderos-api"
        assert repo["full_name"] == "qtwin-io/founderos-api"
        assert repo["default_branch"] == "main"
        assert repo["visibility"] == "private"
        assert repo["archived"] is False
        assert repo["source_url"] == "https://github.com/qtwin-io/founderos-api"
        assert repo["last_activity_at"] == "2026-06-20T00:00:00+00:00"
        assert repo["source"] == "repository_inventory"
        assert repo["evidence_refs"][0]["ref"] == "local-snap-1"
        assert repo["metadata"]["repo_not_jira_project"] is True
        assert "access_token_hint" not in repo["metadata"]
        assert body["normalized"]["issues"] == []
        assert body["normalized"]["pull_requests"] == []

        stored = await _stored_sync_job(sync_job_id=str(sync_job_id))
        assert stored.status == SYNC_JOB_STATUS_PARTIAL
        assert stored.records_seen == 1
        assert stored.records_created == 0
        assert stored.records_updated == 0
        assert stored.started_at is not None
        assert stored.finished_at is not None
        assert stored.cursor_after["persistence_mode"] == "projection"
        assert stored.logs[-1]["local_normalization"]["provider_sync_started"] is False
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_admin_can_run_local_normalization(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([_repo_payload()])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)
        admin_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=MEMBERSHIP_ROLE_ADMIN,
            suffix="admin",
        )

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": admin_email},
                json={"include_issues": False, "include_pull_requests": False},
            )

        assert response.status_code == 200
        assert response.json()["sync_job"]["status"] == "succeeded"
    finally:
        await _cleanup_normalization_fixture(marker)


@pytest.mark.parametrize("role", [MEMBERSHIP_ROLE_MEMBER, MEMBERSHIP_ROLE_VIEWER])
async def test_member_and_viewer_cannot_run_local_normalization(
    monkeypatch,
    role: str,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        user_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=role,
            suffix=role,
        )
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": user_email},
                json={},
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient workspace role"}
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_normalize_local_rejects_unknown_and_cross_workspace_jobs(monkeypatch) -> None:
    marker = uuid4().hex
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)
    await _cleanup_normalization_fixture(other_marker)

    try:
        created = await _bootstrap_workspace(marker)
        other = await _bootstrap_workspace(other_marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)

        async with _async_client() as client:
            unknown = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{uuid4()}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )
            cross_workspace = await client.post(
                f"/api/v1/workspaces/{other['workspace']['id']}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(other_marker)["owner_email"]},
                json={},
            )

        assert unknown.status_code == 404
        assert unknown.json() == {"detail": "github sync job not found"}
        assert cross_workspace.status_code == 404
        assert cross_workspace.json() == {"detail": "github sync job not found"}
    finally:
        await _cleanup_normalization_fixture(marker)
        await _cleanup_normalization_fixture(other_marker)


async def test_normalize_local_rejects_non_github_non_manual_and_succeeded_jobs(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        github_connection_id = await _seed_connection(created["workspace"]["id"])
        jira_connection_id = await _seed_connection(
            created["workspace"]["id"],
            provider=INTEGRATION_PROVIDER_JIRA,
            suffix="jira",
        )
        non_github_id = await _seed_sync_job(
            created["workspace"]["id"],
            jira_connection_id,
            provider=INTEGRATION_PROVIDER_JIRA,
        )
        non_manual_id = await _seed_sync_job(
            created["workspace"]["id"],
            github_connection_id,
            sync_type=SYNC_JOB_TYPE_INITIAL,
        )
        succeeded_id = await _seed_sync_job(
            created["workspace"]["id"],
            github_connection_id,
            status=SYNC_JOB_STATUS_SUCCEEDED,
        )

        async with _async_client() as client:
            non_github = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{non_github_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )
            non_manual = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{non_manual_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )
            succeeded = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{succeeded_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert non_github.status_code == 400
        assert non_github.json() == {"detail": "github manual sync job required"}
        assert non_manual.status_code == 400
        assert non_manual.json() == {"detail": "github manual sync job required"}
        assert succeeded.status_code == 409
        assert succeeded.json() == {"detail": "github sync job must be queued"}
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_normalize_local_empty_inventory_returns_warning(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([], warnings=["no repositories matched local inventory"])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["counts"] == {"repositories": 0, "issues": 0, "pull_requests": 0}
        assert body["normalized"]["repositories"] == []
        assert body["sync_job"]["status"] == "partial"
        assert any("No local GitHub repository inventory" in warning for warning in body["warnings"])
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_owner_can_persist_canonical_repositories(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([_repo_payload()])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)
        source_event_count_before = await _count(SourceEvent)
        evidence_count_before = await _count_workspace(EvidenceRef, workspace_id)
        task_count_before = await _count_workspace(Task, workspace_id)
        pull_request_count_before = await _count_workspace(PullRequest, workspace_id)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "include_issues": False,
                    "include_pull_requests": False,
                    "persist_if_supported": True,
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["persistence_mode"] == "canonical"
        assert body["counts"] == {"repositories": 1, "issues": 0, "pull_requests": 0}
        assert body["sync_job"]["status"] == "succeeded"
        assert body["sync_job"]["records_seen"] == 1
        assert body["sync_job"]["records_created"] == 1
        assert body["sync_job"]["records_updated"] == 0

        stored = await _stored_sync_job(str(sync_job_id))
        assert stored.status == SYNC_JOB_STATUS_SUCCEEDED
        assert stored.records_seen == 1
        assert stored.records_created == 1
        assert stored.records_updated == 0
        assert stored.cursor_after["persistence_mode"] == "canonical"
        assert stored.cursor_after["canonical_persistence"] == {
            "source_records_created": 1,
            "source_records_updated": 0,
            "repositories_created": 1,
            "repositories_updated": 0,
            "tasks_created": 0,
            "tasks_updated": 0,
            "pull_requests_created": 0,
            "pull_requests_updated": 0,
        }
        assert stored.logs[-1]["local_normalization"]["source_records_created"] == 1
        assert stored.logs[-1]["local_normalization"]["repositories_created"] == 1

        source_record, repository = await _stored_canonical_repo_rows(
            workspace_id,
            "qtwin-io/founderos-api",
        )
        assert source_record.record_type == "repository"
        assert source_record.connection_id == connection_id
        assert source_record.sync_job_id == sync_job_id
        assert source_record.payload_hash
        assert source_record.payload["normalized_repository"]["full_name"] == (
            "qtwin-io/founderos-api"
        )
        assert source_record.payload["evidence_refs"][0]["ref"] == "local-snap-1"
        assert repository.provider == "github"
        assert repository.name == "founderos-api"
        assert repository.full_name == "qtwin-io/founderos-api"
        assert repository.default_branch == "main"
        assert repository.visibility == "private"
        assert repository.archived is False
        assert repository.source_url == "https://github.com/qtwin-io/founderos-api"
        assert repository.repo_metadata["metadata"]["repo_not_jira_project"] is True

        serialized = json.dumps(
            {
                "payload": source_record.payload,
                "repo_metadata": repository.repo_metadata,
                "logs": stored.logs,
            },
            default=str,
            sort_keys=True,
        )
        assert "must-not-leak" not in serialized
        assert "access_token_hint" not in serialized
        assert "webhook_secret" not in serialized
        assert await _count(SourceEvent) == source_event_count_before
        assert await _count_workspace(EvidenceRef, workspace_id) == evidence_count_before
        assert await _count_workspace(Task, workspace_id) == task_count_before
        assert await _count_workspace(PullRequest, workspace_id) == pull_request_count_before
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_canonical_repository_persistence_is_idempotent(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([_repo_payload()])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection_id = await _seed_connection(workspace_id)
        first_sync_job_id = await _seed_sync_job(workspace_id, connection_id)
        second_sync_job_id = await _seed_sync_job(workspace_id, connection_id)

        async with _async_client() as client:
            first = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/sync-jobs/{first_sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "include_issues": False,
                    "include_pull_requests": False,
                    "persist_if_supported": True,
                },
            )
            second = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/sync-jobs/{second_sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "include_issues": False,
                    "include_pull_requests": False,
                    "persist_if_supported": True,
                },
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["sync_job"]["records_created"] == 1
        assert first.json()["sync_job"]["records_updated"] == 0
        assert second.json()["sync_job"]["records_created"] == 0
        assert second.json()["sync_job"]["records_updated"] == 1
        assert await _count_workspace(SourceRecord, workspace_id) == 1
        assert await _count_workspace(Repository, workspace_id) == 1

        stored_second = await _stored_sync_job(str(second_sync_job_id))
        assert stored_second.cursor_after["canonical_persistence"] == {
            "source_records_created": 0,
            "source_records_updated": 1,
            "repositories_created": 0,
            "repositories_updated": 1,
            "tasks_created": 0,
            "tasks_updated": 0,
            "pull_requests_created": 0,
            "pull_requests_updated": 0,
        }
        source_record, repository = await _stored_canonical_repo_rows(
            workspace_id,
            "qtwin-io/founderos-api",
        )
        assert source_record.sync_job_id == second_sync_job_id
        assert repository.full_name == "qtwin-io/founderos-api"
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_owner_can_persist_canonical_issues_and_pull_requests(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([_repo_payload()])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection_id = await _seed_connection(workspace_id)
        issue_external_id = "qtwin-io/founderos-api#issue/42"
        pull_request_external_id = "qtwin-io/founderos-api#pull/7"
        sync_job_id = await _seed_sync_job(
            workspace_id,
            connection_id,
            cursor_before=_work_item_cursor(
                issues=[_issue_payload()],
                pull_requests=[_pull_request_payload()],
            ),
        )
        source_event_count_before = await _count(SourceEvent)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"persist_if_supported": True},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["persistence_mode"] == "canonical"
        assert body["counts"] == {"repositories": 1, "issues": 1, "pull_requests": 1}
        assert body["sync_job"]["status"] == "succeeded"
        assert body["sync_job"]["records_seen"] == 3
        assert body["sync_job"]["records_created"] == 3
        assert body["sync_job"]["records_updated"] == 0
        assert not any("issues were not available" in warning for warning in body["warnings"])
        assert not any("pull requests were not available" in warning for warning in body["warnings"])

        stored = await _stored_sync_job(str(sync_job_id))
        assert stored.cursor_after["canonical_persistence"] == {
            "source_records_created": 3,
            "source_records_updated": 0,
            "repositories_created": 1,
            "repositories_updated": 0,
            "tasks_created": 1,
            "tasks_updated": 0,
            "pull_requests_created": 1,
            "pull_requests_updated": 0,
        }

        issue_source_record = await _stored_source_record(workspace_id, issue_external_id)
        pull_source_record = await _stored_source_record(workspace_id, pull_request_external_id)
        source_record, repository = await _stored_canonical_repo_rows(
            workspace_id,
            "qtwin-io/founderos-api",
        )
        task = await _stored_task(workspace_id, issue_external_id)
        pull_request = await _stored_pull_request(workspace_id, pull_request_external_id)

        assert source_record.record_type == "repository"
        assert issue_source_record.record_type == "issue"
        assert pull_source_record.record_type == "pull_request"
        assert task.source_record_id == issue_source_record.id
        assert task.status == "open"
        assert task.source_url == "https://github.com/qtwin-io/founderos-api/issues/42"
        assert task.task_metadata["github_object_type"] == "issue"
        assert task.task_metadata["repository_full_name"] == "qtwin-io/founderos-api"
        assert pull_request.repository_id == repository.id
        assert pull_request.state == "open"
        assert pull_request.source_url == "https://github.com/qtwin-io/founderos-api/pull/7"
        assert pull_request.pr_metadata["github_object_type"] == "pull_request"

        serialized = json.dumps(
            {
                "normalized": body["normalized"],
                "issue_source_record": issue_source_record.payload,
                "pull_source_record": pull_source_record.payload,
                "task_metadata": task.task_metadata,
                "pr_metadata": pull_request.pr_metadata,
                "logs": stored.logs,
            },
            default=str,
            sort_keys=True,
        )
        assert "must-not-leak" not in serialized
        assert "access_token_hint" not in serialized
        assert "webhook_secret" not in serialized
        assert await _count(SourceEvent) == source_event_count_before
        assert await _count_workspace(SourceRecord, workspace_id) == 3
        assert await _count_workspace(Repository, workspace_id) == 1
        assert await _count_workspace(Task, workspace_id) == 1
        assert await _count_workspace(PullRequest, workspace_id) == 1
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_canonical_github_work_persistence_is_idempotent(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([_repo_payload()])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection_id = await _seed_connection(workspace_id)
        cursor = _work_item_cursor(
            issues=[_issue_payload()],
            pull_requests=[_pull_request_payload()],
        )
        first_sync_job_id = await _seed_sync_job(
            workspace_id,
            connection_id,
            cursor_before=cursor,
        )
        second_sync_job_id = await _seed_sync_job(
            workspace_id,
            connection_id,
            cursor_before=cursor,
        )

        async with _async_client() as client:
            first = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/sync-jobs/{first_sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"persist_if_supported": True},
            )
            second = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/sync-jobs/{second_sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"persist_if_supported": True},
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["sync_job"]["records_created"] == 3
        assert first.json()["sync_job"]["records_updated"] == 0
        assert second.json()["sync_job"]["records_created"] == 0
        assert second.json()["sync_job"]["records_updated"] == 3
        assert await _count_workspace(SourceRecord, workspace_id) == 3
        assert await _count_workspace(Repository, workspace_id) == 1
        assert await _count_workspace(Task, workspace_id) == 1
        assert await _count_workspace(PullRequest, workspace_id) == 1

        stored_second = await _stored_sync_job(str(second_sync_job_id))
        assert stored_second.cursor_after["canonical_persistence"] == {
            "source_records_created": 0,
            "source_records_updated": 3,
            "repositories_created": 0,
            "repositories_updated": 1,
            "tasks_created": 0,
            "tasks_updated": 1,
            "pull_requests_created": 0,
            "pull_requests_updated": 1,
        }
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_github_operational_work_read_model_filters_open_state(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([_repo_payload()])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection_id = await _seed_connection(workspace_id)
        sync_job_id = await _seed_sync_job(
            workspace_id,
            connection_id,
            cursor_before=_work_item_cursor(
                issues=[
                    _issue_payload(number=42, state="open"),
                    _issue_payload(number=43, state="closed"),
                ],
                pull_requests=[
                    _pull_request_payload(number=7, state="open"),
                    _pull_request_payload(number=8, state="merged"),
                ],
            ),
        )

        async with _async_client() as client:
            normalize_response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"persist_if_supported": True},
            )
            open_response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/operational-work",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )
            all_response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/operational-work",
                headers=_headers(),
                params={
                    "owner_email": _bootstrap_payload(marker)["owner_email"],
                    "state": "all",
                },
            )
            merged_response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/operational-work",
                headers=_headers(),
                params={
                    "owner_email": _bootstrap_payload(marker)["owner_email"],
                    "state": "merged",
                },
            )

        assert normalize_response.status_code == 200, normalize_response.text
        assert open_response.status_code == 200, open_response.text
        open_body = open_response.json()
        assert open_body["source"] == "canonical_github_operational_work"
        assert open_body["is_live"] is False
        assert open_body["state"] == "open"
        assert open_body["counts"] == {"issues": 1, "pull_requests": 1}
        assert open_body["issues"][0]["external_id"] == "qtwin-io/founderos-api#issue/42"
        assert open_body["issues"][0]["repository_full_name"] == "qtwin-io/founderos-api"
        assert open_body["pull_requests"][0]["external_id"] == (
            "qtwin-io/founderos-api#pull/7"
        )
        assert open_body["pull_requests"][0]["repository_full_name"] == (
            "qtwin-io/founderos-api"
        )

        assert all_response.status_code == 200, all_response.text
        assert all_response.json()["counts"] == {"issues": 2, "pull_requests": 2}
        assert merged_response.status_code == 200, merged_response.text
        assert merged_response.json()["counts"] == {"issues": 0, "pull_requests": 1}
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_normalize_local_does_not_call_live_source_or_graph_paths(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)


    async def fake_repository_read(**_kwargs):
        return _repository_result([_repo_payload()])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)
        source_event_count_before = await _count(SourceEvent)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "include_issues": False,
                    "include_pull_requests": False,
                    "persist_if_supported": True,
                },
            )

        assert response.status_code == 200
        assert response.json()["provider_sync_started"] is False
        assert await _count(SourceEvent) == source_event_count_before
        assert not Path("app/services/source_control.py").exists()
    finally:
        await _cleanup_normalization_fixture(marker)


def test_github_normalization_api_does_not_create_migration_file() -> None:
    version_files = {path.name for path in Path("migrations/versions").glob("*.py")}
    assert not any("github_normalization" in name for name in version_files)
    assert not any("github_graph_upsert" in name for name in version_files)
