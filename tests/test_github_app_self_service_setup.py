from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.base import AsyncSessionLocal, Base
from app.db.canonical_models import Repository
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    UserSession,
    Workspace,
)
from app.db.integration_models import (
    GITHUB_APP_INSTALLATION_STATUS_ACTIVE,
    GITHUB_APP_SETUP_PHASE_COMPLETED,
    GITHUB_APP_SETUP_PHASE_FAILED,
    GITHUB_APP_SETUP_PHASE_INSTALLATION_PENDING,
    GITHUB_APP_SETUP_PHASE_OAUTH_PENDING,
    GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION,
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_DISABLED,
    GitHubAppCredential,
    GitHubAppInstallation,
    GitHubAppSetupSession,
    IntegrationConnection,
)
from app.main import app
from app.services import (
    github_app_credential_service,
    github_app_setup_provider,
    github_app_setup_service,
)
from app.services.github_app_setup_provider import (
    GitHubManifestConversion,
    GitHubOAuthToken,
    GitHubVerifiedInstallation,
)
from app.services.github_app_credential_service import GitHubAppSigningCredential
from app.services.github_app_setup_service import (
    GitHubAppManifestStartInput,
    GitHubAppSetupError,
    begin_github_app_oauth_from_installation,
    complete_github_app_manifest_callback,
    complete_github_app_oauth_callback,
    finalize_github_app_repositories,
    get_github_app_setup_status,
    launch_github_app_installation,
    refresh_github_app_repository_inventory,
    start_github_app_manifest_setup,
    trusted_github_app_origin,
)
from app.services.github_app_token_service import (
    GitHubAppTokenError,
    GitHubInstallationAccessToken,
)
from app.services.secret_encryption import SecretEncryptionError, decrypt_secret
from app.services.session_service import create_session


APP_ORIGIN = "http://127.0.0.1:3000"
PLAIN_PRIVATE_KEY = "plain-private-key-test-placeholder"
PLAIN_CLIENT_SECRET = "plain-client-secret-test-placeholder"
PLAIN_WEBHOOK_SECRET = "plain-webhook-secret-test-placeholder"
OAUTH_ACCESS_TOKEN = "temporary-oauth-token-test-placeholder"
INSTALLATION_ACCESS_TOKEN = "temporary-installation-token-test-placeholder"


@dataclass(frozen=True)
class _Actor:
    user_id: UUID
    email: str
    session_token: str


@dataclass(frozen=True)
class _WorkspaceFixture:
    marker: str
    workspace_id: UUID
    actors: dict[str, _Actor]
    app_id: str
    installation_id: str


@dataclass(frozen=True)
class _OAuthPreparation:
    oauth_state: str
    authorization_url: str
    installation: GitHubVerifiedInstallation


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(
        settings,
        "secret_encryption_key",
        SecretStr("test-github-app-encryption-key"),
    )
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")
    monkeypatch.setattr(settings, "cors_allowed_origins", APP_ORIGIN)


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_workspace() -> _WorkspaceFixture:
    marker = uuid4().hex
    role_names = {
        MEMBERSHIP_ROLE_OWNER: "Owner",
        MEMBERSHIP_ROLE_ADMIN: "Admin",
        MEMBERSHIP_ROLE_MEMBER: "Member",
        MEMBERSHIP_ROLE_VIEWER: "Viewer",
    }
    async with AsyncSessionLocal() as session:
        users = {
            role: User(
                email=f"github-self-service-{marker}-{role}@example.test",
                name=f"GitHub Setup {name}",
            )
            for role, name in role_names.items()
        }
        session.add_all(list(users.values()))
        await session.flush()
        workspace = Workspace(
            name=f"GitHub Setup {marker}",
            slug=f"github-self-service-{marker}",
            created_by_user_id=users[MEMBERSHIP_ROLE_OWNER].id,
        )
        session.add(workspace)
        await session.flush()
        session.add_all(
            [
                Membership(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role=role,
                )
                for role, user in users.items()
            ]
        )
        actors: dict[str, _Actor] = {}
        for role, user in users.items():
            raw_token, _row = await create_session(session, user.id)
            actors[role] = _Actor(
                user_id=user.id,
                email=user.email,
                session_token=raw_token,
            )
        await session.commit()
    return _WorkspaceFixture(
        marker=marker,
        workspace_id=workspace.id,
        actors=actors,
        app_id=str(int(marker[:12], 16)),
        installation_id=str(int(marker[12:24], 16)),
    )


async def _cleanup_workspace(fixture: _WorkspaceFixture) -> None:
    user_ids = [actor.user_id for actor in fixture.actors.values()]
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(Repository).where(Repository.workspace_id == fixture.workspace_id)
        )
        await session.execute(
            delete(GitHubAppSetupSession).where(
                GitHubAppSetupSession.workspace_id == fixture.workspace_id
            )
        )
        await session.execute(
            delete(GitHubAppInstallation).where(
                GitHubAppInstallation.workspace_id == fixture.workspace_id
            )
        )
        await session.execute(
            delete(IntegrationConnection).where(
                IntegrationConnection.workspace_id == fixture.workspace_id
            )
        )
        await session.execute(
            delete(GitHubAppCredential).where(
                GitHubAppCredential.workspace_id == fixture.workspace_id
            )
        )
        await session.execute(delete(UserSession).where(UserSession.user_id.in_(user_ids)))
        await session.execute(
            delete(Membership).where(Membership.workspace_id == fixture.workspace_id)
        )
        await session.execute(
            delete(Workspace).where(Workspace.id == fixture.workspace_id)
        )
        await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


def _manifest_conversion(fixture: _WorkspaceFixture) -> GitHubManifestConversion:
    return GitHubManifestConversion(
        app_id=fixture.app_id,
        app_slug=f"founderos-{fixture.marker[:12]}",
        app_name=f"FounderOS {fixture.marker[:8]}",
        client_id=f"client-{fixture.marker[:12]}",
        client_secret=PLAIN_CLIENT_SECRET,
        private_key_pem=PLAIN_PRIVATE_KEY,
        webhook_secret=PLAIN_WEBHOOK_SECRET,
        html_url=f"https://github.com/apps/founderos-{fixture.marker[:12]}",
        owner_login="founderos-test",
        owner_id="1234",
        owner_type="Organization",
        permissions={"issues": "read", "pull_requests": "read"},
    )


