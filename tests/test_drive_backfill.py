from fastapi.testclient import TestClient

import app.api.drive as drive_api
from app.db.models import IngestedEvent
from app.integrations.source_registry import validate_source_event_contract
from app.main import app
from app.services.production_operation_guard import PRODUCTION_OPERATION_ACK

DRIVE_FOLDER_ID = "drive-folder-test"
SAFE_DRIVE_LIMIT = 7
PROD_OPERATION_PARAMS = {
    "allow_production_operation": "true",
    "confirm_production_operation": PRODUCTION_OPERATION_ACK,
}


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

    def fail_list_ai_inbox_files(*, max_results: int) -> list[dict]:
        raise AssertionError("disabled Drive backfill must not call connector path")

    monkeypatch.setattr(drive_api, "list_ai_inbox_files", fail_list_ai_inbox_files)

    with TestClient(app) as client:
        response = client.post("/v1/drive/backfill?persist=false")

    assert response.status_code == 403
    assert response.json() == {"detail": "Google Drive backfill is disabled."}


def test_enabled_drive_backfill_requires_folder_boundary(monkeypatch) -> None:
    _enable_drive_backfill(monkeypatch, folder_id=None)

    def fail_list_ai_inbox_files(*, max_results: int) -> list[dict]:
        raise AssertionError("Drive backfill without folder boundary must not call connector path")

    monkeypatch.setattr(drive_api, "list_ai_inbox_files", fail_list_ai_inbox_files)

    with TestClient(app) as client:
        missing = client.post("/v1/drive/backfill?persist=false")
        _enable_drive_backfill(monkeypatch, folder_id="  ")
        blank = client.post("/v1/drive/backfill?persist=false")

    assert missing.status_code == 400
    assert missing.json() == {
        "detail": "Google Drive backfill requires GOOGLE_DRIVE_AI_INBOX_FOLDER_ID."
    }
    assert blank.status_code == 400
    assert blank.json() == {
        "detail": "Google Drive backfill requires GOOGLE_DRIVE_AI_INBOX_FOLDER_ID."
    }


def test_enabled_drive_backfill_rejects_invalid_limits_without_calling_connector(
    monkeypatch,
) -> None:
    _enable_drive_backfill(monkeypatch)

    def fail_list_ai_inbox_files(*, max_results: int) -> list[dict]:
        raise AssertionError("invalid Drive limit must not call connector path")

    monkeypatch.setattr(drive_api, "list_ai_inbox_files", fail_list_ai_inbox_files)

    with TestClient(app) as client:
        zero = client.post("/v1/drive/backfill?persist=false&max_results=0")
        negative = client.post("/v1/drive/backfill?persist=false&max_results=-1")
        too_large = client.post(
            f"/v1/drive/backfill?persist=false&max_results="
            f"{drive_api.DRIVE_BACKFILL_MAX_RESULTS + 1}"
        )

    assert zero.status_code == 422
    assert negative.status_code == 422
    assert too_large.status_code == 422


def test_enabled_drive_backfill_uses_safe_default_limit(monkeypatch) -> None:
    seen_limits: list[int] = []
    _enable_drive_backfill(monkeypatch)

    def fake_list_ai_inbox_files(*, max_results: int) -> list[dict]:
        seen_limits.append(max_results)
        return []

    monkeypatch.setattr(drive_api, "list_ai_inbox_files", fake_list_ai_inbox_files)

    with TestClient(app) as client:
        response = client.post("/v1/drive/backfill?persist=false")

    assert response.status_code == 202
    assert response.json()["discovered"] == 0
    assert seen_limits == [drive_api.DRIVE_BACKFILL_DEFAULT_MAX_RESULTS]


