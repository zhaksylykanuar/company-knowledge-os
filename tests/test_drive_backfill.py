from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

import app.api.drive as drive_api
from app.db.base import AsyncSessionLocal, engine
from app.db.models import AuditLog
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.integrations.source_registry import validate_source_event_contract
from app.main import app
from app.services.production_operation_guard import PRODUCTION_OPERATION_ACK
from app.services.source_control import ACTION_BACKFILL, ACTION_PREVIEW_SYNC

DRIVE_FOLDER_ID = "drive-folder-test"
SAFE_DRIVE_LIMIT = 7


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        for table in (
            AuditLog.__table__,
            SourceControlState.__table__,
            SourceRunRequest.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceRunRequest).where(SourceRunRequest.request_key.like(f"%{marker}%"))
        )
        await session.execute(
            delete(SourceControlState).where(
                SourceControlState.last_request_key.like(f"%{marker}%")
            )
        )
        await session.commit()


def _trap_connector(monkeypatch, message: str) -> None:
    def fail_connector_call(*args: object, **kwargs: object) -> None:
        raise AssertionError(message)

    monkeypatch.setattr(drive_api, "list_ai_inbox_files", fail_connector_call)
    monkeypatch.setattr(drive_api, "download_file_text", fail_connector_call)


async def test_drive_backfill_route_records_preview_request_without_connector(
    monkeypatch,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    request_key = f"drive-preview-{marker}"
    private_folder = "PRIVATE_DRIVE_FOLDER_DO_NOT_RETURN"
    monkeypatch.setattr(drive_api.settings, "api_auth_enabled", False)
    monkeypatch.setattr(drive_api.settings, "google_drive_backfill_enabled", False)
    monkeypatch.setattr(drive_api.settings, "google_drive_ai_inbox_folder_id", private_folder)
    _trap_connector(monkeypatch, "Drive request wrapper must not call connector")

    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/drive/backfill",
                params={
                    "request_key": request_key,
                    "max_results": SAFE_DRIVE_LIMIT,
                    "persist": "false",
                },
            )

        assert response.status_code == 202
        body = response.json()
        request = body["source_control_request"]
        assert body["provider"] == "drive"
        assert body["mode"] == "source_control_request"
        assert body["redacted"] is True
        assert body["persist"] is False
        assert body["max_results"] == SAFE_DRIVE_LIMIT
        assert body["status"] == "requested"
        assert body["source_type"] == "drive"
        assert body["action_type"] == ACTION_PREVIEW_SYNC
        assert request["request_key"] == request_key
        assert request["external_side_effect"] is False
        assert request["result_summary"]["mode"] == "request_only"
        assert request["input_snapshot"]["external_side_effect"] is False
        assert request["input_snapshot"]["input"] == {
            "max_results": SAFE_DRIVE_LIMIT,
            "persist_requested": False,
            "folder_boundary_configured": True,
            "allow_live_provider_execution": False,
            "live_provider_ack_supplied": False,
            "allow_production_operation": False,
            "production_ack_supplied": False,
            "legacy_route": "/api/v1/drive/backfill",
        }
        assert private_folder not in response.text

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(SourceRunRequest).where(SourceRunRequest.request_key == request_key)
            )
        assert row is not None
        assert row.source_type == "drive"
        assert row.action_type == ACTION_PREVIEW_SYNC
        assert row.external_side_effect is False
    finally:
        await _cleanup(marker)


async def test_drive_backfill_route_maps_persist_to_backfill_without_ack_or_connector(
    monkeypatch,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    request_key = f"drive-backfill-{marker}"
    monkeypatch.setattr(drive_api.settings, "api_auth_enabled", False)
    monkeypatch.setattr(drive_api.settings, "google_drive_backfill_enabled", False)
    monkeypatch.setattr(drive_api.settings, "google_drive_ai_inbox_folder_id", "")
    _trap_connector(monkeypatch, "Drive backfill request must not call connector")

    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/drive/backfill",
                params={
                    "request_key": request_key,
                    "max_results": 1,
                    "persist": "true",
                },
            )

        assert response.status_code == 202
        body = response.json()
        request = body["source_control_request"]
        assert body["action_type"] == ACTION_BACKFILL
        assert body["persist"] is True
        assert request["source_type"] == "drive"
        assert request["action_type"] == ACTION_BACKFILL
        assert request["external_side_effect"] is False
        assert request["input_snapshot"]["input"]["persist_requested"] is True
        assert request["input_snapshot"]["input"]["folder_boundary_configured"] is False
    finally:
        await _cleanup(marker)