def _verified_installation(
    fixture: _WorkspaceFixture,
    *,
    app_id: str | None = None,
) -> GitHubVerifiedInstallation:
    return GitHubVerifiedInstallation(
        installation_id=fixture.installation_id,
        app_id=app_id or fixture.app_id,
        account_login="founderos-test",
        account_id="5678",
        account_type="Organization",
        repository_selection="selected",
        permissions={"issues": "read", "pull_requests": "read"},
        suspended=False,
    )


def _state_from_url(url: str) -> str:
    state = parse_qs(urlsplit(url).query).get("state")
    assert state and len(state) == 1
    return state[0]


async def _prepare_oauth_pending(
    monkeypatch: pytest.MonkeyPatch,
    fixture: _WorkspaceFixture,
) -> _OAuthPreparation:
    conversion = _manifest_conversion(fixture)
    installation = _verified_installation(fixture)

    async def fake_exchange_manifest_code(code: str) -> GitHubManifestConversion:
        assert code == "manifest-code"
        return conversion

    async def fake_get_app_installation(
        *, credential, installation_id: str
    ) -> GitHubVerifiedInstallation:
        assert credential.app_id == fixture.app_id
        assert credential.private_key_pem == PLAIN_PRIVATE_KEY
        assert installation_id == fixture.installation_id
        return installation

    monkeypatch.setattr(
        github_app_setup_provider,
        "exchange_manifest_code",
        fake_exchange_manifest_code,
    )
    monkeypatch.setattr(
        github_app_setup_provider,
        "get_app_installation",
        fake_get_app_installation,
    )

    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]
    async with AsyncSessionLocal() as session:
        manifest_launch = await start_github_app_manifest_setup(
            session,
            workspace_id=fixture.workspace_id,
            actor_user_id=owner.user_id,
            payload=GitHubAppManifestStartInput(
                owner_type="user",
                organization_login=None,
                app_origin=APP_ORIGIN,
            ),
        )
        manifest_result = await complete_github_app_manifest_callback(
            session,
            workspace_id=fixture.workspace_id,
            actor_user_id=owner.user_id,
            state=_state_from_url(manifest_launch.action_url),
            code="manifest-code",
        )
        assert manifest_result.succeeded is True
        install_launch = await launch_github_app_installation(
            session,
            workspace_id=fixture.workspace_id,
            actor_user_id=owner.user_id,
        )
        oauth_launch = await begin_github_app_oauth_from_installation(
            session,
            workspace_id=fixture.workspace_id,
            actor_user_id=owner.user_id,
            installation_id=fixture.installation_id,
            state=_state_from_url(install_launch.redirect_url),
        )
        assert oauth_launch.succeeded is True
        assert oauth_launch.redirect_url is not None
        await session.commit()

    return _OAuthPreparation(
        oauth_state=_state_from_url(oauth_launch.redirect_url),
        authorization_url=oauth_launch.redirect_url,
        installation=installation,
    )


def test_github_app_models_are_registered_in_alembic_metadata() -> None:
    assert {
        "github_app_credentials",
        "github_app_installations",
        "github_app_setup_sessions",
    } <= set(Base.metadata.tables)


def test_github_app_permissions_require_both_read_capabilities() -> None:
    github_app_setup_provider.ensure_read_only_permissions(
        {"issues": "read", "pull_requests": "read", "metadata": "read"}
    )
    for permissions in (
        {},
        {"issues": "read"},
        {"issues": "read", "pull_requests": "write"},
        {"issues": "read", "pull_requests": "read", "contents": "read"},
    ):
        with pytest.raises(
            github_app_setup_provider.GitHubAppSetupProviderError,
            match="github_app_permissions_not_read_only",
        ):
            github_app_setup_provider.ensure_read_only_permissions(permissions)


def test_github_app_urls_require_exact_canonical_paths() -> None:
    valid_app_url = "https://github.com/apps/founderos-test"
    assert github_app_setup_provider._safe_github_url(valid_app_url) == valid_app_url
    assert github_app_credential_service._safe_github_url(valid_app_url) == valid_app_url
    assert (
        github_app_setup_provider._safe_github_url(
            valid_app_url,
            expected_slug="FounderOS-Test",
        )
        == valid_app_url
    )
    assert (
        github_app_credential_service._safe_github_url(
            valid_app_url,
            expected_slug="FounderOS-Test",
        )
        == valid_app_url
    )

    invalid_app_urls = (
        None,
        "",
        " https://github.com/apps/founderos-test",
        "https://github.com/apps/founderos-test ",
        "http://github.com/apps/founderos-test",
        "https://GITHUB.com/apps/founderos-test",
        "https://github.com:443/apps/founderos-test",
        "https://github.com:444/apps/founderos-test",
        "https://github.com.evil.example/apps/founderos-test",
        "https://evil.example/github.com/apps/founderos-test",
        "https://github.com@evil.example/apps/founderos-test",
        "https://user:password@github.com/apps/founderos-test",
        "https://github.com/apps/founderos-test/installations/new",
        "https://github.com/apps/founderos-test/",
        "https://github.com/apps/founderos-test?",
        "https://github.com/apps/founderos-test?token=hidden",
        "https://github.com/apps/founderos-test#",
        "https://github.com/apps/founderos-test#fragment",
        "https://github.com/apps/founderos-test\\@evil.example",
        "https://github.com/apps/founderos test",
        "https://github.com/apps/founderos-test\x00hidden",
        "https://github.com/apps/founderos-test\n.evil.example",
        "https://github.com/apps/founderos%2Ftest",
        "https://github.com/apps/",
        f"https://github.com/apps/{'a' * 121}",
        f"https://github.com/apps/{'a' * 1000}",
    )
    for invalid in invalid_app_urls:
        assert github_app_setup_provider._safe_github_url(invalid) is None
        assert github_app_credential_service._safe_github_url(invalid) is None
    assert (
        github_app_setup_provider._safe_github_url(
            valid_app_url,
            expected_slug="different-app",
        )
        is None
    )
    assert (
        github_app_credential_service._safe_github_url(
            valid_app_url,
            expected_slug="different-app",
        )
        is None
    )

    valid_repository_url = "https://github.com/founderos-test/alpha"
    assert (
        github_app_setup_service._safe_github_repository_url(
            valid_repository_url,
            expected_full_name="FounderOS-Test/Alpha",
        )
        == valid_repository_url
    )

    invalid_repository_urls = (
        None,
        "",
        " https://github.com/founderos-test/alpha",
        "https://github.com/founderos-test/alpha ",
        "http://github.com/founderos-test/alpha",
        "https://GITHUB.com/founderos-test/alpha",
        "https://github.com:443/founderos-test/alpha",
        "https://github.com:444/founderos-test/alpha",
        "https://github.com.evil.example/founderos-test/alpha",
        "https://evil.example/github.com/founderos-test/alpha",
        "https://github.com@evil.example/founderos-test/alpha",
        "https://user:password@github.com/founderos-test/alpha",
        "https://github.com/founderos-test/alpha/issues/1",
        "https://github.com/founderos-test/alpha/",
        "https://github.com/founderos-test/alpha?",
        "https://github.com/founderos-test/alpha?token=hidden",
        "https://github.com/founderos-test/alpha#",
        "https://github.com/founderos-test/alpha#fragment",
        "https://github.com/founderos-test\\alpha",
        "https://github.com/founderos test/alpha",
        "https://github.com/founderos-test/alpha\x00hidden",
        "https://github.com/founderos-test/alpha\n.evil.example",
        "https://github.com/founderos-test%2Falpha",
        "https://github.com/founderos-test",
        "https://github.com/founderos-test/alpha/extra",
        f"https://github.com/founderos-test/{'a' * 1000}",
    )
    for invalid in invalid_repository_urls:
        assert github_app_setup_service._safe_github_repository_url(invalid) is None

    assert (
        github_app_setup_service._safe_github_repository_url(
            valid_repository_url,
            expected_full_name="founderos-test/beta",
        )
        is None
    )


