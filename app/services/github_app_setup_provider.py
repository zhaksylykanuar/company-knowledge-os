from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization

from app.services.github_app_credential_service import (
    GitHubAppOAuthCredential,
    GitHubAppSigningCredential,
)
from app.services.github_app_token_service import GitHubAppTokenError, build_github_app_jwt


GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_WEB_BASE_URL = "https://github.com"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_APP_REQUIRED_READ_PERMISSIONS = frozenset({"issues", "pull_requests"})
GITHUB_APP_ALLOWED_READ_PERMISSIONS = frozenset(
    {"issues", "metadata", "pull_requests"}
)

_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
_SLUG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,118}[A-Za-z0-9])?$")


class GitHubAppSetupProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, repr=False)
class GitHubManifestConversion:
    app_id: str
    app_slug: str
    app_name: str
    client_id: str
    client_secret: str
    private_key_pem: str
    webhook_secret: str | None
    html_url: str | None
    owner_login: str | None
    owner_id: str | None
    owner_type: str | None
    permissions: dict[str, str]


@dataclass(frozen=True)
class GitHubVerifiedInstallation:
    installation_id: str
    app_id: str
    account_login: str
    account_id: str | None
    account_type: str | None
    repository_selection: str
    permissions: dict[str, str]
    suspended: bool


@dataclass(frozen=True, repr=False)
class GitHubOAuthToken:
    access_token: str


async def exchange_manifest_code(code: str) -> GitHubManifestConversion:
    safe_code = _safe_code(code, error_code="manifest_code_invalid")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GITHUB_API_BASE_URL}/app-manifests/{safe_code}/conversions",
                headers=_json_headers(),
            )
    except httpx.HTTPError as exc:
        raise GitHubAppSetupProviderError("manifest_exchange_unavailable") from exc
    if not response.is_success:
        raise GitHubAppSetupProviderError("manifest_exchange_rejected")
    try:
        data = response.json()
    except ValueError as exc:
        raise GitHubAppSetupProviderError("manifest_response_invalid") from exc
    if not isinstance(data, Mapping):
        raise GitHubAppSetupProviderError("manifest_response_invalid")

    app_id = _required_identifier(data.get("id"), "manifest_response_invalid")
    app_name = _required_text(data.get("name"), 255, "manifest_response_invalid")
    client_id = _required_text(data.get("client_id"), 255, "manifest_response_invalid")
    client_secret = _required_text(
        data.get("client_secret"), 1000, "manifest_response_invalid"
    )
    private_key = _required_text(data.get("pem"), 16384, "manifest_response_invalid")
    _validate_private_key(private_key)
    html_url = _safe_github_url(data.get("html_url"))
    app_slug = _app_slug(data.get("slug"), html_url=html_url)
    owner = _mapping(data.get("owner"))
    permissions = _permissions(data.get("permissions"))
    ensure_read_only_permissions(permissions)
    return GitHubManifestConversion(
        app_id=app_id,
        app_slug=app_slug,
        app_name=app_name,
        client_id=client_id,
        client_secret=client_secret,
        private_key_pem=private_key,
        webhook_secret=_optional_text(data.get("webhook_secret"), 1000),
        html_url=html_url,
        owner_login=_optional_text(owner.get("login"), 255),
        owner_id=_optional_identifier(owner.get("id")),
        owner_type=_optional_text(owner.get("type"), 40),
        permissions=permissions,
    )


async def get_app_installation(
    *,
    credential: GitHubAppSigningCredential,
    installation_id: str,
) -> GitHubVerifiedInstallation:
    normalized_id = _required_identifier(
        installation_id, "installation_id_invalid"
    )
    try:
        jwt = build_github_app_jwt(credential=credential)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GITHUB_API_BASE_URL}/app/installations/{normalized_id}",
                headers=_json_headers(jwt),
            )
    except (GitHubAppTokenError, httpx.HTTPError) as exc:
        raise GitHubAppSetupProviderError("installation_verification_unavailable") from exc
    if not response.is_success:
        raise GitHubAppSetupProviderError("installation_verification_rejected")
    return _verified_installation(response, expected_id=normalized_id)


