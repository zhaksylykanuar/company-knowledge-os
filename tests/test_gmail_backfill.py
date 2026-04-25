from fastapi.testclient import TestClient

import app.api.gmail as gmail_api
from app.main import app


def test_gmail_backfill_contract(monkeypatch):
    monkeypatch.setattr(
        gmail_api,
        "list_messages",
        lambda query="in:inbox OR in:sent", max_results=10: [{"id": "m1"}],
    )
    monkeypatch.setattr(
        gmail_api,
        "get_message",
        lambda mid: {
            "id": mid,
            "threadId": "t1",
            "historyId": "h1",
            "labelIds": ["INBOX"],
            "snippet": "hello",
        },
    )
    with TestClient(app) as client:
        response = client.post("/v1/gmail/backfill?max_results=1&persist=false")
    assert response.status_code == 202
    body = response.json()
    assert body["events"][0]["idempotency_key"] == "gmail:message:m1:h1"
    assert body["events"][0]["source_system"] == "gmail"
