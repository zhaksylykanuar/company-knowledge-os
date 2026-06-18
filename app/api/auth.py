from collections.abc import Awaitable, Callable
from hmac import compare_digest
from typing import NoReturn, Protocol

from fastapi import HTTPException, Request, status
from pydantic import SecretStr

from app.core.config import settings

API_AUTH_FAILURE_DETAIL = "API authentication failed"


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
