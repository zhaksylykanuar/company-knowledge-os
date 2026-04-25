from fastapi import APIRouter
from sqlalchemy import select
import json
import re
from pathlib import Path

from app.connectors.google_drive import download_file_text, list_ai_inbox_files
from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog, IngestedEvent
from app.db.task_models import ExtractedTask as ExtractedTaskModel
from app.events.schemas import EventEnvelope
from app.services.chunking import chunk_text
from app.agents.llm_runner import LLMAgentRunner

router = APIRouter(prefix="/v1/drive", tags=["drive"])


def _safe_path_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "unknown"


def save_drive_raw_snapshot(file_metadata: dict, text: str) -> str:
    file_id = _safe_path_part(file_metadata["id"])
    modified_time = _safe_path_part(file_metadata.get("modifiedTime", "unknown"))

    snapshot_dir = Path("raw_storage") / "drive" / file_id / modified_time
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    (snapshot_dir / "metadata.json").write_text(
        json.dumps(file_metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (snapshot_dir / "content.txt").write_text(text, encoding="utf-8")

    return f"raw://drive/{file_id}/{modified_time}/content.txt"


@router.post("/backfill")
async def drive_backfill() -> dict:
    files = list_ai_inbox_files()

    saved = 0
    duplicates = 0
    events = []

    async with AsyncSessionLocal() as session:
        for f in files:
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

            text = download_file_text(f["id"])
            raw_content_ref = save_drive_raw_snapshot(f, text)

            chunks = chunk_text(text)

            runner = LLMAgentRunner()
            all_tasks = []

            for chunk in chunks:
                extraction = await runner.extract(
                    source_document_id=f["id"],
                    chunk_id=chunk.chunk_id,
                    raw_object_ref=raw_content_ref,
                    text=chunk.text,
                )

                for task in extraction.tasks:
                    all_tasks.append(task)

            event.raw_object_ref = raw_content_ref

            row = IngestedEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                source_system=event.source_system,
                source_object_id=event.source_object_id,
                idempotency_key=event.idempotency_key,
                correlation_id=event.correlation_id,
                trace_id=event.trace_id,
                raw_object_ref=event.raw_object_ref,
                payload={
                    **event.payload,
                    "raw_content_ref": raw_content_ref,
                    "text_preview": text[:500],
                    "extraction": {"tasks": [task.model_dump() for task in all_tasks]},
                },
            )

            session.add(row)
            for task in all_tasks:
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
                    "chunks_found": len(chunks),
                    "tasks_found": len(all_tasks),
                    "extraction": {"tasks": [task.model_dump() for task in all_tasks]},
                }
            )

        await session.commit()

    return {
        "discovered": len(files),
        "saved": saved,
        "duplicates": duplicates,
        "events": events,
    }