async def test_provider_requests_use_fixed_github_origin_and_validated_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, str, str]] = []

    class RejectingResponse:
        is_success = False

    class RecordingClient:
        def __init__(self, *, base_url: str, timeout: float) -> None:
            requests.append(("CLIENT", base_url, str(timeout)))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, path: str, **_kwargs):
            requests.append(("POST", path, ""))
            return RejectingResponse()

        async def get(self, path: str, **_kwargs):
            requests.append(("GET", path, ""))
            return RejectingResponse()

    monkeypatch.setattr(
        github_app_setup_provider.httpx,
        "AsyncClient",
        RecordingClient,
    )
    monkeypatch.setattr(
        github_app_setup_provider,
        "build_github_app_jwt",
        lambda **_kwargs: "test-jwt",
    )

    with pytest.raises(
        github_app_setup_provider.GitHubAppSetupProviderError,
        match="manifest_exchange_rejected",
    ):
        await github_app_setup_provider.exchange_manifest_code("safe-code")
    with pytest.raises(
        github_app_setup_provider.GitHubAppSetupProviderError,
        match="installation_verification_rejected",
    ):
        await github_app_setup_provider.get_app_installation(
            credential=GitHubAppSigningCredential(
                app_id="12345",
                private_key_pem="not-used-by-test",
            ),
            installation_id="123",
        )

    assert requests == [
        ("CLIENT", "https://api.github.com", "30.0"),
        ("POST", "/app-manifests/safe-code/conversions", ""),
        ("CLIENT", "https://api.github.com", "30.0"),
        ("GET", "/app/installations/123", ""),
    ]
    for unsafe_code in (
        "safe-code/../../metadata",
        "safe-code%2Fmetadata",
        "https://attacker.example.test",
    ):
        with pytest.raises(
            github_app_setup_provider.GitHubAppSetupProviderError,
            match="manifest_code_invalid",
        ):
            await github_app_setup_provider.exchange_manifest_code(unsafe_code)


async def test_manifest_is_exact_read_only_and_persists_only_state_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]
    try:
        async with AsyncSessionLocal() as session:
            launch = await start_github_app_manifest_setup(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                payload=GitHubAppManifestStartInput(
                    owner_type="user",
                    organization_login=None,
                    app_origin=APP_ORIGIN,
                ),
            )
            await session.commit()

        manifest = json.loads(launch.manifest)
        assert manifest["public"] is False
        assert manifest["default_events"] == []
        assert manifest["default_permissions"] == {
            "issues": "read",
            "pull_requests": "read",
        }
        assert manifest["request_oauth_on_install"] is False
        assert manifest["setup_on_update"] is False
        assert set(manifest) == {
            "name",
            "url",
            "description",
            "redirect_url",
            "callback_urls",
            "setup_url",
            "public",
            "default_events",
            "default_permissions",
            "request_oauth_on_install",
            "setup_on_update",
        }
        raw_state = _state_from_url(launch.action_url)
        async with AsyncSessionLocal() as session:
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
        assert setup is not None
        assert setup.state_hash is not None
        assert len(setup.state_hash) == 64
        assert setup.state_hash != raw_state
        assert raw_state not in setup.app_origin
        assert setup.encrypted_pkce_verifier is None
    finally:
        await _cleanup_workspace(fixture)


async def test_origin_and_organization_are_strictly_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]
    try:
        assert trusted_github_app_origin(f" {APP_ORIGIN}/ ") == APP_ORIGIN
        for value, code in [
            ("https://attacker.example.test", "app_origin_not_allowed"),
            (f"{APP_ORIGIN}/github", "app_origin_invalid"),
            (f"{APP_ORIGIN}?next=https://attacker.example.test", "app_origin_invalid"),
            ("http://user:pass@127.0.0.1:3000", "app_origin_invalid"),
        ]:
            with pytest.raises(GitHubAppSetupError, match=code):
                trusted_github_app_origin(value)

        async with AsyncSessionLocal() as session:
            with pytest.raises(
                GitHubAppSetupError,
                match="github_organization_login_invalid",
            ):
                await start_github_app_manifest_setup(
                    session,
                    workspace_id=fixture.workspace_id,
                    actor_user_id=owner.user_id,
                    payload=GitHubAppManifestStartInput(
                        owner_type="organization",
                        organization_login="bad/org",
                        app_origin=APP_ORIGIN,
                    ),
                )
            launch = await start_github_app_manifest_setup(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                payload=GitHubAppManifestStartInput(
                    owner_type="organization",
                    organization_login="founderos-test",
                    app_origin=APP_ORIGIN,
                ),
            )
            await session.commit()
        assert (
            urlsplit(launch.action_url).path
            == "/organizations/founderos-test/settings/apps/new"
        )
    finally:
        await _cleanup_workspace(fixture)


