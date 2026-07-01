from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
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
GITHUB_APP_CONNECTION_METHOD = "github_app_installation"
GITHUB_APP_EXTERNAL_ACCOUNT_PREFIX = "github_app_installation:"
GITHUB_APP_INSTALLATION_TOKEN_STRATEGY = "mint_installation_token_just_in_time"
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
GITHUB_APP_INSTALLATION_ALREADY_BOUND = (
    "github app installation is already bound to another workspace"
)
GITHUB_APP_INSTALLATION_INVALID_REPOSITORY_SELECTION = (
    "github app repository_selection must be all, selected, or unknown"
)


@dataclass(frozen=True)
class GitHubProviderTokenConnectionInput:
    access_token: str
    display_name: str | None = None
    external_account_id: str | None = None
    scopes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GitHubAppInstallationConnectionInput:
    installation_id: str
    account_login: str
    account_id: str | None = None
    repository_selection: str = "unknown"
    selected_repositories: list[dict[str, Any]] = field(default_factory=list)
    display_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class GitHubAppInstallationConnectionError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


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
    app_config = github_app_config_status()

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
    has_valid_token_record = (
        selected["status"] == INTEGRATION_CONNECTION_STATUS_CONNECTED
        and bool(selected["has_access_token"])
    )
    if (
        selected["status"] == INTEGRATION_CONNECTION_STATUS_CONNECTED
        and not selected["has_access_token"]
        and is_app_installation
    ):
        warnings.append(GITHUB_APP_TOKEN_WARNING)
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
        if has_valid_token_record
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


async def create_or_update_github_app_installation_connection(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    payload: GitHubAppInstallationConnectionInput,
) -> dict[str, Any]:
    installation_id = _normalized_installation_id(payload.installation_id)
    external_account_id = _github_app_external_account_id(installation_id)
    repository_selection = _safe_repository_selection(payload.repository_selection)
    await _ensure_installation_is_not_bound_elsewhere(
        session,
        workspace_id=workspace_id,
        external_account_id=external_account_id,
    )

    connection = await _find_github_app_installation_connection(
        session,
        workspace_id=workspace_id,
        external_account_id=external_account_id,
    )
    if connection is None:
        connection = IntegrationConnection(
            workspace_id=workspace_id,
            provider=INTEGRATION_PROVIDER_GITHUB,
        )
        session.add(connection)

    connection.status = INTEGRATION_CONNECTION_STATUS_CONNECTED
    connection.display_name = (
        payload.display_name
        or f"GitHub App: {_safe_text(payload.account_login, max_length=120)}"
    )
    connection.external_account_id = external_account_id
    connection.scopes = ["github_app_installation"]
    connection.encrypted_access_token = None
    connection.encrypted_refresh_token = None
    connection.token_expires_at = None
    connection.provider_metadata = _github_app_installation_metadata(
        payload=payload,
        installation_id=installation_id,
        repository_selection=repository_selection,
    )
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


async def _find_github_app_installation_connection(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    external_account_id: str,
) -> IntegrationConnection | None:
    return await session.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.workspace_id == workspace_id)
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(IntegrationConnection.external_account_id == external_account_id)
    )


async def _ensure_installation_is_not_bound_elsewhere(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    external_account_id: str,
) -> None:
    existing = await session.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(IntegrationConnection.external_account_id == external_account_id)
    )
    if existing is not None and existing.workspace_id != workspace_id:
        raise GitHubAppInstallationConnectionError(
            GITHUB_APP_INSTALLATION_ALREADY_BOUND
        )


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
        if not isinstance(raw_scope, str):
            continue
        scope = raw_scope.strip()
        if not scope or scope in seen:
            continue
        normalized.append(scope[:120])
        seen.add(scope)
    return normalized


