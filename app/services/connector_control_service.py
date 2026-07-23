"""Secure workspace connector configuration and bounded health checks.

The control center owns configuration receipts, encrypted provider credentials,
and explicit read probes. It never returns stored credentials or raw provider
payloads. Write checks are readiness-only and never call a provider.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import CONNECTOR_DESCRIPTORS
from app.core.config import settings
from app.db.integration_models import (
    GITHUB_APP_INSTALLATION_STATUS_ACTIVE,
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_DISABLED,
    INTEGRATION_CONNECTION_STATUS_ERROR,
    GitHubAppInstallation,
    IntegrationConnection,
)
from app.services.github_app_credential_service import (
    get_github_app_signing_credential,
)
from app.services.github_app_token_service import mint_installation_access_token
from app.services.real_connector_guard import require_real_connectors_enabled
from app.services.secret_encryption import decrypt_secret, encrypt_secret

CONNECTOR_CONTROL_CONTRACT = "connector-control.v1"
CONNECTOR_CONTROL_SOURCE = "settings_integrations"
SUPPORTED_PROVIDERS = ("github", "jira", "gmail", "drive")

AUTH_METHODS = {
    "github": frozenset({"manual_provider_token"}),
    "jira": frozenset({"jira_cloud_api_token"}),
    "gmail": frozenset({"oauth_access_token"}),
    "drive": frozenset({"oauth_access_token"}),
}

_PROVIDER_NAMES = {
    descriptor.provider: descriptor.name for descriptor in CONNECTOR_DESCRIPTORS
}
_PROVIDER_MANAGE_PATHS = {
    descriptor.provider: descriptor.manage_path for descriptor in CONNECTOR_DESCRIPTORS
}
_SAFE_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")


class ConnectorControlError(ValueError):
    """Safe validation or state error suitable for an API response."""


@dataclass(frozen=True, repr=False)
class ConnectorConfigurationInput:
    provider: str
    auth_method: str
    access_token: str
    display_name: str | None = None
    base_url: str | None = None
    account_email: str | None = None
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderProbeResult:
    account_label: str | None = None
    scopes: tuple[str, ...] = ()
    records_visible: int | None = None


class ProviderProbeError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider_call_performed: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.provider_call_performed = provider_call_performed


async def build_connector_control_center(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    """Return safe connection state without decrypting credentials."""

    rows = list(
        (
            await session.scalars(
                select(IntegrationConnection)
                .where(IntegrationConnection.workspace_id == workspace_id)
                .order_by(IntegrationConnection.created_at.desc())
            )
        ).all()
    )
    installation = await _active_github_installation(
        session,
        workspace_id=workspace_id,
    )

    connectors: list[dict[str, Any]] = []
    for provider in SUPPORTED_PROVIDERS:
        removable_connection = _settings_connection_from_rows(
            rows,
            provider=provider,
        )
        connection = _select_connection(
            rows,
            provider=provider,
            installation=installation,
        )
        connectors.append(
            _connector_payload(
                provider=provider,
                connection=connection,
                installation=installation
                if connection is not None
                and installation is not None
                and connection.id == installation.connection_id
                else None,
                removable_credential_present=bool(
                    removable_connection is not None
                    and removable_connection.encrypted_access_token
                ),
            )
        )

    return {
        "contract": CONNECTOR_CONTROL_CONTRACT,
        "workspace_id": str(workspace_id),
        "connectors": connectors,
        "summary": {
            "total": len(connectors),
            "configured": sum(1 for item in connectors if item["configured"]),
            "verified": sum(
                1 for item in connectors if item["state"] == "read_verified"
            ),
            "errors": sum(1 for item in connectors if item["state"] == "error"),
        },
        "boundary": {
            "provider_calls": False,
            "external_writes": False,
            "stored_secrets_returned": False,
            "write_checks_are_dry_run": True,
        },
    }


async def apply_connector_configuration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    payload: ConnectorConfigurationInput,
) -> dict[str, Any]:
    """Encrypt and save one supported connector configuration.

    Applying configuration performs no provider call. A separate explicit read
    check promotes the connection to ``connected``.
    """

    provider = _provider(payload.provider)
    auth_method = payload.auth_method.strip()
    if auth_method not in AUTH_METHODS[provider]:
        raise ConnectorControlError("unsupported authentication method")

    access_token = payload.access_token.strip()
    if not access_token:
        raise ConnectorControlError("credential is required")
    encrypted_access_token = encrypt_secret(access_token)

    display_name = _optional_text(payload.display_name, max_length=255)
    account_email = _optional_text(payload.account_email, max_length=320)
    scopes = _safe_scopes(payload.scopes)
    base_url: str | None = None
    if provider == "jira":
        if account_email is None or "@" not in account_email:
            raise ConnectorControlError("Jira account email is required")
        base_url = _normalize_jira_cloud_url(payload.base_url)
    elif payload.base_url:
        raise ConnectorControlError("custom provider URLs are not supported")

    connection = await _settings_connection(
        session,
        workspace_id=workspace_id,
        provider=provider,
    )
    now = _utcnow()
    if connection is None:
        connection = IntegrationConnection(
            workspace_id=workspace_id,
            provider=provider,
        )
        session.add(connection)

    safe_metadata = {
        "connection_method": auth_method,
        "created_via": CONNECTOR_CONTROL_SOURCE,
        "token_validated": False,
        "control_center": {
            "contract": CONNECTOR_CONTROL_CONTRACT,
            "auth_method": auth_method,
            "configured_at": now.isoformat(),
            "base_url": base_url,
            "account_email": account_email if provider == "jira" else None,
            "read_check": None,
            "write_check": None,
        },
    }
    connection.status = INTEGRATION_CONNECTION_STATUS_DISABLED
    connection.display_name = display_name or _PROVIDER_NAMES.get(provider, provider)
    connection.external_account_id = account_email
    connection.scopes = scopes
    connection.encrypted_access_token = encrypted_access_token
    connection.encrypted_refresh_token = None
    connection.token_expires_at = None
    connection.provider_metadata = safe_metadata
    connection.last_error = None
    await session.flush()

    return _connector_payload(
        provider=provider,
        connection=connection,
        installation=None,
        removable_credential_present=True,
    )


async def disconnect_connector_configuration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    provider: str,
) -> dict[str, Any]:
    """Remove only the credential saved through the control center.

    The durable row is retained so sync history and foreign-key references stay
    valid. Managed GitHub App credentials are owned by the GitHub setup flow and
    are never removed here.
    """

    normalized_provider = _provider(provider)
    connection = await _settings_connection(
        session,
        workspace_id=workspace_id,
        provider=normalized_provider,
    )
    if connection is None or not connection.encrypted_access_token:
        raise ConnectorControlError(
            "no control-center credential is configured for this provider"
        )

    metadata = _metadata(connection)
    control = dict(_control_metadata(connection))
    control.update(
        {
            "contract": CONNECTOR_CONTROL_CONTRACT,
            "credential_removed_at": _utcnow().isoformat(),
            "base_url": None,
            "account_email": None,
            "read_check": None,
            "write_check": None,
        }
    )
    metadata["token_validated"] = False
    metadata["control_center"] = control

    connection.status = INTEGRATION_CONNECTION_STATUS_DISABLED
    connection.external_account_id = None
    connection.scopes = []
    connection.encrypted_access_token = None
    connection.encrypted_refresh_token = None
    connection.token_expires_at = None
    connection.provider_metadata = metadata
    connection.last_error = None
    await session.flush()

    return _connector_payload(
        provider=normalized_provider,
        connection=connection,
        installation=None,
        removable_credential_present=False,
    )


async def run_connector_read_check(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    provider: str,
    requested_by_operator: bool,
) -> dict[str, Any]:
    """Perform one explicit, bounded, read-only provider request."""

    normalized_provider = _provider(provider)
    if requested_by_operator:
        require_real_connectors_enabled()

    rows = list(
        (
            await session.scalars(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == workspace_id,
                    IntegrationConnection.provider == normalized_provider,
                )
            )
        ).all()
    )
    installation = (
        await _active_github_installation(session, workspace_id=workspace_id)
        if normalized_provider == "github"
        else None
    )
    connection = _select_connection(
        rows,
        provider=normalized_provider,
        installation=installation,
    )
    if connection is None:
        raise ConnectorControlError("connector is not configured")

    checked_at = _utcnow().isoformat()
    try:
        result = await _probe_connection(
            session,
            workspace_id=workspace_id,
            connection=connection,
            provider=normalized_provider,
            installation=installation
            if installation is not None
            and installation.connection_id == connection.id
            else None,
        )
    except ProviderProbeError as exc:
        receipt = {
            "status": "failed",
            "code": exc.code,
            "message": exc.message,
            "checked_at": checked_at,
            "provider_call_performed": exc.provider_call_performed,
            "external_write_performed": False,
        }
        connection.status = INTEGRATION_CONNECTION_STATUS_ERROR
        connection.last_error = exc.code
        _set_control_receipt(connection, "read_check", receipt)
        await session.flush()
        return receipt

    receipt = {
        "status": "passed",
        "code": "read_verified",
        "message": "Read access verified.",
        "checked_at": checked_at,
        "provider_call_performed": True,
        "external_write_performed": False,
        "account_label": result.account_label,
        "scopes": list(result.scopes),
        "records_visible": result.records_visible,
    }
    connection.status = INTEGRATION_CONNECTION_STATUS_CONNECTED
    connection.last_error = None
    if result.account_label:
        connection.external_account_id = result.account_label[:255]
    if result.scopes:
        connection.scopes = list(result.scopes)
    metadata = _metadata(connection)
    metadata["token_validated"] = True
    connection.provider_metadata = metadata
    _set_control_receipt(connection, "read_check", receipt)
    await session.flush()
    return receipt


async def run_connector_write_readiness_check(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    provider: str,
) -> dict[str, Any]:
    """Evaluate write gates without decrypting credentials or calling providers."""

    normalized_provider = _provider(provider)
    rows = list(
        (
            await session.scalars(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == workspace_id,
                    IntegrationConnection.provider == normalized_provider,
                )
            )
        ).all()
    )
    installation = (
        await _active_github_installation(session, workspace_id=workspace_id)
        if normalized_provider == "github"
        else None
    )
    connection = _select_connection(
        rows,
        provider=normalized_provider,
        installation=installation,
    )

    configured = bool(
        connection is not None
        and (
            connection.encrypted_access_token
            or (
                installation is not None
                and installation.connection_id == connection.id
            )
        )
    )
    read_verified = bool(
        connection is not None
        and _read_check(connection).get("status") == "passed"
    )
    allowlist_configured = bool(
        normalized_provider == "github"
        and (settings.github_write_allowed_repos or "").strip()
    )
    github_supported = normalized_provider == "github"
    checks = {
        "credential_configured": configured,
        "read_verified": read_verified,
        "write_feature_enabled": bool(settings.enable_write_actions),
        "approval_required": bool(settings.require_approval_for_writes),
        "target_allowlist_configured": allowlist_configured,
        "provider_write_supported": github_supported,
    }
    ready = bool(
        github_supported
        and configured
        and read_verified
        and settings.enable_write_actions
        and settings.require_approval_for_writes
        and allowlist_configured
    )
    receipt = {
        "status": "ready" if ready else "guarded",
        "code": "write_ready" if ready else "write_guarded",
        "message": (
            "Write gates are ready; every write still requires an approved "
            "ActionProposal and an explicit repository target."
            if ready
            else "No external write was attempted. Resolve the failed gates "
            "before creating an approved ActionProposal."
        ),
        "checked_at": _utcnow().isoformat(),
        "checks": checks,
        "provider_call_performed": False,
        "external_write_performed": False,
    }
    if connection is not None:
        _set_control_receipt(connection, "write_check", receipt)
        await session.flush()
    return receipt


async def _probe_connection(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection: IntegrationConnection,
    provider: str,
    installation: GitHubAppInstallation | None,
) -> ProviderProbeResult:
    if provider == "github" and installation is not None:
        return await _probe_managed_github(
            session,
            workspace_id=workspace_id,
            installation=installation,
        )

    encrypted_token = connection.encrypted_access_token
    if not encrypted_token:
        raise ProviderProbeError(
            "credential_missing",
            "A provider credential has not been saved.",
        )
    try:
        access_token = decrypt_secret(encrypted_token)
    except Exception as exc:
        raise ProviderProbeError(
            "credential_unavailable",
            "The saved credential could not be opened.",
        ) from exc

    if provider == "github":
        return await _probe_github_token(access_token)
    if provider == "jira":
        control = _control_metadata(connection)
        base_url = _normalize_jira_cloud_url(control.get("base_url"))
        account_email = _optional_text(control.get("account_email"), max_length=320)
        if account_email is None:
            raise ProviderProbeError(
                "configuration_incomplete",
                "Jira account email is missing.",
            )
        return await _probe_jira(
            access_token,
            base_url=base_url,
            account_email=account_email,
        )
    if provider == "gmail":
        return await _probe_gmail(access_token)
    if provider == "drive":
        return await _probe_drive(access_token)
    raise ProviderProbeError("unsupported_provider", "Provider is not supported.")


async def _probe_managed_github(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    installation: GitHubAppInstallation,
) -> ProviderProbeResult:
    try:
        credential = await get_github_app_signing_credential(
            session,
            workspace_id=workspace_id,
        )
        if credential is None:
            raise ProviderProbeError(
                "credential_missing",
                "The managed GitHub App credential is unavailable.",
            )
    except ProviderProbeError:
        raise
    except Exception as exc:
        raise ProviderProbeError(
            "credential_unavailable",
            "The managed GitHub App credential could not be opened.",
        ) from exc

    try:
        token = await mint_installation_access_token(
            installation_id=installation.installation_id,
            credential=credential,
        )
        data, _ = await _get_json(
            "https://api.github.com/installation/repositories?per_page=1&page=1",
            headers={
                "Authorization": f"Bearer {token.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "founderOS",
            },
        )
    except ProviderProbeError:
        raise
    except Exception as exc:
        raise ProviderProbeError(
            "provider_unavailable",
            "GitHub App read verification failed.",
            provider_call_performed=True,
        ) from exc
    records_visible = _safe_nonnegative_int(data.get("total_count"))
    if records_visible is None:
        repositories = data.get("repositories")
        records_visible = len(repositories) if isinstance(repositories, list) else None
    return ProviderProbeResult(
        account_label=installation.account_login[:255],
        scopes=tuple(
            sorted(
                str(key)[:100]
                for key, value in (installation.permissions or {}).items()
                if value
            )
        ),
        records_visible=records_visible,
    )


async def _probe_github_token(access_token: str) -> ProviderProbeResult:
    data, headers = await _get_json(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "founderOS",
        },
    )
    login = _optional_text(data.get("login"), max_length=255)
    scope_header = headers.get("x-oauth-scopes", "")
    return ProviderProbeResult(
        account_label=login,
        scopes=tuple(
            item.strip()[:100] for item in scope_header.split(",") if item.strip()
        ),
    )


async def _probe_jira(
    access_token: str,
    *,
    base_url: str,
    account_email: str,
) -> ProviderProbeResult:
    data, _ = await _get_json(
        f"{base_url}/rest/api/3/myself",
        auth=httpx.BasicAuth(account_email, access_token),
        headers={"Accept": "application/json", "User-Agent": "founderOS"},
    )
    return ProviderProbeResult(
        account_label=_optional_text(
            data.get("displayName") or data.get("emailAddress"),
            max_length=255,
        )
    )


async def _probe_gmail(access_token: str) -> ProviderProbeResult:
    data, _ = await _get_json(
        "https://gmail.googleapis.com/gmail/v1/users/me/profile",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "founderOS",
        },
    )
    return ProviderProbeResult(
        account_label=_optional_text(data.get("emailAddress"), max_length=255),
        records_visible=_safe_nonnegative_int(data.get("messagesTotal")),
    )


async def _probe_drive(access_token: str) -> ProviderProbeResult:
    data, _ = await _get_json(
        "https://www.googleapis.com/drive/v3/about?fields=user(displayName,emailAddress)",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "founderOS",
        },
    )
    user = data.get("user")
    if not isinstance(user, Mapping):
        user = {}
    return ProviderProbeResult(
        account_label=_optional_text(
            user.get("emailAddress") or user.get("displayName"),
            max_length=255,
        )
    )


async def _get_json(
    url: str,
    *,
    headers: Mapping[str, str],
    auth: httpx.Auth | None = None,
) -> tuple[dict[str, Any], Mapping[str, str]]:
    timeout = max(3, min(int(settings.connector_network_timeout_seconds), 30))
    try:
        async with httpx.AsyncClient(timeout=float(timeout)) as client:
            response = await client.get(url, headers=dict(headers), auth=auth)
    except httpx.HTTPError as exc:
        raise ProviderProbeError(
            "provider_unavailable",
            "The provider could not be reached.",
            provider_call_performed=True,
        ) from exc

    if response.status_code < 200 or response.status_code >= 300:
        code, message = _safe_provider_error(response.status_code)
        raise ProviderProbeError(
            code,
            message,
            provider_call_performed=True,
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderProbeError(
            "invalid_provider_response",
            "The provider returned an invalid response.",
            provider_call_performed=True,
        ) from exc
    if not isinstance(data, Mapping):
        raise ProviderProbeError(
            "invalid_provider_response",
            "The provider returned an invalid response.",
            provider_call_performed=True,
        )
    return dict(data), response.headers


def _connector_payload(
    *,
    provider: str,
    connection: IntegrationConnection | None,
    installation: GitHubAppInstallation | None,
    removable_credential_present: bool = False,
) -> dict[str, Any]:
    managed_github = bool(
        provider == "github"
        and connection is not None
        and installation is not None
        and installation.connection_id == connection.id
    )
    metadata = _metadata(connection) if connection is not None else {}
    control = _control_metadata(connection) if connection is not None else {}
    read_check = _read_check(connection)
    write_check = _receipt(connection, "write_check")
    credential_present = bool(
        managed_github
        or (connection is not None and connection.encrypted_access_token)
    )
    configured = bool(connection is not None and credential_present)
    if read_check.get("status") == "passed":
        state = "read_verified"
    elif read_check.get("status") == "failed" or (
        connection is not None
        and connection.status == INTEGRATION_CONNECTION_STATUS_ERROR
    ):
        state = "error"
    elif configured:
        state = "saved_unverified"
    else:
        state = "not_configured"

    auth_method = (
        "github_app_installation"
        if managed_github
        else _optional_text(
            control.get("auth_method") or metadata.get("connection_method"),
            max_length=80,
        )
    )
    account_label: str | None = None
    if managed_github and installation is not None:
        account_label = installation.account_login[:255]
    elif connection is not None and credential_present:
        account_label = (
            _optional_text(connection.external_account_id, max_length=255)
            or _optional_text(connection.display_name, max_length=255)
        )

    warnings: list[str] = []
    if provider in {"gmail", "drive"}:
        warnings.append(
            "Manual OAuth access tokens can expire; automatic OAuth refresh is not implemented yet."
        )
    if provider == "github" and not managed_github:
        warnings.append(
            "A managed GitHub App is recommended; personal tokens are an advanced fallback."
        )
    return {
        "provider": provider,
        "name": _PROVIDER_NAMES.get(provider, provider.title()),
        "state": state,
        "connection_status": connection.status if connection is not None else None,
        "configured": configured,
        "credential_present": credential_present,
        "removable_credential_present": removable_credential_present,
        "auth_method": auth_method,
        "display_name": connection.display_name if connection is not None else None,
        "account_label": account_label,
        "base_url": _optional_text(control.get("base_url"), max_length=500),
        "scopes": list(connection.scopes or []) if connection is not None else [],
        "last_checked_at": _optional_text(read_check.get("checked_at"), max_length=80),
        "read_check": read_check or None,
        "write_check": write_check or None,
        "read_test_supported": True,
        "write_test_mode": "dry_run",
        "manage_path": _PROVIDER_MANAGE_PATHS.get(provider),
        "warnings": warnings,
    }


async def _settings_connection(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    provider: str,
) -> IntegrationConnection | None:
    rows = (
        await session.scalars(
            select(IntegrationConnection)
            .where(
                IntegrationConnection.workspace_id == workspace_id,
                IntegrationConnection.provider == provider,
            )
            .order_by(IntegrationConnection.created_at.desc())
        )
    ).all()
    return _settings_connection_from_rows(
        list(rows),
        provider=provider,
    )


async def _active_github_installation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> GitHubAppInstallation | None:
    return await session.scalar(
        select(GitHubAppInstallation).where(
            GitHubAppInstallation.workspace_id == workspace_id,
            GitHubAppInstallation.status == GITHUB_APP_INSTALLATION_STATUS_ACTIVE,
        )
    )


def _select_connection(
    rows: list[IntegrationConnection],
    *,
    provider: str,
    installation: GitHubAppInstallation | None,
) -> IntegrationConnection | None:
    provider_rows = [row for row in rows if row.provider == provider]
    if provider == "github" and installation is not None:
        managed = next(
            (
                row
                for row in provider_rows
                if row.id == installation.connection_id
            ),
            None,
        )
        if managed is not None:
            return managed
    settings_row = next(
        (
            row
            for row in provider_rows
            if _metadata(row).get("created_via") == CONNECTOR_CONTROL_SOURCE
        ),
        None,
    )
    return settings_row or (provider_rows[0] if provider_rows else None)


def _settings_connection_from_rows(
    rows: list[IntegrationConnection],
    *,
    provider: str,
) -> IntegrationConnection | None:
    return next(
        (
            row
            for row in rows
            if row.provider == provider
            and _metadata(row).get("created_via") == CONNECTOR_CONTROL_SOURCE
        ),
        None,
    )


def _set_control_receipt(
    connection: IntegrationConnection,
    receipt_name: str,
    receipt: Mapping[str, Any],
) -> None:
    metadata = _metadata(connection)
    control = dict(_control_metadata(connection))
    control.setdefault("contract", CONNECTOR_CONTROL_CONTRACT)
    control[receipt_name] = dict(receipt)
    metadata["control_center"] = control
    connection.provider_metadata = metadata


def _metadata(connection: IntegrationConnection | None) -> dict[str, Any]:
    if connection is None or not isinstance(connection.provider_metadata, Mapping):
        return {}
    return dict(connection.provider_metadata)


def _control_metadata(connection: IntegrationConnection | None) -> dict[str, Any]:
    raw = _metadata(connection).get("control_center")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _receipt(
    connection: IntegrationConnection | None,
    receipt_name: str,
) -> dict[str, Any]:
    raw = _control_metadata(connection).get(receipt_name)
    return dict(raw) if isinstance(raw, Mapping) else {}


def _read_check(connection: IntegrationConnection | None) -> dict[str, Any]:
    return _receipt(connection, "read_check")


def _provider(value: str) -> str:
    provider = value.strip().casefold()
    if provider not in SUPPORTED_PROVIDERS:
        raise ConnectorControlError("unsupported connector provider")
    return provider


def _normalize_jira_cloud_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConnectorControlError("Jira Cloud site URL is required")
    raw = value.strip()
    parsed = urlsplit(raw)
    hostname = parsed.hostname.casefold() if parsed.hostname else ""
    try:
        port = parsed.port
    except ValueError as exc:
        raise ConnectorControlError("invalid Jira Cloud site URL") from exc
    if (
        parsed.scheme.casefold() != "https"
        or not hostname.endswith(".atlassian.net")
        or hostname == "atlassian.net"
        or not _SAFE_HOST_RE.fullmatch(hostname)
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConnectorControlError(
            "Jira URL must be an HTTPS *.atlassian.net site without a path"
        )
    return f"https://{hostname}"


def _safe_scopes(values: tuple[str, ...]) -> list[str]:
    if len(values) > 50:
        raise ConnectorControlError("too many scopes")
    scopes: list[str] = []
    for value in values:
        scope = _optional_text(value, max_length=500)
        if scope and scope not in scopes:
            scopes.append(scope)
    return scopes


def _optional_text(value: Any, *, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().split())
    if not normalized:
        return None
    return normalized[:max_length]


def _safe_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _safe_provider_error(status_code: int) -> tuple[str, str]:
    if status_code in {401, 403}:
        return "authorization_failed", "The provider rejected the credential."
    if status_code == 404:
        return "provider_resource_not_found", "The provider resource was not found."
    if status_code == 429:
        return "provider_rate_limited", "The provider rate limit was reached."
    if status_code >= 500:
        return "provider_unavailable", "The provider is temporarily unavailable."
    return "provider_rejected", "The provider rejected the read verification request."


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