async def test_manifest_api_requires_browser_admin_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]
    endpoint = f"/api/v1/workspaces/{fixture.workspace_id}/github/app-setup/manifest"
    payload = {
        "owner_type": "user",
        "organization_login": None,
        "app_origin": APP_ORIGIN,
    }
    try:
        async with _async_client() as client:
            operator = await client.post(
                endpoint,
                headers={"X-FounderOS-API-Key": "test-api-key"},
                params={"owner_email": owner.email},
                json=payload,
            )
        assert operator.status_code == 403
        assert operator.json() == {
            "detail": "browser session required for GitHub App setup"
        }

        async with _async_client() as client:
            operator_status = await client.get(
                f"/api/v1/workspaces/{fixture.workspace_id}/github/app-setup",
                headers={"X-FounderOS-API-Key": "test-api-key"},
                params={"owner_email": owner.email},
            )
        assert operator_status.status_code == 200
        assert operator_status.json()["can_manage"] is False
        assert operator_status.json()["can_restart"] is False
        assert operator_status.json()["installation_settings_url"] is None

        for role in (MEMBERSHIP_ROLE_MEMBER, MEMBERSHIP_ROLE_VIEWER):
            async with _async_client() as client:
                client.cookies.set(
                    settings.session_cookie_name,
                    fixture.actors[role].session_token,
                )
                forbidden = await client.post(endpoint, json=payload)
            assert forbidden.status_code == 403
            assert forbidden.json() == {"detail": "insufficient workspace role"}

        async with _async_client() as client:
            client.cookies.set(
                settings.session_cookie_name,
                fixture.actors[MEMBERSHIP_ROLE_ADMIN].session_token,
            )
            allowed = await client.post(endpoint, json=payload)
        assert allowed.status_code == 201, allowed.text
        assert allowed.json()["phase"] == "manifest_pending"
        assert urlsplit(allowed.json()["action_url"]).netloc == "github.com"
    finally:
        await _cleanup_workspace(fixture)


async def test_manifest_conversion_encrypts_secrets_and_state_is_one_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]
    other_actor = fixture.actors[MEMBERSHIP_ROLE_ADMIN]
    provider_calls = 0

    async def fake_exchange_manifest_code(code: str) -> GitHubManifestConversion:
        nonlocal provider_calls
        assert code == "manifest-code"
        provider_calls += 1
        return _manifest_conversion(fixture)

    monkeypatch.setattr(
        github_app_setup_provider,
        "exchange_manifest_code",
        fake_exchange_manifest_code,
    )
    try:
        async with AsyncSessionLocal() as session:
            launch = await start_github_app_manifest_setup(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                payload=GitHubAppManifestStartInput(
                    owner_type="user",
                    organization_login=None,
                    app_origin=APP_ORIGIN,
                ),
            )
            await session.commit()
        raw_state = _state_from_url(launch.action_url)

        async with AsyncSessionLocal() as session:
            with pytest.raises(
                GitHubAppSetupError,
                match="github_app_setup_state_invalid",
            ):
                await complete_github_app_manifest_callback(
                    session,
                    workspace_id=fixture.workspace_id,
                    actor_user_id=other_actor.user_id,
                    state=raw_state,
                    code="manifest-code",
                )
        assert provider_calls == 0

        async with AsyncSessionLocal() as session:
            with pytest.raises(
                GitHubAppSetupError,
                match="github_app_setup_state_invalid",
            ):
                await complete_github_app_manifest_callback(
                    session,
                    workspace_id=fixture.workspace_id,
                    actor_user_id=owner.user_id,
                    state=raw_state,
                    code="manifest-code",
                    now=launch.expires_at + timedelta(seconds=1),
                )
        assert provider_calls == 0

        async with AsyncSessionLocal() as session:
            result = await complete_github_app_manifest_callback(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                state=raw_state,
                code="manifest-code",
                now=launch.expires_at - timedelta(seconds=1),
            )
            await session.commit()
        assert result.succeeded is True
        assert provider_calls == 1

        async with AsyncSessionLocal() as session:
            credential = await session.scalar(
                select(GitHubAppCredential).where(
                    GitHubAppCredential.workspace_id == fixture.workspace_id
                )
            )
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
        assert credential is not None and setup is not None
        assert credential.encrypted_private_key != PLAIN_PRIVATE_KEY
        assert credential.encrypted_client_secret != PLAIN_CLIENT_SECRET
        assert credential.encrypted_webhook_secret != PLAIN_WEBHOOK_SECRET
        assert decrypt_secret(credential.encrypted_private_key) == PLAIN_PRIVATE_KEY
        assert decrypt_secret(credential.encrypted_client_secret) == PLAIN_CLIENT_SECRET
        assert decrypt_secret(credential.encrypted_webhook_secret or "") == PLAIN_WEBHOOK_SECRET
        assert setup.phase == GITHUB_APP_SETUP_PHASE_INSTALLATION_PENDING
        assert setup.state_hash is None

        async with AsyncSessionLocal() as session:
            with pytest.raises(
                GitHubAppSetupError,
                match="github_app_setup_state_invalid",
            ):
                await complete_github_app_manifest_callback(
                    session,
                    workspace_id=fixture.workspace_id,
                    actor_user_id=owner.user_id,
                    state=raw_state,
                    code="manifest-code",
                )
        assert provider_calls == 1
    finally:
        await _cleanup_workspace(fixture)


