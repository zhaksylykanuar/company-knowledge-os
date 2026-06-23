from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_DISABLED,
    INTEGRATION_CONNECTION_STATUS_ERROR,
    INTEGRATION_CONNECTION_STATUS_REVOKED,
    INTEGRATION_PROVIDER_GITHUB,
    IntegrationConnection,
)
from app.services.secret_encryption import encrypt_secret

GITHUB_CONNECTION_PROVIDER = INTEGRATION_PROVIDER_GITHUB
GITHUB_CONNECTION_STATUS_LOCAL_BRIDGE_ONLY = "local_bridge_only"
GITHUB_CONNECTION_STATUS_NOT_CONNECTED = "not_connected"
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
_SAFE_METADATA_KEYS = {"token_validated"}
GITHUB_PROVIDER_TOKEN_WARNING = (
    "GitHub token is stored for future sync but was not validated with GitHub in this step."
)


@dataclass(frozen=True)
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
    selected = _select_status_connection(connections)
    warnings: list[str] = []

    if selected is None:
        return {
            "provider": INTEGRATION_PROVIDER_GITHUB,
            "status": GITHUB_CONNECTION_STATUS_LOCAL_BRIDGE_ONLY,
            "connection_id": None,
            "display_name": None,
            "last_sync_at": None,
            "last_error": None,
            "has_connection_record": False,
            "has_valid_token_record": False,
            "repository_read_available": True,
            "repository_read_source": GITHUB_REPOSITORY_READ_SOURCE_LOCAL_BRIDGE,
            "is_live": False,
            "warnings": [
                "no GitHub IntegrationConnection exists; repository read uses local bridge only"
            ],
        }

    has_valid_token_record = (
        selected["status"] == INTEGRATION_CONNECTION_STATUS_CONNECTED
        and bool(selected["has_access_token"])
    )
    if selected["status"] == INTEGRATION_CONNECTION_STATUS_CONNECTED and not selected[
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
        if has_valid_token_record
        else GITHUB_REPOSITORY_READ_SOURCE_LOCAL_BRIDGE
    )
    return {
        "provider": INTEGRATION_PROVIDER_GITHUB,
        "status": selected["status"],
        "connection_id": selected["id"],
        "display_name": selected["display_name"],
        "last_sync_at": selected["last_sync_at"],
        "last_error": selected["last_error"],
        "has_connection_record": True,
        "has_valid_token_record": has_valid_token_record,
        "repository_read_available": True,
        "repository_read_source": repository_read_source,
        "is_live": False,
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
        == "manual_provider_token"
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
        "connection_method": "manual_provider_token",
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
        if not isinstance(raw_scope, str):
            continue
        scope = raw_scope.strip()
        if not scope or scope in seen:
            continue
        normalized.append(scope[:120])
        seen.add(scope)
    return normalized
