from fastapi.testclient import TestClient

import app.api.drive as drive_api
from app.integrations.source_registry import validate_source_event_contract
from app.main import app


def test_drive_backfill_contract(monkeypatch):
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
