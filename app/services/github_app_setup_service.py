from __future__ import annotations

from base64 import urlsafe_b64encode
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
import secrets
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import resolved_cors_allowed_origins, settings
from app.db.canonical_models import Repository, SOURCE_RECORD_PROVIDER_GITHUB
from app.db.identity_models import Workspace
from app.db.integration_models import (
    GITHUB_APP_CREDENTIAL_STATUS_ACTIVE,
    GITHUB_APP_INSTALLATION_STATUS_ACTIVE,
    GITHUB_APP_SETUP_PHASE_CANCELLED,
    GITHUB_APP_SETUP_PHASE_COMPLETED,
    GITHUB_APP_SETUP_PHASE_FAILED,
    GITHUB_APP_SETUP_PHASE_INSTALLATION_PENDING,
    GITHUB_APP_SETUP_PHASE_MANIFEST_EXCHANGING,
    GITHUB_APP_SETUP_PHASE_MANIFEST_PENDING,
    GITHUB_APP_SETUP_PHASE_OAUTH_EXCHANGING,
    GITHUB_APP_SETUP_PHASE_OAUTH_PENDING,
    GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION,
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_DISABLED,
    INTEGRATION_PROVIDER_GITHUB,
    GitHubAppCredential,
    GitHubAppInstallation,
    GitHubAppSetupSession,
    IntegrationConnection,
)
from app.services import github_app_setup_provider, github_repository_client
from app.services.github_app_credential_service import (
    GitHubAppCredentialError,
    GitHubManifestCredentialInput,
    get_active_github_app_credential,
    get_github_app_oauth_credential,
    get_github_app_signing_credential,
    redact_github_app_credential,
    store_manifest_github_app_credential,
    verify_github_app_secret_storage_ready,
)
from app.services.github_app_token_service import (
    GitHubAppTokenError,
    mint_installation_access_token,
)
from app.services.github_connection_service import (
    GITHUB_APP_CONNECTION_METHOD,
    GITHUB_APP_EXTERNAL_ACCOUNT_PREFIX,
    GITHUB_APP_MANAGED_CONNECTION_SOURCE,
)
from app.services.secret_encryption import (
    SecretEncryptionError,
    decrypt_secret,
    encrypt_secret,
)


GITHUB_APP_SETUP_TTL = timedelta(hours=1)
GITHUB_APP_OAUTH_TTL = timedelta(minutes=15)
GITHUB_APP_REPOSITORY_SELECTION_TTL = timedelta(days=1)
GITHUB_APP_MAX_REPOSITORIES = 500
GITHUB_APP_MAX_SELECTED_REPOSITORIES = 100

_ORGANIZATION_LOGIN_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
)
_APP_NAME_PART_RE = re.compile(r"[^A-Za-z0-9-]+")


class GitHubAppSetupError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class GitHubAppManifestStartInput:
    owner_type: str
    organization_login: str | None
    app_origin: str


@dataclass(frozen=True)
class GitHubManifestLaunch:
    phase: str
    action_url: str
    manifest: str
    expires_at: datetime


@dataclass(frozen=True)
class GitHubInstallLaunch:
    phase: str
    redirect_url: str
    expires_at: datetime


@dataclass(frozen=True)
class GitHubCallbackResult:
    succeeded: bool
    error_code: str | None = None
    redirect_url: str | None = None


async def get_github_app_setup_status(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID | None,
    can_manage: bool,
) -> dict[str, Any]:
    credential = await get_active_github_app_credential(
        session,
        workspace_id=workspace_id,
    )
    setup = await session.scalar(
        select(GitHubAppSetupSession).where(
            GitHubAppSetupSession.workspace_id == workspace_id
        )
    )
    installation = await session.scalar(
        select(GitHubAppInstallation).where(
            GitHubAppInstallation.workspace_id == workspace_id
        )
    )
    connection = None
    if installation is not None:
        connection = await session.get(IntegrationConnection, installation.connection_id)

    installation_verified = bool(
        credential is not None
        and installation is not None
        and installation.status == GITHUB_APP_INSTALLATION_STATUS_ACTIVE
        and installation.credential_id == credential.id
        and connection is not None
        and connection.workspace_id == workspace_id
        and connection.provider == INTEGRATION_PROVIDER_GITHUB
        and connection.id == installation.connection_id
    )

    owned_setup = setup is not None and setup.created_by_user_id == actor_user_id
    phase = _public_phase(
        setup=setup,
        installation=installation,
        connection=connection,
        owned_setup=owned_setup,
        installation_verified=installation_verified,
    )
    error_code = setup.error_code if setup is not None and owned_setup else None
    if setup is not None and owned_setup and _expired(setup) and phase not in {
        "connected",
        GITHUB_APP_SETUP_PHASE_COMPLETED,
    }:
        phase = GITHUB_APP_SETUP_PHASE_FAILED
        error_code = "setup_expired"

    repositories = (
        _safe_repository_inventory(setup.repository_inventory)
        if setup is not None and owned_setup
        else []
    )
    selected_repositories = _selected_repositories(connection)
    credential_status = redact_github_app_credential(credential)

    return {
        "phase": phase,
        "credential_source": credential_status["credential_source"],
        "app_slug": credential_status["app_slug"],
        "app_name": credential_status.get("app_name"),
        "installation_account": (
            installation.account_login if installation is not None else None
        ),
        "installation_settings_url": (
            _safe_installation_settings_url(installation.installation_settings_url)
            if can_manage and installation is not None
            else None
        ),
        "repository_count": len(repositories)
        if repositories
        else installation.repository_count
        if installation is not None
        else 0,
        "repositories": repositories,
        "selected_repositories": selected_repositories,
        "expires_at": (
            setup.expires_at if setup is not None and owned_setup else None
        ),
        "error_code": error_code,
        "install_url": (
            _github_install_url(credential.app_slug)
            if credential is not None
            and owned_setup
            and phase
            in {
                GITHUB_APP_SETUP_PHASE_INSTALLATION_PENDING,
                GITHUB_APP_SETUP_PHASE_FAILED,
            }
            else None
        ),
        "can_manage": can_manage,
        "can_restart": bool(can_manage and setup is not None and phase != "connected"),
        "setup_owned_by_current_user": owned_setup,
        "installation_verified": installation_verified,
        "secrets_encrypted": credential is not None,
        "installation_tokens_persisted": False,
        "provider_writes_enabled": False,
    }


