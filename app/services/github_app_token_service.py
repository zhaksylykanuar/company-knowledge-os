from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from pydantic import SecretStr

from app.core.config import Settings, settings

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_APP_JWT_LIFETIME_SECONDS = 540
GITHUB_APP_JWT_BACKDATE_SECONDS = 60


class GitHubAppTokenError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class GitHubInstallationAccessToken:
    token: str
    expires_at: str | None = None


async def mint_installation_access_token(
    *,
    installation_id: str,
    config: Settings = settings,
) -> GitHubInstallationAccessToken:
    """Mint a short-lived GitHub App installation access token just-in-time.

    The returned token is intentionally an in-memory value for the caller to use
    immediately for read-only provider calls. It must not be persisted.
    """

    normalized_installation_id = _safe_installation_id(installation_id)
    app_jwt = build_github_app_jwt(config=config)
    url = (
        f"{GITHUB_API_BASE_URL}/app/installations/"
        f"{normalized_installation_id}/access_tokens"
    )
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "founderOS",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers)
    except httpx.HTTPError as exc:
        raise GitHubAppTokenError("github app token request failed") from exc

    if response.status_code < 200 or response.status_code >= 300:
        raise GitHubAppTokenError(_safe_response_detail(response))

    data = response.json()
    if not isinstance(data, dict):
        raise GitHubAppTokenError("github app token response was not an object")
    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        raise GitHubAppTokenError("github app token response did not include a token")
    expires_at = data.get("expires_at")
    return GitHubInstallationAccessToken(
        token=token.strip(),
        expires_at=expires_at.strip()[:100] if isinstance(expires_at, str) else None,
    )


def build_github_app_jwt(
    *,
    config: Settings = settings,
    now: datetime | None = None,
) -> str:
    app_id = _safe_app_id(config.github_app_id)
    private_key = _load_private_key(config)
    issued_at = int(
        ((now or datetime.now(timezone.utc)) - timedelta(seconds=GITHUB_APP_JWT_BACKDATE_SECONDS)).timestamp()
    )
    expires_at = issued_at + GITHUB_APP_JWT_LIFETIME_SECONDS
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iat": issued_at,
        "exp": expires_at,
        "iss": app_id,
    }
    signing_input = (
        f"{_base64url_json(header)}.{_base64url_json(payload)}".encode("ascii")
    )
    signature = private_key.sign(
        signing_input,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return f"{signing_input.decode('ascii')}.{_base64url_bytes(signature)}"


def _load_private_key(config: Settings) -> Any:
    private_key_pem = _secret_value(config.github_app_private_key)
    if private_key_pem is None and config.github_app_private_key_path:
        try:
            private_key_pem = Path(config.github_app_private_key_path).read_text(
                encoding="utf-8"
            )
        except OSError as exc:
            raise GitHubAppTokenError(
                "github app private key path could not be read"
            ) from exc
    if private_key_pem is None:
        raise GitHubAppTokenError(
            "FOUNDEROS_GITHUB_APP_PRIVATE_KEY or "
            "FOUNDEROS_GITHUB_APP_PRIVATE_KEY_PATH is required"
        )
    try:
        return serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=None,
        )
    except ValueError as exc:
        raise GitHubAppTokenError("github app private key is invalid") from exc


def _safe_app_id(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GitHubAppTokenError("FOUNDEROS_GITHUB_APP_ID is required")
    return value.strip()[:100]


def _safe_installation_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GitHubAppTokenError("github app installation_id is required")
    return value.strip()[:100]


def _secret_value(value: SecretStr | str | None) -> str | None:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _base64url_json(value: dict[str, Any]) -> str:
    return _base64url_bytes(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _base64url_bytes(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _safe_response_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        message = data.get("message")
        if isinstance(message, str) and message.strip():
            return f"github app token request failed: {message.strip()[:300]}"
    return f"github app token request failed: http_{response.status_code}"
