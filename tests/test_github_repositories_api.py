from pathlib import Path
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.services.github_repository_read_service as github_repository_service
from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import Membership, User, Workspace
from app.db.integration_models import IntegrationConnection, SyncJob
from app.main import app
from app.services.repository_source_inventory import (
    INVENTORY_DISCOVERY_SNAPSHOT,
    INVENTORY_LEGACY_SEED,
    INVENTORY_SOURCE_EVENTS,
)


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
        "owner_email": f"github-read-{marker}{suffix}@example.test",
        "owner_name": "GitHub Read Owner",
        "workspace_name": f"GitHub Read {marker}{suffix}",
        "workspace_slug": f"github-read-{marker}{suffix}",
    }


async def _cleanup_workspace_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"github-read-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"github-read-{marker}%@example.test")
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


def _inventory_payload(
    repositories: list[dict],
    *,
    source_class: str = INVENTORY_DISCOVERY_SNAPSHOT,
) -> dict:
    return {
        "source_class": source_class,
        "network_calls": False,
        "db_written": False,
        "source_snapshot": {
            "snapshot_key": "local-snap-1",
            "path": "discovery/github/local-snap-1/raw/repos.json",
        },
        "repositories": repositories,
    }


async def _count(model: type) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_github_repositories_requires_api_key(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories",
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 401
        assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
        assert "test-api-key" not in response.text
    finally:
        await _cleanup_workspace_fixture(marker)


async def test_github_repositories_requires_owner_email_context(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories",
                headers=_headers(),
            )

        assert response.status_code == 403
        assert response.json() == {
            "detail": "owner_email is required for operator workspace access"
        }
    finally:
        await _cleanup_workspace_fixture(marker)


async def test_github_repositories_requires_workspace_access(monkeypatch) -> None:
    marker = uuid4().hex
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup_workspace_fixture(marker)
    await _cleanup_workspace_fixture(other_marker)

    try:
        created = await _bootstrap_workspace(marker)
        await _bootstrap_workspace(other_marker)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(other_marker)["owner_email"]},
            )

        assert response.status_code == 404
        assert response.json() == {"detail": "workspace not found"}
    finally:
        await _cleanup_workspace_fixture(marker)
        await _cleanup_workspace_fixture(other_marker)


async def test_github_repositories_returns_empty_state_without_local_data(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_fixture(marker)

    async def fake_inventory(**_kwargs):
        return _inventory_payload([], source_class=INVENTORY_LEGACY_SEED)

    monkeypatch.setattr(
        github_repository_service,
        "load_repository_source_inventory",
        fake_inventory,
    )

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["repositories"] == []
        assert body["count"] == 0
        assert body["source"] == "repository_inventory"
        assert body["is_live"] is False
        assert any("legacy seed catalog is not returned" in warning for warning in body["warnings"])
    finally:
        await _cleanup_workspace_fixture(marker)


async def test_github_repositories_returns_local_inventory_with_filters_and_evidence(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_fixture(marker)

    async def fake_inventory(**_kwargs):
        return _inventory_payload(
            [
                {
                    "repo_key": "founderos-api",
                    "full_name": "qtwin-io/founderos-api",
                    "provider_key": "github",
                    "source_class": INVENTORY_DISCOVERY_SNAPSHOT,
                    "visibility": "private",
                    "archived": False,
                    "default_branch": "main",
                    "source_url": "https://github.com/qtwin-io/founderos-api",
                    "last_observed_at": "2026-06-20T00:00:00+00:00",
                    "repo_role": "component_evidence",
                    "repo_not_jira_project": True,
                },
                {
                    "repo_key": "old-api",
                    "full_name": "qtwin-io/old-api",
                    "provider_key": "github",
                    "source_class": INVENTORY_DISCOVERY_SNAPSHOT,
                    "visibility": "private",
                    "archived": True,
                    "default_branch": "main",
                    "source_url": "https://github.com/qtwin-io/old-api",
                    "last_observed_at": "2026-06-19T00:00:00+00:00",
                    "repo_role": "component_evidence",
                    "repo_not_jira_project": True,
                },
            ]
        )

    monkeypatch.setattr(
        github_repository_service,
        "load_repository_source_inventory",
        fake_inventory,
    )

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories",
                headers=_headers(),
                params={
                    "owner_email": _bootstrap_payload(marker)["owner_email"],
                    "search": "founderos",
                    "visibility": "private",
                    "archived": "false",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        repo = body["repositories"][0]
        assert repo["name"] == "founderos-api"
        assert repo["full_name"] == "qtwin-io/founderos-api"
        assert repo["default_branch"] == "main"
        assert repo["visibility"] == "private"
        assert repo["archived"] is False
        assert repo["source_url"] == "https://github.com/qtwin-io/founderos-api"
        assert repo["source"] == "repository_inventory"
        assert repo["evidence_refs"] == [
            {
                "kind": "repository_inventory_snapshot",
                "source": INVENTORY_DISCOVERY_SNAPSHOT,
                "ref": "local-snap-1",
                "url": None,
            }
        ]
        assert repo["metadata"]["repo_not_jira_project"] is True
        assert body["is_live"] is False
    finally:
        await _cleanup_workspace_fixture(marker)


async def test_github_repositories_preserves_source_event_evidence_refs(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_fixture(marker)

    async def fake_inventory(**_kwargs):
        return _inventory_payload(
            [
                {
                    "repo_key": "event-api",
                    "full_name": "qtwin-io/event-api",
                    "provider_key": "github",
                    "source_class": INVENTORY_SOURCE_EVENTS,
                    "visibility": "unknown",
                    "archived": False,
                    "last_observed_at": "2026-06-21T00:00:00+00:00",
                    "evidence_refs": [
                        {
                            "kind": "source_event",
                            "source": INVENTORY_SOURCE_EVENTS,
                            "ref": "sevt-test-event-api",
                            "url": None,
                        }
                    ],
                    "repo_role": "component_evidence",
                    "repo_not_jira_project": True,
                    "source_event_count": 2,
                }
            ],
            source_class=INVENTORY_SOURCE_EVENTS,
        )

    monkeypatch.setattr(
        github_repository_service,
        "load_repository_source_inventory",
        fake_inventory,
    )

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200
        repo = response.json()["repositories"][0]
        assert repo["evidence_refs"][0]["ref"] == "sevt-test-event-api"
        assert repo["metadata"]["source_event_count"] == 2
    finally:
        await _cleanup_workspace_fixture(marker)


async def test_github_repositories_makes_no_provider_call_or_connection_write(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_fixture(marker)

    async def fake_inventory(**_kwargs):
        return _inventory_payload([])

    monkeypatch.setattr(
        github_repository_service,
        "load_repository_source_inventory",
        fake_inventory,
    )

    try:
        created = await _bootstrap_workspace(marker)
        connection_count_before = await _count(IntegrationConnection)
        sync_job_count_before = await _count(SyncJob)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/repositories",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200
        assert response.json()["is_live"] is False
        assert await _count(IntegrationConnection) == connection_count_before
        assert await _count(SyncJob) == sync_job_count_before
    finally:
        await _cleanup_workspace_fixture(marker)


def test_github_repositories_api_does_not_create_migration_file() -> None:
    version_files = {path.name for path in Path("migrations/versions").glob("*.py")}
    assert not any("github_repositories" in name for name in version_files)