async def start_github_app_manifest_setup(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    payload: GitHubAppManifestStartInput,
    now: datetime | None = None,
) -> GitHubManifestLaunch:
    try:
        verify_github_app_secret_storage_ready()
    except (GitHubAppCredentialError, SecretEncryptionError) as exc:
        raise GitHubAppSetupError("github_app_secret_storage_unavailable") from exc
    safe_origin = trusted_github_app_origin(payload.app_origin)
    owner_type, organization_login = _manifest_owner(
        payload.owner_type,
        payload.organization_login,
    )
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise GitHubAppSetupError("workspace_not_found")
    existing_installation = await session.scalar(
        select(GitHubAppInstallation).where(
            GitHubAppInstallation.workspace_id == workspace_id
        )
    )
    if existing_installation is not None:
        raise GitHubAppSetupError("github_app_already_connected")
    existing_credential = await get_active_github_app_credential(
        session,
        workspace_id=workspace_id,
    )
    if existing_credential is not None:
        raise GitHubAppSetupError("github_app_already_created")

    setup = await session.scalar(
        select(GitHubAppSetupSession)
        .where(GitHubAppSetupSession.workspace_id == workspace_id)
        .with_for_update()
    )
    if setup is None:
        setup = GitHubAppSetupSession(
            workspace_id=workspace_id,
            created_by_user_id=actor_user_id,
            phase=GITHUB_APP_SETUP_PHASE_MANIFEST_PENDING,
            app_origin=safe_origin,
            expires_at=_now(now) + GITHUB_APP_SETUP_TTL,
        )
        session.add(setup)

    raw_state = _new_state()
    current_time = _now(now)
    setup.created_by_user_id = actor_user_id
    setup.credential_id = None
    setup.connection_id = None
    setup.phase = GITHUB_APP_SETUP_PHASE_MANIFEST_PENDING
    setup.state_hash = _hash_state(raw_state)
    setup.encrypted_pkce_verifier = None
    setup.app_origin = safe_origin
    setup.installation_id = None
    setup.installation_account_login = None
    setup.installation_account_id = None
    setup.repository_selection = None
    setup.repository_inventory = []
    setup.error_code = None
    setup.expires_at = current_time + GITHUB_APP_SETUP_TTL
    setup.completed_at = None
    setup.cancelled_at = None

    callback_urls = github_app_callback_urls(
        app_origin=safe_origin,
        workspace_id=workspace_id,
    )
    app_name = _manifest_app_name(workspace.slug)
    manifest = {
        "name": app_name,
        "url": f"{safe_origin}/github",
        "description": (
            "FounderOS reads selected repository metadata, issues, and pull requests."
        ),
        "redirect_url": callback_urls["manifest"],
        "callback_urls": [callback_urls["oauth"]],
        "setup_url": callback_urls["installation"],
        "public": False,
        "default_events": [],
        "default_permissions": {
            "issues": "read",
            "pull_requests": "read",
        },
        "request_oauth_on_install": False,
        "setup_on_update": False,
    }
    action_base = (
        "https://github.com/settings/apps/new"
        if owner_type == "user"
        else "https://github.com/organizations/"
        f"{quote(organization_login or '', safe='')}/settings/apps/new"
    )
    action_url = f"{action_base}?{urlencode({'state': raw_state})}"
    await session.flush()
    return GitHubManifestLaunch(
        phase=setup.phase,
        action_url=action_url,
        manifest=json.dumps(manifest, separators=(",", ":"), ensure_ascii=False),
        expires_at=setup.expires_at,
    )


