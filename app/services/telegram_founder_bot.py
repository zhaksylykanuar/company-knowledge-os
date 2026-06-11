"""Founder Telegram bot: inbound Q&A loop (vision Phase A1).

Operator-launched long-polling loop. It answers allowlisted founder messages
with stored read models, including persisted project status snapshots. It never
creates drafts/intentions/results and replies only to the configured chat.

Live Telegram calls (getUpdates/sendMessage) go through the existing
provider execution guard; transports are injectable for tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.digest import (
    DEFAULT_DIGEST_ENTRY_LIMIT,
    PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
)
from app.services.founder_digest_rendering import (
    render_founder_attention_digest_text,
)
from app.services.provider_execution_guard import (
    ProviderExecutionBlockedError,
    require_live_provider_execution_ack,
)
from app.services.telegram_delivery import (
    TELEGRAM_API_BASE_URL,
    TelegramSendMessageTransport,
    send_telegram_plain_text,
)
from app.services.status_engine import DEFAULT_ORGANIZATION_ID

DEFAULT_STATUS_WINDOW_HOURS = 24
DEFAULT_POLL_TIMEOUT_SECONDS = 25

COMMAND_STATUS = "status"
COMMAND_HELP = "help"
COMMAND_UNKNOWN = "unknown"

_STATUS_TEXT_HINTS = (
    "статус",
    "status",
    "что у нас",
    "что происходит",
    "что с ",
    "что по ",
    "как дела",
)

HELP_REPLY = (
    "Я — FounderOS. Сейчас умею:\n"
    "/status — дайджест внимания за последние 24 часа\n"
    "/help — эта справка\n\n"
    "Скоро: /dev, /risks, /followups, вопросы свободным текстом."
)

IGNORED_UPDATE_REPLY = None

_STATUS_COLOR_EMOJI = {
    "green": "🟢",
    "yellow": "🟡",
    "red": "🔴",
    "unknown": "⚪",
}


@dataclass(frozen=True)
class _ProjectEntity:
    entity_id: str
    canonical_name: str


@dataclass(frozen=True)
class FounderBotIterationResult:
    updates_seen: int
    updates_from_allowed_chat: int
    replies_sent: int
    next_offset: int | None
    blocked_reason: str | None = None
    transient_error: str | None = None


def _get_updates_url(bot_token: str) -> str:
    return f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/getUpdates"


def _long_poll_read_timeout_seconds(poll_timeout_seconds: int) -> float:
    """HTTP read timeout must exceed the Telegram long-poll hold time."""

    return float(max(1, int(poll_timeout_seconds)) + 15)


def _build_long_poll_transport(
    poll_timeout_seconds: int,
) -> TelegramSendMessageTransport:
    import httpx

    timeout = httpx.Timeout(
        connect=10.0,
        read=_long_poll_read_timeout_seconds(poll_timeout_seconds),
        write=10.0,
        pool=10.0,
    )

    async def _post_json(url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=dict(payload))
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, Mapping):
            return {"ok": False, "error_code": response.status_code}
        result: dict[str, Any] = {str(key): value for key, value in body.items()}
        if response.status_code >= 400:
            result["ok"] = False
            result.setdefault("error_code", response.status_code)
        return result

    return _post_json


async def fetch_telegram_updates(
    *,
    bot_token: str,
    offset: int | None,
    poll_timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS,
    transport: TelegramSendMessageTransport | None = None,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> Mapping[str, Any]:
    """Fetch updates; live calls require the provider execution ack."""

    if transport is None:
        require_live_provider_execution_ack(
            provider="telegram",
            boundary="telegram_get_updates",
            allow_live_provider_execution=allow_live_provider_execution,
            provider_execution_ack=provider_execution_ack,
        )
        transport = _build_long_poll_transport(poll_timeout_seconds)

    payload: dict[str, Any] = {
        "timeout": int(poll_timeout_seconds),
        "allowed_updates": ["message"],
    }
    if offset is not None:
        payload["offset"] = int(offset)
    return await transport(_get_updates_url(bot_token), payload)


def parse_founder_command(text: str | None) -> str:
    if not isinstance(text, str) or not text.strip():
        return COMMAND_UNKNOWN

    cleaned = text.strip().casefold()
    first_token = cleaned.split()[0].split("@")[0]
    if first_token in ("/status",):
        return COMMAND_STATUS
    if first_token in ("/help", "/start"):
        return COMMAND_HELP
    if any(hint in cleaned for hint in _STATUS_TEXT_HINTS):
        return COMMAND_STATUS
    return COMMAND_UNKNOWN


async def build_status_reply_text(
    *,
    window_hours: int = DEFAULT_STATUS_WINDOW_HOURS,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
    now: datetime | None = None,
    question_text: str | None = None,
    require_recognized_project: bool = False,
    organization_id: str = DEFAULT_ORGANIZATION_ID,
) -> str | None:
    """Render founder digest v2 for the trailing window from stored data.

    When the question mentions a known project alias, the reply names the
    recognized project explicitly (entity resolution, Phase A2). Per-project
    status content arrives with the Jira/GitHub sync slices. With
    ``require_recognized_project=True`` the function returns None when no
    known project is mentioned, so callers can fall back to help.
    """

    from app.db.base import AsyncSessionLocal
    from app.services.digest import build_persisted_attention_digest_read_model
    from app.services.entity_resolution import (
        ENTITY_TYPE_PROJECT,
        resolve_entities_in_text,
    )

    safe_now = now or datetime.now(timezone.utc)
    start_at = safe_now - timedelta(hours=max(1, int(window_hours)))
    recognized = []
    recognized_snapshot_block: str | None = None
    async with AsyncSessionLocal() as session:
        if question_text:
            try:
                recognized = await resolve_entities_in_text(
                    session,
                    question_text,
                    entity_type=ENTITY_TYPE_PROJECT,
                )
            except Exception:
                recognized = []
        if require_recognized_project and not recognized:
            return None
        if recognized:
            # Project question -> project-focused Jira view, not the inbox digest.
            try:
                snapshot, detailed_text = await _build_and_save_project_snapshot(
                    session,
                    project_entity_id=recognized[0].entity_id,
                    project_name=recognized[0].canonical_name,
                    now=safe_now,
                    organization_id=organization_id,
                )
                await session.commit()
                recognized_snapshot_block = _render_project_snapshot_block(
                    project_name=recognized[0].canonical_name,
                    snapshot=snapshot,
                )
                if detailed_text is not None:
                    return recognized_snapshot_block + "\n\n" + detailed_text
            except Exception:
                pass
        elif question_text:
            try:
                project_snapshots = await _build_all_project_snapshots(
                    session,
                    now=safe_now,
                    organization_id=organization_id,
                )
                if project_snapshots:
                    await session.commit()
                    return _render_all_project_snapshots(project_snapshots)
            except Exception:
                pass
        digest = await build_persisted_attention_digest_read_model(
            session,
            start_at=start_at,
            end_at=safe_now,
            limit_per_section=limit,
            marker_filter=PERSISTED_ATTENTION_MARKER_FILTER_NO_MARKER_ONLY,
        )

    text = render_founder_attention_digest_text(digest, generated_at=safe_now)
    if recognized:
        project = recognized[0]
        prefix = (
            f"📂 Проект: {project.canonical_name} "
            f"(распознал «{project.matched_alias}»)\n"
            "Jira-проекты ещё не замаплены (map_jira_projects.py). "
            "Пока общий дайджест:\n\n"
        )
        if recognized_snapshot_block is not None:
            prefix = recognized_snapshot_block + "\n\n" + prefix
        return prefix + text
    return text


async def _build_all_project_snapshots(
    session: Any,
    *,
    now: datetime,
    organization_id: str,
) -> list[tuple[_ProjectEntity, Any]]:
    projects = await _load_project_entities(session)
    snapshots: list[tuple[_ProjectEntity, Any]] = []
    for project in projects:
        snapshot, _detailed_text = await _build_and_save_project_snapshot(
            session,
            project_entity_id=project.entity_id,
            project_name=project.canonical_name,
            now=now,
            organization_id=organization_id,
        )
        snapshots.append((project, snapshot))
    return snapshots


async def _load_project_entities(session: Any) -> list[_ProjectEntity]:
    from sqlalchemy import select

    from app.db.graph_models import EntityRecord
    from app.services.entity_resolution import ENTITY_TYPE_PROJECT

    rows = (
        await session.execute(
            select(EntityRecord.entity_id, EntityRecord.canonical_name)
            .where(EntityRecord.entity_type == ENTITY_TYPE_PROJECT)
            .order_by(EntityRecord.canonical_name, EntityRecord.entity_id)
        )
    ).all()
    return [
        _ProjectEntity(entity_id=str(entity_id), canonical_name=str(canonical_name))
        for entity_id, canonical_name in rows
    ]


async def _build_and_save_project_snapshot(
    session: Any,
    *,
    project_entity_id: str,
    project_name: str,
    now: datetime,
    organization_id: str,
) -> tuple[Any, str | None]:
    from app.services.github_graph_mapping import repos_for_project
    from app.services.jira_graph_mapping import jira_keys_for_project
    from app.services.project_status_view import (
        load_project_issue_snapshots,
        load_repo_activity,
        render_project_status_text,
    )
    from app.services.status_engine import (
        ENTITY_TYPE_PROJECT,
        build_project_status_snapshot,
    )
    from app.services.status_snapshot_repository import (
        get_latest_status_snapshot,
        save_status_snapshot,
    )

    keys = await jira_keys_for_project(session, project_entity_id)
    issue_snapshots = await load_project_issue_snapshots(session, keys)
    repos = await repos_for_project(session, project_entity_id)
    repo_activity = await load_repo_activity(session, repos, now=now)
    previous = await get_latest_status_snapshot(
        session,
        organization_id=organization_id,
        entity_type=ENTITY_TYPE_PROJECT,
        entity_id=project_entity_id,
    )
    snapshot = build_project_status_snapshot(
        project_entity_id=project_entity_id,
        project_name=project_name,
        jira_keys=keys,
        snapshots=issue_snapshots,
        repo_activity=repo_activity,
        previous_snapshot=previous,
        organization_id=organization_id,
        now=now,
    )
    await save_status_snapshot(session, snapshot)
    detailed_text = None
    if keys:
        detailed_text = render_project_status_text(
            project_name=project_name,
            jira_keys=keys,
            snapshots=issue_snapshots,
            repo_activity=repo_activity,
            now=now,
        )
    return snapshot, detailed_text


def _render_project_snapshot_block(*, project_name: str, snapshot: Any) -> str:
    emoji = _STATUS_COLOR_EMOJI.get(str(snapshot.status_color), "⚪")
    return "\n".join(
        [
            f"{emoji} Snapshot: {project_name}",
            f"confidence: {float(snapshot.confidence):.2f}",
            "what_changed: " + _format_changes(snapshot.what_changed, limit=5),
            f"summary: {snapshot.summary}",
        ]
    )


def _render_all_project_snapshots(
    project_snapshots: list[tuple[_ProjectEntity, Any]],
) -> str:
    lines = ["📊 Project snapshots", ""]
    for project, snapshot in project_snapshots:
        emoji = _STATUS_COLOR_EMOJI.get(str(snapshot.status_color), "⚪")
        lines.append(
            f"{emoji} {project.canonical_name} — "
            f"confidence: {float(snapshot.confidence):.2f} — "
            f"changed: {_format_changes(snapshot.what_changed, limit=1)}"
        )
        lines.append(f"  {snapshot.summary}")
    return "\n".join(lines) + "\n"


def _format_changes(changes: Any, *, limit: int = 3) -> str:
    items = [item for item in changes if isinstance(item, Mapping)]
    if not items:
        return "no changes"
    rendered = [_format_change(item) for item in items[:limit]]
    if len(items) > limit:
        rendered.append(f"+{len(items) - limit} more")
    return "; ".join(rendered)


def _format_change(change: Mapping[str, Any]) -> str:
    field = str(change.get("field") or "snapshot")
    kind = str(change.get("change") or "changed")
    if field == "snapshot" and kind == "created":
        return "first snapshot"
    if kind == "changed":
        before = change.get("from")
        after = change.get("to")
        if before is not None or after is not None:
            return f"{field}: {before} -> {after}"
        return f"{field} changed"
    ids = change.get("ids")
    if isinstance(ids, list) and ids:
        return f"{field} {kind}: {', '.join(str(item) for item in ids[:3])}"
    return f"{field} {kind}"


def _update_chat_id(update: Mapping[str, Any]) -> str | None:
    message = update.get("message")
    if not isinstance(message, Mapping):
        return None
    chat = message.get("chat")
    if not isinstance(chat, Mapping):
        return None
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    return str(chat_id)


def _update_text(update: Mapping[str, Any]) -> str | None:
    message = update.get("message")
    if not isinstance(message, Mapping):
        return None
    text = message.get("text")
    return text if isinstance(text, str) else None


async def build_reply_for_update(
    update: Mapping[str, Any],
    *,
    allowed_chat_id: str,
    window_hours: int = DEFAULT_STATUS_WINDOW_HOURS,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
    now: datetime | None = None,
) -> str | None:
    """Return reply text for an allowlisted founder message, else None."""

    chat_id = _update_chat_id(update)
    if chat_id is None or chat_id != str(allowed_chat_id):
        return IGNORED_UPDATE_REPLY

    text = _update_text(update)
    command = parse_founder_command(text)
    if command == COMMAND_STATUS:
        return await build_status_reply_text(
            window_hours=window_hours,
            limit=limit,
            now=now,
            question_text=text,
        )
    if command == COMMAND_UNKNOWN and text:
        # Free text mentioning a known project counts as a status question.
        recognized_reply = await build_status_reply_text(
            window_hours=window_hours,
            limit=limit,
            now=now,
            question_text=text,
            require_recognized_project=True,
        )
        if recognized_reply is not None:
            return recognized_reply
    return HELP_REPLY


def _next_offset(updates: list[Mapping[str, Any]], current: int | None) -> int | None:
    update_ids = [
        int(update["update_id"])
        for update in updates
        if isinstance(update.get("update_id"), int)
    ]
    if not update_ids:
        return current
    return max(update_ids) + 1


async def run_founder_bot_iteration(
    *,
    bot_token: str,
    allowed_chat_id: str,
    offset: int | None,
    window_hours: int = DEFAULT_STATUS_WINDOW_HOURS,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
    poll_timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS,
    get_updates_transport: TelegramSendMessageTransport | None = None,
    send_message_transport: TelegramSendMessageTransport | None = None,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
    now: datetime | None = None,
) -> FounderBotIterationResult:
    """One getUpdates poll: answer allowlisted messages, advance offset."""

    try:
        response = await fetch_telegram_updates(
            bot_token=bot_token,
            offset=offset,
            poll_timeout_seconds=poll_timeout_seconds,
            transport=get_updates_transport,
            allow_live_provider_execution=allow_live_provider_execution,
            provider_execution_ack=provider_execution_ack,
        )
    except ProviderExecutionBlockedError as exc:
        return FounderBotIterationResult(
            updates_seen=0,
            updates_from_allowed_chat=0,
            replies_sent=0,
            next_offset=offset,
            blocked_reason=exc.reason_code,
        )
    except Exception:
        # Long polling routinely hits transient network errors; the loop
        # must survive them and retry with the same offset.
        return FounderBotIterationResult(
            updates_seen=0,
            updates_from_allowed_chat=0,
            replies_sent=0,
            next_offset=offset,
            transient_error="get_updates_request_failed",
        )

    raw_updates = response.get("result")
    updates = [u for u in raw_updates if isinstance(u, Mapping)] if isinstance(
        raw_updates, list
    ) else []

    allowed_count = 0
    replies_sent = 0
    for update in updates:
        reply = await build_reply_for_update(
            update,
            allowed_chat_id=allowed_chat_id,
            window_hours=window_hours,
            limit=limit,
            now=now,
        )
        if reply is None:
            continue
        allowed_count += 1
        result = await send_telegram_plain_text(
            bot_token=bot_token,
            chat_id=allowed_chat_id,
            text=reply,
            transport=send_message_transport,
            allow_live_provider_execution=allow_live_provider_execution,
            provider_execution_ack=provider_execution_ack,
        )
        if result.success:
            replies_sent += 1

    return FounderBotIterationResult(
        updates_seen=len(updates),
        updates_from_allowed_chat=allowed_count,
        replies_sent=replies_sent,
        next_offset=_next_offset(updates, offset),
    )
