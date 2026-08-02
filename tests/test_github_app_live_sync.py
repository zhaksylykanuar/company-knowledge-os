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
from app.db.base import AsyncSessionLocal
from app.db.briefing_models import Briefing, BriefingItem
from app.db.canonical_models import EvidenceRef, PullRequest, Repository, SourceRecord, Task
from app.db.identity_models import (
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    GITHUB_APP_CREDENTIAL_STATUS_ACTIVE,
    GITHUB_APP_INSTALLATION_STATUS_ACTIVE,
    GitHubAppCredential,
    GitHubAppInstallation,
    IntegrationConnection,
    SyncJob,
)
from app.main import app
from app.services import github_app_live_sync_service
from app.services.github_app_credential_service import GitHubAppSigningCredential
from app.services.github_app_token_service import (
    GitHubInstallationAccessToken,
    build_github_app_jwt,
)
from app.services.github_repository_client import GitHubRepositoryClientError
from app.services.github_sync_worker_service import process_one_github_sync_job
from app.services.secret_encryption import encrypt_secret
from app.services.session_service import create_session


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "secret_encryption_key", SecretStr("test-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")
    monkeypatch.setattr(settings, "enable_real_connectors", True)


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _run_worker_once() -> bool:
    async with AsyncClient() as client:
        return await process_one_github_sync_job(
            client=client,
            worker_id="test-worker",
        )


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


async def _owner_session_token(marker: str) -> str:
    async with AsyncSessionLocal() as session:
        user = await session.scalar(
            select(User).where(
                User.email == _bootstrap_payload(marker)["owner_email"]
            )
        )
        assert user is not None
        raw_token, _row = await create_session(session, user.id)
        await session.commit()
    return raw_token


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
                delete(GitHubAppInstallation).where(
                    GitHubAppInstallation.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(GitHubAppCredential).where(
                    GitHubAppCredential.workspace_id.in_(workspace_ids)
                )
            )
            briefing_ids = list(
                (
                    await session.execute(
                        select(Briefing.id).where(
                            Briefing.workspace_id.in_(workspace_ids)
                        )
                    )
                ).scalars()
            )
            if briefing_ids:
                await session.execute(
                    delete(BriefingItem).where(
                        BriefingItem.briefing_id.in_(briefing_ids)
                    )
                )
                await session.execute(delete(Briefing).where(Briefing.id.in_(briefing_ids)))
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


async def _create_unverified_app_connection(
    workspace_id: str,
) -> dict:
    async with AsyncSessionLocal() as session:
        connection = IntegrationConnection(
            workspace_id=UUID(workspace_id),
            provider="github",
            status="connected",
            display_name="Unverified GitHub App",
            external_account_id="github_app_installation:98765",
            scopes=["github_app_installation"],
            provider_metadata={
                "connection_method": "github_app_installation",
                "installation_id": "98765",
                "installation_verified": False,
                "provider_reads_enabled": False,
                "provider_writes_enabled": False,
                "selected_repositories": [
                    {"full_name": "qtwin-io/company-knowledge-os"}
                ],
            },
        )
        session.add(connection)
        await session.commit()
        return {"id": str(connection.id)}


