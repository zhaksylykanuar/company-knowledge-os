import base64

from fastapi.testclient import TestClient

import app.api.gmail as gmail_api
from app.db.models import IngestedEvent
from app.db.source_models import DocumentChunk, SourceDocument
from app.integrations.source_registry import validate_source_event_contract
from app.main import app
from app.services.raw_storage import sha256_text

SAFE_GMAIL_QUERY = "label:founderos-test"
BROAD_GMAIL_QUERY = "in:inbox OR in:sent"


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


def _gmail_body_data(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def _enable_gmail_backfill(monkeypatch, *, configured_query: str | None = None) -> None:
    monkeypatch.setattr(gmail_api.settings, "google_gmail_backfill_enabled", True)
    monkeypatch.setattr(gmail_api.settings, "google_gmail_backfill_query", configured_query)


def test_gmail_backfill_rejects_when_disabled_without_calling_connector(monkeypatch) -> None:
    monkeypatch.setattr(gmail_api.settings, "google_gmail_backfill_enabled", False)

    def fail_list_messages(query: str, max_results: int) -> list[dict]:
        raise AssertionError("disabled Gmail backfill must not call connector path")

    monkeypatch.setattr(gmail_api, "list_messages", fail_list_messages)

    with TestClient(app) as client:
        response = client.post(
            "/v1/gmail/backfill",
            params={"max_results": 1, "persist": "false", "query": SAFE_GMAIL_QUERY},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Gmail backfill is disabled."}


def test_enabled_gmail_backfill_rejects_missing_blank_or_broad_query(monkeypatch) -> None:
    _enable_gmail_backfill(monkeypatch)

    def fail_list_messages(query: str, max_results: int) -> list[dict]:
        raise AssertionError("invalid Gmail query must not call connector path")

    monkeypatch.setattr(gmail_api, "list_messages", fail_list_messages)

    with TestClient(app) as client:
        missing = client.post(
            "/v1/gmail/backfill",
            params={"max_results": 1, "persist": "false"},
        )
        blank = client.post(
            "/v1/gmail/backfill",
            params={"max_results": 1, "persist": "false", "query": "  "},
        )
        broad = client.post(
            "/v1/gmail/backfill",
            params={"max_results": 1, "persist": "false", "query": BROAD_GMAIL_QUERY},
        )

    assert missing.status_code == 400
    assert missing.json() == {"detail": "Gmail backfill requires an explicit safe query."}
    assert blank.status_code == 400
    assert blank.json() == {"detail": "Gmail backfill requires an explicit safe query."}
    assert broad.status_code == 400
    assert broad.json() == {
        "detail": "Gmail backfill query is too broad; choose a narrower query."
    }


def test_enabled_gmail_backfill_can_use_configured_safe_query(monkeypatch) -> None:
    seen_queries: list[str] = []
    _enable_gmail_backfill(monkeypatch, configured_query=SAFE_GMAIL_QUERY)

    def fake_list_messages(query: str, max_results: int) -> list[dict]:
        seen_queries.append(query)
        return []

    monkeypatch.setattr(
        gmail_api,
        "list_messages",
        fake_list_messages,
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/gmail/backfill",
            params={"max_results": 1, "persist": "false"},
        )

    assert response.status_code == 202
    assert response.json()["discovered"] == 0
    assert seen_queries == [SAFE_GMAIL_QUERY]


def test_gmail_backfill_contract(monkeypatch):
    _enable_gmail_backfill(monkeypatch)
    monkeypatch.setattr(
        gmail_api,
        "list_messages",
        lambda query=SAFE_GMAIL_QUERY, max_results=10: [{"id": "m1"}],
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
        response = client.post(
            "/v1/gmail/backfill",
            params={"max_results": 1, "persist": "false", "query": SAFE_GMAIL_QUERY},
        )
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


def test_extract_readable_gmail_body_text_prefers_nested_plain_text() -> None:
    msg = {
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/html",
                            "body": {"data": _gmail_body_data("<p>HTML body</p>")},
                        },
                        {
                            "mimeType": "text/plain",
                            "body": {"data": _gmail_body_data("Plain body")},
                        },
                    ],
                }
            ],
        }
    }

    assert gmail_api.extract_readable_gmail_body_text(msg) == "Plain body"


def test_extract_readable_gmail_body_text_falls_back_to_html() -> None:
    msg = {
        "payload": {
            "mimeType": "text/html",
            "body": {
                "data": _gmail_body_data(
                    "<html><body><p>Hello <strong>team</strong></p><p>Next step</p></body></html>"
                )
            },
        }
    }

    assert gmail_api.extract_readable_gmail_body_text(msg) == "Hello team\nNext step"


def test_extract_readable_gmail_body_text_skips_attachment_parts() -> None:
    msg = {
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "filename": "notes.txt",
                    "mimeType": "text/plain",
                    "body": {
                        "attachmentId": "att-1",
                        "data": _gmail_body_data("Attachment content"),
                    },
                },
                {
                    "mimeType": "text/plain",
                    "body": {"data": _gmail_body_data("Inline body")},
                },
            ],
        }
    }

    assert gmail_api.extract_readable_gmail_body_text(msg) == "Inline body"


def test_build_gmail_document_records_skips_messages_without_readable_body() -> None:
    msg = {
        "id": "m1",
        "threadId": "t1",
        "historyId": "h1",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "filename": "notes.txt",
                    "mimeType": "text/plain",
                    "body": {
                        "attachmentId": "att-1",
                        "data": _gmail_body_data("Attachment content"),
                    },
                }
            ],
        },
    }

    source_document, chunks, readable_text = gmail_api.build_gmail_document_records(
        msg, "raw://gmail/m1/h1/message.json"
    )

    assert source_document is None
    assert chunks == []
    assert readable_text is None


