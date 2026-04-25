from fastapi import APIRouter
from sqlalchemy import select

from app.agents.runner import get_agent_runner
from app.connectors.google_drive import download_file_text, list_ai_inbox_files
from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog, IngestedEvent
from app.db.task_models import ExtractedTask as ExtractedTaskModel
from app.events.schemas import EventEnvelope

router = APIRouter(prefix="/v1/drive", tags=["drive"])


@router.post("/backfill")
async def drive_backfill() -> dict:
    files = list_ai_inbox_files()

    saved = 0
    duplicates = 0
    events = []

    async with AsyncSessionLocal() as session:
        for f in files:
            text = download_file_text(f["id"])
            runner = get_agent_runner()
            extraction = await runner.extract(
                source_document_id=f["id"],
                chunk_id="chunk_0",
                raw_object_ref=f"raw://drive/{f['id']}/metadata.json",
                text=text,
            )

            event = EventEnvelope(
                event_type="drive.file.discovered",
                source_system="drive",
                source_object_id=f["id"],
                idempotency_key=f"drive:file:{f['id']}:{f.get('modifiedTime')}",
                raw_object_ref=f"raw://drive/{f['id']}/metadata.json",
                payload=f,
            )

            existing = await session.scalar(
                select(IngestedEvent).where(
                    IngestedEvent.idempotency_key == event.idempotency_key
                )
            )

            if existing:
                duplicates += 1
                events.append(
                    {
                        "accepted": True,
                        "duplicate": True,
                        "event_id": existing.event_id,
                        "source_object_id": event.source_object_id,
                    }
                )
                continue

            row = IngestedEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                source_system=event.source_system,
                source_object_id=event.source_object_id,
                idempotency_key=event.idempotency_key,
                correlation_id=event.correlation_id,
                trace_id=event.trace_id,
                raw_object_ref=event.raw_object_ref,
                payload={**event.payload, "text_preview": text[:500], "extraction": extraction.model_dump()},
            )

            session.add(row)
            for task in extraction.tasks:
                session.add(
                    ExtractedTaskModel(
                        title=task.title,
                        confidence=task.confidence,
                        source_event_id=event.event_id,
                        evidence_refs=[ref.model_dump() for ref in task.evidence_refs],
                    )
                )
            session.add(
                AuditLog(
                    event_type="drive.file.discovered",
                    actor="system",
                    correlation_id=event.correlation_id,
                    trace_id=event.trace_id,
                    payload={
                        "idempotency_key": event.idempotency_key,
                        "source_object_id": event.source_object_id,
                        "name": f.get("name"),
                    },
                )
            )

            saved += 1
            events.append(
                {
                    "accepted": True,
                    "duplicate": False,
                    "event_id": event.event_id,
                    "source_object_id": event.source_object_id,
                    "tasks_found": len(extraction.tasks),
                    "extraction": extraction.model_dump(),
                }
            )

        await session.commit()

    return {
        "discovered": len(files),
        "saved": saved,
        "duplicates": duplicates,
        "events": events,
    }