async def _create_managed_app_connection(workspace_id: str, marker: str) -> dict:
    workspace_uuid = UUID(workspace_id)
    async with AsyncSessionLocal() as session:
        credential = GitHubAppCredential(
            workspace_id=workspace_uuid,
            app_id=f"managed-{marker}",
            app_slug=f"founderos-managed-{marker}",
            app_name="FounderOS managed test app",
            client_id=f"client-{marker}",
            encrypted_private_key=encrypt_secret("managed-test-private-key"),
            encrypted_client_secret=encrypt_secret("managed-test-client-secret"),
            callback_url="http://127.0.0.1:3000/api/v1/github/app-setup/oauth/callback",
            source="manifest",
            status=GITHUB_APP_CREDENTIAL_STATUS_ACTIVE,
            last_verified_at=datetime.now(timezone.utc),
        )
        session.add(credential)
        await session.flush()
        connection = IntegrationConnection(
            workspace_id=workspace_uuid,
            provider="github",
            status="connected",
            display_name="GitHub App: qtwin-io",
            external_account_id="github_app_installation:98765",
            scopes=["github_app_installation", "read_only"],
            provider_metadata={
                "connection_method": "github_app_installation",
                "installation_id": "98765",
                "installation_verified": True,
                "provider_reads_enabled": True,
                "provider_writes_enabled": False,
                "installation_access_token_persisted": False,
                "selected_repositories": [
                    {"full_name": "qtwin-io/company-knowledge-os"}
                ],
                "created_via": "founderos_self_service",
            },
        )
        session.add(connection)
        await session.flush()
        session.add(
            GitHubAppInstallation(
                workspace_id=workspace_uuid,
                credential_id=credential.id,
                connection_id=connection.id,
                installation_id="98765",
                account_login="qtwin-io",
                repository_selection="selected",
                verified_at=datetime.now(timezone.utc),
                repository_count=1,
                status=GITHUB_APP_INSTALLATION_STATUS_ACTIVE,
            )
        )
        await session.commit()
    return {"id": str(connection.id)}


def _install_mock_provider(
    monkeypatch,
    *,
    installed: bool = True,
) -> dict[str, int]:
    calls = {"token": 0, "repositories": 0, "issues": 0, "pull_requests": 0}

    async def fake_mint_installation_access_token(
        *,
        installation_id: str,
        credential: GitHubAppSigningCredential,
        client: AsyncClient | None = None,
    ) -> GitHubInstallationAccessToken:
        assert client is not None
        assert installation_id == "98765"
        assert credential.app_id.startswith("managed-")
        assert credential.private_key_pem == "managed-test-private-key"
        calls["token"] += 1
        return GitHubInstallationAccessToken(
            token="jit-installation-token",
            expires_at="2026-07-01T12:00:00Z",
        )

    async def fake_list_installation_repositories(
        *,
        access_token: str,
        per_page: int = 100,
        max_pages: int = 10,
        client: AsyncClient | None = None,
    ) -> list[dict]:
        assert client is not None
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
        client: AsyncClient | None = None,
    ) -> list[dict]:
        assert client is not None
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
        client: AsyncClient | None = None,
    ) -> list[dict]:
        assert client is not None
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
    credential = GitHubAppSigningCredential(
        app_id="12345",
        private_key_pem=private_key_pem,
    )

    token = build_github_app_jwt(
        credential=credential,
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


async def test_github_app_live_sync_fails_closed_when_real_connectors_disabled(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "enable_real_connectors", False)
    await _cleanup_fixture(marker)

    async def fail_provider_call(**_kwargs):
        raise AssertionError("provider token mint/read must stay disabled")

    monkeypatch.setattr(
        github_app_live_sync_service.github_app_token_service,
        "mint_installation_access_token",
        fail_provider_call,
    )
    monkeypatch.setattr(
        github_app_live_sync_service.github_repository_client,
        "list_installation_repositories",
        fail_provider_call,
    )
    monkeypatch.setattr(
        github_app_live_sync_service.github_issue_client,
        "list_issues",
        fail_provider_call,
    )
    monkeypatch.setattr(
        github_app_live_sync_service.github_pull_request_client,
        "list_pull_requests",
        fail_provider_call,
    )

    try:
        created = await _bootstrap_workspace(marker)
        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/app-installation/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": str(uuid4()),
                    "repositories": ["qtwin-io/company-knowledge-os"],
                },
            )

        assert response.status_code == 409
        assert response.json() == {"detail": "real provider connectors are disabled"}
    finally:
        await _cleanup_fixture(marker)