async def complete_github_app_manifest_callback(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    state: str,
    code: str,
    now: datetime | None = None,
) -> GitHubCallbackResult:
    setup = await _claim_setup_state(
        session,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        raw_state=state,
        expected_phase=GITHUB_APP_SETUP_PHASE_MANIFEST_PENDING,
        claimed_phase=GITHUB_APP_SETUP_PHASE_MANIFEST_EXCHANGING,
        now=now,
    )
    try:
        conversion = await github_app_setup_provider.exchange_manifest_code(code)
        callback_url = github_app_callback_urls(
            app_origin=setup.app_origin,
            workspace_id=workspace_id,
        )["oauth"]
        credential = await store_manifest_github_app_credential(
            session,
            workspace_id=workspace_id,
            created_by_user_id=actor_user_id,
            payload=GitHubManifestCredentialInput(
                app_id=conversion.app_id,
                app_slug=conversion.app_slug,
                app_name=conversion.app_name,
                client_id=conversion.client_id,
                private_key_pem=conversion.private_key_pem,
                client_secret=conversion.client_secret,
                webhook_secret=conversion.webhook_secret,
                callback_url=callback_url,
                owner_login=conversion.owner_login,
                owner_id=conversion.owner_id,
                owner_type=conversion.owner_type,
                permissions=conversion.permissions,
                html_url=conversion.html_url,
            ),
        )
    except (
        GitHubAppCredentialError,
        SecretEncryptionError,
        github_app_setup_provider.GitHubAppSetupProviderError,
    ) as exc:
        error_code = getattr(exc, "code", None) or getattr(exc, "detail", None)
        _fail_setup(setup, _safe_error_code(error_code, "manifest_setup_failed"))
        return GitHubCallbackResult(False, error_code=setup.error_code)

    setup.credential_id = credential.id
    setup.phase = GITHUB_APP_SETUP_PHASE_INSTALLATION_PENDING
    setup.error_code = None
    setup.expires_at = _now(now) + GITHUB_APP_SETUP_TTL
    await session.flush()
    return GitHubCallbackResult(True)


async def launch_github_app_installation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    now: datetime | None = None,
) -> GitHubInstallLaunch:
    setup = await _owned_setup_for_update(
        session,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
    )
    credential = await get_active_github_app_credential(
        session,
        workspace_id=workspace_id,
    )
    if setup is None or credential is None:
        raise GitHubAppSetupError("github_app_setup_not_ready")
    if setup.phase not in {
        GITHUB_APP_SETUP_PHASE_INSTALLATION_PENDING,
        GITHUB_APP_SETUP_PHASE_FAILED,
    }:
        raise GitHubAppSetupError("github_app_installation_not_available")
    raw_state = _new_state()
    setup.phase = GITHUB_APP_SETUP_PHASE_INSTALLATION_PENDING
    setup.state_hash = _hash_state(raw_state)
    setup.error_code = None
    setup.expires_at = _now(now) + GITHUB_APP_SETUP_TTL
    await session.flush()
    return GitHubInstallLaunch(
        phase=setup.phase,
        redirect_url=_github_install_url(credential.app_slug, state=raw_state),
        expires_at=setup.expires_at,
    )


async def begin_github_app_oauth_from_installation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    installation_id: str,
    state: str,
    now: datetime | None = None,
) -> GitHubCallbackResult:
    setup = await _owned_setup_for_update(
        session,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
    )
    if (
        setup is None
        or setup.phase != GITHUB_APP_SETUP_PHASE_INSTALLATION_PENDING
        or _expired(setup, now=now)
    ):
        raise GitHubAppSetupError("github_app_setup_state_invalid")
    if setup.state_hash != _hash_state(state):
        raise GitHubAppSetupError("github_app_setup_state_invalid")
    setup.state_hash = None

    try:
        signing = await get_github_app_signing_credential(
            session,
            workspace_id=workspace_id,
        )
        oauth = await get_github_app_oauth_credential(
            session,
            workspace_id=workspace_id,
        )
    except SecretEncryptionError:
        _fail_setup(setup, "github_app_secret_storage_unavailable")
        setup.encrypted_pkce_verifier = None
        return GitHubCallbackResult(False, error_code=setup.error_code)
    if signing is None or oauth is None:
        _fail_setup(setup, "github_app_credentials_unavailable")
        return GitHubCallbackResult(False, error_code=setup.error_code)
    try:
        installation = await github_app_setup_provider.get_app_installation(
            credential=signing,
            installation_id=installation_id,
        )
        if installation.app_id != signing.app_id or installation.suspended:
            raise github_app_setup_provider.GitHubAppSetupProviderError(
                "installation_verification_rejected"
            )
        github_app_setup_provider.ensure_read_only_permissions(
            installation.permissions
        )
    except github_app_setup_provider.GitHubAppSetupProviderError as exc:
        _fail_setup(setup, exc.code)
        return GitHubCallbackResult(False, error_code=setup.error_code)

    verifier = _new_pkce_verifier()
    oauth_state = _new_state()
    setup.installation_id = installation.installation_id
    setup.installation_account_login = installation.account_login
    setup.installation_account_id = installation.account_id
    setup.repository_selection = installation.repository_selection
    try:
        setup.encrypted_pkce_verifier = encrypt_secret(verifier)
    except SecretEncryptionError:
        _fail_setup(setup, "github_app_secret_storage_unavailable")
        return GitHubCallbackResult(False, error_code=setup.error_code)
    setup.state_hash = _hash_state(oauth_state)
    setup.phase = GITHUB_APP_SETUP_PHASE_OAUTH_PENDING
    setup.error_code = None
    setup.expires_at = _now(now) + GITHUB_APP_OAUTH_TTL
    authorization_url = github_app_setup_provider.build_oauth_authorization_url(
        credential=oauth,
        state=oauth_state,
        code_challenge=_pkce_challenge(verifier),
    )
    await session.flush()
    return GitHubCallbackResult(True, redirect_url=authorization_url)