def test_drive_backfill_contract(monkeypatch):
    seen_limits: list[int] = []
    _enable_drive_backfill(monkeypatch)
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

    def fake_list_ai_inbox_files(*, max_results: int) -> list[dict]:
        seen_limits.append(max_results)
        return [file_metadata]

    monkeypatch.setattr(
        drive_api,
        "list_ai_inbox_files",
        fake_list_ai_inbox_files,
    )
    with TestClient(app) as client:
        response = client.post(f"/v1/drive/backfill?persist=false&max_results={SAFE_DRIVE_LIMIT}")
    assert response.status_code == 202
    body = response.json()
    assert body["provider"] == "drive"
    assert body["persist"] is False
    assert body["max_results"] == SAFE_DRIVE_LIMIT
    assert body["redacted"] is True
    assert body["discovered"] == 1
    assert body["saved"] == 0
    assert body["duplicates"] == 0
    assert body["events"] == [
        {
            "accepted": True,
            "persisted": False,
            "redacted": True,
            "source_system": "drive",
            "source_object_type": "file",
            "event_type": "drive.file.ingested",
        }
    ]
    assert seen_limits == [SAFE_DRIVE_LIMIT]
    assert "file1" not in response.text
    assert "demo.txt" not in response.text


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
        lambda max_results: [
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
        response = client.post(
            "/v1/drive/backfill",
            params={"persist": "true", **PROD_OPERATION_PARAMS},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["saved"] == 1
    assert body["provider"] == "drive"
    assert body["redacted"] is True
    assert body["events"][0]["persisted"] is True
    assert body["events"][0]["duplicate"] is False
    assert body["events"][0]["event_id"].startswith("evt_")
    assert "file1" not in response.text
    assert "demo.txt" not in response.text
    assert "Drive text" not in response.text
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


def test_drive_backfill_response_omits_raw_full_document_content(monkeypatch, tmp_path):
    added: list[object] = []
    normalized: list[IngestedEvent] = []
    raw_content = "PRIVATE_DRIVE_DOCUMENT_CONTENT_DO_NOT_RETURN"
    private_file_name = "PRIVATE_DRIVE_FILENAME_DO_NOT_RETURN"
    private_web_view_link = "https://drive.example.test/private-link-do-not-return"
    private_web_content_link = "https://drive.example.test/private-content-do-not-return"
    _enable_drive_backfill(monkeypatch)

    async def fake_normalize(session, ingested_event):
        normalized.append(ingested_event)
        return None

    monkeypatch.setattr(
        drive_api,
        "list_ai_inbox_files",
        lambda max_results: [
            {
                "id": "file-private",
                "name": private_file_name,
                "modifiedTime": "2026-01-01T00:00:00Z",
                "mimeType": "text/plain",
                "webViewLink": private_web_view_link,
                "webContentLink": private_web_content_link,
            }
        ],
    )
    monkeypatch.setattr(
        drive_api,
        "download_file_text",
        lambda file_id, mime_type=None: raw_content,
    )
    monkeypatch.setattr(drive_api, "raw_storage_root", lambda: tmp_path)
    monkeypatch.setattr(drive_api, "AsyncSessionLocal", _fake_session_factory(added))
    monkeypatch.setattr(drive_api, "normalize_ingested_event_to_source_event", fake_normalize)

    with TestClient(app) as client:
        response = client.post(
            "/v1/drive/backfill",
            params={
                "persist": "true",
                "max_results": SAFE_DRIVE_LIMIT,
                **PROD_OPERATION_PARAMS,
            },
        )

    assert response.status_code == 202
    body = response.json()
    assert body["provider"] == "drive"
    assert body["redacted"] is True
    assert body["saved"] == 1
    assert body["events"][0]["redacted"] is True
    assert raw_content not in response.text
    assert private_file_name not in response.text
    assert private_web_view_link not in response.text
    assert private_web_content_link not in response.text
    assert "file-private" not in response.text
    assert "source_document_id" not in body["events"][0]
    assert "source_object_id" not in body["events"][0]
    assert "payload" not in body["events"][0]