def test_gmail_backfill_persist_creates_source_document_and_chunk(monkeypatch, tmp_path):
    added: list[object] = []
    normalized: list[IngestedEvent] = []
    readable_text = "Hello from Gmail body.\nDecision: use the document chunk path."
    _enable_gmail_backfill(monkeypatch)

    async def fake_normalize(session, ingested_event):
        normalized.append(ingested_event)
        return None

    monkeypatch.setattr(
        gmail_api,
        "list_messages",
        lambda query=SAFE_GMAIL_QUERY, max_results=10: [{"id": "m1"}],
    )
    monkeypatch.setattr(
        gmail_api,
        "get_message",
        lambda mid: {
            "id": mid,
            "threadId": "t1",
            "historyId": "h1",
            "internalDate": "1767225600000",
            "labelIds": ["INBOX"],
            "snippet": "ignored snippet",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Subject", "value": "FounderOS weekly update"},
                    {"name": "From", "value": "founder@example.com"},
                    {"name": "To", "value": "team@example.com"},
                ],
                "body": {"data": _gmail_body_data(readable_text)},
            },
        },
    )
    monkeypatch.setattr(gmail_api, "raw_storage_root", lambda: tmp_path)
    monkeypatch.setattr(gmail_api, "AsyncSessionLocal", _fake_session_factory(added))
    monkeypatch.setattr(gmail_api, "normalize_ingested_event_to_source_event", fake_normalize)

    with TestClient(app) as client:
        response = client.post(
            "/v1/gmail/backfill",
            params={"max_results": 1, "persist": "true", "query": SAFE_GMAIL_QUERY},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["saved"] == 1

    source_document = next(item for item in added if isinstance(item, SourceDocument))
    chunks = [item for item in added if isinstance(item, DocumentChunk)]
    raw_ref = "raw://gmail/m1/h1/message.json"

    assert (tmp_path / "gmail" / "m1" / "h1" / "message.json").exists()
    assert source_document.source_system == "gmail"
    assert source_document.source_object_id == "m1"
    assert source_document.raw_object_ref == raw_ref
    assert source_document.content_hash == sha256_text(readable_text)
    assert source_document.title == "FounderOS weekly update"
    assert source_document.metadata_json["message_id"] == "m1"
    assert source_document.metadata_json["thread_id"] == "t1"
    assert source_document.metadata_json["subject"] == "FounderOS weekly update"
    assert source_document.metadata_json["raw_object_ref"] == raw_ref

    assert len(chunks) == 1
    assert chunks[0].source_system == "gmail"
    assert chunks[0].source_object_id == "m1"
    assert chunks[0].raw_object_ref == raw_ref
    assert chunks[0].text == readable_text
    assert chunks[0].content_hash == sha256_text(chunks[0].text)
    assert chunks[0].metadata_json["message_id"] == "m1"
    assert chunks[0].metadata_json["thread_id"] == "t1"
    assert chunks[0].metadata_json["subject"] == "FounderOS weekly update"

    assert len(normalized) == 1
    ingested_event = normalized[0]
    assert ingested_event in added
    assert ingested_event.event_type == "gmail.message.ingested"
    assert ingested_event.source_system == "gmail"
    assert ingested_event.source_object_id == "m1"
    assert ingested_event.raw_object_ref == raw_ref
    assert ingested_event.payload["source_object_type"] == "message"
    assert ingested_event.payload["subject"] == "FounderOS weekly update"


def test_gmail_backfill_persist_skips_source_event_without_subject(monkeypatch, tmp_path):
    added: list[object] = []
    normalized: list[IngestedEvent] = []
    readable_text = "Readable body without a subject should still persist raw data."
    _enable_gmail_backfill(monkeypatch)

    async def fake_normalize(session, ingested_event):
        normalized.append(ingested_event)
        return None

    monkeypatch.setattr(
        gmail_api,
        "list_messages",
        lambda query=SAFE_GMAIL_QUERY, max_results=10: [{"id": "m2"}],
    )
    monkeypatch.setattr(
        gmail_api,
        "get_message",
        lambda mid: {
            "id": mid,
            "threadId": "t2",
            "historyId": "h2",
            "labelIds": ["INBOX"],
            "snippet": "ignored snippet",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "founder@example.com"},
                    {"name": "To", "value": "team@example.com"},
                ],
                "body": {"data": _gmail_body_data(readable_text)},
            },
        },
    )
    monkeypatch.setattr(gmail_api, "raw_storage_root", lambda: tmp_path)
    monkeypatch.setattr(gmail_api, "AsyncSessionLocal", _fake_session_factory(added))
    monkeypatch.setattr(gmail_api, "normalize_ingested_event_to_source_event", fake_normalize)

    with TestClient(app) as client:
        response = client.post(
            "/v1/gmail/backfill",
            params={"max_results": 1, "persist": "true", "query": SAFE_GMAIL_QUERY},
        )

    assert response.status_code == 202
    assert response.json()["saved"] == 1
    assert normalized == []

    raw_ref = "raw://gmail/m2/h2/message.json"
    ingested_event = next(item for item in added if isinstance(item, IngestedEvent))
    source_document = next(item for item in added if isinstance(item, SourceDocument))

    assert (tmp_path / "gmail" / "m2" / "h2" / "message.json").exists()
    assert ingested_event.event_type == "gmail.message.ingested"
    assert ingested_event.raw_object_ref == raw_ref
    assert ingested_event.payload["source_object_type"] == "message"
    assert "subject" not in ingested_event.payload
    assert source_document.source_system == "gmail"
    assert source_document.source_object_id == "m2"
    assert source_document.title is None
