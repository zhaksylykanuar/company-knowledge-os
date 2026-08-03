from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.integration_models import (
    GITHUB_APP_CREDENTIAL_STATUS_ACTIVE,
    GitHubAppCredential,
)
from app.services.secret_encryption import decrypt_secret, encrypt_secret


_GITHUB_APP_SLUG_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,118}[A-Za-z0-9])?$"
)


class GitHubAppCredentialError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True, repr=False)
class GitHubAppSigningCredential:
    app_id: str
    private_key_pem: str


@dataclass(frozen=True, repr=False)
class GitHubAppOAuthCredential:
    app_id: str
    app_slug: str
    client_id: str
    client_secret: str
    private_key_pem: str
    callback_url: str


@dataclass(frozen=True, repr=False)
class GitHubManifestCredentialInput:
    app_id: str
    app_slug: str
    app_name: str
    client_id: str
    private_key_pem: str
    client_secret: str
    webhook_secret: str | None
    callback_url: str
    owner_login: str | None = None
    owner_id: str | None = None
    owner_type: str | None = None
    permissions: dict[str, str] | None = None
    html_url: str | None = None


def verify_github_app_secret_storage_ready() -> None:
    """Fail before GitHub creates an App if encrypted persistence is unusable."""

    probe = "github-app-setup-preflight"
    encrypted = encrypt_secret(probe)
    if decrypt_secret(encrypted) != probe:
        raise GitHubAppCredentialError("github_app_secret_storage_unavailable")


async def get_active_github_app_credential(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> GitHubAppCredential | None:
    return await session.scalar(
        select(GitHubAppCredential)
        .where(GitHubAppCredential.workspace_id == workspace_id)
        .where(GitHubAppCredential.status == GITHUB_APP_CREDENTIAL_STATUS_ACTIVE)
    )


async def get_github_app_signing_credential(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> GitHubAppSigningCredential | None:
    credential = await get_active_github_app_credential(
        session,
        workspace_id=workspace_id,
    )
    if credential is None:
        return None
    return GitHubAppSigningCredential(
        app_id=credential.app_id,
        private_key_pem=decrypt_secret(credential.encrypted_private_key),
    )


async def get_github_app_oauth_credential(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> GitHubAppOAuthCredential | None:
    credential = await get_active_github_app_credential(
        session,
        workspace_id=workspace_id,
    )
    if credential is None:
        return None
    return GitHubAppOAuthCredential(
        app_id=credential.app_id,
        app_slug=credential.app_slug,
        client_id=credential.client_id,
        client_secret=decrypt_secret(credential.encrypted_client_secret),
        private_key_pem=decrypt_secret(credential.encrypted_private_key),
        callback_url=credential.callback_url,
    )


async def store_manifest_github_app_credential(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    created_by_user_id: UUID,
    payload: GitHubManifestCredentialInput,
) -> GitHubAppCredential:
    conflicting = await session.scalar(
        select(GitHubAppCredential)
        .where(GitHubAppCredential.app_id == payload.app_id)
        .where(GitHubAppCredential.workspace_id != workspace_id)
    )
    if conflicting is not None:
        raise GitHubAppCredentialError("github_app_already_bound")

    # Validate and encrypt the complete provider response before attaching a new
    # ORM row or mutating an existing one. A local encryption failure must not
    # leave a partially populated credential pending in the session.
    app_id = _required_text(payload.app_id, max_length=100)
    app_slug = _required_text(payload.app_slug, max_length=120)
    app_name = _required_text(payload.app_name, max_length=255)
    client_id = _required_text(payload.client_id, max_length=255)
    encrypted_private_key = encrypt_secret(payload.private_key_pem)
    encrypted_client_secret = encrypt_secret(payload.client_secret)
    encrypted_webhook_secret = (
        encrypt_secret(payload.webhook_secret) if payload.webhook_secret else None
    )
    owner_login = _optional_text(payload.owner_login, max_length=255)
    owner_id = _optional_text(payload.owner_id, max_length=100)
    owner_type = _optional_text(payload.owner_type, max_length=40)
    permissions = _safe_permissions(payload.permissions or {})
    html_url = _safe_github_url(payload.html_url, expected_slug=app_slug)
    callback_url = _required_url(payload.callback_url)

    credential = await session.scalar(
        select(GitHubAppCredential).where(
            GitHubAppCredential.workspace_id == workspace_id
        )
    )
    if credential is None:
        credential = GitHubAppCredential(workspace_id=workspace_id)
        session.add(credential)

    credential.app_id = app_id
    credential.app_slug = app_slug
    credential.app_name = app_name
    credential.client_id = client_id
    credential.encrypted_private_key = encrypted_private_key
    credential.encrypted_client_secret = encrypted_client_secret
    credential.encrypted_webhook_secret = encrypted_webhook_secret
    credential.owner_login = owner_login
    credential.owner_id = owner_id
    credential.owner_type = owner_type
    credential.permissions = permissions
    credential.html_url = html_url
    credential.callback_url = callback_url
    credential.source = "manifest"
    credential.status = GITHUB_APP_CREDENTIAL_STATUS_ACTIVE
    credential.created_by_user_id = created_by_user_id
    credential.last_verified_at = datetime.now(timezone.utc)
    credential.last_error = None
    await session.flush()
    await session.refresh(credential)
    return credential


def redact_github_app_credential(
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
            "webhook_secret_configured": False,
            "callback_url": None,
        }
    return {
        "configured": credential.status == GITHUB_APP_CREDENTIAL_STATUS_ACTIVE,
        "credential_source": "managed",
        "app_id_configured": True,
        "app_slug": credential.app_slug,
        "app_name": credential.app_name,
        "private_key_configured": bool(credential.encrypted_private_key),
        "webhook_secret_configured": bool(credential.encrypted_webhook_secret),
        "callback_url": credential.callback_url,
    }


def _required_text(value: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise GitHubAppCredentialError("github_app_credential_invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise GitHubAppCredentialError("github_app_credential_invalid")
    return normalized


def _optional_text(value: Any, *, max_length: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:max_length]


def _required_url(value: str) -> str:
    normalized = _optional_text(value, max_length=1000)
    if normalized is None or not normalized.startswith(("http://", "https://")):
        raise GitHubAppCredentialError("github_app_callback_url_invalid")
    return normalized


def _safe_github_url(
    value: Any,
    *,
    expected_slug: str | None = None,
) -> str | None:
    """Retain only GitHub's canonical App page for the validated App slug."""

    if (
        not isinstance(value, str)
        or not value
        or len(value) > 1000
        or "?" in value
        or "#" in value
        or "\\" in value
        or any(character.isspace() for character in value)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return None
    try:
        parsed = urlsplit(value)
        parsed.port
    except (UnicodeError, ValueError):
        return None
    parts = parsed.path.split("/")
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or len(parts) != 3
        or parts[:2] != ["", "apps"]
        or _GITHUB_APP_SLUG_RE.fullmatch(parts[2]) is None
        or (
            expected_slug is not None
            and (
                _GITHUB_APP_SLUG_RE.fullmatch(expected_slug) is None
                or parts[2].casefold() != expected_slug.casefold()
            )
        )
    ):
        return None
    return value


def _safe_permissions(value: dict[str, Any]) -> dict[str, str]:
    return {
        str(key)[:100]: str(raw)[:20]
        for key, raw in value.items()
        if isinstance(key, str) and isinstance(raw, str)
    }
