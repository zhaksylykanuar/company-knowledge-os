"""Basic application logging (MVP §1.5 "basic logging").

This module provides two small, deterministic pieces:

- ``configure_logging`` sets up a single stream handler with a stable,
  machine-greppable format and an env-driven level (``FOUNDEROS_LOG_LEVEL`` /
  ``LOG_LEVEL``, default ``INFO``). It is idempotent so repeated app startups in
  tests do not attach duplicate handlers.
- ``RequestLoggingMiddleware`` logs one line per HTTP request with the method,
  the *path only* (never the query string), the response status code, and the
  wall-clock duration in milliseconds.

Sanitization boundary (AGENTS.md / SECURITY_BASELINE.md): the request logger
records only method, URL path, status, and duration. It never logs query-string
values, request/response bodies, headers, cookies, tokens, API keys, or provider
payloads, so no secret-bearing data can leak into logs.
"""

from __future__ import annotations

import logging
import time
from starlette.types import ASGIApp

REQUEST_LOGGER_NAME = "founderos.request"
_APP_LOGGER_NAME = "founderos"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _resolve_level(level_name: str | None) -> int:
    candidate = (level_name or "INFO").strip().upper()
    resolved = logging.getLevelName(candidate)
    # ``getLevelName`` returns an ``int`` for known names and a ``str`` for
    # unknown ones; fall back to INFO for anything unrecognized.
    return resolved if isinstance(resolved, int) else logging.INFO


def configure_logging(level_name: str | None = "INFO") -> None:
    """Idempotently configure the founderOS application logger.

    A dedicated ``founderos`` logger is used (rather than mutating the root
    logger) so the configuration is predictable across app startups and test
    runs. Re-invocation only updates the level and never stacks handlers.
    """

    level = _resolve_level(level_name)
    logger = logging.getLogger(_APP_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)
    else:
        for handler in logger.handlers:
            handler.setLevel(logging.NOTSET)


class RequestLoggingMiddleware:
    """ASGI middleware that logs sanitized request/response metadata.

    Only ``method``, URL ``path`` (no query string), status code, and duration
    in milliseconds are logged. Bodies, headers, cookies, and query values are
    never read or logged, so secrets cannot leak through this path.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._logger = logging.getLogger(REQUEST_LOGGER_NAME)

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        method = str(scope.get("method", "-"))
        path = str(scope.get("path", "-"))
        started_at = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):  # type: ignore[no-untyped-def]
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", status_code))
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000.0
            self._logger.info(
                "request method=%s path=%s status=%s duration_ms=%.1f",
                method,
                path,
                status_code,
                duration_ms,
            )