def build_oauth_authorization_url(
    *,
    credential: GitHubAppOAuthCredential,
    state: str,
    code_challenge: str,
) -> str:
    params = httpx.QueryParams(
        {
            "client_id": credential.client_id,
            "redirect_uri": credential.callback_url,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{GITHUB_WEB_BASE_URL}/login/oauth/authorize?{params}"


async def exchange_oauth_code(
    *,
    credential: GitHubAppOAuthCredential,
    code: str,
    code_verifier: str,
) -> GitHubOAuthToken:
    safe_code = _safe_code(code, error_code="oauth_code_invalid")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GITHUB_WEB_BASE_URL}/login/oauth/access_token",
                headers={"Accept": "application/json", "User-Agent": "founderOS"},
                data={
                    "client_id": credential.client_id,
                    "client_secret": credential.client_secret,
                    "code": safe_code,
                    "redirect_uri": credential.callback_url,
                    "code_verifier": code_verifier,
                },
            )
    except httpx.HTTPError as exc:
        raise GitHubAppSetupProviderError("oauth_exchange_unavailable") from exc
    if not response.is_success:
        raise GitHubAppSetupProviderError("oauth_exchange_rejected")
    try:
        data = response.json()
    except ValueError as exc:
        raise GitHubAppSetupProviderError("oauth_response_invalid") from exc
    if not isinstance(data, Mapping):
        raise GitHubAppSetupProviderError("oauth_response_invalid")
    if data.get("error"):
        raise GitHubAppSetupProviderError("oauth_exchange_rejected")
    access_token = _required_text(
        data.get("access_token"), 4096, "oauth_response_invalid"
    )
    return GitHubOAuthToken(access_token=access_token)


async def list_user_installations(
    *,
    access_token: str,
    per_page: int = 100,
    max_pages: int = 10,
) -> list[GitHubVerifiedInstallation]:
    installations: list[GitHubVerifiedInstallation] = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(1, max_pages + 1):
                response = await client.get(
                    f"{GITHUB_API_BASE_URL}/user/installations",
                    headers=_json_headers(access_token),
                    params={"per_page": per_page, "page": page},
                )
                if not response.is_success:
                    raise GitHubAppSetupProviderError(
                        "user_installations_verification_rejected"
                    )
                try:
                    data = response.json()
                except ValueError as exc:
                    raise GitHubAppSetupProviderError(
                        "user_installations_response_invalid"
                    ) from exc
                if not isinstance(data, Mapping) or not isinstance(
                    data.get("installations"), list
                ):
                    raise GitHubAppSetupProviderError(
                        "user_installations_response_invalid"
                    )
                raw_page = data["installations"]
                for item in raw_page:
                    if not isinstance(item, Mapping):
                        continue
                    installations.append(_verified_installation_data(item))
                if len(raw_page) < per_page:
                    return installations
    except GitHubAppSetupProviderError:
        raise
    except httpx.HTTPError as exc:
        raise GitHubAppSetupProviderError(
            "user_installations_verification_unavailable"
        ) from exc
    raise GitHubAppSetupProviderError("user_installations_pagination_limit")


async def revoke_oauth_token_best_effort(
    *,
    credential: GitHubAppOAuthCredential,
    access_token: str,
) -> None:
    """Revoke only this temporary token; never revoke the user's whole grant."""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.request(
                "DELETE",
                f"{GITHUB_API_BASE_URL}/applications/{credential.client_id}/token",
                auth=(credential.client_id, credential.client_secret),
                headers=_json_headers(),
                json={"access_token": access_token},
            )
    except httpx.HTTPError:
        return


def ensure_read_only_permissions(permissions: Mapping[str, str]) -> None:
    if any(name not in GITHUB_APP_ALLOWED_READ_PERMISSIONS for name in permissions):
        raise GitHubAppSetupProviderError("github_app_permissions_not_read_only")
    if any(value != "read" for value in permissions.values()) or any(
        permissions.get(name) != "read"
        for name in GITHUB_APP_REQUIRED_READ_PERMISSIONS
    ):
        raise GitHubAppSetupProviderError("github_app_permissions_not_read_only")


