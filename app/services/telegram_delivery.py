from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

TELEGRAM_MESSAGE_CHAR_LIMIT = 4096
DEFAULT_TELEGRAM_CHUNK_SIZE = 3900
TELEGRAM_API_BASE_URL = "https://api.telegram.org"

TelegramSendMessageTransport = Callable[
    [str, Mapping[str, str]],
    Awaitable[Mapping[str, Any]],
]


@dataclass(frozen=True)
class TelegramDeliveryResult:
    success: bool
    attempted_chunks: int
    sent_chunks: int
    message_ids: tuple[int | str, ...] = ()
    error_summary: str | None = None


def _require_non_empty(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    return cleaned


def split_telegram_plain_text(
    text: str,
    *,
    max_chars: int = DEFAULT_TELEGRAM_CHUNK_SIZE,
) -> list[str]:
    """Split rendered plain text into Telegram-safe chunks.

    Splitting is deterministic, prefers line boundaries, and only breaks a line
    when that line is longer than the configured chunk size.
    """

    if max_chars < 1 or max_chars > TELEGRAM_MESSAGE_CHAR_LIMIT:
        raise ValueError("max_chars must be between 1 and 4096")
    if not text.strip():
        raise ValueError("text must not be empty")

    chunks: list[str] = []
    current = ""

    for line in text.splitlines(keepends=True):
        if len(line) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                line[index : index + max_chars]
                for index in range(0, len(line), max_chars)
            )
            continue

        if len(current) + len(line) <= max_chars:
            current += line
        else:
            if current:
                chunks.append(current)
            current = line

    if current:
        chunks.append(current)

    return chunks


def build_telegram_send_message_payload(
    *,
    chat_id: str,
    text: str,
) -> dict[str, str]:
    if text == "":
        raise ValueError("text must not be empty")
    if len(text) > TELEGRAM_MESSAGE_CHAR_LIMIT:
        raise ValueError("text must be at most 4096 characters")

    return {
        "chat_id": _require_non_empty(chat_id, field_name="chat_id"),
        "text": text,
    }


def _send_message_url(bot_token: str) -> str:
    return f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendMessage"


def _safe_failure_summary(response: Mapping[str, Any], *, bot_token: str) -> str:
    error_code = response.get("error_code")
    if error_code is not None:
        summary = f"Telegram API sendMessage failed with error_code {error_code}"
    else:
        summary = "Telegram API sendMessage failed"

    return summary.replace(bot_token, "[redacted]")


def _message_id_from_response(response: Mapping[str, Any]) -> int | str | None:
    result = response.get("result")
    if not isinstance(result, Mapping):
        return None

    message_id = result.get("message_id")
    if isinstance(message_id, (int, str)):
        return message_id

    return None


async def _httpx_post_json(url: str, payload: Mapping[str, str]) -> Mapping[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=dict(payload))

    try:
        body = response.json()
    except ValueError:
        body = None

    if not isinstance(body, Mapping):
        return {
            "ok": False,
            "error_code": response.status_code,
        }

    result: dict[str, Any] = {str(key): value for key, value in body.items()}
    if response.status_code >= 400:
        result["ok"] = False
        result.setdefault("error_code", response.status_code)

    return result


async def send_telegram_plain_text(
    *,
    bot_token: str,
    chat_id: str,
    text: str,
    transport: TelegramSendMessageTransport | None = None,
    chunk_size: int = DEFAULT_TELEGRAM_CHUNK_SIZE,
) -> TelegramDeliveryResult:
    token = _require_non_empty(bot_token, field_name="bot_token")
    cleaned_chat_id = _require_non_empty(chat_id, field_name="chat_id")
    chunks = split_telegram_plain_text(text, max_chars=chunk_size)
    post_json = transport or _httpx_post_json
    url = _send_message_url(token)

    message_ids: list[int | str] = []
    attempted_chunks = 0
    sent_chunks = 0

    for chunk in chunks:
        attempted_chunks += 1
        payload = build_telegram_send_message_payload(
            chat_id=cleaned_chat_id,
            text=chunk,
        )

        try:
            response = await post_json(url, payload)
        except Exception:
            return TelegramDeliveryResult(
                success=False,
                attempted_chunks=attempted_chunks,
                sent_chunks=sent_chunks,
                message_ids=tuple(message_ids),
                error_summary="Telegram API sendMessage request failed",
            )

        if response.get("ok") is not True:
            return TelegramDeliveryResult(
                success=False,
                attempted_chunks=attempted_chunks,
                sent_chunks=sent_chunks,
                message_ids=tuple(message_ids),
                error_summary=_safe_failure_summary(response, bot_token=token),
            )

        sent_chunks += 1
        message_id = _message_id_from_response(response)
        if message_id is not None:
            message_ids.append(message_id)

    return TelegramDeliveryResult(
        success=True,
        attempted_chunks=attempted_chunks,
        sent_chunks=sent_chunks,
        message_ids=tuple(message_ids),
    )