async def test_unverified_legacy_app_connection_cannot_start_provider_reads(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    async def fail_provider_call(**_kwargs):
        raise AssertionError("unverified installation must fail before provider read")

    monkeypatch.setattr(
        github_app_live_sync_service.github_app_token_service,
        "mint_installation_access_token",
        fail_provider_call,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection = await _create_unverified_app_connection(workspace_id)

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
            "detail": "github app installation is not provider-verified"
        }
    finally:
        await _cleanup_fixture(marker)


async def test_verified_managed_app_can_read_with_global_connector_gate_disabled(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    async def fake_signing_credential(
        _session,
        *,
        workspace_id: UUID,
    ) -> GitHubAppSigningCredential:
        assert str(workspace_id)
        return GitHubAppSigningCredential(
            app_id="managed-test-app",
            private_key_pem="managed-test-private-key",
        )

    monkeypatch.setattr(
        github_app_live_sync_service,
        "get_github_app_signing_credential",
        fake_signing_credential,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection = await _create_managed_app_connection(workspace_id, marker)
        calls = _install_mock_provider(monkeypatch)
        monkeypatch.setattr(settings, "enable_real_connectors", False)

        async with _async_client() as client:
            operator_response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/connections/app-installation/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": connection["id"],
                    "repositories": ["qtwin-io/company-knowledge-os"],
                },
            )
        assert operator_response.status_code == 409
        assert operator_response.json() == {
            "detail": "real provider connectors are disabled"
        }
        assert calls == {
            "token": 0,
            "repositories": 0,
            "issues": 0,
            "pull_requests": 0,
        }

        session_token = await _owner_session_token(marker)
        async with _async_client() as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/connections/app-installation/sync",
                json={
                    "connection_id": connection["id"],
                    "repositories": ["qtwin-io/company-knowledge-os"],
                    "include_issues": True,
                    "include_pull_requests": True,
                },
            )

        assert response.status_code == 202, response.text
        assert response.json()["capabilities"] == {
            "read_only_sync": True,
            "external_writes": False,
            "installation_access_token_persisted": False,
        }
        assert response.json()["sync_job"]["status"] == "queued"
        assert calls == {
            "token": 0,
            "repositories": 0,
            "issues": 0,
            "pull_requests": 0,
        }
        assert await _run_worker_once() is True
        assert calls == {
            "token": 1,
            "repositories": 1,
            "issues": 1,
            "pull_requests": 1,
        }
    finally:
        await _cleanup_fixture(marker)


async def test_verified_managed_app_cannot_read_outside_saved_repository_selection(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    async def fake_signing_credential(
        _session,
        *,
        workspace_id: UUID,
    ) -> GitHubAppSigningCredential:
        assert str(workspace_id)
        return GitHubAppSigningCredential(
            app_id="managed-test-app",
            private_key_pem="managed-test-private-key",
        )

    async def fail_provider_call(**_kwargs):
        raise AssertionError("unselected repository must fail before provider read")

    monkeypatch.setattr(
        github_app_live_sync_service,
        "get_github_app_signing_credential",
        fake_signing_credential,
    )
    monkeypatch.setattr(
        github_app_live_sync_service.github_app_token_service,
        "mint_installation_access_token",
        fail_provider_call,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection = await _create_managed_app_connection(workspace_id, marker)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/connections/app-installation/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": connection["id"],
                    "repositories": ["qtwin-io/not-selected"],
                },
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "github repository is not part of the app installation"
        }
    finally:
        await _cleanup_fixture(marker)


async def test_managed_app_fails_closed_after_workspace_credential_deletion(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    async def fail_provider_call(**_kwargs):
        raise AssertionError("deleted managed credential must fail before provider read")

    monkeypatch.setattr(
        github_app_live_sync_service.github_app_token_service,
        "mint_installation_access_token",
        fail_provider_call,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection = await _create_managed_app_connection(workspace_id, marker)

        async with AsyncSessionLocal() as session:
            credential = await session.scalar(
                select(GitHubAppCredential).where(
                    GitHubAppCredential.workspace_id == UUID(workspace_id)
                )
            )
            assert credential is not None
            await session.delete(credential)
            await session.commit()

        async with _async_client() as client:
            status_response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/connection-status",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )
            sync_response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/github/connections/app-installation/sync",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "connection_id": connection["id"],
                    "repositories": ["qtwin-io/company-knowledge-os"],
                },
            )

        assert status_response.status_code == 200
        assert status_response.json()["installation_verified"] is False
        assert status_response.json()["live_read_available"] is False
        assert sync_response.status_code == 409
        assert sync_response.json() == {
            "detail": "github app installation is not provider-verified"
        }
    finally:
        await _cleanup_fixture(marker)