def find_verified_user_installation(
    *,
    installations: list[GitHubVerifiedInstallation],
    installation_id: str,
    app_id: str,
) -> GitHubVerifiedInstallation:
    for installation in installations:
        if installation.installation_id != installation_id:
            continue
        if installation.app_id != app_id or installation.suspended:
            break
        ensure_read_only_permissions(installation.permissions)
        return installation
    raise GitHubAppSetupProviderError("installation_not_available_to_user")


def _verified_installation(
    response: httpx.Response,
    *,
    expected_id: str,
) -> GitHubVerifiedInstallation:
    try:
        data = response.json()
    except ValueError as exc:
        raise GitHubAppSetupProviderError("installation_response_invalid") from exc
    if not isinstance(data, Mapping):
        raise GitHubAppSetupProviderError("installation_response_invalid")
    installation = _verified_installation_data(data)
    if installation.installation_id != expected_id:
        raise GitHubAppSetupProviderError("installation_response_invalid")
    ensure_read_only_permissions(installation.permissions)
    return installation


def _verified_installation_data(data: Mapping[str, Any]) -> GitHubVerifiedInstallation:
    account = _mapping(data.get("account"))
    return GitHubVerifiedInstallation(
        installation_id=_required_identifier(
            data.get("id"), "installation_response_invalid"
        ),
        app_id=_required_identifier(
            data.get("app_id"), "installation_response_invalid"
        ),
        account_login=_required_text(
            account.get("login"), 255, "installation_response_invalid"
        ),
        account_id=_optional_identifier(account.get("id")),
        account_type=_optional_text(account.get("type"), 40),
        repository_selection=_repository_selection(data.get("repository_selection")),
        permissions=_permissions(data.get("permissions")),
        suspended=data.get("suspended_at") is not None,
    )


def _json_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "founderOS",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_code(value: Any, *, error_code: str) -> str:
    if not isinstance(value, str) or _CODE_RE.fullmatch(value) is None:
        raise GitHubAppSetupProviderError(error_code)
    return value


def _required_identifier(value: Any, error_code: str) -> str:
    if isinstance(value, bool):
        raise GitHubAppSetupProviderError(error_code)
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        raise GitHubAppSetupProviderError(error_code)
    text = value.strip()
    if not text or len(text) > 100 or not text.isdigit():
        raise GitHubAppSetupProviderError(error_code)
    return text


def _optional_identifier(value: Any) -> str | None:
    try:
        return _required_identifier(value, "identifier_invalid")
    except GitHubAppSetupProviderError:
        return None


def _required_text(value: Any, max_length: int, error_code: str) -> str:
    if not isinstance(value, str):
        raise GitHubAppSetupProviderError(error_code)
    text = value.strip()
    if not text or len(text) > max_length:
        raise GitHubAppSetupProviderError(error_code)
    return text


def _optional_text(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:max_length]


def _app_slug(value: Any, *, html_url: str | None) -> str:
    slug = value.strip() if isinstance(value, str) and value.strip() else None
    if slug is None and html_url:
        slug = html_url.rstrip("/").rsplit("/", 1)[-1]
    if slug is None or len(slug) > 120 or _SLUG_RE.fullmatch(slug) is None:
        raise GitHubAppSetupProviderError("manifest_response_invalid")
    return slug


def _safe_github_url(value: Any) -> str | None:
    text = _optional_text(value, 1000)
    if text and text.startswith("https://github.com/apps/") and "@" not in text:
        return text
    return None


def _permissions(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key)[:100]: raw
        for key, raw in value.items()
        if isinstance(key, str) and isinstance(raw, str)
    }


def _repository_selection(value: Any) -> str:
    return value if value in {"all", "selected"} else "unknown"


def _validate_private_key(value: str) -> None:
    try:
        serialization.load_pem_private_key(value.encode("utf-8"), password=None)
    except (TypeError, ValueError) as exc:
        raise GitHubAppSetupProviderError("manifest_private_key_invalid") from exc
