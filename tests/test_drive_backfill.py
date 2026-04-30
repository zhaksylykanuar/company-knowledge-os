from fastapi.testclient import TestClient

import app.api.drive as drive_api
from app.db.models import IngestedEvent
from app.integrations.source_registry import validate_source_event_contract
from app.main import app

DRIVE_FOLDER_ID = "drive-folder-test"


class FakeAsyncSession:
    def __init__(self, added: list[object]) -> None:
        self.added = added

    async def __aenter__(self) -> "FakeAsyncSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def scalar(self, statement) -> None:
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


def _fake_session_factory(added: list[object]):
    def factory() -> FakeAsyncSession:
        return FakeAsyncSession(added)

    return factory


def _enable_drive_backfill(monkeypatch, *, folder_id: str | None = DRIVE_FOLDER_ID) -> None:
    monkeypatch.setattr(drive_api.settings, "google_drive_backfill_enabled", True)
    monkeypatch.setattr(drive_api.settings, "google_drive_ai_inbox_folder_id", folder_id)


def test_drive_backfill_rejects_when_disabled_without_calling_connector(monkeypatch) -> None:
    monkeypatch.setattr(drive_api.settings, "google_drive_backfill_enabled", False)
    monkeypatch.setattr(drive_api.settings, "google_drive_ai_inbox_folder_id", DRIVE_FOLDER_ID)

    def fail_list_ai_inbox_files() -> list[dict]:
        raise AssertionError("disabled Drive backfill must not call connector path")

    monkeypatch.setattr(drive_api, "list_ai_inbox_files", fail_list_ai_inbox_files)

    with TestClient(app) as client:
        response = client.post("/v1/drive/backfill?persist=false")

    assert response.status_code == 403
    assert response.json() == {"detail": "Google Drive backfill is disabled."}


def test_enabled_drive_backfill_requires_folder_boundary(monkeypatch) -> None:
    _enable_drive_backfill(monkeypatch, folder_id=None)

    def fail_list_ai_inbox_files() -> list[dict]:
        raise AssertionError("Drive backfill without folder boundary must not call connector path")

    monkeypatch.setattr(drive_api, "list_ai_inbox_files", fail_list_ai_inbox_files)

    with TestClient(app) as client:
        response = client.post("/v1/drive/backfill?persist=false")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Google Drive backfill requires GOOGLE_DRIVE_AI_INBOX_FOLDER_ID."
    }


def test_drive_backfill_contract(monkeypatch):
    _enable_drive_backfill(monkeypatch)
    monkeypatch.setattr(
        drive_api,
        "list_ai_inbox_files",
        lambda: [{"id": "file1", "name": "demo.txt", "modifiedTime": "2026-01-01T00:00:00Z"}],
    )
    with TestClient(app) as client:
        response = client.post("/v1/drive/backfill?persist=false")
    assert response.status_code == 202
    body = response.json()
    event = body["events"][0]
    payload = event["payload"]

    assert event["idempotency_key"] == "drive:file:file1:2026-01-01T00:00:00Z"
    assert event["event_type"] == "drive.file.ingested"
    assert payload["source_object_type"] == "file"
    assert payload["title"] == "demo.txt"
    assert validate_source_event_contract(
        source_system=event["source_system"],
        source_object_type=payload["source_object_type"],
        event_type=event["event_type"],
        payload=payload,
    ) == []


def test_drive_backfill_persist_normalizes_new_ingested_event(monkeypatch, tmp_path):
    added: list[object] = []
    normalized: list[IngestedEvent] = []
    _enable_drive_backfill(monkeypatch)

    async def fake_normalize(session, ingested_event):
        normalized.append(ingested_event)
        return None

    monkeypatch.setattr(
        drive_api,
        "list_ai_inbox_files",
        lambda: [
            {
                "id": "file1",
                "name": "demo.txt",
                "modifiedTime": "2026-01-01T00:00:00Z",
                "mimeType": "text/plain",
            }
        ],
    )
    monkeypatch.setattr(drive_api, "download_file_text", lambda file_id, mime_type=None: "Drive text")
    monkeypatch.setattr(drive_api, "raw_storage_root", lambda: tmp_path)
    monkeypatch.setattr(drive_api, "AsyncSessionLocal", _fake_session_factory(added))
    monkeypatch.setattr(drive_api, "normalize_ingested_event_to_source_event", fake_normalize)

    with TestClient(app) as client:
        response = client.post("/v1/drive/backfill?persist=true")

    assert response.status_code == 202
    assert response.json()["saved"] == 1
    assert len(normalized) == 1

    ingested_event = normalized[0]
    assert ingested_event in added
    assert ingested_event.event_type == "drive.file.ingested"
    assert ingested_event.source_system == "drive"
    assert ingested_event.source_object_id == "file1"
    assert ingested_event.payload["source_object_type"] == "file"
    assert ingested_event.payload["title"] == "demo.txt"
    assert ingested_event.raw_object_ref == "raw://drive/file1/2026-01-01T00-00-00Z/metadata.json"
    assert ingested_event.payload["raw_content_ref"] == (
        "raw://drive/file1/2026-01-01T00-00-00Z/content.txt"
    )
    assert ingested_event.trace_id
    assert ingested_event.correlation_id