async def test_manifest_encryption_failure_does_not_leave_partial_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]

    async def fake_exchange_manifest_code(code: str) -> GitHubManifestConversion:
        assert code == "manifest-code"
        return _manifest_conversion(fixture)

    def fail_encryption(value: str) -> str:
        assert value
        raise SecretEncryptionError("test-only encryption failure detail")

    monkeypatch.setattr(
        github_app_setup_provider,
        "exchange_manifest_code",
        fake_exchange_manifest_code,
    )
    try:
        async with AsyncSessionLocal() as session:
            launch = await start_github_app_manifest_setup(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                payload=GitHubAppManifestStartInput(
                    owner_type="user",
                    organization_login=None,
                    app_origin=APP_ORIGIN,
                ),
            )
            await session.commit()

        monkeypatch.setattr(
            github_app_credential_service,
            "encrypt_secret",
            fail_encryption,
        )
        async with AsyncSessionLocal() as session:
            result = await complete_github_app_manifest_callback(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                state=_state_from_url(launch.action_url),
                code="manifest-code",
            )
            await session.commit()
        assert result.succeeded is False
        assert result.error_code == "manifest_setup_failed"

        async with AsyncSessionLocal() as session:
            credential = await session.scalar(
                select(GitHubAppCredential).where(
                    GitHubAppCredential.workspace_id == fixture.workspace_id
                )
            )
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
        assert credential is None
        assert setup is not None
        assert setup.phase == GITHUB_APP_SETUP_PHASE_FAILED
        assert "encryption failure detail" not in (setup.error_code or "")
    finally:
        await _cleanup_workspace(fixture)


async def test_installation_callback_stores_hashed_oauth_state_and_encrypted_pkce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    try:
        prepared = await _prepare_oauth_pending(monkeypatch, fixture)
        query = parse_qs(urlsplit(prepared.authorization_url).query)
        assert query["code_challenge_method"] == ["S256"]
        assert query["state"] == [prepared.oauth_state]
        assert len(query["code_challenge"][0]) >= 43

        async with AsyncSessionLocal() as session:
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
        assert setup is not None
        assert setup.phase == GITHUB_APP_SETUP_PHASE_OAUTH_PENDING
        assert setup.state_hash is not None
        assert len(setup.state_hash) == 64
        assert setup.state_hash != prepared.oauth_state
        assert setup.encrypted_pkce_verifier is not None
        assert setup.encrypted_pkce_verifier.startswith("fernet:v2:")
        verifier = decrypt_secret(setup.encrypted_pkce_verifier)
        assert 43 <= len(verifier) <= 128
        assert verifier not in prepared.authorization_url
        assert query["code_challenge"][0] != verifier
    finally:
        await _cleanup_workspace(fixture)


async def test_installation_callback_requires_exact_one_time_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]
    provider_calls = 0

    async def fake_exchange_manifest_code(code: str) -> GitHubManifestConversion:
        assert code == "manifest-code"
        return _manifest_conversion(fixture)

    async def fake_get_app_installation(
        *, credential, installation_id: str
    ) -> GitHubVerifiedInstallation:
        nonlocal provider_calls
        assert credential.app_id == fixture.app_id
        assert installation_id == fixture.installation_id
        provider_calls += 1
        return _verified_installation(fixture)

    monkeypatch.setattr(
        github_app_setup_provider,
        "exchange_manifest_code",
        fake_exchange_manifest_code,
    )
    monkeypatch.setattr(
        github_app_setup_provider,
        "get_app_installation",
        fake_get_app_installation,
    )
    try:
        async with AsyncSessionLocal() as session:
            manifest_launch = await start_github_app_manifest_setup(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                payload=GitHubAppManifestStartInput(
                    owner_type="user",
                    organization_login=None,
                    app_origin=APP_ORIGIN,
                ),
            )
            await complete_github_app_manifest_callback(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                state=_state_from_url(manifest_launch.action_url),
                code="manifest-code",
            )
            install_launch = await launch_github_app_installation(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
            )
            await session.commit()
        installation_state = _state_from_url(install_launch.redirect_url)

        for invalid_state in ("", "wrong-state"):
            async with AsyncSessionLocal() as session:
                with pytest.raises(
                    GitHubAppSetupError,
                    match="github_app_setup_state_invalid",
                ):
                    await begin_github_app_oauth_from_installation(
                        session,
                        workspace_id=fixture.workspace_id,
                        actor_user_id=owner.user_id,
                        installation_id=fixture.installation_id,
                        state=invalid_state,
                    )
        assert provider_calls == 0

        async with AsyncSessionLocal() as session:
            result = await begin_github_app_oauth_from_installation(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                installation_id=fixture.installation_id,
                state=installation_state,
            )
            await session.commit()
        assert result.succeeded is True
        assert provider_calls == 1

        async with AsyncSessionLocal() as session:
            with pytest.raises(
                GitHubAppSetupError,
                match="github_app_setup_state_invalid",
            ):
                await begin_github_app_oauth_from_installation(
                    session,
                    workspace_id=fixture.workspace_id,
                    actor_user_id=owner.user_id,
                    installation_id=fixture.installation_id,
                    state=installation_state,
                )
        assert provider_calls == 1
    finally:
        await _cleanup_workspace(fixture)


