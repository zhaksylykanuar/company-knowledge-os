from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hmac import compare_digest
from typing import NoReturn, Protocol
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from pydantic import SecretStr

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import User
from app.services.session_service import validate_session

API_AUTH_FAILURE_DETAIL = "API authentication failed"
AUTH_MODE_OPERATOR_API_KEY = "operator_api_key"
AUTH_MODE_SESSION = "session"

# Environments where running with API auth disabled is an accepted developer
# convenience. Any other environment (private beta, staging, production, ...)
# must boot fail-closed or startup is aborted — see enforce_fail_closed_auth.
LOCAL_LIKE_APP_ENVS = frozenset({"local", "dev", "development", "test", "testing"})


class FailClosedAuthError(RuntimeError):
    """Raised at startup when a non-local environment is not fail-closed."""


@dataclass(frozen=True)
class CurrentActor:
    auth_mode: str
    user_id: UUID | None
    email: str | None
    is_operator: bool


class ApiAuthConfig(Protocol):
    api_auth_enabled: bool
    api_auth_key: SecretStr | str | None
    api_auth_header_name: str


def _reject_api_auth() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=API_AUTH_FAILURE_DETAIL,
    )


def _configured_key(config: ApiAuthConfig) -> str | None:
    key = config.api_auth_key
    if isinstance(key, SecretStr):
        key = key.get_secret_value()

    if not isinstance(key, str):
        return None

    stripped = key.strip()
    return stripped or None


def _configured_header_name(config: ApiAuthConfig) -> str | None:
    header_name = config.api_auth_header_name
    if not isinstance(header_name, str):
        return None

    stripped = header_name.strip()
    return stripped or None


def _accepted_keys(config: ApiAuthConfig) -> list[str]:
    """Every key the backend accepts: the primary api_auth_key, any keys in
    FOUNDEROS_API_KEYS, and — only in local with the browser-dev flag on —
    the local dev key. Read via getattr so minimal config objects still work.
    """

    keys: list[str] = []
    primary = _configured_key(config)
    if primary:
        keys.append(primary)
    raw = getattr(config, "api_keys", None)
    if isinstance(raw, str):
        for part in raw.split(","):
            part = part.strip()
            if part:
                keys.append(part)
    if (
        getattr(config, "app_env", None) == "local"
        and bool(getattr(config, "enable_browser_dev_config", False))
    ):
        dev = getattr(config, "dev_api_key", None)
        if isinstance(dev, str) and dev.strip():
            keys.append(dev.strip())
    return keys


def validate_api_key(*, config: ApiAuthConfig, provided_key: str | None) -> None:
    if not config.api_auth_enabled:
        return

    accepted = _accepted_keys(config)
    if not accepted or not provided_key:
        _reject_api_auth()

    provided = provided_key.encode("utf-8")
    if not any(compare_digest(provided, key.encode("utf-8")) for key in accepted):
        _reject_api_auth()


def build_require_api_key(config: ApiAuthConfig) -> Callable[[Request], Awaitable[None]]:
    async def require_api_key_for_config(request: Request) -> None:
        header_name = _configured_header_name(config)
        provided_key = request.headers.get(header_name) if header_name is not None else None
        validate_api_key(config=config, provided_key=provided_key)

    return require_api_key_for_config


async def require_api_key(request: Request) -> None:
    header_name = _configured_header_name(settings)
    provided_key = request.headers.get(header_name) if header_name is not None else None
    validate_api_key(config=settings, provided_key=provided_key)


async def _user_from_session_cookie(request: Request) -> User | None:
    """Resolve the logged-in User from the browser session cookie, or None.

    Validation (revoked/expired/unknown) and the last_seen_at bump live in
    session_service; we commit so the bump persists.
    """

    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None
    async with AsyncSessionLocal() as db:
        user = await validate_session(db, raw_token)
        await db.commit()
    return user


async def require_session(request: Request) -> User:
    """Browser-only dependency: require a valid session cookie, else 401."""

    user = await _user_from_session_cookie(request)
    if user is None:
        _reject_api_auth()
    return user


async def get_current_actor(request: Request) -> CurrentActor:
    """Resolve the request actor: browser session cookie OR operator API key.

    The session cookie (browser) takes precedence when present and valid; we
    fall back to the operator API key (machine/admin/CI), which preserves the
    existing "auth disabled in local" no-op behavior. This is how the two auth
    modes coexist on the shared product routes.
    """

    user = await _user_from_session_cookie(request)
    if user is not None:
        return CurrentActor(
            auth_mode=AUTH_MODE_SESSION,
            user_id=user.id,
            email=user.email,
            is_operator=False,
        )

    await require_api_key(request)
    return CurrentActor(
        auth_mode=AUTH_MODE_OPERATOR_API_KEY,
        user_id=None,
        email=None,
        is_operator=True,
    )


async def require_operator_or_user(
    actor: CurrentActor = Depends(get_current_actor),
) -> CurrentActor:
    if not actor.is_operator and actor.user_id is None:
        _reject_api_auth()
    return actor


def _normalized_app_env(config: object) -> str:
    app_env = getattr(config, "app_env", "") or ""
    return app_env.strip().casefold() if isinstance(app_env, str) else ""


def is_local_like_env(config: object) -> bool:
    """True when the environment may run with API auth disabled (local/dev)."""

    return _normalized_app_env(config) in LOCAL_LIKE_APP_ENVS


def _has_configured_api_key(config: object) -> bool:
    if _configured_key(config):  # primary api_auth_key
        return True
    raw = getattr(config, "api_keys", None)
    return isinstance(raw, str) and any(part.strip() for part in raw.split(","))


def enforce_fail_closed_auth(config: object) -> None:
    """Abort startup when a non-local environment would run fail-open.

    Local-like environments (APP_ENV=local/dev/test) may keep auth disabled
    for developer convenience. Every other environment must boot with auth
    enabled and at least one configured key; otherwise a single forgotten
    flag would expose the full operator surface to anonymous callers.

    Only env-var names are surfaced in the error — never secret values — so a
    misconfiguration is actionable without leaking key material.
    """

    if is_local_like_env(config):
        return
    if not getattr(config, "api_auth_enabled", False):
        raise FailClosedAuthError(
            "Refusing to start: API authentication is disabled in a non-local "
            "environment. Set APP_ENV=local for local development, or enable "
            "auth by setting API_AUTH_ENABLED and configuring API_AUTH_KEY "
            "(or FOUNDEROS_API_KEYS) before deploying."
        )
    if not _has_configured_api_key(config):
        raise FailClosedAuthError(
            "Refusing to start: API authentication is enabled in a non-local "
            "environment but no API key is configured. Set API_AUTH_KEY or "
            "FOUNDEROS_API_KEYS before deploying."
        )
