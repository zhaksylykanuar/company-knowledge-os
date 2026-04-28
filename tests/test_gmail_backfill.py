from fastapi.testclient import TestClient

import app.api.gmail as gmail_api
from app.integrations.source_registry import validate_source_event_contract
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
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "FounderOS weekly update"},
                ],
            },
        },
    )
    with TestClient(app) as client:
        response = client.post("/v1/gmail/backfill?max_results=1&persist=false")
    assert response.status_code == 202
    body = response.json()
    event = body["events"][0]
    payload = event["payload"]

    assert event["idempotency_key"] == "gmail:message:m1:h1"
    assert event["source_system"] == "gmail"
    assert event["event_type"] == "gmail.message.ingested"
    assert payload["source_object_type"] == "message"
    assert payload["subject"] == "FounderOS weekly update"
    assert validate_source_event_contract(
        source_system=event["source_system"],
        source_object_type=payload["source_object_type"],
        event_type=event["event_type"],
        payload=payload,
    ) == []
