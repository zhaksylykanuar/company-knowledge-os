from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.integration_models import (
    GITHUB_APP_CREDENTIAL_STATUS_ACTIVE,
    GITHUB_APP_INSTALLATION_STATUS_ACTIVE,
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_DISABLED,
    INTEGRATION_CONNECTION_STATUS_ERROR,
    INTEGRATION_CONNECTION_STATUS_REVOKED,
    INTEGRATION_PROVIDER_GITHUB,
    GitHubAppCredential,
    GitHubAppInstallation,
    IntegrationConnection,
)
from app.services.github_app_credential_service import redact_github_app_credential
from app.services.secret_encryption import encrypt_secret

GITHUB_CONNECTION_PROVIDER = INTEGRATION_PROVIDER_GITHUB
GITHUB_CONNECTION_STATUS_LOCAL_BRIDGE_ONLY = "local_bridge_only"
GITHUB_CONNECTION_STATUS_NOT_CONNECTED = "not_connected"
GITHUB_APP_CONNECTION_METHOD = "github_app_installation"
GITHUB_APP_MANAGED_CONNECTION_SOURCE = "founderos_self_service"
GITHUB_APP_EXTERNAL_ACCOUNT_PREFIX = "github_app_installation:"
GITHUB_APP_TOKEN_WARNING = (
    "GitHub App installation uses just-in-time installation tokens; no installation access token is persisted."
)
GITHUB_PROVIDER_TOKEN_CONNECTION_METHOD = "manual_provider_token"
GITHUB_REPOSITORY_READ_SOURCE_LOCAL_BRIDGE = "local_bridge"
GITHUB_REPOSITORY_READ_SOURCE_INTEGRATION_CONNECTION = "integration_connection"

_STATUS_PRIORITY = {
    INTEGRATION_CONNECTION_STATUS_CONNECTED: 0,
    INTEGRATION_CONNECTION_STATUS_ERROR: 1,
    INTEGRATION_CONNECTION_STATUS_REVOKED: 2,
    INTEGRATION_CONNECTION_STATUS_DISABLED: 3,
}
_SENSITIVE_METADATA_KEY_MARKERS = (
    "api_key",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
    "webhook",
)
_SAFE_METADATA_KEYS = {"installation_access_token_persisted", "token_validated"}
GITHUB_PROVIDER_TOKEN_WARNING = (
    "GitHub token is stored for future sync but was not validated with GitHub in this step."
)
@dataclass(frozen=True, repr=False)
class GitHubProviderTokenConnectionInput:
    access_token: str
    display_name: str | None = None
    external_account_id: str | None = None
    scopes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


async def list_github_connections(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(IntegrationConnection)
            .where(IntegrationConnection.workspace_id == workspace_id)
            .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
            .order_by(IntegrationConnection.created_at.desc())
        )
    ).scalars()
    return [redact_connection(connection) for connection in rows]


async def get_github_connection(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection_id: UUID,
) -> dict[str, Any] | None:
    connection = await session.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.workspace_id == workspace_id)
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(IntegrationConnection.id == connection_id)
    )
    if connection is None:
        return None
    return redact_connection(connection)


