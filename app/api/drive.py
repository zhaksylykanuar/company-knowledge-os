from uuid import uuid4

from fastapi import APIRouter, Query, status

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.events.schemas import EventEnvelope
from app.services.raw_storage import raw_storage_root, safe_path_part, write_json, write_text
from app.services.source_control import ACTION_BACKFILL, ACTION_PREVIEW_SYNC, request_source_action

router = APIRouter(prefix="/v1/drive", tags=["drive"])

DRIVE_BACKFILL_DEFAULT_MAX_RESULTS = 10
DRIVE_BACKFILL_MAX_RESULTS = 50


def list_ai_inbox_files(
    *,
    max_results: int,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> list[dict]:
    from app.connectors.google_drive import list_ai_inbox_files as _list_ai_inbox_files

    return _list_ai_inbox_files(
        page_size=max_results,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )


def download_file_text(
    file_id: str,
    mime_type: str | None = None,
    *,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> str:
    from app.connectors.google_drive import download_file_text as _download_file_text

    return _download_file_text(
        file_id,
        mime_type,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )


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


@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED)
async def drive_backfill(
    persist: bool = Query(False),
    max_results: int = Query(
        DRIVE_BACKFILL_DEFAULT_MAX_RESULTS,
        ge=1,
        le=DRIVE_BACKFILL_MAX_RESULTS,
    ),
    allow_production_operation: bool = Query(False),
    confirm_production_operation: str | None = Query(None),
    allow_live_provider_execution: bool = Query(False),
    confirm_live_provider_execution: str | None = Query(None),
    request_key: str | None = Query(None),
) -> dict:
    action_type = ACTION_BACKFILL if persist else ACTION_PREVIEW_SYNC
    safe_request_key = request_key or f"legacy-drive-{action_type}-{uuid4().hex}"
    input_payload = {
        "max_results": max_results,
        "persist_requested": persist,
        "folder_boundary_configured": bool(settings.google_drive_ai_inbox_folder_id),
        "allow_live_provider_execution": bool(allow_live_provider_execution),
        "live_provider_ack_supplied": confirm_live_provider_execution is not None,
        "allow_production_operation": bool(allow_production_operation),
        "production_ack_supplied": confirm_production_operation is not None,
        "legacy_route": "/v1/drive/backfill",
    }
    async with AsyncSessionLocal() as session:
        request = await request_source_action(
            session,
            source_type="drive",
            action_type=action_type,
            request_key=safe_request_key,
            requested_by="legacy_drive_backfill_route",
            input_payload=input_payload,
        )
        await session.commit()
    return {
        "provider": "drive",
        "mode": "source_control_request",
        "redacted": True,
        "persist": persist,
        "max_results": max_results,
        "status": request["status"],
        "request_id": request["request_id"],
        "source_type": request["source_type"],
        "action_type": request["action_type"],
        "source_control_request": request,
    }
