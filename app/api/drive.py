from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog, IngestedEvent
from app.db.source_models import DocumentChunk, SourceDocument
from app.events.schemas import EventEnvelope
from app.services.chunking import chunk_text
from app.services.production_operation_guard import (
    SOURCE_OF_TRUTH_MUTATION,
    ProductionOperationBlockedError,
    require_production_operation_ack,
)
from app.services.raw_storage import raw_storage_root, safe_path_part, sha256_text, write_json, write_text
from app.services.source_events import normalize_ingested_event_to_source_event

router = APIRouter(prefix="/v1/drive", tags=["drive"])

DRIVE_BACKFILL_DEFAULT_MAX_RESULTS = 10
DRIVE_BACKFILL_MAX_RESULTS = 50


def _require_drive_backfill_enabled() -> str:
    if not settings.google_drive_backfill_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Google Drive backfill is disabled.",
        )

    folder_id = settings.google_drive_ai_inbox_folder_id
    cleaned_folder_id = folder_id.strip() if isinstance(folder_id, str) else ""
    if not cleaned_folder_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Drive backfill requires GOOGLE_DRIVE_AI_INBOX_FOLDER_ID.",
        )

    return cleaned_folder_id


def list_ai_inbox_files(*, max_results: int) -> list[dict]:
    from app.connectors.google_drive import list_ai_inbox_files as _list_ai_inbox_files

    return _list_ai_inbox_files(page_size=max_results)


def download_file_text(file_id: str, mime_type: str | None = None) -> str:
    from app.connectors.google_drive import download_file_text as _download_file_text

    return _download_file_text(file_id, mime_type)


def build_drive_event(file_metadata: dict) -> EventEnvelope:
    return EventEnvelope(
        event_type="drive.file.ingested",
        source_system="drive",
        source_object_id=file_metadata["id"],
        idempotency_key=f"drive:file:{file_metadata['id']}:{file_metadata.get('modifiedTime')}",
        raw_object_ref=(
            f"raw://drive/{file_metadata['id']}/"
            f"{file_metadata.get('modifiedTime', 'unknown')}/metadata.json"
        ),
        payload={
            **file_metadata,
            "source_object_type": "file",
            "title": file_metadata.get("name"),
        },
    )


def save_drive_raw_snapshot(
    file_metadata: dict,
    text: str,
    *,
    allow_production_operation: bool = False,
    production_operation_ack: str | None = None,
) -> tuple[str, str]:
    file_id = safe_path_part(file_metadata["id"])
    modified_time = safe_path_part(file_metadata.get("modifiedTime", "unknown"))
    snapshot_dir = raw_storage_root() / "drive" / file_id / modified_time

    write_json(
        snapshot_dir / "metadata.json",
        file_metadata,
        allow_production_operation=allow_production_operation,
        production_operation_ack=production_operation_ack,
    )
    write_text(
        snapshot_dir / "content.txt",
        text,
        allow_production_operation=allow_production_operation,
        production_operation_ack=production_operation_ack,
    )

    metadata_ref = f"raw://drive/{file_id}/{modified_time}/metadata.json"
    content_ref = f"raw://drive/{file_id}/{modified_time}/content.txt"
    return metadata_ref, content_ref


def _redacted_drive_backfill_item(
    *,
    persisted: bool,
    duplicate: bool | None = None,
    event_id: str | None = None,
) -> dict:
    item = {
        "accepted": True,
        "persisted": persisted,
        "redacted": True,
        "source_system": "drive",
        "source_object_type": "file",
        "event_type": "drive.file.ingested",
    }
    if duplicate is not None:
        item["duplicate"] = duplicate
    if event_id is not None:
        item["event_id"] = event_id
    return item


def _redacted_drive_backfill_response(
    *,
    discovered: int,
    saved: int,
    duplicates: int,
    max_results: int,
    persist: bool,
    events: list[dict],
) -> dict:
    return {
        "provider": "drive",
        "persist": persist,
        "max_results": max_results,
        "redacted": True,
        "discovered": discovered,
        "saved": saved,
        "duplicates": duplicates,
        "events": events,
    }