def github_app_config_status(config: Settings = settings) -> dict[str, Any]:
    app_id_configured = _configured_text(config.github_app_id)
    app_slug = _safe_optional_text(config.github_app_slug, max_length=120)
    private_key_configured = _configured_secret(config.github_app_private_key) or _configured_text(
        config.github_app_private_key_path
    )
    webhook_secret_configured = _configured_secret(config.github_app_webhook_secret)
    setup_url = _github_app_setup_url(config=config, app_slug=app_slug)
    callback_url = _safe_url(config.github_app_callback_url)
    missing_env: list[str] = []
    if not app_id_configured:
        missing_env.append("FOUNDEROS_GITHUB_APP_ID")
    if app_slug is None and setup_url is None:
        missing_env.append("FOUNDEROS_GITHUB_APP_SLUG or FOUNDEROS_GITHUB_APP_SETUP_URL")
    if not private_key_configured:
        missing_env.append(
            "FOUNDEROS_GITHUB_APP_PRIVATE_KEY or FOUNDEROS_GITHUB_APP_PRIVATE_KEY_PATH"
        )

    return {
        "configured": not missing_env,
        "app_id_configured": app_id_configured,
        "app_slug": app_slug,
        "private_key_configured": private_key_configured,
        "private_key_source": (
            "inline"
            if _configured_secret(config.github_app_private_key)
            else "path"
            if _configured_text(config.github_app_private_key_path)
            else None
        ),
        "webhook_secret_configured": webhook_secret_configured,
        "setup_url": setup_url,
        "callback_url": callback_url,
        "missing_env": missing_env,
        "installation_tokens_persisted": False,
        "provider_writes_enabled": False,
    }


def _github_app_setup_url(*, config: Settings, app_slug: str | None) -> str | None:
    configured_url = _safe_url(config.github_app_setup_url)
    if configured_url is not None:
        return configured_url
    if app_slug is None:
        return None
    return f"https://github.com/apps/{app_slug}/installations/new"


def _configured_secret(value: SecretStr | str | None) -> bool:
    if isinstance(value, SecretStr):
        return bool(value.get_secret_value().strip())
    return _configured_text(value)


def _configured_text(value: str | None) -> bool:
    return bool(value and value.strip())


def _safe_url(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if stripped.startswith("https://") or stripped.startswith("http://"):
        return stripped[:500]
    return None


def _normalized_installation_id(value: str) -> str:
    normalized = _safe_text(value, max_length=64)
    if not normalized:
        raise GitHubAppInstallationConnectionError(
            "github app installation_id is required"
        )
    return normalized


def _github_app_external_account_id(installation_id: str) -> str:
    return f"{GITHUB_APP_EXTERNAL_ACCOUNT_PREFIX}{installation_id}"


def _safe_repository_selection(value: str) -> str:
    normalized = _safe_text(value, max_length=32).casefold()
    if normalized in {"all", "selected", "unknown"}:
        return normalized
    raise GitHubAppInstallationConnectionError(
        GITHUB_APP_INSTALLATION_INVALID_REPOSITORY_SELECTION
    )


def _github_app_installation_metadata(
    *,
    payload: GitHubAppInstallationConnectionInput,
    installation_id: str,
    repository_selection: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "connection_method": GITHUB_APP_CONNECTION_METHOD,
        "installation_id": installation_id,
        "account_login": _safe_text(payload.account_login, max_length=255),
        "account_id": _safe_optional_text(payload.account_id, max_length=64),
        "repository_selection": repository_selection,
        "selected_repositories": _safe_selected_repositories(
            payload.selected_repositories
        ),
        "token_strategy": GITHUB_APP_INSTALLATION_TOKEN_STRATEGY,
        "installation_access_token_persisted": False,
        "provider_writes_enabled": False,
        "created_via": "github_app_product_connect_foundation",
    }
    safe_user_metadata = _safe_user_metadata(
        payload.metadata,
        plaintext_token="",
    )
    if safe_user_metadata:
        metadata["user_metadata"] = safe_user_metadata
    return metadata


def _safe_selected_repositories(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for raw_item in value[:100]:
        if not isinstance(raw_item, Mapping):
            continue
        item: dict[str, Any] = {}
        for key in ("id", "name", "full_name", "private"):
            if key not in raw_item:
                continue
            raw_value = raw_item[key]
            if key == "private" and isinstance(raw_value, bool):
                item[key] = raw_value
            elif isinstance(raw_value, str | int):
                item[key] = str(raw_value).strip()[:255]
        if item:
            safe.append(item)
    return safe


def _safe_text(value: str, *, max_length: int) -> str:
    return value.strip()[:max_length]


def _safe_optional_text(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:max_length]
