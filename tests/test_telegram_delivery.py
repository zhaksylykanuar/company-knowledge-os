import builtins
from collections.abc import Mapping
from typing import Any

import pytest

import app.services.telegram_delivery as telegram_delivery
from app.services.provider_execution_guard import (
    LIVE_PROVIDER_EXECUTION_ACK,
    PROVIDER_EXECUTION_ACK_REQUIRED,
    PROVIDER_EXECUTION_DEFAULT_DENIED,
)
from app.services.telegram_delivery import (
    TELEGRAM_MESSAGE_CHAR_LIMIT,
    build_telegram_send_message_payload,
    send_telegram_plain_text,
    split_telegram_plain_text,
)


class FakeTelegramTransport:
    def __init__(self, responses: list[Mapping[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def __call__(self, url: str, payload: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append((url, dict(payload)))
        if self.responses:
            return self.responses.pop(0)

        return {
            "ok": True,
            "result": {
                "message_id": len(self.calls),
            },
        }


async def test_send_telegram_plain_text_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="text must not be empty"):
        await send_telegram_plain_text(
            bot_token="TELEGRAM_BOT_TOKEN",
            chat_id="TELEGRAM_CHAT_ID",
            text="  \n\t  ",
            transport=FakeTelegramTransport(),
        )


async def test_send_telegram_plain_text_rejects_missing_bot_token() -> None:
    with pytest.raises(ValueError, match="bot_token must not be empty"):
        await send_telegram_plain_text(
            bot_token=" ",
            chat_id="TELEGRAM_CHAT_ID",
            text="Source activity digest",
            transport=FakeTelegramTransport(),
        )


async def test_send_telegram_plain_text_rejects_missing_chat_id() -> None:
    with pytest.raises(ValueError, match="chat_id must not be empty"):
        await send_telegram_plain_text(
            bot_token="TELEGRAM_BOT_TOKEN",
            chat_id=" ",
            text="Source activity digest",
            transport=FakeTelegramTransport(),
        )


async def test_send_telegram_plain_text_sends_short_text_once_with_plain_payload() -> None:
    transport = FakeTelegramTransport(
        [
            {
                "ok": True,
                "result": {
                    "message_id": 101,
                },
            }
        ]
    )

    result = await send_telegram_plain_text(
        bot_token="TELEGRAM_BOT_TOKEN",
        chat_id="TELEGRAM_CHAT_ID",
        text="Source activity digest",
        transport=transport,
    )

    assert result.success is True
    assert result.attempted_chunks == 1
    assert result.sent_chunks == 1
    assert result.message_ids == (101,)
    assert len(transport.calls) == 1

    url, payload = transport.calls[0]
    assert url.endswith("/sendMessage")
    assert payload == {
        "chat_id": "TELEGRAM_CHAT_ID",
        "text": "Source activity digest",
    }
    assert "parse_mode" not in payload
    assert "TELEGRAM_BOT_TOKEN" not in repr(result)


def test_split_telegram_plain_text_splits_long_text_within_limit() -> None:
    text = "x" * 45

    chunks = split_telegram_plain_text(text, max_chars=20)

    assert chunks == [
        "x" * 20,
        "x" * 20,
        "x" * 5,
    ]
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert "".join(chunks) == text


def test_split_telegram_plain_text_prefers_line_boundaries() -> None:
    text = "first line\nsecond line\nthird line\n"

    chunks = split_telegram_plain_text(text, max_chars=23)

    assert chunks == [
        "first line\nsecond line\n",
        "third line\n",
    ]
    assert "".join(chunks) == text


def test_split_telegram_plain_text_rejects_chunks_over_telegram_limit() -> None:
    with pytest.raises(ValueError, match="max_chars must be between 1 and 4096"):
        split_telegram_plain_text("Source activity digest", max_chars=TELEGRAM_MESSAGE_CHAR_LIMIT + 1)


def test_build_telegram_send_message_payload_does_not_include_parse_mode() -> None:
    payload = build_telegram_send_message_payload(
        chat_id="TELEGRAM_CHAT_ID",
        text="Source activity digest",
    )

    assert payload == {
        "chat_id": "TELEGRAM_CHAT_ID",
        "text": "Source activity digest",
    }
    assert "parse_mode" not in payload


async def test_send_telegram_plain_text_calls_fake_transport_once_per_chunk_in_order() -> None:
    text = "first line\nsecond line\nthird line\n"
    expected_chunks = split_telegram_plain_text(text, max_chars=23)
    transport = FakeTelegramTransport()

    result = await send_telegram_plain_text(
        bot_token="TELEGRAM_BOT_TOKEN",
        chat_id="TELEGRAM_CHAT_ID",
        text=text,
        transport=transport,
        chunk_size=23,
    )

    assert result.success is True
    assert result.attempted_chunks == 2
    assert result.sent_chunks == 2
    assert result.message_ids == (1, 2)
    assert [payload["text"] for _, payload in transport.calls] == expected_chunks


async def test_send_telegram_plain_text_default_denies_live_provider_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_httpx_post_json(
        url: str,
        payload: Mapping[str, str],
    ) -> Mapping[str, Any]:
        raise AssertionError("default-denied live provider path must not call network")

    monkeypatch.setattr(telegram_delivery, "_httpx_post_json", forbidden_httpx_post_json)

    result = await send_telegram_plain_text(
        bot_token="TELEGRAM_BOT_TOKEN",
        chat_id="TELEGRAM_CHAT_ID",
        text="Source activity digest",
    )

    assert result.success is False
    assert result.attempted_chunks == 0
    assert result.sent_chunks == 0
    assert result.error_summary == PROVIDER_EXECUTION_DEFAULT_DENIED
    assert "TELEGRAM_BOT_TOKEN" not in repr(result)


async def test_send_telegram_plain_text_requires_exact_live_provider_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_httpx_post_json(
        url: str,
        payload: Mapping[str, str],
    ) -> Mapping[str, Any]:
        raise AssertionError("missing live provider ack must not call network")

    monkeypatch.setattr(telegram_delivery, "_httpx_post_json", forbidden_httpx_post_json)

    result = await send_telegram_plain_text(
        bot_token="TELEGRAM_BOT_TOKEN",
        chat_id="TELEGRAM_CHAT_ID",
        text="Source activity digest",
        allow_live_provider_execution=True,
        provider_execution_ack="wrong_ack",
    )

    assert result.success is False
    assert result.attempted_chunks == 0
    assert result.sent_chunks == 0
    assert result.error_summary == PROVIDER_EXECUTION_ACK_REQUIRED
    assert "TELEGRAM_BOT_TOKEN" not in repr(result)


async def test_send_telegram_plain_text_live_provider_ack_uses_http_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    async def fake_httpx_post_json(
        url: str,
        payload: Mapping[str, str],
    ) -> Mapping[str, Any]:
        calls.append((url, dict(payload)))
        return {
            "ok": True,
            "result": {
                "message_id": "message-1",
            },
        }

    monkeypatch.setattr(telegram_delivery, "_httpx_post_json", fake_httpx_post_json)

    result = await send_telegram_plain_text(
        bot_token="TELEGRAM_BOT_TOKEN",
        chat_id="TELEGRAM_CHAT_ID",
        text="Source activity digest",
        allow_live_provider_execution=True,
        provider_execution_ack=LIVE_PROVIDER_EXECUTION_ACK,
    )

    assert result.success is True
    assert result.attempted_chunks == 1
    assert result.sent_chunks == 1
    assert result.message_ids == ("message-1",)
    assert len(calls) == 1


async def test_send_telegram_plain_text_stops_on_failure_with_safe_result() -> None:
    transport = FakeTelegramTransport(
        [
            {
                "ok": True,
                "result": {
                    "message_id": "message-1",
                },
            },
            {
                "ok": False,
                "error_code": 429,
                "description": "request failed for TELEGRAM_BOT_TOKEN",
            },
            {
                "ok": True,
                "result": {
                    "message_id": "message-3",
                },
            },
        ]
    )

    result = await send_telegram_plain_text(
        bot_token="TELEGRAM_BOT_TOKEN",
        chat_id="TELEGRAM_CHAT_ID",
        text="a\nb\nc\n",
        transport=transport,
        chunk_size=2,
    )

    assert result.success is False
    assert result.attempted_chunks == 2
    assert result.sent_chunks == 1
    assert result.message_ids == ("message-1",)
    assert result.error_summary == "Telegram API sendMessage failed with error_code 429"
    assert len(transport.calls) == 2
    assert "TELEGRAM_BOT_TOKEN" not in repr(result)
    assert "TELEGRAM_BOT_TOKEN" not in (result.error_summary or "")


async def test_send_telegram_plain_text_uses_injected_transport_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_httpx_post_json(
        url: str,
        payload: Mapping[str, str],
    ) -> Mapping[str, Any]:
        raise AssertionError("test must not call the real Telegram transport")

    monkeypatch.setattr(telegram_delivery, "_httpx_post_json", forbidden_httpx_post_json)
    transport = FakeTelegramTransport()

    result = await send_telegram_plain_text(
        bot_token="TELEGRAM_BOT_TOKEN",
        chat_id="TELEGRAM_CHAT_ID",
        text="Source activity digest",
        transport=transport,
    )

    assert result.success is True
    assert len(transport.calls) == 1


async def test_send_telegram_plain_text_does_not_require_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "openai" or name.startswith("openai."):
            raise AssertionError("Telegram delivery adapter must not import OpenAI")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = await send_telegram_plain_text(
        bot_token="TELEGRAM_BOT_TOKEN",
        chat_id="TELEGRAM_CHAT_ID",
        text="Source activity digest",
        transport=FakeTelegramTransport(),
    )

    assert result.success is True