async def complete_github_app_oauth_callback(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    state: str,
    code: str,
    now: datetime | None = None,
) -> GitHubCallbackResult:
    setup = await _claim_setup_state(
        session,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        raw_state=state,
        expected_phase=GITHUB_APP_SETUP_PHASE_OAUTH_PENDING,
        claimed_phase=GITHUB_APP_SETUP_PHASE_OAUTH_EXCHANGING,
        now=now,
    )
    try:
        oauth = await get_github_app_oauth_credential(
            session,
            workspace_id=workspace_id,
        )
    except SecretEncryptionError:
        _fail_setup(setup, "github_app_secret_storage_unavailable")
        setup.encrypted_pkce_verifier = None
        return GitHubCallbackResult(False, error_code=setup.error_code)
    credential_row = await get_active_github_app_credential(
        session,
        workspace_id=workspace_id,
    )
    if (
        oauth is None
        or credential_row is None
        or setup.installation_id is None
        or setup.encrypted_pkce_verifier is None
    ):
        _fail_setup(setup, "github_app_credentials_unavailable")
        return GitHubCallbackResult(False, error_code=setup.error_code)

    token: github_app_setup_provider.GitHubOAuthToken | None = None
    try:
        verifier = decrypt_secret(setup.encrypted_pkce_verifier)
        token = await github_app_setup_provider.exchange_oauth_code(
            credential=oauth,
            code=code,
            code_verifier=verifier,
        )
        user_installations = await github_app_setup_provider.list_user_installations(
            access_token=token.access_token
        )
        verified = github_app_setup_provider.find_verified_user_installation(
            installations=user_installations,
            installation_id=setup.installation_id,
            app_id=credential_row.app_id,
        )
        connection, installation = await _persist_verified_installation(
            session,
            setup=setup,
            credential=credential_row,
            verified=verified,
            actor_user_id=actor_user_id,
            now=now,
        )
    except (
        GitHubAppCredentialError,
        GitHubAppSetupError,
        SecretEncryptionError,
        github_app_setup_provider.GitHubAppSetupProviderError,
    ) as exc:
        error_code = getattr(exc, "code", None) or getattr(exc, "detail", None)
        _fail_setup(setup, _safe_error_code(error_code, "oauth_verification_failed"))
        setup.encrypted_pkce_verifier = None
        return GitHubCallbackResult(False, error_code=setup.error_code)
    finally:
        if token is not None:
            await github_app_setup_provider.revoke_oauth_token_best_effort(
                credential=oauth,
                access_token=token.access_token,
            )

    setup.credential_id = credential_row.id
    setup.connection_id = connection.id
    setup.installation_id = installation.installation_id
    setup.installation_account_login = installation.account_login
    setup.installation_account_id = installation.account_id
    setup.repository_selection = installation.repository_selection
    setup.repository_inventory = []
    setup.encrypted_pkce_verifier = None
    setup.phase = GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION
    setup.error_code = "repository_inventory_pending"
    setup.expires_at = _now(now) + GITHUB_APP_REPOSITORY_SELECTION_TTL
    await session.flush()
    return GitHubCallbackResult(True)


async def cancel_github_app_oauth_callback(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    state: str,
    now: datetime | None = None,
) -> GitHubCallbackResult:
    setup = await _claim_setup_state(
        session,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        raw_state=state,
        expected_phase=GITHUB_APP_SETUP_PHASE_OAUTH_PENDING,
        claimed_phase=GITHUB_APP_SETUP_PHASE_CANCELLED,
        now=now,
    )
    setup.encrypted_pkce_verifier = None
    setup.error_code = "oauth_denied"
    setup.cancelled_at = _now(now)
    setup.expires_at = _now(now) + GITHUB_APP_SETUP_TTL
    await session.flush()
    return GitHubCallbackResult(False, error_code=setup.error_code)


async def refresh_github_app_repository_inventory(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
) -> list[dict[str, Any]]:
    setup = await _repository_setup_for_update(
        session,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
    )
    installation = await session.scalar(
        select(GitHubAppInstallation)
        .where(GitHubAppInstallation.workspace_id == workspace_id)
        .where(GitHubAppInstallation.status == GITHUB_APP_INSTALLATION_STATUS_ACTIVE)
    )
    credential_row = await get_active_github_app_credential(
        session,
        workspace_id=workspace_id,
    )
    if setup is None or installation is None:
        raise GitHubAppSetupError("github_app_installation_not_verified")
    if (
        credential_row is None
        or installation.credential_id != credential_row.id
        or setup.phase
        not in {
            GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION,
            GITHUB_APP_SETUP_PHASE_COMPLETED,
        }
    ):
        raise GitHubAppSetupError("repository_inventory_not_available")
    try:
        signing = await get_github_app_signing_credential(
            session,
            workspace_id=workspace_id,
        )
        if signing is None:
            raise GitHubAppSetupError("github_app_installation_not_verified")
        installation_token = await mint_installation_access_token(
            installation_id=installation.installation_id,
            credential=signing,
        )
        raw_repositories = await github_repository_client.list_installation_repositories(
            access_token=installation_token.token,
        )
    except (
        GitHubAppSetupError,
        GitHubAppTokenError,
        SecretEncryptionError,
        github_repository_client.GitHubRepositoryClientError,
    ) as exc:
        setup.error_code = "repository_inventory_unavailable"
        raise GitHubAppSetupError("repository_inventory_unavailable") from exc

    repositories = _normalize_provider_repositories(raw_repositories)
    if setup.phase == GITHUB_APP_SETUP_PHASE_COMPLETED:
        connection = await session.get(
            IntegrationConnection,
            installation.connection_id,
        )
        if (
            connection is None
            or connection.workspace_id != workspace_id
            or connection.status != INTEGRATION_CONNECTION_STATUS_CONNECTED
            or setup.connection_id != connection.id
        ):
            raise GitHubAppSetupError("github_app_installation_not_verified")
        setup.phase = GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION
        setup.completed_at = None
    setup.repository_inventory = repositories
    setup.error_code = None if repositories else "repository_inventory_empty"
    setup.expires_at = _now() + GITHUB_APP_REPOSITORY_SELECTION_TTL
    installation.repository_count = len(repositories)
    await session.flush()
    return repositories


