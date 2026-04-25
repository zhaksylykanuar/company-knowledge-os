from fastapi import APIRouter, status
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog, IngestedEvent
from app.events.schemas import EventEnvelope

router = APIRouter()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(event: EventEnvelope) -> dict[str, str | bool]:
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(IngestedEvent).where(IngestedEvent.idempotency_key == event.idempotency_key)
        )
        if existing:
            return {"accepted": True, "duplicate": True, "event_id": existing.event_id}

        session.add(
            IngestedEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                source_system=event.source_system,
                source_object_id=event.source_object_id,
                idempotency_key=event.idempotency_key,
                correlation_id=event.correlation_id,
                trace_id=event.trace_id,
                raw_object_ref=event.raw_object_ref,
                payload=event.payload,
            )
        )
        session.add(
            AuditLog(
                event_type="event.accepted",
                actor="system",
                correlation_id=event.correlation_id,
                trace_id=event.trace_id,
                after_ref=event.event_id,
                payload={"idempotency_key": event.idempotency_key},
            )
        )
        await session.commit()
        return {"accepted": True, "duplicate": False, "event_id": event.event_id}