async def test_spoofed_user_installation_is_rejected_without_token_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]
    try:
        prepared = await _prepare_oauth_pending(monkeypatch, fixture)
        calls = {"exchange": 0, "list": 0, "revoke": 0}

        async def fake_exchange_oauth_code(
            *, credential, code: str, code_verifier: str
        ) -> GitHubOAuthToken:
            assert credential.app_id == fixture.app_id
            assert code == "oauth-code"
            assert 43 <= len(code_verifier) <= 128
            calls["exchange"] += 1
            return GitHubOAuthToken(access_token=OAUTH_ACCESS_TOKEN)

        async def fake_list_user_installations(
            *, access_token: str
        ) -> list[GitHubVerifiedInstallation]:
            assert access_token == OAUTH_ACCESS_TOKEN
            calls["list"] += 1
            return [_verified_installation(fixture, app_id=f"{fixture.app_id}9")]

        async def fake_revoke_oauth_token_best_effort(
            *, credential, access_token: str
        ) -> None:
            assert credential.app_id == fixture.app_id
            assert access_token == OAUTH_ACCESS_TOKEN
            calls["revoke"] += 1

        monkeypatch.setattr(
            github_app_setup_provider,
            "exchange_oauth_code",
            fake_exchange_oauth_code,
        )
        monkeypatch.setattr(
            github_app_setup_provider,
            "list_user_installations",
            fake_list_user_installations,
        )
        monkeypatch.setattr(
            github_app_setup_provider,
            "revoke_oauth_token_best_effort",
            fake_revoke_oauth_token_best_effort,
        )

        async with AsyncSessionLocal() as session:
            result = await complete_github_app_oauth_callback(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                state=prepared.oauth_state,
                code="oauth-code",
            )
            await session.commit()
        assert result.succeeded is False
        assert result.error_code == "installation_not_available_to_user"
        assert calls == {"exchange": 1, "list": 1, "revoke": 1}

        async with AsyncSessionLocal() as session:
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
            connection = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == fixture.workspace_id
                )
            )
            installation = await session.scalar(
                select(GitHubAppInstallation).where(
                    GitHubAppInstallation.workspace_id == fixture.workspace_id
                )
            )
        assert setup is not None
        assert setup.phase == GITHUB_APP_SETUP_PHASE_FAILED
        assert setup.state_hash is None
        assert setup.encrypted_pkce_verifier is None
        assert OAUTH_ACCESS_TOKEN not in json.dumps(setup.repository_inventory)
        assert connection is None
        assert installation is None
    finally:
        await _cleanup_workspace(fixture)


async def test_oauth_denial_cancels_setup_without_provider_call_or_pkce_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]
    try:
        prepared = await _prepare_oauth_pending(monkeypatch, fixture)

        async def fail_provider_call(**_kwargs):
            raise AssertionError("OAuth denial must not call the provider")

        monkeypatch.setattr(
            github_app_setup_provider,
            "exchange_oauth_code",
            fail_provider_call,
        )
        async with _async_client() as client:
            client.cookies.set(settings.session_cookie_name, owner.session_token)
            response = await client.get(
                f"/api/v1/workspaces/{fixture.workspace_id}/github/app-setup/callback/oauth",
                params={
                    "error": "access_denied",
                    "error_description": "untrusted provider text",
                    "state": prepared.oauth_state,
                },
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert (
            response.headers["location"]
            == "/settings/integrations/github#github-setup"
        )
        assert "untrusted provider text" not in response.text
        async with AsyncSessionLocal() as session:
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
        assert setup is not None
        assert setup.phase == "cancelled"
        assert setup.error_code == "oauth_denied"
        assert setup.state_hash is None
        assert setup.encrypted_pkce_verifier is None
        assert setup.cancelled_at is not None
    finally:
        await _cleanup_workspace(fixture)


async def test_oauth_callback_turns_credential_decryption_failure_into_safe_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]
    try:
        prepared = await _prepare_oauth_pending(monkeypatch, fixture)

        async def fail_oauth_credential(*_args, **_kwargs):
            raise SecretEncryptionError("private decryption detail")

        async def fail_provider_call(**_kwargs):
            raise AssertionError("decryption failure must stop before provider call")

        monkeypatch.setattr(
            github_app_setup_service,
            "get_github_app_oauth_credential",
            fail_oauth_credential,
        )
        monkeypatch.setattr(
            github_app_setup_provider,
            "exchange_oauth_code",
            fail_provider_call,
        )

        async with AsyncSessionLocal() as session:
            result = await complete_github_app_oauth_callback(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                state=prepared.oauth_state,
                code="oauth-code",
            )
            await session.commit()

        assert result.succeeded is False
        assert result.error_code == "github_app_secret_storage_unavailable"
        assert "private decryption detail" not in str(result)
        async with AsyncSessionLocal() as session:
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
        assert setup is not None
        assert setup.phase == GITHUB_APP_SETUP_PHASE_FAILED
        assert setup.state_hash is None
        assert setup.encrypted_pkce_verifier is None
    finally:
        await _cleanup_workspace(fixture)


async def test_installation_verification_normalizes_invalid_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = GitHubAppSigningCredential(
        app_id="12345",
        private_key_pem="invalid-private-key",
    )

    def fail_jwt(**_kwargs):
        raise GitHubAppTokenError("private parser detail")

    monkeypatch.setattr(github_app_setup_provider, "build_github_app_jwt", fail_jwt)
    with pytest.raises(
        github_app_setup_provider.GitHubAppSetupProviderError,
        match="installation_verification_unavailable",
    ):
        await github_app_setup_provider.get_app_installation(
            credential=credential,
            installation_id="123",
        )