async def finalize_github_app_repositories(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    selected_repositories: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    setup = await _owned_setup_for_update(
        session,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
    )
    if (
        setup is None
        or setup.phase != GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION
        or _expired(setup, now=now)
    ):
        if setup is not None and _expired(setup, now=now):
            raise GitHubAppSetupError("setup_expired")
        raise GitHubAppSetupError("repository_selection_not_available")
    inventory = _safe_repository_inventory(setup.repository_inventory)
    by_full_name = {repo["full_name"].casefold(): repo for repo in inventory}
    selected = _normalize_selected_repository_names(selected_repositories)
    if not selected:
        raise GitHubAppSetupError("repository_selection_required")
    if len(selected) > GITHUB_APP_MAX_SELECTED_REPOSITORIES:
        raise GitHubAppSetupError("repository_selection_too_large")
    missing = [name for name in selected if name.casefold() not in by_full_name]
    if missing:
        raise GitHubAppSetupError("repository_selection_invalid")

    connection = (
        await session.get(IntegrationConnection, setup.connection_id)
        if setup.connection_id is not None
        else None
    )
    installation = await session.scalar(
        select(GitHubAppInstallation)
        .where(GitHubAppInstallation.workspace_id == workspace_id)
        .where(GitHubAppInstallation.connection_id == setup.connection_id)
        .where(GitHubAppInstallation.status == GITHUB_APP_INSTALLATION_STATUS_ACTIVE)
    )
    credential = (
        await session.get(GitHubAppCredential, setup.credential_id)
        if setup.credential_id is not None
        else None
    )
    if (
        connection is None
        or connection.workspace_id != workspace_id
        or connection.provider != INTEGRATION_PROVIDER_GITHUB
        or connection.status
        not in {
            INTEGRATION_CONNECTION_STATUS_DISABLED,
            INTEGRATION_CONNECTION_STATUS_CONNECTED,
        }
        or _mapping(connection.provider_metadata).get("installation_verified") is not True
        or installation is None
        or installation.installation_id != setup.installation_id
        or credential is None
        or credential.workspace_id != workspace_id
        or credential.status != GITHUB_APP_CREDENTIAL_STATUS_ACTIVE
        or installation.credential_id != credential.id
    ):
        raise GitHubAppSetupError("github_app_installation_not_verified")

    selected_items = [by_full_name[name.casefold()] for name in selected]
    for repository in selected_items:
        await _upsert_setup_repository(
            session,
            workspace_id=workspace_id,
            installation_id=installation.installation_id,
            repository=repository,
        )

    connection.status = INTEGRATION_CONNECTION_STATUS_CONNECTED
    connection.provider_metadata = {
        **_mapping(connection.provider_metadata),
        "connection_method": GITHUB_APP_CONNECTION_METHOD,
        "installation_id": installation.installation_id,
        "installation_verified": True,
        "verification_method": "github_user_installations_pkce",
        "repository_selection": "selected",
        "selected_repositories": [
            {
                "id": item["id"],
                "name": item["name"],
                "full_name": item["full_name"],
                "private": item["private"],
            }
            for item in selected_items
        ],
        "provider_reads_enabled": True,
        "provider_writes_enabled": False,
        "installation_access_token_persisted": False,
        "created_via": GITHUB_APP_MANAGED_CONNECTION_SOURCE,
    }
    connection.last_error = None
    installation.repository_count = len(selected_items)
    setup.repository_inventory = selected_items
    setup.phase = GITHUB_APP_SETUP_PHASE_COMPLETED
    setup.completed_at = _now(now)
    setup.error_code = None
    setup.expires_at = _now(now) + GITHUB_APP_REPOSITORY_SELECTION_TTL
    await session.flush()
    return {
        "phase": "connected",
        "connection_id": str(connection.id),
        "selected_repositories": selected,
        "repository_count": len(selected),
    }


async def restart_github_app_setup(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    now: datetime | None = None,
) -> str:
    setup = await session.scalar(
        select(GitHubAppSetupSession)
        .where(GitHubAppSetupSession.workspace_id == workspace_id)
        .with_for_update()
    )
    credential = await get_active_github_app_credential(
        session,
        workspace_id=workspace_id,
    )
    installation = await session.scalar(
        select(GitHubAppInstallation)
        .where(GitHubAppInstallation.workspace_id == workspace_id)
        .where(GitHubAppInstallation.status == GITHUB_APP_INSTALLATION_STATUS_ACTIVE)
    )
    if setup is None:
        return "not_started"
    setup.created_by_user_id = actor_user_id
    setup.state_hash = None
    setup.encrypted_pkce_verifier = None
    setup.error_code = None
    setup.cancelled_at = None
    setup.expires_at = _now(now) + GITHUB_APP_SETUP_TTL
    connection = (
        await session.get(IntegrationConnection, installation.connection_id)
        if installation is not None
        else None
    )
    if (
        installation is not None
        and credential is not None
        and installation.credential_id == credential.id
        and connection is not None
        and connection.workspace_id == workspace_id
        and connection.status == INTEGRATION_CONNECTION_STATUS_CONNECTED
    ):
        setup.phase = GITHUB_APP_SETUP_PHASE_COMPLETED
        setup.connection_id = installation.connection_id
        return "connected"
    if (
        installation is not None
        and credential is not None
        and installation.credential_id == credential.id
        and connection is not None
        and connection.workspace_id == workspace_id
        and connection.status == INTEGRATION_CONNECTION_STATUS_DISABLED
    ):
        setup.phase = GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION
        setup.connection_id = installation.connection_id
        return setup.phase
    if credential is not None:
        setup.phase = GITHUB_APP_SETUP_PHASE_INSTALLATION_PENDING
        setup.credential_id = credential.id
        setup.installation_id = None
        setup.repository_inventory = []
        return setup.phase
    setup.phase = GITHUB_APP_SETUP_PHASE_CANCELLED
    setup.cancelled_at = _now(now)
    return "not_started"


def trusted_github_app_origin(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
    except (AttributeError, ValueError) as exc:
        raise GitHubAppSetupError("app_origin_invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise GitHubAppSetupError("app_origin_invalid")
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")
    allowed = set(resolved_cors_allowed_origins(settings))
    if origin not in allowed:
        raise GitHubAppSetupError("app_origin_not_allowed")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise GitHubAppSetupError("app_origin_https_required")
    return origin


def github_app_callback_urls(*, app_origin: str, workspace_id: UUID) -> dict[str, str]:
    base = (
        f"{app_origin}/api/v1/workspaces/{workspace_id}/github/app-setup/callback"
    )
    return {
        "manifest": f"{base}/manifest",
        "installation": f"{base}/installation",
        "oauth": f"{base}/oauth",
    }


async def _claim_setup_state(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    raw_state: str,
    expected_phase: str,
    claimed_phase: str,
    now: datetime | None,
) -> GitHubAppSetupSession:
    state_hash = _hash_state(raw_state)
    setup = await session.scalar(
        select(GitHubAppSetupSession)
        .where(GitHubAppSetupSession.workspace_id == workspace_id)
        .where(GitHubAppSetupSession.created_by_user_id == actor_user_id)
        .where(GitHubAppSetupSession.state_hash == state_hash)
        .where(GitHubAppSetupSession.phase == expected_phase)
        .with_for_update()
    )
    if setup is None or _expired(setup, now=now):
        raise GitHubAppSetupError("github_app_setup_state_invalid")
    setup.phase = claimed_phase
    setup.state_hash = None
    await session.flush()
    return setup


async def _owned_setup_for_update(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
) -> GitHubAppSetupSession | None:
    return await session.scalar(
        select(GitHubAppSetupSession)
        .where(GitHubAppSetupSession.workspace_id == workspace_id)
        .where(GitHubAppSetupSession.created_by_user_id == actor_user_id)
        .with_for_update()
    )


async def _repository_setup_for_update(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
) -> GitHubAppSetupSession | None:
    """Lock a repository-selection setup, allowing admin handoff only post-connect."""

    setup = await session.scalar(
        select(GitHubAppSetupSession)
        .where(GitHubAppSetupSession.workspace_id == workspace_id)
        .with_for_update()
    )
    if setup is None or setup.created_by_user_id == actor_user_id:
        return setup
    if setup.phase not in {
        GITHUB_APP_SETUP_PHASE_COMPLETED,
        GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION,
    }:
        return None
    connection = (
        await session.get(IntegrationConnection, setup.connection_id)
        if setup.connection_id is not None
        else None
    )
    if (
        connection is None
        or connection.workspace_id != workspace_id
        or connection.provider != INTEGRATION_PROVIDER_GITHUB
        or connection.status != INTEGRATION_CONNECTION_STATUS_CONNECTED
    ):
        return None
    setup.created_by_user_id = actor_user_id
    return setup


async def _persist_verified_installation(
    session: AsyncSession,
    *,
    setup: GitHubAppSetupSession,
    credential: GitHubAppCredential,
    verified: github_app_setup_provider.GitHubVerifiedInstallation,
    actor_user_id: UUID,
    now: datetime | None,
) -> tuple[IntegrationConnection, GitHubAppInstallation]:
    external_account_id = f"{GITHUB_APP_EXTERNAL_ACCOUNT_PREFIX}{verified.installation_id}"
    conflict = await session.scalar(
        select(GitHubAppInstallation).where(
            GitHubAppInstallation.installation_id == verified.installation_id
        )
    )
    if conflict is not None and conflict.workspace_id != setup.workspace_id:
        raise GitHubAppSetupError("github_app_installation_already_bound")
    connection_conflict = await session.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(IntegrationConnection.external_account_id == external_account_id)
    )
    if (
        connection_conflict is not None
        and connection_conflict.workspace_id != setup.workspace_id
    ):
        raise GitHubAppSetupError("github_app_installation_already_bound")

    connection = await session.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.workspace_id == setup.workspace_id)
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(IntegrationConnection.external_account_id == external_account_id)
    )
    if connection is None:
        connection = IntegrationConnection(
            workspace_id=setup.workspace_id,
            provider=INTEGRATION_PROVIDER_GITHUB,
            external_account_id=external_account_id,
        )
        session.add(connection)
    connection.status = INTEGRATION_CONNECTION_STATUS_DISABLED
    connection.display_name = f"GitHub App: {verified.account_login}"
    connection.scopes = ["github_app_installation", "read_only"]
    connection.encrypted_access_token = None
    connection.encrypted_refresh_token = None
    connection.token_expires_at = None
    connection.provider_metadata = {
        "connection_method": GITHUB_APP_CONNECTION_METHOD,
        "installation_id": verified.installation_id,
        "installation_verified": True,
        "verification_method": "github_user_installations_pkce",
        "repository_selection": verified.repository_selection,
        "selected_repositories": [],
        "provider_reads_enabled": False,
        "provider_writes_enabled": False,
        "installation_access_token_persisted": False,
        "created_via": GITHUB_APP_MANAGED_CONNECTION_SOURCE,
    }
    connection.last_error = None
    await session.flush()

    installation = conflict
    if installation is None:
        installation = await session.scalar(
            select(GitHubAppInstallation).where(
                GitHubAppInstallation.workspace_id == setup.workspace_id
            )
        )
    if installation is None:
        installation = GitHubAppInstallation(
            workspace_id=setup.workspace_id,
            credential_id=credential.id,
            connection_id=connection.id,
            installation_id=verified.installation_id,
            account_login=verified.account_login,
            repository_selection=verified.repository_selection,
            verified_at=_now(now),
        )
        session.add(installation)
    installation.credential_id = credential.id
    installation.connection_id = connection.id
    installation.installation_id = verified.installation_id
    installation.account_login = verified.account_login
    installation.account_id = verified.account_id
    installation.account_type = verified.account_type
    installation.repository_selection = verified.repository_selection
    installation.permissions = verified.permissions
    installation.installation_settings_url = _installation_settings_url(verified)
    installation.verified_by_user_id = actor_user_id
    installation.verified_at = _now(now)
    installation.status = GITHUB_APP_INSTALLATION_STATUS_ACTIVE
    await session.flush()
    return connection, installation


