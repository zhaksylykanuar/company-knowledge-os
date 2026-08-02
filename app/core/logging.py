"""Sanitized structured request logging and bounded runtime counters.

This module provides three deterministic pieces:

- ``configure_logging`` activates structlog JSON events over the standard
  logging backend without stacking handlers.
- ``RequestLoggingMiddleware`` emits one sanitized completion event and a
  server-generated correlation ID per HTTP request.
- ``runtime_request_metrics`` keeps low-cardinality process counters for the
  operator health surface. It stores no paths, users, workspaces, or payloads.

Sanitization boundary (AGENTS.md / SECURITY_BASELINE.md): the request logger
records only a server-generated request ID, method, URL path, status, and
duration. It never logs query-string values, request/response bodies, headers,
cookies, tokens, API keys, or provider payloads.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from uuid import uuid4

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_LOGGER_NAME = "founderos.request"
_APP_LOGGER_NAME = "founderos"
REQUEST_ID_HEADER = "X-Request-ID"
_LOG_FORMAT = "%(message)s"


class RuntimeRequestMetrics:
    """Low-cardinality process metrics without request labels or private data."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._started_at = time.monotonic()
        self._requests_total = 0
        self._responses_4xx_total = 0
        self._responses_5xx_total = 0
        self._in_flight = 0

    def begin(self) -> None:
        with self._lock:
            self._in_flight += 1

    def complete(self, status_code: int) -> None:
        with self._lock:
            self._requests_total += 1
            self._in_flight = max(0, self._in_flight - 1)
            if 400 <= status_code < 500:
                self._responses_4xx_total += 1
            elif status_code >= 500:
                self._responses_5xx_total += 1

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "uptime_seconds": round(
                    max(0.0, time.monotonic() - self._started_at),
                    3,
                ),
                "requests_total": self._requests_total,
                "responses_4xx_total": self._responses_4xx_total,
                "responses_5xx_total": self._responses_5xx_total,
                "in_flight": self._in_flight,
            }

    def reset_for_tests(self) -> None:
        with self._lock:
            self._started_at = time.monotonic()
            self._requests_total = 0
            self._responses_4xx_total = 0
            self._responses_5xx_total = 0
            self._in_flight = 0


runtime_request_metrics = RuntimeRequestMetrics()


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
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(stream_handler)
    else:
        for existing_handler in logger.handlers:
            existing_handler.setLevel(logging.NOTSET)
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.EventRenamer("event"),
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


class RequestLoggingMiddleware:
    """ASGI middleware that logs sanitized request/response metadata.

    Only ``method``, URL ``path`` (no query string), status code, and duration
    in milliseconds are logged. Bodies, headers, cookies, and query values are
    never read or logged, so secrets cannot leak through this path.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._logger = structlog.get_logger(REQUEST_LOGGER_NAME)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        method = str(scope.get("method", "-"))
        path = str(scope.get("path", "-"))
        request_id = uuid4().hex
        started_at = time.perf_counter()
        status_code = 500
        runtime_request_metrics.begin()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", status_code))
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000.0
            runtime_request_metrics.complete(status_code)
            self._logger.info(
                "request_complete",
                request_id=request_id,
                method=method,
                path=path,
                status=status_code,
                duration_ms=round(duration_ms, 1),
            )
