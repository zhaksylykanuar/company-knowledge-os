from __future__ import annotations

from base64 import urlsafe_b64decode
from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.api.auth import settings
from app.core.config import Settings
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import EvidenceRef, PullRequest, Repository, SourceRecord, Task
from app.db.identity_models import (
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import IntegrationConnection, SyncJob
from app.main import app
from app.services import github_app_live_sync_service
from app.services.github_app_token_service import (
    GitHubInstallationAccessToken,
    build_github_app_jwt,
)


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "secret_encryption_key", SecretStr("test-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _bootstrap_payload(marker: str, *, suffix: str = "") -> dict[str, str]:
    return {
        "owner_email": f"github-app-sync-{marker}{suffix}@example.test",
        "owner_name": "GitHub App Sync Owner",
        "workspace_name": f"GitHub App Sync {marker}{suffix}",
        "workspace_slug": f"github-app-sync-{marker}{suffix}",
    }


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
    email = f"github-app-sync-{marker}-{suffix}@example.test"
    async with AsyncSessionLocal() as session:
        user = User(email=email, name=f"GitHub App Sync {role}")
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


async def _cleanup_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"github-app-sync-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"github-app-sync-{marker}%@example.test")
                    )
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(
                delete(EvidenceRef).where(EvidenceRef.workspace_id.in_(workspace_ids))
            )
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


async def _create_app_connection(workspace_id: str, marker: str) -> dict:
    async with _async_client() as client:
        response = await client.post(
            f"/api/v1/workspaces/{workspace_id}/github/connections/app-installation",
            headers=_headers(),
            params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            json={
                "installation_id": "98765",
                "account_login": "qtwin-io",
                "repository_selection": "selected",
                "selected_repositories": [
                    {"full_name": "qtwin-io/company-knowledge-os"}
                ],
            },
        )
    assert response.status_code == 200, response.text
    return response.json()["connection"]


def _install_mock_provider(monkeypatch, *, installed: bool = True) -> dict[str, int]:
    calls = {"token": 0, "repositories": 0, "issues": 0, "pull_requests": 0}

    async def fake_mint_installation_access_token(
        *, installation_id: str
    ) -> GitHubInstallationAccessToken:
        assert installation_id == "98765"
        calls["token"] += 1
        return GitHubInstallationAccessToken(
            token="jit-installation-token",
            expires_at="2026-07-01T12:00:00Z",
        )

    async def fake_list_installation_repositories(
        *, access_token: str, per_page: int = 100, max_pages: int = 10
    ) -> list[dict]:
        assert access_token == "jit-installation-token"
        calls["repositories"] += 1
        if not installed:
            return []
        return [
            {
                "id": 123,
                "name": "company-knowledge-os",
                "full_name": "qtwin-io/company-knowledge-os",
                "private": True,
                "visibility": "private",
                "default_branch": "main",
                "html_url": "https://github.com/qtwin-io/company-knowledge-os",
                "pushed_at": "2026-07-01T08:00:00Z",
                "updated_at": "2026-07-01T08:30:00Z",
            }
        ]

    async def fake_list_issues(
        *,
        access_token: str,
        repository_full_name: str,
        state: str = "all",
        per_page: int = 100,
        max_pages: int = 10,
    ) -> list[dict]:
        assert access_token == "jit-installation-token"
        assert repository_full_name == "qtwin-io/company-knowledge-os"
        assert state == "all"
        calls["issues"] += 1
        return [
            {
                "id": 9001,
                "number": 7,
                "title": "Live issue",
                "state": "open",
                "html_url": "https://github.com/qtwin-io/company-knowledge-os/issues/7",
                "created_at": "2026-07-01T08:00:00Z",
                "updated_at": "2026-07-01T08:15:00Z",
            },
            {
                "id": 9002,
                "number": 8,
                "title": "PR-shaped issue",
                "state": "open",
                "pull_request": {"url": "https://api.github.test/pulls/8"},
            },
        ]

    async def fake_list_pull_requests(
        *,
        access_token: str,
        repository_full_name: str,
        state: str = "all",
        per_page: int = 100,
        max_pages: int = 10,
    ) -> list[dict]:
        assert access_token == "jit-installation-token"
        assert repository_full_name == "qtwin-io/company-knowledge-os"
        assert state == "all"
        calls["pull_requests"] += 1
        return [
            {
                "id": 8001,
                "number": 3,
                "title": "Live PR",
                "state": "closed",
                "merged_at": "2026-07-01T09:00:00Z",
                "html_url": "https://github.com/qtwin-io/company-knowledge-os/pull/3",
                "created_at": "2026-07-01T08:20:00Z",
                "updated_at": "2026-07-01T08:55:00Z",
                "draft": False,
            }
        ]

    async def fail_create_issue(**_kwargs) -> dict:
        raise AssertionError("GitHub App live read sync must not create issues")

    monkeypatch.setattr(
        github_app_live_sync_service.github_app_token_service,
        "mint_installation_access_token",
        fake_mint_installation_access_token,
    )
    monkeypatch.setattr(
        github_app_live_sync_service.github_repository_client,
        "list_installation_repositories",
        fake_list_installation_repositories,
    )
    monkeypatch.setattr(
        github_app_live_sync_service.github_issue_client,
        "list_issues",
        fake_list_issues,
    )
    monkeypatch.setattr(
        github_app_live_sync_service.github_pull_request_client,
        "list_pull_requests",
        fake_list_pull_requests,
    )
    monkeypatch.setattr(
        github_app_live_sync_service.github_issue_client,
        "create_issue",
        fail_create_issue,
        raising=False,
    )
    return calls


async def _count_for_workspace(model: type, workspace_id: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.workspace_id == UUID(workspace_id))
            )
            or 0
        )