async def test_verified_oauth_stays_tokenless_until_nonempty_repository_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch)
    fixture = await _seed_workspace()
    owner = fixture.actors[MEMBERSHIP_ROLE_OWNER]
    admin = fixture.actors[MEMBERSHIP_ROLE_ADMIN]
    viewer = fixture.actors[MEMBERSHIP_ROLE_VIEWER]
    try:
        prepared = await _prepare_oauth_pending(monkeypatch, fixture)
        oauth_calls = {"exchange": 0, "list": 0, "revoke": 0}

        async def fake_exchange_oauth_code(
            *, credential, code: str, code_verifier: str
        ) -> GitHubOAuthToken:
            assert credential.app_id == fixture.app_id
            assert code == "oauth-code"
            assert 43 <= len(code_verifier) <= 128
            oauth_calls["exchange"] += 1
            return GitHubOAuthToken(access_token=OAUTH_ACCESS_TOKEN)

        async def fake_list_user_installations(
            *, access_token: str
        ) -> list[GitHubVerifiedInstallation]:
            assert access_token == OAUTH_ACCESS_TOKEN
            oauth_calls["list"] += 1
            return [prepared.installation]

        async def fake_revoke_oauth_token_best_effort(
            *, credential, access_token: str
        ) -> None:
            assert credential.app_id == fixture.app_id
            assert access_token == OAUTH_ACCESS_TOKEN
            oauth_calls["revoke"] += 1

        monkeypatch.setattr(
            github_app_setup_provider,
            "exchange_oauth_code",
            fake_exchange_oauth_code,
        )
        monkeypatch.setattr(
            github_app_setup_provider,
            "list_user_installations",
            fake_list_user_installations,
        )
        monkeypatch.setattr(
            github_app_setup_provider,
            "revoke_oauth_token_best_effort",
            fake_revoke_oauth_token_best_effort,
        )

        async with AsyncSessionLocal() as session:
            result = await complete_github_app_oauth_callback(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                state=prepared.oauth_state,
                code="oauth-code",
            )
            await session.commit()
        assert result.succeeded is True
        assert oauth_calls == {"exchange": 1, "list": 1, "revoke": 1}

        async with AsyncSessionLocal() as session:
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
            connection = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == fixture.workspace_id
                )
            )
            installation = await session.scalar(
                select(GitHubAppInstallation).where(
                    GitHubAppInstallation.workspace_id == fixture.workspace_id
                )
            )
        assert setup is not None and connection is not None and installation is not None
        assert setup.phase == GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION
        assert setup.state_hash is None
        assert setup.encrypted_pkce_verifier is None
        assert connection.status == INTEGRATION_CONNECTION_STATUS_DISABLED
        assert connection.encrypted_access_token is None
        assert connection.encrypted_refresh_token is None
        assert installation.status == GITHUB_APP_INSTALLATION_STATUS_ACTIVE
        assert installation.verified_by_user_id == owner.user_id
        assert installation.installation_id == fixture.installation_id
        assert OAUTH_ACCESS_TOKEN not in json.dumps(connection.provider_metadata)

        provider_repositories = [
            {
                "id": 101,
                "name": "alpha-ignored",
                "full_name": "founderos-test/alpha",
                "private": True,
                "visibility": "private",
                "archived": False,
                "default_branch": "main",
                "html_url": "https://github.com/founderos-test/alpha",
                "updated_at": "2026-07-14T08:00:00Z",
                "raw_secret": OAUTH_ACCESS_TOKEN,
            },
            {
                "id": 202,
                "full_name": "founderos-test/beta",
                "private": False,
                "visibility": "public",
                "archived": False,
                "default_branch": "trunk",
                "html_url": "https://github.com/founderos-test/beta",
                "updated_at": "2026-07-14T09:00:00Z",
            },
            {
                "id": 303,
                "full_name": "founderos-test/hostile",
                "private": True,
                "visibility": "private",
                "archived": False,
                "default_branch": "main",
                "html_url": (
                    "https://github.com/founderos-test/hostile?token=hidden"
                ),
                "updated_at": "2026-07-14T09:30:00Z",
            },
            {
                "id": 404,
                "full_name": "founderos-test/mismatch",
                "private": True,
                "visibility": "private",
                "archived": False,
                "default_branch": "main",
                "html_url": "https://github.com/founderos-test/different",
                "updated_at": "2026-07-14T09:45:00Z",
            },
        ]
        repository_calls = {"mint": 0, "list": 0}

        async def fake_mint_installation_access_token(
            *, installation_id: str, credential
        ) -> GitHubInstallationAccessToken:
            assert installation_id == fixture.installation_id
            assert credential.app_id == fixture.app_id
            repository_calls["mint"] += 1
            return GitHubInstallationAccessToken(
                token=INSTALLATION_ACCESS_TOKEN,
                expires_at="2026-07-14T10:00:00Z",
            )

        async def fake_list_installation_repositories(
            *, access_token: str, per_page: int = 100, max_pages: int = 10
        ) -> list[dict]:
            assert access_token == INSTALLATION_ACCESS_TOKEN
            assert per_page == 100
            assert max_pages == 10
            repository_calls["list"] += 1
            return provider_repositories

        monkeypatch.setattr(
            github_app_setup_service,
            "mint_installation_access_token",
            fake_mint_installation_access_token,
        )
        monkeypatch.setattr(
            github_app_setup_service.github_repository_client,
            "list_installation_repositories",
            fake_list_installation_repositories,
        )

        async with AsyncSessionLocal() as session:
            inventory = await refresh_github_app_repository_inventory(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
            )
            assert [item["full_name"] for item in inventory] == [
                "founderos-test/alpha",
                "founderos-test/beta",
                "founderos-test/hostile",
                "founderos-test/mismatch",
            ]
            assert all("raw_secret" not in item for item in inventory)
            assert {
                item["full_name"]: item["source_url"] for item in inventory
            } == {
                "founderos-test/alpha": "https://github.com/founderos-test/alpha",
                "founderos-test/beta": "https://github.com/founderos-test/beta",
                "founderos-test/hostile": None,
                "founderos-test/mismatch": None,
            }
            setup_row = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
            installation_row = await session.scalar(
                select(GitHubAppInstallation).where(
                    GitHubAppInstallation.workspace_id == fixture.workspace_id
                )
            )
            assert setup_row is not None and installation_row is not None
            with pytest.raises(GitHubAppSetupError, match="setup_expired"):
                await finalize_github_app_repositories(
                    session,
                    workspace_id=fixture.workspace_id,
                    actor_user_id=owner.user_id,
                    selected_repositories=["founderos-test/alpha"],
                    now=setup_row.expires_at + timedelta(seconds=1),
                )
            installation_row.status = "suspended"
            await session.flush()
            with pytest.raises(
                GitHubAppSetupError,
                match="github_app_installation_not_verified",
            ):
                await finalize_github_app_repositories(
                    session,
                    workspace_id=fixture.workspace_id,
                    actor_user_id=owner.user_id,
                    selected_repositories=["founderos-test/alpha"],
                )
            installation_row.status = GITHUB_APP_INSTALLATION_STATUS_ACTIVE
            await session.flush()
            with pytest.raises(
                GitHubAppSetupError,
                match="repository_selection_required",
            ):
                await finalize_github_app_repositories(
                    session,
                    workspace_id=fixture.workspace_id,
                    actor_user_id=owner.user_id,
                    selected_repositories=[],
                )
            with pytest.raises(
                GitHubAppSetupError,
                match="repository_selection_invalid",
            ):
                await finalize_github_app_repositories(
                    session,
                    workspace_id=fixture.workspace_id,
                    actor_user_id=owner.user_id,
                    selected_repositories=["attacker/not-installed"],
                )
            finalized = await finalize_github_app_repositories(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                selected_repositories=["founderos-test/alpha"],
                now=datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc),
            )
            await session.commit()

        assert repository_calls == {"mint": 1, "list": 1}
        assert finalized["phase"] == "connected"
        assert finalized["selected_repositories"] == ["founderos-test/alpha"]

        async with AsyncSessionLocal() as session:
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
            connection = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == fixture.workspace_id
                )
            )
            repository = await session.scalar(
                select(Repository).where(
                    Repository.workspace_id == fixture.workspace_id
                )
            )
        assert setup is not None and connection is not None and repository is not None
        assert setup.phase == GITHUB_APP_SETUP_PHASE_COMPLETED
        assert [item["full_name"] for item in setup.repository_inventory] == [
            "founderos-test/alpha"
        ]
        assert "founderos-test/beta" not in json.dumps(setup.repository_inventory)
        assert connection.status == INTEGRATION_CONNECTION_STATUS_CONNECTED
        assert connection.provider_metadata["provider_writes_enabled"] is False
        assert connection.provider_metadata["installation_access_token_persisted"] is False
        assert connection.provider_metadata["selected_repositories"] == [
            {
                "id": "101",
                "name": "alpha",
                "full_name": "founderos-test/alpha",
                "private": True,
            }
        ]
        persisted_text = json.dumps(
            {
                "setup_inventory": setup.repository_inventory,
                "connection_metadata": connection.provider_metadata,
                "repository_metadata": repository.repo_metadata,
            }
        )
        assert OAUTH_ACCESS_TOKEN not in persisted_text
        assert INSTALLATION_ACCESS_TOKEN not in persisted_text

        expected_settings_url = (
            "https://github.com/organizations/founderos-test/settings/installations/"
            f"{fixture.installation_id}"
        )
        async with AsyncSessionLocal() as session:
            owner_status = await get_github_app_setup_status(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                can_manage=True,
            )
            viewer_status = await get_github_app_setup_status(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=viewer.user_id,
                can_manage=False,
            )
        assert owner_status["installation_settings_url"] == expected_settings_url
        assert viewer_status["phase"] == "connected"
        assert viewer_status["installation_settings_url"] is None

        async with AsyncSessionLocal() as session:
            installation = await session.scalar(
                select(GitHubAppInstallation).where(
                    GitHubAppInstallation.workspace_id == fixture.workspace_id
                )
            )
            assert installation is not None
            installation.installation_settings_url = (
                "https://github.com/organizations/founderos-test/extra/"
                f"settings/installations/{fixture.installation_id}"
            )
            await session.commit()
        async with AsyncSessionLocal() as session:
            unsafe_url_status = await get_github_app_setup_status(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=admin.user_id,
                can_manage=True,
            )
            installation = await session.scalar(
                select(GitHubAppInstallation).where(
                    GitHubAppInstallation.workspace_id == fixture.workspace_id
                )
            )
            assert installation is not None
            installation.installation_settings_url = expected_settings_url
            await session.commit()
        assert unsafe_url_status["installation_settings_url"] is None

        async with AsyncSessionLocal() as session:
            reconfigured_inventory = await refresh_github_app_repository_inventory(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=admin.user_id,
            )
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
            connection = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == fixture.workspace_id
                )
            )
            assert setup is not None and connection is not None
            assert setup.phase == GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION
            assert setup.created_by_user_id == admin.user_id
            assert connection.status == INTEGRATION_CONNECTION_STATUS_CONNECTED
            assert connection.provider_metadata["provider_reads_enabled"] is True
            assert connection.provider_metadata["selected_repositories"][0][
                "full_name"
            ] == "founderos-test/alpha"
            await session.commit()
        assert len(reconfigured_inventory) == 4
        assert repository_calls == {"mint": 2, "list": 2}

        async with AsyncSessionLocal() as session:
            admin_draft_status = await get_github_app_setup_status(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=admin.user_id,
                can_manage=True,
            )
            owner_live_status = await get_github_app_setup_status(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=owner.user_id,
                can_manage=True,
            )
        assert admin_draft_status["phase"] == GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION
        assert owner_live_status["phase"] == "connected"

        async with AsyncSessionLocal() as session:
            setup = await session.scalar(
                select(GitHubAppSetupSession).where(
                    GitHubAppSetupSession.workspace_id == fixture.workspace_id
                )
            )
            assert setup is not None
            setup.expires_at = datetime(2026, 7, 13, tzinfo=timezone.utc)
            await session.commit()
        async with AsyncSessionLocal() as session:
            expired_draft_status = await get_github_app_setup_status(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=admin.user_id,
                can_manage=True,
            )
            assert expired_draft_status["phase"] == "connected"
            await refresh_github_app_repository_inventory(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=admin.user_id,
            )
            renewed_status = await get_github_app_setup_status(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=admin.user_id,
                can_manage=True,
            )
            assert renewed_status["phase"] == GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION
            await session.commit()
        assert repository_calls == {"mint": 3, "list": 3}

        async with AsyncSessionLocal() as session:
            updated = await finalize_github_app_repositories(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=admin.user_id,
                selected_repositories=["founderos-test/beta"],
            )
            connection = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == fixture.workspace_id
                )
            )
            assert connection is not None
            assert connection.status == INTEGRATION_CONNECTION_STATUS_CONNECTED
            await session.commit()
        assert updated["selected_repositories"] == ["founderos-test/beta"]

        async with AsyncSessionLocal() as session:
            installation = await session.scalar(
                select(GitHubAppInstallation).where(
                    GitHubAppInstallation.workspace_id == fixture.workspace_id
                )
            )
            assert installation is not None
            installation.status = "suspended"
            await session.commit()
        async with AsyncSessionLocal() as session:
            status_payload = await get_github_app_setup_status(
                session,
                workspace_id=fixture.workspace_id,
                actor_user_id=admin.user_id,
                can_manage=True,
            )
        assert status_payload["phase"] == GITHUB_APP_SETUP_PHASE_FAILED
        assert status_payload["installation_verified"] is False
    finally:
        await _cleanup_workspace(fixture)