@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED)
async def drive_backfill(
    persist: bool = Query(True),
    max_results: int = Query(
        DRIVE_BACKFILL_DEFAULT_MAX_RESULTS,
        ge=1,
        le=DRIVE_BACKFILL_MAX_RESULTS,
    ),
    allow_production_operation: bool = Query(False),
    confirm_production_operation: str | None = Query(None),
) -> dict:
    _require_drive_backfill_enabled()
    if persist:
        try:
            require_production_operation_ack(
                operation_class=SOURCE_OF_TRUTH_MUTATION,
                boundary="drive_backfill_persist",
                allow_production_operation=allow_production_operation,
                production_operation_ack=confirm_production_operation,
            )
        except ProductionOperationBlockedError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=exc.reason_code,
            ) from exc

    files = list_ai_inbox_files(max_results=max_results)
    events = []
    saved = 0
    duplicates = 0

    if not persist:
        for _file_metadata in files:
            events.append(_redacted_drive_backfill_item(persisted=False))
        return _redacted_drive_backfill_response(
            discovered=len(files),
            saved=0,
            duplicates=0,
            max_results=max_results,
            persist=persist,
            events=events,
        )

    async with AsyncSessionLocal() as session:
        session.add(
            AuditLog(
                event_type="drive.backfill.started",
                actor="system",
                correlation_id="system",
                trace_id="system",
                payload={"files": len(files)},
            )
        )

        for file_metadata in files:
            event = build_drive_event(file_metadata)
            existing = await session.scalar(
                select(IngestedEvent).where(IngestedEvent.idempotency_key == event.idempotency_key)
            )
            if existing:
                duplicates += 1
                events.append(
                    _redacted_drive_backfill_item(
                        persisted=True,
                        duplicate=True,
                        event_id=existing.event_id,
                    )
                )
                continue

            text = download_file_text(file_metadata["id"], file_metadata.get("mimeType"))
            metadata_ref, content_ref = save_drive_raw_snapshot(
                file_metadata,
                text,
                allow_production_operation=allow_production_operation,
                production_operation_ack=confirm_production_operation,
            )
            content_hash = sha256_text(text)
            source_document_id = f"drive:{file_metadata['id']}:{content_hash[:12]}"
            chunks = chunk_text(text)

            event.raw_object_ref = metadata_ref
            event.payload = {
                **event.payload,
                "raw_content_ref": content_ref,
                "content_hash": content_hash,
                "source_document_id": source_document_id,
                "chunks_found": len(chunks),
                "text_preview": text[:500],
            }

            ingested_event = IngestedEvent(
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
            session.add(ingested_event)
            await session.flush()
            await normalize_ingested_event_to_source_event(session, ingested_event)
            existing_doc = await session.scalar(
                select(SourceDocument).where(SourceDocument.source_document_id == source_document_id)
            )
            if not existing_doc:
                session.add(
                    SourceDocument(
                        source_document_id=source_document_id,
                        source_system="drive",
                        source_object_id=file_metadata["id"],
                        title=file_metadata.get("name"),
                        source_url=file_metadata.get("webViewLink"),
                        mime_type=file_metadata.get("mimeType"),
                        raw_object_ref=content_ref,
                        content_hash=content_hash,
                        modified_at=file_metadata.get("modifiedTime"),
                        metadata_json=file_metadata,
                    )
                )
                for chunk in chunks:
                    session.add(
                        DocumentChunk(
                            source_document_id=source_document_id,
                            chunk_id=chunk.chunk_id,
                            source_system="drive",
                            source_object_id=file_metadata["id"],
                            raw_object_ref=content_ref,
                            text=chunk.text,
                            start_char=chunk.start_char,
                            end_char=chunk.end_char,
                            content_hash=sha256_text(chunk.text),
                            metadata_json={"source_url": file_metadata.get("webViewLink")},
                        )
                    )
            session.add(
                AuditLog(
                    event_type=event.event_type,
                    actor="system",
                    correlation_id=event.correlation_id,
                    trace_id=event.trace_id,
                    after_ref=event.event_id,
                    payload={
                        "idempotency_key": event.idempotency_key,
                        "source_object_id": event.source_object_id,
                        "name": file_metadata.get("name"),
                    },
                )
            )

            saved += 1
            events.append(
                _redacted_drive_backfill_item(
                    persisted=True,
                    duplicate=False,
                    event_id=event.event_id,
                )
            )

        await session.commit()

    return _redacted_drive_backfill_response(
        discovered=len(files),
        saved=saved,
        duplicates=duplicates,
        max_results=max_results,
        persist=persist,
        events=events,
    )