async def _sync_job_payload(workspace_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        sync_job = await session.scalar(
            select(SyncJob)
            .where(SyncJob.workspace_id == UUID(workspace_id))
            .order_by(SyncJob.created_at.desc())
        )
        assert sync_job is not None
        return {
            "cursor_before": sync_job.cursor_before,
            "cursor_after": sync_job.cursor_after,
            "logs": sync_job.logs,
        }


def test_build_github_app_jwt_uses_app_id_without_exposing_private_key() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    config = Settings(
        github_app_id="12345",
        github_app_private_key=SecretStr(private_key_pem),
        _env_file=None,
    )

    token = build_github_app_jwt(
        config=config,
        now=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )

    header_b64, payload_b64, signature_b64 = token.split(".")
    header = json.loads(_decode_base64url(header_b64))
    payload = json.loads(_decode_base64url(payload_b64))
    assert header == {"alg": "RS256", "typ": "JWT"}
    assert payload["iss"] == "12345"
    assert payload["exp"] > payload["iat"]
    assert signature_b64
    assert "PRIVATE KEY" not in token


async def test_github_app_live_sync_reads_and_persists_without_token_storage_or_writes(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection = await _create_app_connection(workspace_id, marker)
        calls = _install_mock_provider(monkeypatch)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/connections/app-installation/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": connection["id"],
                    "repositories": ["qtwin-io/company-knowledge-os"],
                    "include_issues": True,
                    "include_pull_requests": True,
                },
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_live"] is True
        assert body["provider_sync_started"] is True
        assert body["external_write_performed"] is False
        assert body["capabilities"] == {
            "read_only_sync": True,
            "external_writes": False,
            "installation_access_token_persisted": False,
        }
        assert body["totals"] == {
            "repositories": 1,
            "issues": 1,
            "pull_requests": 1,
            "skipped_pull_requests": 1,
        }
        assert body["counts"] == {"repositories": 1, "issues": 1, "pull_requests": 1}
        assert calls == {"token": 1, "repositories": 1, "issues": 1, "pull_requests": 1}
        assert await _count_for_workspace(Repository, workspace_id) == 1
        assert await _count_for_workspace(Task, workspace_id) == 1
        assert await _count_for_workspace(PullRequest, workspace_id) == 1

        async with AsyncSessionLocal() as session:
            stored_connection = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.id == UUID(connection["id"])
                )
            )
            assert stored_connection is not None
            assert stored_connection.encrypted_access_token is None
            assert stored_connection.encrypted_refresh_token is None

        sync_job_payload = await _sync_job_payload(workspace_id)
        serialized_sync_job = json.dumps(sync_job_payload, default=str)
        assert "jit-installation-token" not in serialized_sync_job
        assert "installation_access_token_persisted" in serialized_sync_job
    finally:
        await _cleanup_fixture(marker)