async def test_drive_backfill_route_redacts_operator_acks(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    request_key = f"drive-acks-{marker}"
    private_live_ack = "PRIVATE_DRIVE_LIVE_ACK_DO_NOT_RETURN"
    private_prod_ack = "PRIVATE_DRIVE_PROD_ACK_DO_NOT_RETURN"
    monkeypatch.setattr(drive_api.settings, "api_auth_enabled", False)
    _trap_connector(monkeypatch, "Drive ack capture must not call connector")

    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/drive/backfill",
                params={
                    "request_key": request_key,
                    "persist": "true",
                    "allow_live_provider_execution": "true",
                    "confirm_live_provider_execution": private_live_ack,
                    "allow_production_operation": "true",
                    "confirm_production_operation": private_prod_ack,
                },
            )

        assert response.status_code == 202
        input_snapshot = response.json()["source_control_request"]["input_snapshot"]["input"]
        assert input_snapshot["allow_live_provider_execution"] is True
        assert input_snapshot["live_provider_ack_supplied"] is True
        assert input_snapshot["allow_production_operation"] is True
        assert input_snapshot["production_ack_supplied"] is True
        assert private_live_ack not in response.text
        assert private_prod_ack not in response.text
    finally:
        await _cleanup(marker)


async def test_drive_backfill_route_is_idempotent_by_request_key(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    request_key = f"drive-idempotent-{marker}"
    monkeypatch.setattr(drive_api.settings, "api_auth_enabled", False)
    _trap_connector(monkeypatch, "Drive idempotency request must not call connector")

    try:
        async with _client() as client:
            first = await client.post(
                "/api/v1/drive/backfill",
                params={
                    "request_key": request_key,
                    "max_results": 1,
                    "persist": "false",
                },
            )
            second = await client.post(
                "/api/v1/drive/backfill",
                params={
                    "request_key": request_key,
                    "max_results": 1,
                    "persist": "false",
                },
            )

        assert first.status_code == 202
        assert second.status_code == 202
        first_request = first.json()["source_control_request"]
        second_request = second.json()["source_control_request"]
        assert second_request["idempotent"] is True
        assert second_request["request_id"] == first_request["request_id"]
    finally:
        await _cleanup(marker)


async def test_drive_backfill_route_rejects_invalid_limits_without_request(
    monkeypatch,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    monkeypatch.setattr(drive_api.settings, "api_auth_enabled", False)
    _trap_connector(monkeypatch, "invalid Drive limit must not call connector")

    try:
        async with _client() as client:
            zero = await client.post(
                "/api/v1/drive/backfill",
                params={
                    "request_key": f"drive-zero-{marker}",
                    "persist": "false",
                    "max_results": 0,
                },
            )
            negative = await client.post(
                "/api/v1/drive/backfill",
                params={
                    "request_key": f"drive-negative-{marker}",
                    "persist": "false",
                    "max_results": -1,
                },
            )
            too_large = await client.post(
                "/api/v1/drive/backfill",
                params={
                    "request_key": f"drive-limit-{marker}",
                    "persist": "false",
                    "max_results": drive_api.DRIVE_BACKFILL_MAX_RESULTS + 1,
                },
            )

        assert zero.status_code == 422
        assert negative.status_code == 422
        assert too_large.status_code == 422

        async with AsyncSessionLocal() as session:
            count = len(
                (
                    await session.execute(
                        select(SourceRunRequest).where(
                            SourceRunRequest.request_key.like(f"%{marker}%")
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert count == 0
    finally:
        await _cleanup(marker)


def test_drive_backfill_event_contract() -> None:
    file_metadata = {
        "id": "file1",
        "name": "demo.txt",
        "modifiedTime": "2026-01-01T00:00:00Z",
    }
    event = drive_api.build_drive_event(file_metadata)

    assert event.idempotency_key == "drive:file:file1:2026-01-01T00:00:00Z"
    assert event.event_type == "drive.file.ingested"
    assert event.payload["source_object_type"] == "file"
    assert event.payload["title"] == "demo.txt"
    assert validate_source_event_contract(
        source_system=event.source_system,
        source_object_type=event.payload["source_object_type"],
        event_type=event.event_type,
        payload=event.payload,
    ) == []


def test_save_drive_raw_snapshot_writes_metadata_and_content_with_explicit_ack(tmp_path) -> None:
    file_metadata = {
        "id": "file1",
        "name": "demo.txt",
        "modifiedTime": "2026-01-01T00:00:00Z",
        "mimeType": "text/plain",
    }
    original_root = drive_api.raw_storage_root
    drive_api.raw_storage_root = lambda: tmp_path
    try:
        metadata_ref, content_ref = drive_api.save_drive_raw_snapshot(
            file_metadata,
            "Drive text",
            allow_production_operation=True,
            production_operation_ack=PRODUCTION_OPERATION_ACK,
        )
    finally:
        drive_api.raw_storage_root = original_root

    assert metadata_ref == "raw://drive/file1/2026-01-01T00-00-00Z/metadata.json"
    assert content_ref == "raw://drive/file1/2026-01-01T00-00-00Z/content.txt"
    assert (tmp_path / "drive" / "file1" / "2026-01-01T00-00-00Z" / "metadata.json").exists()
    assert (tmp_path / "drive" / "file1" / "2026-01-01T00-00-00Z" / "content.txt").exists()