async def _upsert_setup_repository(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    installation_id: str,
    repository: Mapping[str, Any],
) -> Repository:
    external_id = str(repository["id"])
    full_name = str(repository["full_name"])
    row = await session.scalar(
        select(Repository)
        .where(Repository.workspace_id == workspace_id)
        .where(Repository.provider == SOURCE_RECORD_PROVIDER_GITHUB)
        .where(
            or_(
                Repository.external_id == external_id,
                Repository.full_name == full_name,
            )
        )
    )
    if row is None:
        row = Repository(
            workspace_id=workspace_id,
            provider=SOURCE_RECORD_PROVIDER_GITHUB,
            external_id=external_id,
            name=str(repository["name"]),
            full_name=full_name,
        )
        session.add(row)
    row.external_id = external_id
    row.name = str(repository["name"])
    row.full_name = full_name
    row.default_branch = _safe_text(repository.get("default_branch"), 255)
    row.visibility = str(repository["visibility"])
    row.archived = bool(repository["archived"])
    row.source_url = _safe_github_repository_url(repository.get("source_url"))
    row.repo_metadata = {
        "source": "github_app_setup",
        "installation_id": installation_id,
        "selected": True,
    }
    row.last_activity_at = _parse_provider_datetime(repository.get("last_activity_at"))
    await session.flush()
    return row


