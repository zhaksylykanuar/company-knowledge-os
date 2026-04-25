from fastapi.testclient import TestClient

import app.api.drive as drive_api
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
    assert body["events"][0]["idempotency_key"] == "drive:file:file1:2026-01-01T00:00:00Z"
    assert body["events"][0]["event_type"] == "drive.file.discovered"
