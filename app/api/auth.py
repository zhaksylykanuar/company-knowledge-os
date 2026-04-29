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


def validate_api_key(*, config: ApiAuthConfig, provided_key: str | None) -> None:
    if not config.api_auth_enabled:
        return

    expected_key = _configured_key(config)
    if expected_key is None or not provided_key:
        _reject_api_auth()

    if not compare_digest(provided_key.encode("utf-8"), expected_key.encode("utf-8")):
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