async def test_github_app_live_sync_is_workspace_scoped_before_provider_reads(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)
    await _cleanup_fixture(other_marker)

    async def fail_mint_installation_access_token(**_kwargs) -> GitHubInstallationAccessToken:
        raise AssertionError("wrong-workspace connection must fail before provider read")

    monkeypatch.setattr(
        github_app_live_sync_service.github_app_token_service,
        "mint_installation_access_token",
        fail_mint_installation_access_token,
    )

    try:
        created = await _bootstrap_workspace(marker)
        other = await _bootstrap_workspace(other_marker)
        connection = await _create_app_connection(created["workspace"]["id"], marker)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{other['workspace']['id']}/github/connections/app-installation/sync",
                headers=_headers(),
                params={
                    "owner_email": _bootstrap_payload(other_marker)["owner_email"]
                },
                json={
                    "connection_id": connection["id"],
                    "repositories": ["qtwin-io/company-knowledge-os"],
                },
            )

        assert response.status_code == 404
        assert response.json() == {"detail": "github connection not found"}
    finally:
        await _cleanup_fixture(marker)
        await _cleanup_fixture(other_marker)


async def test_member_and_viewer_cannot_run_github_app_live_sync(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    async def fail_mint_installation_access_token(**_kwargs) -> GitHubInstallationAccessToken:
        raise AssertionError("RBAC rejection must happen before provider read")

    monkeypatch.setattr(
        github_app_live_sync_service.github_app_token_service,
        "mint_installation_access_token",
        fail_mint_installation_access_token,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection = await _create_app_connection(workspace_id, marker)

        for role in (MEMBERSHIP_ROLE_MEMBER, MEMBERSHIP_ROLE_VIEWER):
            user_email = await _add_workspace_user(
                workspace_id,
                marker,
                role=role,
                suffix=role,
            )
            async with _async_client() as client:
                response = await client.post(
                    f"/api/v1/workspaces/{workspace_id}/github/connections/app-installation/sync",
                    headers=_headers(),
                    params={"owner_email": user_email},
                    json={
                        "connection_id": connection["id"],
                        "repositories": ["qtwin-io/company-knowledge-os"],
                    },
                )

            assert response.status_code == 403
            assert response.json() == {"detail": "insufficient workspace role"}
    finally:
        await _cleanup_fixture(marker)


async def test_github_app_live_sync_rejects_repository_outside_installation(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection = await _create_app_connection(workspace_id, marker)
        calls = _install_mock_provider(monkeypatch, installed=False)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/connections/app-installation/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": connection["id"],
                    "repositories": ["qtwin-io/company-knowledge-os"],
                },
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "github repository is not part of the app installation"
        }
        assert calls == {"token": 1, "repositories": 1, "issues": 0, "pull_requests": 0}
        assert await _count_for_workspace(Repository, workspace_id) == 0
    finally:
        await _cleanup_fixture(marker)


async def test_github_app_live_sync_rejects_invalid_state_before_provider_reads(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    async def fail_mint_installation_access_token(**_kwargs) -> GitHubInstallationAccessToken:
        raise AssertionError("invalid state must fail before provider read")

    monkeypatch.setattr(
        github_app_live_sync_service.github_app_token_service,
        "mint_installation_access_token",
        fail_mint_installation_access_token,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection = await _create_app_connection(workspace_id, marker)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/connections/app-installation/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": connection["id"],
                    "repositories": ["qtwin-io/company-knowledge-os"],
                    "issue_states": ["triaged"],
                },
            )

        assert response.status_code == 400
        assert response.json() == {"detail": "invalid github issue state"}
    finally:
        await _cleanup_fixture(marker)


def _decode_base64url(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return urlsafe_b64decode(f"{value}{padding}".encode("ascii")).decode("utf-8")
