from __future__ import annotations

import builtins
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.services.github_repository_read_service as github_repository_read_service
from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GITHUB,
    SYNC_JOB_STATUS_FAILED,
    SYNC_JOB_STATUS_PARTIAL,
    SYNC_JOB_STATUS_QUEUED,
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
        "owner_email": f"briefing-{marker}{suffix}@example.test",
        "owner_name": "Briefing Owner",
        "workspace_name": f"Briefing {marker}{suffix}",
        "workspace_slug": f"briefing-{marker}{suffix}",
    }


async def _cleanup_briefing_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"briefing-{marker}%"))
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"briefing-{marker}%@example.test")
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
    email = f"briefing-{marker}-{suffix}@example.test"
    async with AsyncSessionLocal() as session:
        user = User(email=email, name=f"Briefing {role}")
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
    status: str = INTEGRATION_CONNECTION_STATUS_CONNECTED,
) -> UUID:
    async with AsyncSessionLocal() as session:
        connection = IntegrationConnection(
            workspace_id=UUID(workspace_id),
            provider=INTEGRATION_PROVIDER_GITHUB,
            status=status,
            display_name="Briefing GitHub connection",
            external_account_id="briefing-account",
            scopes=["repo:read"],
            encrypted_access_token="encrypted-access-placeholder",
            provider_metadata={
                "login": "briefing-org",
                "access_token_hint": "must-not-leak",
            },
        )
        session.add(connection)
        await session.commit()
        return connection.id


async def _seed_sync_job(
    workspace_id: str,
    connection_id: UUID,
    *,
    status: str = SYNC_JOB_STATUS_QUEUED,
    records_seen: int = 0,
    logs: list[dict] | None = None,
    error_message: str | None = None,
) -> UUID:
    async with AsyncSessionLocal() as session:
        sync_job = SyncJob(
            workspace_id=UUID(workspace_id),
            connection_id=connection_id,
            provider=INTEGRATION_PROVIDER_GITHUB,
            status=status,
            sync_type=SYNC_JOB_TYPE_MANUAL,
            records_seen=records_seen,
            logs=logs,
            error_message=error_message,
        )
        session.add(sync_job)
        await session.commit()
        return sync_job.id


async def _stored_sync_job(sync_job_id: UUID) -> SyncJob:
    async with AsyncSessionLocal() as session:
        sync_job = await session.scalar(select(SyncJob).where(SyncJob.id == sync_job_id))
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


def _repository_payload(*, evidence_refs: list[dict] | None = None) -> dict:
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
        "evidence_refs": evidence_refs
        if evidence_refs is not None
        else [
            {
                "kind": "repository_inventory_snapshot",
                "source": INVENTORY_DISCOVERY_SNAPSHOT,
                "ref": "local-snap-1",
                "url": None,
            }
        ],
        "metadata": {"repo_not_jira_project": True},
    }


async def test_manual_briefing_requires_api_key(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_briefing_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/briefings/manual",
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert response.status_code == 401
        assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    finally:
        await _cleanup_briefing_fixture(marker)


async def test_manual_briefing_requires_owner_email_context(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_briefing_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/briefings/manual",
                headers=_headers(),
                json={},
            )

        assert response.status_code == 403
        assert response.json() == {
            "detail": "owner_email is required for operator workspace access"
        }
    finally:
        await _cleanup_briefing_fixture(marker)


@pytest.mark.parametrize("role", [MEMBERSHIP_ROLE_MEMBER, MEMBERSHIP_ROLE_VIEWER])
async def test_member_and_viewer_can_read_manual_briefing(monkeypatch, role: str) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_briefing_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        user_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=role,
            suffix=role,
        )

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/briefings/manual",
                headers=_headers(),
                params={"owner_email": user_email},
                json={},
            )

        assert response.status_code == 200
        assert response.json()["briefing"]["llm_used"] is False
    finally:
        await _cleanup_briefing_fixture(marker)