async def get_github_connection_status(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    connections = await list_github_connections(session, workspace_id=workspace_id)
    managed_credential = await _get_workspace_github_app_credential(
        session,
        workspace_id=workspace_id,
    )
    verified_installation, verified_connection = (
        await _get_verified_github_app_installation_connection(
            session,
            workspace_id=workspace_id,
        )
    )
    selected = (
        redact_connection(verified_connection)
        if verified_connection is not None
        else _select_status_connection(connections)
    )
    warnings: list[str] = []
    app_config = _workspace_github_app_config(managed_credential)

    if selected is None:
        return {
            "provider": INTEGRATION_PROVIDER_GITHUB,
            "status": GITHUB_CONNECTION_STATUS_LOCAL_BRIDGE_ONLY,
            "connection_method": None,
            "connection_id": None,
            "display_name": None,
            "last_sync_at": None,
            "last_error": None,
            "has_connection_record": False,
            "has_valid_token_record": False,
            "installation_verified": False,
            "live_read_available": False,
            "selected_repositories": [],
            "repository_read_available": True,
            "repository_read_source": GITHUB_REPOSITORY_READ_SOURCE_LOCAL_BRIDGE,
            "is_live": False,
            "app": app_config,
            "warnings": [
                "no GitHub IntegrationConnection exists; repository read uses local bridge only"
            ],
        }

    connection_method = _connection_method(selected)
    is_app_installation = connection_method == GITHUB_APP_CONNECTION_METHOD
    managed_installation_verified = bool(
        is_app_installation
        and verified_installation is not None
        and verified_connection is not None
        and selected["id"] == verified_connection.id
        and managed_credential is not None
        and managed_credential.status == GITHUB_APP_CREDENTIAL_STATUS_ACTIVE
        and verified_installation.credential_id == managed_credential.id
    )
    legacy_installation_verified = bool(
        is_app_installation
        and managed_credential is None
        and not _metadata_matches(
            selected,
            "created_via",
            GITHUB_APP_MANAGED_CONNECTION_SOURCE,
        )
        and _metadata_bool(selected, "installation_verified")
    )
    installation_verified = (
        managed_installation_verified or legacy_installation_verified
    )
    has_valid_token_record = (
        selected["status"] == INTEGRATION_CONNECTION_STATUS_CONNECTED
        and bool(selected["has_access_token"])
    )
    jit_live_read_available = bool(
        selected["status"] == INTEGRATION_CONNECTION_STATUS_CONNECTED
        and is_app_installation
        and installation_verified
        and app_config["configured"]
        and (
            managed_credential is None
            or _metadata_bool(selected, "provider_reads_enabled")
        )
    )
    live_read_available = has_valid_token_record or jit_live_read_available
    selected_repositories = (
        _selected_repository_full_names(
            verified_connection.provider_metadata
            if managed_installation_verified and verified_connection is not None
            else selected.get("metadata")
        )
        if is_app_installation
        else []
    )
    if (
        selected["status"] == INTEGRATION_CONNECTION_STATUS_CONNECTED
        and not selected["has_access_token"]
        and is_app_installation
    ):
        if installation_verified:
            warnings.append(GITHUB_APP_TOKEN_WARNING)
        else:
            warnings.append(
                "GitHub App installation is not provider-verified; live read is disabled"
            )
    elif selected["status"] == INTEGRATION_CONNECTION_STATUS_CONNECTED and not selected[
        "has_access_token"
    ]:
        warnings.append(
            "GitHub connection record is connected but has no encrypted access token record"
        )
    if selected["status"] != INTEGRATION_CONNECTION_STATUS_CONNECTED:
        warnings.append(
            f"GitHub connection status is {selected['status']}; live provider readiness is not implied"
        )

    repository_read_source = (
        GITHUB_REPOSITORY_READ_SOURCE_INTEGRATION_CONNECTION
        if live_read_available
        else GITHUB_REPOSITORY_READ_SOURCE_LOCAL_BRIDGE
    )
    return {
        "provider": INTEGRATION_PROVIDER_GITHUB,
        "status": selected["status"],
        "connection_method": connection_method,
        "connection_id": selected["id"],
        "display_name": selected["display_name"],
        "last_sync_at": selected["last_sync_at"],
        "last_error": selected["last_error"],
        "has_connection_record": True,
        "has_valid_token_record": has_valid_token_record,
        "installation_verified": installation_verified,
        "live_read_available": live_read_available,
        "selected_repositories": selected_repositories,
        "repository_read_available": True,
        "repository_read_source": repository_read_source,
        "is_live": False,
        "app": app_config,
        "warnings": warnings,
    }


async def create_or_update_github_provider_token_connection(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    payload: GitHubProviderTokenConnectionInput,
) -> dict[str, Any]:
    connection = await _find_provider_token_connection(
        session,
        workspace_id=workspace_id,
        external_account_id=payload.external_account_id,
    )
    encrypted_access_token = encrypt_secret(payload.access_token)
    provider_metadata = _provider_token_metadata(
        user_metadata=payload.metadata,
        plaintext_token=payload.access_token,
    )
    if connection is None:
        connection = IntegrationConnection(
            workspace_id=workspace_id,
            provider=INTEGRATION_PROVIDER_GITHUB,
        )
        session.add(connection)

    connection.status = INTEGRATION_CONNECTION_STATUS_CONNECTED
    connection.display_name = payload.display_name or "GitHub manual connection"
    connection.external_account_id = payload.external_account_id
    connection.scopes = _safe_scopes(payload.scopes)
    connection.encrypted_access_token = encrypted_access_token
    connection.encrypted_refresh_token = None
    connection.token_expires_at = None
    connection.provider_metadata = provider_metadata
    connection.last_error = None
    await session.flush()
    await session.refresh(connection)
    return redact_connection(connection)


def redact_connection(connection: IntegrationConnection) -> dict[str, Any]:
    return {
        "id": connection.id,
        "provider": connection.provider,
        "status": connection.status,
        "display_name": connection.display_name,
        "external_account_id": connection.external_account_id,
        "scopes": list(connection.scopes or []),
        "token_expires_at": connection.token_expires_at,
        "last_sync_at": connection.last_sync_at,
        "last_error": connection.last_error,
        "has_access_token": bool(connection.encrypted_access_token),
        "has_refresh_token": bool(connection.encrypted_refresh_token),
        "connection_method": _metadata_connection_method(connection.provider_metadata),
        "metadata": _redact_metadata(connection.provider_metadata),
        "created_at": connection.created_at,
        "updated_at": connection.updated_at,
    }


async def _find_provider_token_connection(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    external_account_id: str | None,
) -> IntegrationConnection | None:
    base_query = (
        select(IntegrationConnection)
        .where(IntegrationConnection.workspace_id == workspace_id)
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
    )
    if external_account_id:
        return await session.scalar(
            base_query.where(IntegrationConnection.external_account_id == external_account_id)
        )

    rows = (
        await session.execute(
            base_query.where(IntegrationConnection.external_account_id.is_(None))
        )
    ).scalars()
    manual_connections = [
        connection
        for connection in rows
        if isinstance(connection.provider_metadata, Mapping)
        and connection.provider_metadata.get("connection_method")
        == GITHUB_PROVIDER_TOKEN_CONNECTION_METHOD
    ]
    if len(manual_connections) == 1:
        return manual_connections[0]
    return None


def _select_status_connection(
    connections: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not connections:
        return None
    for status, _priority in sorted(
        _STATUS_PRIORITY.items(),
        key=lambda item: item[1],
    ):
        for connection in connections:
            if connection["status"] == status:
                return connection
    return connections[0]


async def _get_workspace_github_app_credential(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> GitHubAppCredential | None:
    return await session.scalar(
        select(GitHubAppCredential).where(
            GitHubAppCredential.workspace_id == workspace_id
        )
    )


async def _get_verified_github_app_installation_connection(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> tuple[GitHubAppInstallation | None, IntegrationConnection | None]:
    installation = await session.scalar(
        select(GitHubAppInstallation)
        .where(GitHubAppInstallation.workspace_id == workspace_id)
        .where(GitHubAppInstallation.status == GITHUB_APP_INSTALLATION_STATUS_ACTIVE)
        .order_by(GitHubAppInstallation.verified_at.desc())
    )
    if installation is None:
        return None, None
    connection = await session.get(IntegrationConnection, installation.connection_id)
    if (
        connection is None
        or connection.workspace_id != workspace_id
        or connection.provider != INTEGRATION_PROVIDER_GITHUB
        or _metadata_connection_method(connection.provider_metadata)
        != GITHUB_APP_CONNECTION_METHOD
    ):
        return None, None
    return installation, connection


def _metadata_bool(connection: Mapping[str, Any], key: str) -> bool:
    metadata = connection.get("metadata")
    return isinstance(metadata, Mapping) and metadata.get(key) is True


def _metadata_matches(
    connection: Mapping[str, Any],
    key: str,
    expected: str,
) -> bool:
    metadata = connection.get("metadata")
    return isinstance(metadata, Mapping) and metadata.get(key) == expected


def _selected_repository_full_names(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    raw_repositories = value.get("selected_repositories")
    if not isinstance(raw_repositories, list):
        return []
    selected: list[str] = []
    seen: set[str] = set()
    for item in raw_repositories[:100]:
        raw_full_name = item.get("full_name") if isinstance(item, Mapping) else item
        if not isinstance(raw_full_name, str):
            continue
        full_name = raw_full_name.strip()[:255]
        folded = full_name.casefold()
        if full_name.count("/") != 1 or not full_name or folded in seen:
            continue
        selected.append(full_name)
        seen.add(folded)
    return selected


def _connection_method(connection: Mapping[str, Any]) -> str | None:
    raw_method = connection.get("connection_method")
    return raw_method if isinstance(raw_method, str) and raw_method else None


def _metadata_connection_method(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return None
    raw_method = value.get("connection_method")
    return raw_method if isinstance(raw_method, str) and raw_method else None


def _redact_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): _redact_metadata_value(raw_value)
        for key, raw_value in value.items()
        if isinstance(key, str) and not _metadata_key_is_sensitive(key)
    }


def _redact_metadata_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _redact_metadata(value)
    if isinstance(value, list):
        return [_redact_metadata_value(item) for item in value[:20]]
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, bool | int | float) or value is None:
        return value
    return str(value)[:500]


def _metadata_key_is_sensitive(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    if normalized in _SAFE_METADATA_KEYS:
        return False
    return any(marker in normalized for marker in _SENSITIVE_METADATA_KEY_MARKERS)


def _provider_token_metadata(
    *,
    user_metadata: Mapping[str, Any],
    plaintext_token: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "connection_method": GITHUB_PROVIDER_TOKEN_CONNECTION_METHOD,
        "token_validated": False,
        "created_via": "founderos_operator_bridge",
    }
    safe_user_metadata = _safe_user_metadata(user_metadata, plaintext_token=plaintext_token)
    if safe_user_metadata:
        metadata["user_metadata"] = safe_user_metadata
    return metadata


def _safe_user_metadata(value: Any, *, plaintext_token: str) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): safe_value
            for key, raw_value in value.items()
            if isinstance(key, str) and not _metadata_key_is_sensitive(key)
            for safe_value in [_safe_user_metadata(raw_value, plaintext_token=plaintext_token)]
            if safe_value is not None
        }
    if isinstance(value, list):
        return [
            safe_value
            for item in value[:20]
            for safe_value in [_safe_user_metadata(item, plaintext_token=plaintext_token)]
            if safe_value is not None
        ]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped == plaintext_token:
            return None
        return stripped[:500]
    if isinstance(value, bool | int | float) or value is None:
        return value
    return str(value)[:500]


def _safe_scopes(scopes: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_scope in scopes[:50]:
        scope = raw_scope.strip()
        if not scope or scope in seen:
            continue
        normalized.append(scope[:120])
        seen.add(scope)
    return normalized


def _workspace_github_app_config(
    credential: GitHubAppCredential | None,
) -> dict[str, Any]:
    if credential is None:
        return {
            "configured": False,
            "credential_source": "none",
            "app_id_configured": False,
            "app_slug": None,
            "app_name": None,
            "private_key_configured": False,
            "private_key_source": None,
            "webhook_secret_configured": False,
            "setup_url": None,
            "callback_url": None,
            "missing_requirements": ["github_app_product_setup"],
            "installation_tokens_persisted": False,
            "provider_writes_enabled": False,
        }

    managed = redact_github_app_credential(credential)
    configured = bool(managed["configured"])
    app_slug = managed["app_slug"] if configured else None
    return {
        "configured": configured,
        "credential_source": "managed",
        "app_id_configured": bool(managed["app_id_configured"]),
        "app_slug": app_slug,
        "app_name": managed["app_name"],
        "private_key_configured": bool(managed["private_key_configured"]),
        "private_key_source": "encrypted_database" if configured else None,
        "webhook_secret_configured": bool(
            managed["webhook_secret_configured"]
        ),
        "setup_url": (
            f"https://github.com/apps/{app_slug}/installations/new"
            if isinstance(app_slug, str) and app_slug
            else None
        ),
        "callback_url": managed["callback_url"],
        "missing_requirements": [],
        "installation_tokens_persisted": False,
        "provider_writes_enabled": False,
    }


def _safe_text(value: str, *, max_length: int) -> str:
    return value.strip()[:max_length]