def _normalize_provider_repositories(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value[:GITHUB_APP_MAX_REPOSITORIES]:
        full_name = _safe_repository_full_name(raw.get("full_name"))
        identifier = _safe_identifier(raw.get("id"))
        if full_name is None or identifier is None or full_name.casefold() in seen:
            continue
        visibility = raw.get("visibility")
        if visibility not in {"public", "private", "internal"}:
            visibility = "private" if raw.get("private") is True else "public"
        normalized.append(
            {
                "id": identifier,
                "name": full_name.rsplit("/", 1)[-1],
                "full_name": full_name,
                "private": bool(raw.get("private")),
                "visibility": visibility,
                "archived": bool(raw.get("archived")),
                "default_branch": _safe_text(raw.get("default_branch"), 255),
                "source_url": _safe_github_repository_url(
                    raw.get("source_url") or raw.get("html_url")
                ),
                "last_activity_at": _safe_datetime_text(
                    raw.get("last_activity_at") or raw.get("updated_at")
                ),
            }
        )
        seen.add(full_name.casefold())
    return sorted(normalized, key=lambda item: item["full_name"].casefold())


def _safe_repository_inventory(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return _normalize_provider_repositories(
        [dict(item) for item in value if isinstance(item, Mapping)]
    )


def _selected_repositories(connection: IntegrationConnection | None) -> list[str]:
    if connection is None:
        return []
    metadata = _mapping(connection.provider_metadata)
    value = metadata.get("selected_repositories")
    if not isinstance(value, list):
        return []
    selected: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            full_name = _safe_repository_full_name(item.get("full_name"))
            if full_name:
                selected.append(full_name)
    return selected


def _public_phase(
    *,
    setup: GitHubAppSetupSession | None,
    installation: GitHubAppInstallation | None,
    connection: IntegrationConnection | None,
    owned_setup: bool,
    installation_verified: bool,
) -> str:
    if (
        installation_verified
        and installation is not None
        and connection is not None
        and connection.status == INTEGRATION_CONNECTION_STATUS_CONNECTED
        and setup is not None
        and owned_setup
        and setup.phase == GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION
        and not _expired(setup)
    ):
        return GITHUB_APP_SETUP_PHASE_REPOSITORY_SELECTION
    if (
        installation_verified
        and installation is not None
        and connection is not None
        and connection.status == INTEGRATION_CONNECTION_STATUS_CONNECTED
    ):
        return "connected"
    if setup is None:
        return "not_started"
    if not owned_setup and setup.phase not in {
        GITHUB_APP_SETUP_PHASE_COMPLETED,
        GITHUB_APP_SETUP_PHASE_CANCELLED,
    }:
        return "manifest_pending"
    if setup.phase == GITHUB_APP_SETUP_PHASE_COMPLETED:
        return GITHUB_APP_SETUP_PHASE_FAILED
    if setup.phase == GITHUB_APP_SETUP_PHASE_CANCELLED:
        return GITHUB_APP_SETUP_PHASE_CANCELLED if owned_setup else "not_started"
    return setup.phase


def _manifest_owner(
    owner_type: str,
    organization_login: str | None,
) -> tuple[str, str | None]:
    if owner_type == "user":
        return owner_type, None
    if owner_type != "organization":
        raise GitHubAppSetupError("github_app_owner_type_invalid")
    login = _safe_text(organization_login, 39)
    if login is None or _ORGANIZATION_LOGIN_RE.fullmatch(login) is None:
        raise GitHubAppSetupError("github_organization_login_invalid")
    return owner_type, login


def _manifest_app_name(workspace_slug: str) -> str:
    safe_slug = _APP_NAME_PART_RE.sub("-", workspace_slug).strip("-") or "workspace"
    return f"FounderOS-{safe_slug[:14]}-{secrets.token_hex(3)}"[:34]


def _github_install_url(app_slug: str, *, state: str | None = None) -> str:
    base = f"https://github.com/apps/{quote(app_slug, safe='-')}/installations/new"
    return f"{base}?{urlencode({'state': state})}" if state else base


def _installation_settings_url(
    installation: github_app_setup_provider.GitHubVerifiedInstallation,
) -> str:
    if (installation.account_type or "").casefold() == "organization":
        return (
            "https://github.com/organizations/"
            f"{quote(installation.account_login, safe='-')}/settings/installations/"
            f"{installation.installation_id}"
        )
    return f"https://github.com/settings/installations/{installation.installation_id}"


def _normalize_selected_repository_names(value: list[str]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for raw in value:
        full_name = _safe_repository_full_name(raw)
        if full_name and full_name.casefold() not in seen:
            selected.append(full_name)
            seen.add(full_name.casefold())
    return selected


def _safe_repository_full_name(value: Any) -> str | None:
    text = _safe_text(value, 500)
    if text is None or text.count("/") != 1:
        return None
    owner, name = text.split("/", 1)
    if not owner or not name or any(part in {".", ".."} for part in (owner, name)):
        return None
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in (owner, name)):
        return None
    return text


def _safe_github_repository_url(value: Any) -> str | None:
    text = _safe_text(value, 1000)
    if text is None:
        return None
    parsed = urlsplit(text)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or "@" in text:
        return None
    return text


def _safe_installation_settings_url(value: Any) -> str | None:
    text = _safe_text(value, 1000)
    if text is None:
        return None
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    parts = parsed.path.rstrip("/").strip("/").split("/")
    personal_path = (
        len(parts) == 3
        and parts[:2] == ["settings", "installations"]
        and parts[2].isdigit()
    )
    organization_path = (
        len(parts) == 5
        and parts[0] == "organizations"
        and _ORGANIZATION_LOGIN_RE.fullmatch(parts[1]) is not None
        and parts[2:4] == ["settings", "installations"]
        and parts[4].isdigit()
    )
    if not personal_path and not organization_path:
        return None
    return text


def _safe_datetime_text(value: Any) -> str | None:
    text = _safe_text(value, 100)
    if text is None:
        return None
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return text


def _parse_provider_datetime(value: Any) -> datetime | None:
    text = _safe_datetime_text(value)
    if text is None:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _safe_identifier(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    text = _safe_text(value, 100)
    return text if text and text.isdigit() else None


def _safe_text(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:max_length]


def _safe_error_code(value: Any, fallback: str) -> str:
    text = _safe_text(value, 120)
    if text and re.fullmatch(r"[a-z0-9_]+", text):
        return text
    return fallback


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _fail_setup(setup: GitHubAppSetupSession, error_code: str) -> None:
    setup.phase = GITHUB_APP_SETUP_PHASE_FAILED
    setup.state_hash = None
    setup.error_code = _safe_error_code(error_code, "github_app_setup_failed")


def _new_state() -> str:
    return secrets.token_urlsafe(32)


def _hash_state(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise GitHubAppSetupError("github_app_setup_state_invalid")
    return sha256(value.encode("utf-8")).hexdigest()


def _new_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def _pkce_challenge(verifier: str) -> str:
    return urlsafe_b64encode(sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode(
        "ascii"
    )


def _now(value: datetime | None = None) -> datetime:
    return value or datetime.now(timezone.utc)


def _expired(
    setup: GitHubAppSetupSession,
    *,
    now: datetime | None = None,
) -> bool:
    return setup.expires_at <= _now(now)
