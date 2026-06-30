"""Persist and read deterministic Founder Briefings (Briefings Chunk 1).

This layer SAVES the output of the existing deterministic generator
(``app.services.founder_briefing_service.generate_manual_founder_briefing``) as
``Briefing`` + ``BriefingItem`` rows and reads them back as history. It does not
generate anything itself and adds no LLM — the generated content shape is
preserved verbatim so a persisted briefing re-renders identically.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.briefing_models import (
    BRIEFING_GENERATED_BY_DETERMINISTIC_V0,
    Briefing,
    BriefingItem,
)

# Persisted briefings carry this marker instead of the generator's "transient".
BRIEFING_PERSISTENCE_PERSISTED = "persisted"


async def persist_briefing(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    created_by_user_id: UUID | None,
    generated: dict[str, Any],
    generated_by: str = BRIEFING_GENERATED_BY_DETERMINISTIC_V0,
) -> Briefing:
    """Save a generated briefing dict (the ``briefing`` payload) and its items.

    ``generated`` is the inner ``briefing`` mapping returned by
    ``generate_manual_founder_briefing``. Item ordering is preserved via
    ``position``. The briefing is flushed so ids are assigned; the caller commits.
    """

    briefing = Briefing(
        workspace_id=workspace_id,
        created_by_user_id=created_by_user_id,
        generated_by=generated_by,
        title=str(generated.get("title") or ""),
        summary=str(generated.get("summary") or ""),
        as_of=generated.get("generated_at"),
        signals=_jsonable(generated.get("signals")) or {},
        warnings=[str(warning) for warning in (generated.get("warnings") or [])],
    )
    for position, item in enumerate(generated.get("items") or []):
        briefing.items.append(
            BriefingItem(
                position=position,
                item_key=str(item.get("id") or ""),
                category=str(item.get("category") or ""),
                title=str(item.get("title") or ""),
                summary=str(item.get("summary") or ""),
                severity=str(item.get("severity") or ""),
                confidence=float(item.get("confidence") or 0.0),
                recommended_next_step=item.get("recommended_next_step"),
                evidence_refs=_jsonable(item.get("evidence_refs")) or [],
                related_entities=[
                    str(entity) for entity in (item.get("related_entities") or [])
                ],
                warnings=[str(warning) for warning in (item.get("warnings") or [])],
            )
        )
    session.add(briefing)
    await session.flush()
    return briefing


async def list_briefings(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[Briefing]:
    """Return a workspace's briefings newest-first, with items eager-loaded."""

    result = await session.execute(
        select(Briefing)
        .where(Briefing.workspace_id == workspace_id)
        .order_by(Briefing.created_at.desc(), Briefing.id.desc())
        .limit(limit)
        .offset(offset)
        .options(selectinload(Briefing.items))
    )
    return list(result.scalars().all())


async def count_briefings(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> int:
    """Count a workspace's persisted briefings."""

    return int(
        await session.scalar(
            select(func.count())
            .select_from(Briefing)
            .where(Briefing.workspace_id == workspace_id)
        )
        or 0
    )


async def get_briefing(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    briefing_id: UUID,
) -> Briefing | None:
    """Read one briefing by id, scoped to its workspace (isolation enforced here).

    The ``workspace_id`` predicate is the isolation boundary: a briefing from
    another workspace is simply not found, so callers cannot read across
    workspaces even with a valid id.
    """

    result = await session.execute(
        select(Briefing)
        .where(Briefing.id == briefing_id)
        .where(Briefing.workspace_id == workspace_id)
        .options(selectinload(Briefing.items))
    )
    return result.scalar_one_or_none()


def serialize_briefing(briefing: Briefing) -> dict[str, Any]:
    """Full persisted-briefing payload (with items), mirroring the generator."""

    return {
        "id": briefing.id,
        "workspace_id": briefing.workspace_id,
        "created_at": briefing.created_at,
        "generated_at": briefing.as_of,
        "generated_by": briefing.generated_by,
        "title": briefing.title,
        "summary": briefing.summary,
        "is_live": False,
        "llm_used": False,
        "persistence": BRIEFING_PERSISTENCE_PERSISTED,
        "items": [_serialize_item(item) for item in briefing.items],
        "signals": briefing.signals or {},
        "warnings": list(briefing.warnings or []),
    }


def serialize_briefing_summary(briefing: Briefing) -> dict[str, Any]:
    """Compact history-list entry (no items)."""

    return {
        "id": briefing.id,
        "created_at": briefing.created_at,
        "generated_at": briefing.as_of,
        "generated_by": briefing.generated_by,
        "title": briefing.title,
        "summary": briefing.summary,
        "item_count": len(briefing.items),
        "signals": briefing.signals or {},
    }


def _serialize_item(item: BriefingItem) -> dict[str, Any]:
    return {
        "id": item.item_key,
        "category": item.category,
        "title": item.title,
        "summary": item.summary,
        "severity": item.severity,
        "confidence": item.confidence,
        "evidence_refs": list(item.evidence_refs or []),
        "related_entities": list(item.related_entities or []),
        "recommended_next_step": item.recommended_next_step,
        "warnings": list(item.warnings or []),
    }


def _jsonable(value: Any) -> Any:
    """Defensive pass-through; the generator already emits JSON-safe data."""

    return value