async def test_github_app_live_sync_reads_and_persists_without_token_storage_or_writes(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection = await _create_managed_app_connection(workspace_id, marker)
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

        assert response.status_code == 202, response.text
        queued = response.json()
        assert queued["is_live"] is False
        assert queued["provider_sync_started"] is False
        assert queued["external_write_performed"] is False
        assert queued["capabilities"] == {
            "read_only_sync": True,
            "external_writes": False,
            "installation_access_token_persisted": False,
        }
        assert calls == {"token": 0, "repositories": 0, "issues": 0, "pull_requests": 0}
        assert await _run_worker_once() is True
        async with _async_client() as client:
            job_response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/sync-jobs/"
                f"{queued['sync_job']['id']}",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )
        assert job_response.status_code == 200, job_response.text
        job = job_response.json()
        assert job["status"] == "succeeded"
        assert job["execution_started"] is True
        assert job["progress"]["counts"] == {
            "repositories": 1,
            "issues": 1,
            "pull_requests": 1,
            "skipped_pull_requests": 1,
        }
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


async def test_github_app_synced_data_feeds_brain_and_briefing_with_workspace_isolation(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    try:
        created_a = await _bootstrap_workspace(marker)
        created_b = await _bootstrap_workspace(marker, suffix="-b")
        workspace_a = created_a["workspace"]["id"]
        workspace_b = created_b["workspace"]["id"]
        owner_a = _bootstrap_payload(marker)["owner_email"]
        owner_b = _bootstrap_payload(marker, suffix="-b")["owner_email"]
        connection = await _create_managed_app_connection(workspace_a, marker)
        _install_mock_provider(monkeypatch)

        async with _async_client() as client:
            sync_response = await client.post(
                f"/api/v1/workspaces/{workspace_a}/github/connections/app-installation/sync",
                headers=_headers(),
                params={"owner_email": owner_a},
                json={
                    "connection_id": connection["id"],
                    "repositories": ["qtwin-io/company-knowledge-os"],
                },
            )
            assert sync_response.status_code == 202, sync_response.text
            assert await _run_worker_once() is True
            brain_a = await client.get(
                f"/api/v1/workspaces/{workspace_a}/company-brain",
                headers=_headers(),
                params={"owner_email": owner_a},
            )
            briefing_a = await client.post(
                f"/api/v1/workspaces/{workspace_a}/briefings/manual",
                headers=_headers(),
                params={"owner_email": owner_a},
                json={},
            )
            brain_b = await client.get(
                f"/api/v1/workspaces/{workspace_b}/company-brain",
                headers=_headers(),
                params={"owner_email": owner_b},
            )
            briefing_b = await client.post(
                f"/api/v1/workspaces/{workspace_b}/briefings/manual",
                headers=_headers(),
                params={"owner_email": owner_b},
                json={},
            )
            wrong_owner_brain = await client.get(
                f"/api/v1/workspaces/{workspace_a}/company-brain",
                headers=_headers(),
                params={"owner_email": owner_b},
            )

        assert brain_a.status_code == 200, brain_a.text
        brain_a_body = brain_a.json()
        assert brain_a_body["summary"]["repositories"] == 1
        assert brain_a_body["summary"]["open_issues"] == 1
        assert brain_a_body["summary"]["merged_pull_requests"] == 1
        assert brain_a_body["repositories"][0]["full_name"] == (
            "qtwin-io/company-knowledge-os"
        )
        evidence_labels = {ref["label"] for ref in brain_a_body["evidence"]}
        assert "qtwin-io/company-knowledge-os" in evidence_labels
        assert "9001" in evidence_labels
        assert "qtwin-io/company-knowledge-os#pull/3" in evidence_labels
        serialized_brain_a = json.dumps(brain_a_body, sort_keys=True)
        assert "jit-installation-token" not in serialized_brain_a

        assert briefing_a.status_code == 200, briefing_a.text
        briefing_a_body = briefing_a.json()["briefing"]
        assert briefing_a_body["llm_used"] is False
        assert briefing_a_body["persistence"] == "persisted"
        assert any(item["evidence_refs"] for item in briefing_a_body["items"])
        briefing_refs = [
            ref
            for item in briefing_a_body["items"]
            for ref in item["evidence_refs"]
        ]
        assert any(
            ref["kind"] == "sync_job"
            and ref["ref"] == sync_response.json()["sync_job"]["id"]
            for ref in briefing_refs
        )
        assert "jit-installation-token" not in json.dumps(briefing_a_body, sort_keys=True)
        assert "company-knowledge-os" in json.dumps(briefing_a_body, sort_keys=True)

        assert brain_b.status_code == 200, brain_b.text
        brain_b_body = brain_b.json()
        assert brain_b_body["summary"]["repositories"] == 0
        assert brain_b_body["evidence"] == []
        assert "company-knowledge-os" not in json.dumps(brain_b_body, sort_keys=True)

        assert briefing_b.status_code == 200, briefing_b.text
        briefing_b_body = briefing_b.json()["briefing"]
        serialized_briefing_b = json.dumps(briefing_b_body, sort_keys=True)
        assert sync_response.json()["sync_job"]["id"] not in serialized_briefing_b
        assert connection["id"] not in serialized_briefing_b
        assert wrong_owner_brain.status_code == 404
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
        connection = await _create_managed_app_connection(
            created["workspace"]["id"],
            marker,
        )

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
        connection = await _create_managed_app_connection(workspace_id, marker)

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
        connection = await _create_managed_app_connection(workspace_id, marker)
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

        assert response.status_code == 202
        assert calls == {"token": 0, "repositories": 0, "issues": 0, "pull_requests": 0}
        assert await _run_worker_once() is True
        async with _async_client() as client:
            job_response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/sync-jobs/"
                f"{response.json()['sync_job']['id']}",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )
        assert job_response.status_code == 200
        assert job_response.json()["status"] == "failed"
        assert calls == {"token": 1, "repositories": 1, "issues": 0, "pull_requests": 0}
        assert await _count_for_workspace(Repository, workspace_id) == 0
    finally:
        await _cleanup_fixture(marker)