async def test_empty_workspace_returns_transient_briefing_with_warnings(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_briefing_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([], warnings=["no repositories matched local inventory"])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/briefings/manual",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert response.status_code == 200
        briefing = response.json()["briefing"]
        assert briefing["title"] == "Founder Briefing"
        assert briefing["workspace_id"] == created["workspace"]["id"]
        assert briefing["is_live"] is False
        assert briefing["llm_used"] is False
        assert briefing["persistence"] == "transient"
        assert briefing["signals"]["github"] == {
            "connection_status": "local_bridge_only",
            "repository_count": 0,
            "queued_sync_jobs": 0,
            "latest_sync_job_status": None,
        }
        assert any("no connection record" in warning for warning in briefing["warnings"])
        assert any("No evidence refs" in warning for warning in briefing["warnings"])
    finally:
        await _cleanup_briefing_fixture(marker)


async def test_manual_briefing_includes_connection_without_token_leak(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_briefing_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/briefings/manual",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert response.status_code == 200
        assert str(connection_id) in response.text
        assert "encrypted-access-placeholder" not in response.text
        assert "must-not-leak" not in response.text
        connection_item = next(
            item
            for item in response.json()["briefing"]["items"]
            if item["id"] == "github-connection"
        )
        assert connection_item["category"] == "status"
        assert connection_item["evidence_refs"][0]["kind"] == "integration_connection"
    finally:
        await _cleanup_briefing_fixture(marker)


async def test_manual_briefing_preserves_repository_evidence_refs(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_briefing_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([_repository_payload()])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/briefings/manual",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"limit": 10},
            )

        assert response.status_code == 200
        briefing = response.json()["briefing"]
        repo_item = next(
            item for item in briefing["items"] if item["id"] == "github-repositories"
        )
        assert briefing["signals"]["github"]["repository_count"] == 1
        assert repo_item["evidence_refs"][0]["ref"] == "local-snap-1"
        assert "qtwin-io/founderos-api" in repo_item["related_entities"]
        assert not any("No evidence refs" in warning for warning in repo_item["warnings"])
    finally:
        await _cleanup_briefing_fixture(marker)


async def test_manual_briefing_warns_when_repository_evidence_missing(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_briefing_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([_repository_payload(evidence_refs=[])])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/briefings/manual",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert response.status_code == 200
        repo_item = next(
            item
            for item in response.json()["briefing"]["items"]
            if item["id"] == "github-repositories"
        )
        assert repo_item["evidence_refs"] == []
        assert any("No evidence refs" in warning for warning in repo_item["warnings"])
    finally:
        await _cleanup_briefing_fixture(marker)


async def test_manual_briefing_includes_sync_job_and_failed_risk(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_briefing_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(
            created["workspace"]["id"],
            connection_id,
            status=SYNC_JOB_STATUS_FAILED,
            error_message="local normalization failed",
        )

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/briefings/manual",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        assert response.status_code == 200
        briefing = response.json()["briefing"]
        assert briefing["signals"]["github"]["latest_sync_job_status"] == "failed"
        sync_item = next(
            item for item in briefing["items"] if item["id"] == "github-sync-jobs"
        )
        assert sync_item["category"] == "risk"
        assert sync_item["severity"] == "high"
        assert sync_item["evidence_refs"][0]["ref"] == str(sync_job_id)
    finally:
        await _cleanup_briefing_fixture(marker)


async def test_manual_briefing_reads_normalization_logs_without_mutating_sync_job(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_briefing_fixture(marker)

    async def fake_repository_read(**_kwargs):
        return _repository_result([])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    normalization_log = {
        "local_normalization": {
            "performed": True,
            "provider_sync_started": False,
            "persistence_mode": "projection",
            "counts": {"repositories": 1, "issues": 0, "pull_requests": 0},
            "warnings": [
                "GitHub issues were not available in local source; returned empty issues array.",
                "GitHub pull requests were not available in local source; returned empty pull_requests array.",
            ],
        }
    }

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(
            created["workspace"]["id"],
            connection_id,
            status=SYNC_JOB_STATUS_PARTIAL,
            records_seen=1,
            logs=[normalization_log],
        )
        before = await _stored_sync_job(sync_job_id)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/briefings/manual",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        after = await _stored_sync_job(sync_job_id)
        assert response.status_code == 200
        normalization_item = next(
            item
            for item in response.json()["briefing"]["items"]
            if item["id"] == "github-normalization"
        )
        assert normalization_item["category"] == "update"
        assert "repositories=1" in normalization_item["summary"]
        assert any("issues/PRs unavailable" in warning for warning in normalization_item["warnings"])
        assert after.status == before.status
        assert after.records_seen == before.records_seen
        assert after.logs == before.logs
    finally:
        await _cleanup_briefing_fixture(marker)


async def test_manual_briefing_does_not_call_llm_provider_source_or_mutate_sync_jobs(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_briefing_fixture(marker)


    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "openai" or name.startswith("openai."):
            raise AssertionError("OpenAI should not be imported by manual briefing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    async def fake_repository_read(**_kwargs):
        return _repository_result([_repository_payload()])

    monkeypatch.setattr(
        github_repository_read_service,
        "list_workspace_github_repositories",
        fake_repository_read,
    )

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(
            created["workspace"]["id"],
            connection_id,
            status=SYNC_JOB_STATUS_QUEUED,
        )
        sync_job_count_before = await _count(SyncJob)
        before = await _stored_sync_job(sync_job_id)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/briefings/manual",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={},
            )

        after = await _stored_sync_job(sync_job_id)
        assert response.status_code == 200
        briefing = response.json()["briefing"]
        assert briefing["is_live"] is False
        assert briefing["llm_used"] is False
        assert briefing["persistence"] == "transient"
        assert await _count(SyncJob) == sync_job_count_before
        assert after.status == before.status
        assert after.records_seen == before.records_seen
        assert after.logs == before.logs
    finally:
        await _cleanup_briefing_fixture(marker)


def test_manual_briefing_api_does_not_create_migration_file() -> None:
    version_files = {path.name for path in Path("migrations/versions").glob("*.py")}
    assert not any("briefing" in name for name in version_files)
