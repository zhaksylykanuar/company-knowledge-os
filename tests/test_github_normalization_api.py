from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.connectors.github as github_connector
import app.services.github_repository_read_service as github_repository_read_service
import app.services.source_control as source_control_service
from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.graph_models import EntityRecord
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
from app.db.source_control_models import SourceRunRequest
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
) -> UUID:
    async with AsyncSessionLocal() as session:
        sync_job = SyncJob(
            workspace_id=UUID(workspace_id),
            connection_id=connection_id,
            provider=provider,
            status=status,
            sync_type=sync_type,
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
        },
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


async def test_normalize_local_rejects_deferred_persistence(monkeypatch) -> None:
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
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"persist_if_supported": True},
            )

        assert response.status_code == 400
        assert response.json() == {
            "detail": "persistent graph upsert is deferred for GitHub normalization"
        }
        stored = await _stored_sync_job(str(sync_job_id))
        assert stored.status == SYNC_JOB_STATUS_QUEUED
        assert stored.started_at is None
    finally:
        await _cleanup_normalization_fixture(marker)


async def test_normalize_local_does_not_call_live_source_or_graph_paths(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_normalization_fixture(marker)

    def fail_live_call(*_args, **_kwargs):
        raise AssertionError("live/source action should not be called")

    monkeypatch.setattr(
        github_connector,
        "fetch_org_repository_inventory_summary",
        fail_live_call,
    )
    monkeypatch.setattr(github_connector, "list_repository_events", fail_live_call)
    monkeypatch.setattr(source_control_service, "request_source_action", fail_live_call)

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
        source_run_request_count_before = await _count(SourceRunRequest)
        entity_count_before = await _count(EntityRecord)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}/normalize-local",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert response.status_code == 200
        assert response.json()["provider_sync_started"] is False
        assert await _count(SourceEvent) == source_event_count_before
        assert await _count(SourceRunRequest) == source_run_request_count_before
        assert await _count(EntityRecord) == entity_count_before
    finally:
        await _cleanup_normalization_fixture(marker)


def test_github_normalization_api_does_not_create_migration_file() -> None:
    version_files = {path.name for path in Path("migrations/versions").glob("*.py")}
    assert not any("github_normalization" in name for name in version_files)
    assert not any("github_graph_upsert" in name for name in version_files)
