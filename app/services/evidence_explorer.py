"""Source / evidence explorer: browse the events behind the graph.

Surfaces the *sanitized* source-event layer (title/summary/source_url
produced during normalization) — never raw connector payloads or raw
storage bodies (CLAUDE.md). Each event view also shows the normalized
item, the graph nodes that reference it and the findings generated from
it. Visibility is enforced: founder sees raw_object_ref; team sees only
working details; investor cannot see raw evidence at all.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Text, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.graph_models import EntityRecord
from app.db.models import IngestedEvent
from app.db.second_opinion_models import SecondOpinionFinding
from app.services.visibility import SCOPE_FOUNDER, SCOPE_INVESTOR, SCOPE_TEAM

# Already-sanitized fields safe for the working (team) view.
_TEAM_EVENT_FIELDS = (
    "source_event_id",
    "source_system",
    "event_type",
    "source_object_type",
    "source_object_id",
    "title",
    "received_at",
    "source_event_ts",
)


def investor_blocked(viewer_scope: str) -> bool:
    return viewer_scope == SCOPE_INVESTOR


async def list_source_events(
    session: AsyncSession,
    *,
    source_object_id: str | None = None,
    source_system: str | None = None,
    status: str | None = None,
    run_id: str | None = None,
    limit: int = 50,
    viewer_scope: str = SCOPE_FOUNDER,
) -> list[dict[str, Any]]:
    query = (
        select(SourceEvent, IngestedEvent.status)
        .outerjoin(
            IngestedEvent,
            IngestedEvent.event_id == SourceEvent.ingested_event_id,
        )
        .order_by(SourceEvent.id.desc())
    )
    if source_object_id is not None:
        query = query.where(
            SourceEvent.source_object_id.like(f"%{source_object_id}%")
        )
    if source_system is not None:
        query = query.where(SourceEvent.source_system == source_system)
    if status is not None:
        query = query.where(IngestedEvent.status == status)
    if run_id is not None:
        query = query.where(SourceEvent.created_by_run_id == run_id)
    rows = (await session.execute(query.limit(limit))).all()
    out: list[dict[str, Any]] = []
    for row, event_status in rows:
        normalized_at = await session.scalar(
            select(func.max(NormalizedActivityItemRecord.created_at)).where(
                NormalizedActivityItemRecord.source_object_id.like(
                    f"%{row.source_object_id}%"
                )
            )
        )
        item = {
            "source_event_id": row.source_event_id,
            "source_system": row.source_system,
            "event_type": row.event_type,
            "source_object_type": row.source_object_type,
            "source_object_id": row.source_object_id,
            "title": row.title,
            "status": event_status or "received",
            "received_at": row.created_at.isoformat() if row.created_at else None,
            "normalized_at": normalized_at.isoformat() if normalized_at else None,
            "redaction": {
                "viewer_scope": viewer_scope,
                "raw_object_ref_visible": viewer_scope == SCOPE_FOUNDER,
                "raw_body_visible": False,
            },
        }
        if viewer_scope == SCOPE_FOUNDER:
            item["raw_object_ref"] = row.raw_object_ref
            item["source_url"] = row.source_url
        out.append(item)
    return out


def _full_event_view(row: SourceEvent) -> dict[str, Any]:
    return {
        "source_event_id": row.source_event_id,
        "source_system": row.source_system,
        "event_type": row.event_type,
        "source_object_type": row.source_object_type,
        "source_object_id": row.source_object_id,
        "title": row.title,
        "summary": row.summary,
        "source_url": row.source_url,
        "received_at": row.created_at.isoformat() if row.created_at else None,
        "source_event_ts": (
            row.source_event_ts.isoformat() if row.source_event_ts else None
        ),
        "raw_object_ref": row.raw_object_ref,
        "schema_version": row.schema_version,
    }


async def build_source_event_view(
    session: AsyncSession,
    *,
    source_event_id: str,
    viewer_scope: str = SCOPE_FOUNDER,
) -> dict[str, Any] | None:
    if investor_blocked(viewer_scope):
        return None
    row = await session.scalar(
        select(SourceEvent).where(SourceEvent.source_event_id == source_event_id)
    )
    if row is None:
        return None

    full = _full_event_view(row)
    if viewer_scope == SCOPE_TEAM:
        # Working view: drop summary/source_url/raw_object_ref.
        event = {key: full[key] for key in _TEAM_EVENT_FIELDS}
    else:
        event = full

    object_id = row.source_object_id

    normalized_rows = (
        await session.execute(
            select(NormalizedActivityItemRecord)
            .where(
                NormalizedActivityItemRecord.source_object_id.like(f"%{object_id}%")
            )
            .order_by(NormalizedActivityItemRecord.id.desc())
            .limit(5)
        )
    ).scalars()
    normalized = [
        {
            "activity_item_id": item.activity_item_id,
            "source": item.source,
            "activity_type": item.activity_type,
            "title": item.title,
            "normalized_at": (
                item.created_at.isoformat() if item.created_at else None
            ),
            "occurred_at": (
                item.activity_created_at.isoformat()
                if item.activity_created_at
                else None
            ),
        }
        for item in normalized_rows
    ]

    # Graph nodes that reference this object id (jira project, repo, etc.).
    linked_nodes: list[dict[str, Any]] = []
    prefix = object_id.split("-")[0] if "-" in object_id else object_id
    node_rows = (
        await session.execute(
            select(EntityRecord)
            .where(
                or_(
                    EntityRecord.entity_id.like(f"%{prefix}%"),
                    EntityRecord.canonical_name.like(f"%{prefix}%"),
                )
            )
            .limit(10)
        )
    ).scalars()
    for node in node_rows:
        linked_nodes.append(
            {
                "entity_id": node.entity_id,
                "entity_type": node.entity_type,
                "name": node.canonical_name,
            }
        )

    # Findings generated from this evidence.
    finding_rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(
                SecondOpinionFinding.evidence_refs.cast(Text).like(
                    f"%{object_id}%"
                )
            )
            .limit(10)
        )
    ).scalars()
    findings = [
        {
            "finding_key": f.finding_key,
            "finding_type": f.finding_type,
            "summary": f.summary,
            "severity": f.severity,
            "status": f.status,
        }
        for f in finding_rows
        if viewer_scope == SCOPE_FOUNDER or f.visibility_scope == SCOPE_TEAM
    ]

    return {
        "event": event,
        "normalized_events": normalized,
        "linked_graph_nodes": linked_nodes,
        "findings_generated": findings,
        "viewer_scope": viewer_scope,
    }
