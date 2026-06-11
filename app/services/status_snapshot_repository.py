from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.status_models import StatusSnapshotRecord
from app.services.status_engine import StatusSnapshot


async def get_latest_status_snapshot(
    session: AsyncSession,
    *,
    organization_id: str,
    entity_type: str,
    entity_id: str,
) -> StatusSnapshotRecord | None:
    return await session.scalar(
        select(StatusSnapshotRecord)
        .where(StatusSnapshotRecord.organization_id == organization_id)
        .where(StatusSnapshotRecord.entity_type == entity_type)
        .where(StatusSnapshotRecord.entity_id == entity_id)
        .order_by(
            StatusSnapshotRecord.created_at.desc(),
            StatusSnapshotRecord.id.desc(),
        )
        .limit(1)
    )


async def save_status_snapshot(
    session: AsyncSession,
    snapshot: StatusSnapshot,
) -> StatusSnapshotRecord:
    record = StatusSnapshotRecord(
        organization_id=snapshot.organization_id,
        entity_type=snapshot.entity_type,
        entity_id=snapshot.entity_id,
        status_color=snapshot.status_color,
        summary=snapshot.summary,
        what_changed_json=list(snapshot.what_changed),
        current_work_json=list(snapshot.current_work),
        blockers_json=list(snapshot.blockers),
        risks_json=list(snapshot.risks),
        conflicts_json=list(snapshot.conflicts),
        recommendations_json=list(snapshot.recommendations),
        confidence=snapshot.confidence,
        confidence_reason=snapshot.confidence_reason,
        last_meaningful_update_at=snapshot.last_meaningful_update_at,
        evidence_source_ids_json=list(snapshot.evidence_source_ids),
    )
    session.add(record)
    await session.flush()
    return record
