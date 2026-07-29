from __future__ import annotations

import json
import logging

from httpx import ASGITransport, AsyncClient

from app.core.logging import (
    REQUEST_LOGGER_NAME,
    RequestLoggingMiddleware,
    configure_logging,
)
from app.main import app


def test_configure_logging_is_idempotent_and_sets_level() -> None:
    logger = logging.getLogger("founderos")
    configure_logging("INFO")
    first_handler_count = len(logger.handlers)
    assert first_handler_count >= 1
    assert logger.level == logging.INFO

    configure_logging("WARNING")
    # Re-invocation must not stack duplicate handlers.
    assert len(logger.handlers) == first_handler_count
    assert logger.level == logging.WARNING

    # Unknown level names fall back to INFO instead of raising.
    configure_logging("not-a-real-level")
    assert logger.level == logging.INFO


def test_request_logging_middleware_logs_sanitized_line() -> None:
    # The founderos logger intentionally disables propagation, so attach a
    # capturing handler directly to the request logger rather than relying on
    # pytest's caplog (which hooks the root logger).
    configure_logging("INFO")
    request_logger = logging.getLogger(REQUEST_LOGGER_NAME)
    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _Capture(level=logging.INFO)
    request_logger.addHandler(handler)
    try:
        import anyio

        async def _call() -> int:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # A query string with a secret-like value must never be logged.
                response = await client.get("/health?token=SUPER_SECRET_VALUE")
                return response.status_code

        status = anyio.run(_call)
    finally:
        request_logger.removeHandler(handler)

    assert status in {200, 204}
    records = [r for r in captured if r.name == REQUEST_LOGGER_NAME]
    assert records, "expected at least one request log line"
    events = [json.loads(record.getMessage()) for record in records]
    event = events[-1]
    # The structured event carries only bounded request metadata.
    assert event["event"] == "request_complete"
    assert event["method"] == "GET"
    assert event["path"] == "/health"
    assert event["status"] == 200
    assert isinstance(event["duration_ms"], float)
    assert len(event["request_id"]) == 32
    # Sanitization: query values are never logged.
    blob = " ".join(record.getMessage() for record in records)
    assert "SUPER_SECRET_VALUE" not in blob
    assert "token=" not in blob


def test_middleware_passes_through_non_http_scopes() -> None:
    seen: dict[str, object] = {}

    async def app_stub(scope, receive, send):  # type: ignore[no-untyped-def]
        seen["type"] = scope.get("type")

    middleware = RequestLoggingMiddleware(app_stub)

    import anyio

    async def _run() -> None:
        await middleware({"type": "lifespan"}, _noop_receive, _noop_send)

    anyio.run(_run)
    assert seen["type"] == "lifespan"


async def _noop_receive():  # type: ignore[no-untyped-def]
    return {"type": "noop"}


async def _noop_send(_message):  # type: ignore[no-untyped-def]
    return None