async def test_github_app_live_sync_surfaces_sanitized_rate_limit_detail(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_fixture(marker)

    async def fake_mint_installation_access_token(
        *,
        installation_id: str,
        credential: GitHubAppSigningCredential,
        client: AsyncClient | None = None,
    ) -> GitHubInstallationAccessToken:
        assert installation_id == "98765"
        assert credential.app_id.startswith("managed-")
        assert client is not None
        return GitHubInstallationAccessToken(token="jit-installation-token")

    async def fake_list_installation_repositories(**_kwargs) -> list[dict]:
        raise GitHubRepositoryClientError(
            "github repository read request failed; http_403; "
            "message=API rate limit exceeded.; rate_limited=true; "
            "retry_after_seconds=60; rate_limit_remaining=0"
        )

    async def fail_list_issues(**_kwargs) -> list[dict]:
        raise AssertionError("rate-limited repository read must stop before issues")

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
        fail_list_issues,
    )

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        connection = await _create_managed_app_connection(workspace_id, marker)

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

        assert response.status_code == 202
        assert await _run_worker_once() is True
        async with _async_client() as client:
            job_response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/github/sync-jobs/"
                f"{response.json()['sync_job']['id']}",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )
        assert job_response.status_code == 200
        job = job_response.json()
        assert job["status"] == "queued"
        assert job["progress"]["phase"] == "retry_scheduled"
        assert job["error_message"] == "github sync will retry"
        assert "API rate limit exceeded" not in job_response.text
        assert "jit-installation-token" not in job_response.text
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
        connection = await _create_managed_app_connection(workspace_id, marker)

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
