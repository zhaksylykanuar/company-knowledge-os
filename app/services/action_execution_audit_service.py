from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.action_models import ActionExecutionEvent
from app.services.action_proposal_service import SECRET_LIKE_KEYS


async def append_execution_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    action_proposal_id: UUID,
    event_type: str,
    actor: str,
    status: str,
    message: str,
    idempotency_key: str,
    provider: str | None = None,
    action: str | None = None,
    external_execution_enabled: bool = False,
    confirmation_received: bool = False,
    event_metadata: Mapping[str, Any] | None = None,
    external_result_id: str | None = None,
    external_result_url: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> ActionExecutionEvent:
    existing = await session.scalar(
        select(ActionExecutionEvent).where(
            ActionExecutionEvent.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return existing

    event = ActionExecutionEvent(
        workspace_id=workspace_id,
        action_proposal_id=action_proposal_id,
        event_type=event_type,
        actor=_safe_text(actor, fallback="system", limit=80),
        status=status,
        message=_safe_text(message, fallback="Audit event recorded locally.", limit=500),
        event_metadata=_sanitize_metadata(event_metadata or {}),
        idempotency_key=_safe_text(idempotency_key, fallback="", limit=500),
        provider=_optional_text(provider, limit=40),
        action=_optional_text(action, limit=80),
        external_execution_enabled=external_execution_enabled,
        confirmation_received=confirmation_received,
        external_result_id=_optional_text(external_result_id, limit=255),
        external_result_url=_optional_text(external_result_url, limit=1000),
        error_code=_optional_text(error_code, limit=120),
        error_message=_optional_text(error_message, limit=500),
    )
    try:
        async with session.begin_nested():
            session.add(event)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(ActionExecutionEvent).where(
                ActionExecutionEvent.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return existing
        raise
    await session.refresh(event)
    return event


async def list_execution_events(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    action_proposal_id: UUID,
) -> list[ActionExecutionEvent]:
    rows = (
        await session.execute(
            select(ActionExecutionEvent)
            .where(ActionExecutionEvent.workspace_id == workspace_id)
            .where(ActionExecutionEvent.action_proposal_id == action_proposal_id)
            .order_by(
                ActionExecutionEvent.created_at.asc(),
                _event_order_case(),
                ActionExecutionEvent.id.asc(),
            )
        )
    ).scalars()
    return list(rows)


def serialize_execution_event(event: ActionExecutionEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "event": event.event_type,
        "actor": event.actor,
        "status": event.status,
        "message": event.message,
        "event_metadata": event.event_metadata or {},
        "provider": event.provider,
        "action": event.action,
        "external_execution_enabled": event.external_execution_enabled,
        "confirmation_received": event.confirmation_received,
        "external_result_id": event.external_result_id,
        "external_result_url": event.external_result_url,
        "error_code": event.error_code,
        "error_message": event.error_message,
        "created_at": event.created_at,
    }


def execution_event_idempotency_key(
    *,
    workspace_id: UUID,
    action_proposal_id: UUID,
    event_type: str,
    external_execution_enabled: bool,
    confirmation_received: bool,
    preview_hash: str | None = None,
    reason: str | None = None,
) -> str:
    basis = {
        "action_proposal_id": str(action_proposal_id),
        "confirmation_received": confirmation_received,
        "event_type": event_type,
        "external_execution_enabled": external_execution_enabled,
        "preview_hash": preview_hash,
        "reason": reason,
        "workspace_id": str(workspace_id),
    }
    digest = stable_digest(basis)
    return f"action-execution-event:{event_type}:{digest}"


def stable_digest(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]


def _sanitize_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).strip()
            if not key_text:
                continue
            if key_text.casefold() in SECRET_LIKE_KEYS:
                continue
            sanitized[key_text[:120]] = _sanitize_metadata(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_metadata(item) for item in value[:50]]
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, bool | int | float) or value is None:
        return value
    return str(value)[:500]


def _optional_text(value: str | None, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped[:limit] if stripped else None


def _safe_text(value: str | None, *, fallback: str, limit: int) -> str:
    return _optional_text(value, limit=limit) or fallback[:limit]


def _event_order_case():
    return case(
        {
            "execution_preview_generated": 10,
            "execution_preview_blocked": 11,
            "execution_unsupported": 12,
            "execution_confirmation_missing": 20,
            "execution_confirmation_received_but_disabled": 21,
            "execution_blocked": 22,
            "execution_confirmation_received": 30,
            "execution_started": 40,
            "execution_succeeded": 50,
            "execution_failed": 51,
            "execution_duplicate_returned_existing_receipt": 60,
        },
        value=ActionExecutionEvent.event_type,
        else_=100,
    )
