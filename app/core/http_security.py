"""Scoped HTTP response security policies."""

from __future__ import annotations

from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import resolved_cors_allowed_origins, settings

PRIVATE_NO_STORE = "private, no-store"
_WORKSPACE_API_PREFIX = "/api/v1/workspaces/"
_CONNECTORS_PATH_SEGMENT = "/connectors"
_LOCAL_LIKE_ENVS = frozenset({"local", "dev", "development", "test", "testing"})
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_PUBLIC_AUTH_COOKIE_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/enroll",
        "/api/v1/auth/setup-password",
    }
)
_LOCAL_DOC_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})
_BASE_SECURITY_HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": (
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
    ),
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
_HOSTED_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'none'"
    ),
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


def _is_local_like() -> bool:
    return settings.app_env.strip().casefold() in _LOCAL_LIKE_ENVS


def _has_session_cookie(headers: Headers) -> bool:
    raw_cookie = headers.get("cookie")
    if not raw_cookie:
        return False
    parsed = SimpleCookie()
    try:
        parsed.load(raw_cookie)
    except CookieError:
        return False
    return settings.session_cookie_name in parsed


def _origin_from_header(value: str, *, allow_path: bool) -> str | None:
    try:
        parsed = urlsplit(value.strip())
        _ = parsed.port
    except (UnicodeError, ValueError):
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (not allow_path and (parsed.path not in {"", "/"} or parsed.query))
    ):
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _request_origin(headers: Headers) -> str | None:
    origin = headers.get("origin")
    if origin is not None:
        return _origin_from_header(origin, allow_path=False)
    referer = headers.get("referer")
    if referer is not None:
        return _origin_from_header(referer, allow_path=True)
    return None


def _requires_origin_check(scope: Scope, headers: Headers) -> bool:
    if str(scope.get("method", "")).upper() not in _MUTATING_METHODS:
        return False
    path = str(scope.get("path", ""))
    return _has_session_cookie(headers) or path in _PUBLIC_AUTH_COOKIE_PATHS


class HttpSecurityMiddleware:
    """Apply hosted headers, local-only docs and browser Origin enforcement."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        local_like = _is_local_like()

        async def send_with_security_headers(message: Message) -> None:
            if message.get("type") == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in _BASE_SECURITY_HEADERS.items():
                    response_headers[name] = value
                if not local_like:
                    for name, value in _HOSTED_SECURITY_HEADERS.items():
                        response_headers[name] = value
                if path.startswith("/api/v1/auth/"):
                    response_headers["Cache-Control"] = PRIVATE_NO_STORE
            await send(message)

        if not local_like and path in _LOCAL_DOC_PATHS:
            await JSONResponse(
                status_code=404,
                content={"detail": "Not Found"},
            )(scope, receive, send_with_security_headers)
            return

        headers = Headers(scope=scope)
        if _requires_origin_check(scope, headers):
            request_origin = _request_origin(headers)
            allowed_origins = set(resolved_cors_allowed_origins(settings))
            if request_origin is None:
                if not local_like:
                    await JSONResponse(
                        status_code=403,
                        content={"detail": "browser origin validation failed"},
                    )(scope, receive, send_with_security_headers)
                    return
            elif request_origin not in allowed_origins:
                await JSONResponse(
                    status_code=403,
                    content={"detail": "browser origin validation failed"},
                )(scope, receive, send_with_security_headers)
                return

        await self._app(scope, receive, send_with_security_headers)


class ConnectorResponseNoStoreMiddleware:
    """Prevent caching for every workspace connector response.

    Applying the policy at the ASGI boundary also covers responses created
    before endpoint execution, including authentication, authorization and
    request-validation failures.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        path = str(scope.get("path", ""))
        protect_response = bool(
            scope.get("type") == "http"
            and path.startswith(_WORKSPACE_API_PREFIX)
            and _CONNECTORS_PATH_SEGMENT in path
        )
        if not protect_response:
            await self._app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = PRIVATE_NO_STORE
            await send(message)

        await self._app(scope, receive, send_wrapper)
