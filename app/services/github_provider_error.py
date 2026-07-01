from __future__ import annotations

from collections.abc import Mapping

import httpx


def safe_github_response_detail(
    response: httpx.Response,
    *,
    operation: str,
) -> str:
    """Return a sanitized GitHub provider error detail.

    Only includes bounded GitHub error message text, HTTP status, and safe
    rate-limit headers. It never includes request headers, authorization values,
    response bodies, or provider payload dumps.
    """

    status = response.status_code
    parts = [f"{operation} failed", f"http_{status}"]
    message = _response_message(response)
    if message:
        parts.append(f"message={message}")
    rate_limit_parts = _rate_limit_parts(response=response, message=message)
    parts.extend(rate_limit_parts)
    return "; ".join(parts)


def _response_message(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, Mapping):
        return None
    message = data.get("message")
    if not isinstance(message, str):
        return None
    stripped = " ".join(message.strip().split())
    return stripped[:300] if stripped else None


def _rate_limit_parts(*, response: httpx.Response, message: str | None) -> list[str]:
    headers = response.headers
    retry_after = _safe_header(headers.get("retry-after"))
    remaining = _safe_header(headers.get("x-ratelimit-remaining"))
    reset = _safe_header(headers.get("x-ratelimit-reset"))
    resource = _safe_header(headers.get("x-ratelimit-resource"))
    message_text = (message or "").casefold()
    rate_limited = (
        response.status_code == 429
        or retry_after is not None
        or remaining == "0"
        or "rate limit" in message_text
        or "secondary rate limit" in message_text
    )
    if not rate_limited:
        return []
    parts = ["rate_limited=true"]
    if retry_after is not None:
        parts.append(f"retry_after_seconds={retry_after}")
    if reset is not None:
        parts.append(f"rate_limit_reset_epoch={reset}")
    if remaining is not None:
        parts.append(f"rate_limit_remaining={remaining}")
    if resource is not None:
        parts.append(f"rate_limit_resource={resource}")
    return parts


def _safe_header(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:80]
