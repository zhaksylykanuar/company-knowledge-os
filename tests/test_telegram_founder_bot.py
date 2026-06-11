from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import pytest

from app.services import telegram_founder_bot as bot
from app.services.provider_execution_guard import ProviderExecutionBlockedError

NOW = datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc)
ALLOWED_CHAT = "777000111"


def _update(
    *,
    update_id: int = 100,
    chat_id: str = ALLOWED_CHAT,
    text: str | None = "/status",
) -> dict[str, Any]:
    message: dict[str, Any] = {"chat": {"id": chat_id}}
    if text is not None:
        message["text"] = text
    return {"update_id": update_id, "message": message}


class _FakeTransport:
    def __init__(self, responses: list[Mapping[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    async def __call__(self, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((url, dict(payload)))
        if not self.responses:
            raise AssertionError("unexpected extra transport call")
        return self.responses.pop(0)


def test_parse_founder_command_variants() -> None:
    assert bot.parse_founder_command("/status") == bot.COMMAND_STATUS
    assert bot.parse_founder_command("/status@founder_bot") == bot.COMMAND_STATUS
    assert bot.parse_founder_command("Что у нас с SSAP?") == bot.COMMAND_STATUS
    assert bot.parse_founder_command("что с ssap") == bot.COMMAND_STATUS
    assert bot.parse_founder_command("что по разработке") == bot.COMMAND_STATUS
    assert bot.parse_founder_command("как дела?") == bot.COMMAND_STATUS
    assert bot.parse_founder_command("какой статус?") == bot.COMMAND_STATUS
    assert bot.parse_founder_command("/help") == bot.COMMAND_HELP
    assert bot.parse_founder_command("/start") == bot.COMMAND_HELP
    assert bot.parse_founder_command("привет") == bot.COMMAND_UNKNOWN
    assert bot.parse_founder_command(None) == bot.COMMAND_UNKNOWN
    assert bot.parse_founder_command("   ") == bot.COMMAND_UNKNOWN


async def test_fetch_updates_without_ack_is_blocked() -> None:
    with pytest.raises(ProviderExecutionBlockedError):
        await bot.fetch_telegram_updates(
            bot_token="test-token",
            offset=None,
        )


async def test_reply_ignores_non_allowlisted_chats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_status(**_kwargs: object) -> str:
        raise AssertionError("must not build status for foreign chats")

    monkeypatch.setattr(bot, "build_status_reply_text", forbidden_status)

    reply = await bot.build_reply_for_update(
        _update(chat_id="999"),
        allowed_chat_id=ALLOWED_CHAT,
        now=NOW,
    )

    assert reply is None


async def test_reply_help_for_unknown_text() -> None:
    reply = await bot.build_reply_for_update(
        _update(text="привет"),
        allowed_chat_id=ALLOWED_CHAT,
        now=NOW,
    )

    assert reply == bot.HELP_REPLY
    assert "/status" in reply


async def test_iteration_answers_status_and_advances_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_status(**_kwargs: object) -> str:
        return "🧠 Дайджест внимания • 12.06.2026 09:00\n\nСпокойно.\n"

    monkeypatch.setattr(bot, "build_status_reply_text", fake_status)

    get_updates = _FakeTransport(
        [
            {
                "ok": True,
                "result": [
                    _update(update_id=41, chat_id="999", text="/status"),
                    _update(update_id=42, text="/status"),
                ],
            }
        ]
    )
    send_message = _FakeTransport(
        [{"ok": True, "result": {"message_id": 7}}]
    )

    result = await bot.run_founder_bot_iteration(
        bot_token="test-token",
        allowed_chat_id=ALLOWED_CHAT,
        offset=40,
        get_updates_transport=get_updates,
        send_message_transport=send_message,
        now=NOW,
    )

    assert result.updates_seen == 2
    assert result.updates_from_allowed_chat == 1
    assert result.replies_sent == 1
    assert result.next_offset == 43

    get_url, get_payload = get_updates.calls[0]
    assert get_url.endswith("/gettoken/getUpdates") is False
    assert "getUpdates" in get_url
    assert get_payload["offset"] == 40

    send_url, send_payload = send_message.calls[0]
    assert "sendMessage" in send_url
    assert send_payload["chat_id"] == ALLOWED_CHAT
    assert "Дайджест внимания" in send_payload["text"]


def test_long_poll_read_timeout_exceeds_poll_hold() -> None:
    assert bot._long_poll_read_timeout_seconds(25) > 25
    assert bot._long_poll_read_timeout_seconds(0) > 0


async def test_iteration_survives_transient_network_error() -> None:
    async def failing_transport(
        _url: str, _payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        raise TimeoutError("simulated read timeout")

    result = await bot.run_founder_bot_iteration(
        bot_token="test-token",
        allowed_chat_id=ALLOWED_CHAT,
        offset=55,
        get_updates_transport=failing_transport,
    )

    assert result.transient_error == "get_updates_request_failed"
    assert result.blocked_reason is None
    assert result.next_offset == 55
    assert result.replies_sent == 0


async def test_iteration_reports_guard_block_without_transports() -> None:
    result = await bot.run_founder_bot_iteration(
        bot_token="test-token",
        allowed_chat_id=ALLOWED_CHAT,
        offset=None,
    )

    assert result.blocked_reason is not None
    assert result.updates_seen == 0
    assert result.replies_sent == 0


async def test_status_reply_renders_founder_digest_from_empty_window() -> None:
    text = await bot.build_status_reply_text(
        window_hours=1,
        now=datetime(2199, 6, 1, tzinfo=timezone.utc),
    )

    assert text.startswith("🧠 Дайджест внимания")
    assert "Действий не требуется." in text
    assert "[Открыть главное]" in text
