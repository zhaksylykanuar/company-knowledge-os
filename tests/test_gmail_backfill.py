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
SAFE_GMAIL_LIMIT = 7


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

    async def rollback(self) -> None:
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
    seen_calls: list[tuple[str, int]] = []
    _enable_gmail_backfill(monkeypatch, configured_query=SAFE_GMAIL_QUERY)

    def fake_list_messages(query: str, max_results: int) -> list[dict]:
        seen_calls.append((query, max_results))
        return []

    monkeypatch.setattr(
        gmail_api,
        "list_messages",
        fake_list_messages,
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/gmail/backfill",
            params={"max_results": SAFE_GMAIL_LIMIT, "persist": "false"},
        )

    assert response.status_code == 202
    assert response.json()["discovered"] == 0
    assert seen_calls == [(SAFE_GMAIL_QUERY, SAFE_GMAIL_LIMIT)]


def test_enabled_gmail_backfill_uses_safe_default_limit(monkeypatch) -> None:
    seen_calls: list[tuple[str, int]] = []
    _enable_gmail_backfill(monkeypatch, configured_query=SAFE_GMAIL_QUERY)

    def fake_list_messages(query: str, max_results: int) -> list[dict]:
        seen_calls.append((query, max_results))
        return []

    monkeypatch.setattr(gmail_api, "list_messages", fake_list_messages)

    with TestClient(app) as client:
        response = client.post(
            "/v1/gmail/backfill",
            params={"persist": "false"},
        )

    assert response.status_code == 202
    assert response.json()["discovered"] == 0
    assert seen_calls == [
        (SAFE_GMAIL_QUERY, gmail_api.GMAIL_BACKFILL_DEFAULT_MAX_RESULTS)
    ]


def test_gmail_backfill_connector_failure_returns_safe_non_500(monkeypatch) -> None:
    unsafe_marker = "PRIVATE_CONNECTOR_FAILURE_MARKER_DO_NOT_RETURN"
    monkeypatch.setattr(gmail_api.settings, "api_auth_enabled", False)
    _enable_gmail_backfill(monkeypatch, configured_query=SAFE_GMAIL_QUERY)

    def fail_list_messages(query: str, max_results: int) -> list[dict]:
        raise FileNotFoundError(unsafe_marker)

    monkeypatch.setattr(gmail_api, "list_messages", fail_list_messages)

    with TestClient(app) as client:
        response = client.post(
            "/v1/gmail/backfill",
            params={"persist": "true"},
        )

    assert response.status_code == gmail_api.status.HTTP_424_FAILED_DEPENDENCY
    assert response.json() == {"detail": "Gmail backfill dependency is unavailable."}
    assert unsafe_marker not in response.text


def test_enabled_gmail_backfill_rejects_invalid_limits_without_calling_connector(
    monkeypatch,
) -> None:
    _enable_gmail_backfill(monkeypatch)

    def fail_list_messages(query: str, max_results: int) -> list[dict]:
        raise AssertionError("invalid Gmail limit must not call connector path")

    monkeypatch.setattr(gmail_api, "list_messages", fail_list_messages)

    with TestClient(app) as client:
        zero = client.post(
            "/v1/gmail/backfill",
            params={"max_results": 0, "persist": "false", "query": SAFE_GMAIL_QUERY},
        )
        negative = client.post(
            "/v1/gmail/backfill",
            params={"max_results": -1, "persist": "false", "query": SAFE_GMAIL_QUERY},
        )
        too_large = client.post(
            "/v1/gmail/backfill",
            params={
                "max_results": gmail_api.GMAIL_BACKFILL_MAX_RESULTS + 1,
                "persist": "false",
                "query": SAFE_GMAIL_QUERY,
            },
        )

    assert zero.status_code == 422
    assert negative.status_code == 422
    assert too_large.status_code == 422


def test_gmail_backfill_contract(monkeypatch):
    _enable_gmail_backfill(monkeypatch)
    msg = {
        "id": "m1",
        "threadId": "t1",
        "historyId": "h1",
        "labelIds": ["INBOX"],
        "snippet": "hello",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "FounderOS weekly update"},
            ],
        },
    }
    event = gmail_api.build_gmail_event(msg)

    assert event.idempotency_key == "gmail:message:m1:h1"
    assert event.source_system == "gmail"
    assert event.event_type == "gmail.message.ingested"
    assert event.payload["source_object_type"] == "message"
    assert event.payload["subject"] == "FounderOS weekly update"
    assert validate_source_event_contract(
        source_system=event.source_system,
        source_object_type=event.payload["source_object_type"],
        event_type=event.event_type,
        payload=event.payload,
    ) == []

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
    assert body["provider"] == "gmail"
    assert body["persist"] is False
    assert body["max_results"] == 1
    assert body["redacted"] is True
    assert body["discovered"] == 1
    assert body["saved"] == 0
    assert body["duplicates"] == 0
    assert body["events"] == [
        {
            "accepted": True,
            "persisted": False,
            "redacted": True,
            "source_system": "gmail",
            "source_object_type": "message",
            "event_type": "gmail.message.ingested",
        }
    ]
    assert "FounderOS weekly update" not in response.text
    assert "hello" not in response.text


def test_gmail_backfill_response_redacts_sensitive_metadata(monkeypatch):
    raw_body = "PRIVATE_GMAIL_BODY_DO_NOT_RETURN"
    private_snippet = "PRIVATE_SNIPPET_DO_NOT_RETURN"
    private_subject = "PRIVATE_SUBJECT_DO_NOT_RETURN"
    private_sender = "private-founder-subject@example.test"
    private_recipient = "private-recipient@example.test"
    private_attachment_name = "PRIVATE_ATTACHMENT_NAME_DO_NOT_RETURN.pdf"
    _enable_gmail_backfill(monkeypatch)

    monkeypatch.setattr(
        gmail_api,
        "list_messages",
        lambda query=SAFE_GMAIL_QUERY, max_results=10: [{"id": "m-private"}],
    )
    monkeypatch.setattr(
        gmail_api,
        "get_message",
        lambda mid: {
            "id": mid,
            "threadId": "t-private",
            "historyId": "h-private",
            "labelIds": ["INBOX"],
            "snippet": private_snippet,
            "payload": {
                "mimeType": "multipart/mixed",
                "headers": [
                    {"name": "Subject", "value": private_subject},
                    {"name": "From", "value": private_sender},
                    {"name": "To", "value": private_recipient},
                ],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": _gmail_body_data(raw_body)},
                    },
                    {
                        "filename": private_attachment_name,
                        "mimeType": "application/pdf",
                        "body": {"attachmentId": "attachment-private"},
                    },
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
    assert body["provider"] == "gmail"
    assert body["redacted"] is True
    assert body["discovered"] == 1
    assert body["events"][0]["redacted"] is True
    assert raw_body not in response.text
    assert _gmail_body_data(raw_body) not in response.text
    assert private_snippet not in response.text
    assert private_subject not in response.text
    assert private_sender not in response.text
    assert private_recipient not in response.text
    assert private_attachment_name not in response.text
    assert "payload" not in body["events"][0]
    assert "idempotency_key" not in body["events"][0]
    assert "source_object_id" not in body["events"][0]
    assert "thread_id" not in body["events"][0]


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
    assert body["provider"] == "gmail"
    assert body["redacted"] is True
    assert body["events"][0]["persisted"] is True
    assert body["events"][0]["duplicate"] is False
    assert body["events"][0]["event_id"].startswith("evt_")
    assert "m1" not in response.text
    assert "t1" not in response.text
    assert "ignored snippet" not in response.text
    assert "FounderOS weekly update" not in response.text
    assert "founder@example.com" not in response.text
    assert "team@example.com" not in response.text
    assert readable_text not in response.text

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


def test_gmail_backfill_persist_reports_per_item_failure_safely(monkeypatch, tmp_path):
    added: list[object] = []
    state = {"flush_calls": 0, "rollbacks": 0}
    unsafe_error_marker = "OFFLINE_PERSISTENCE_FAILURE_MARKER_DO_NOT_RETURN"
    unsafe_body_marker = "OFFLINE_BODY_MARKER_DO_NOT_RETURN"
    _enable_gmail_backfill(monkeypatch)

    class FailingOnceSession(FakeAsyncSession):
        async def flush(self) -> None:
            state["flush_calls"] += 1
            if state["flush_calls"] == 3:
                raise RuntimeError(unsafe_error_marker)

        async def rollback(self) -> None:
            state["rollbacks"] += 1

    def failing_session_factory() -> FailingOnceSession:
        return FailingOnceSession(added)

    refs = [{"id": f"offline-message-{index}"} for index in range(5)]
    messages = {
        ref["id"]: {
            "id": ref["id"],
            "threadId": f"offline-thread-{index}",
            "historyId": f"offline-history-{index}",
            "labelIds": ["OFFLINE_LABEL"],
            "payload": {
                "mimeType": "text/plain",
                "headers": [],
                "body": {"data": _gmail_body_data(f"{unsafe_body_marker}-{index}")},
            },
        }
        for index, ref in enumerate(refs)
    }

    monkeypatch.setattr(
        gmail_api,
        "list_messages",
        lambda query=SAFE_GMAIL_QUERY, max_results=5: refs[:max_results],
    )
    monkeypatch.setattr(gmail_api, "get_message", lambda mid: messages[mid])
    monkeypatch.setattr(gmail_api, "raw_storage_root", lambda: tmp_path)
    monkeypatch.setattr(gmail_api, "AsyncSessionLocal", failing_session_factory)

    with TestClient(app) as client:
        response = client.post(
            "/v1/gmail/backfill",
            params={"max_results": 5, "persist": "true", "query": SAFE_GMAIL_QUERY},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["provider"] == "gmail"
    assert body["persist"] is True
    assert body["max_results"] == 5
    assert body["redacted"] is True
    assert body["discovered"] == 5
    assert body["saved"] == 4
    assert body["duplicates"] == 0
    assert body["failed"] == 1
    assert body["status"] == gmail_api.GMAIL_BACKFILL_STATUS_COMPLETED_WITH_FAILURES
    assert state["flush_calls"] == 5
    assert state["rollbacks"] == 1

    successful_items = [
        item for item in body["events"] if item.get("status") != "persist_failed"
    ]
    failed_items = [
        item for item in body["events"] if item.get("status") == "persist_failed"
    ]
    assert len(successful_items) == 4
    assert len(failed_items) == 1
    assert failed_items[0] == {
        "accepted": False,
        "persisted": False,
        "redacted": True,
        "source_system": "gmail",
        "source_object_type": "message",
        "event_type": "gmail.message.ingested",
        "status": gmail_api.GMAIL_BACKFILL_STATUS_PERSIST_FAILED,
        "error_code": gmail_api.GMAIL_BACKFILL_STATUS_PERSIST_FAILED,
    }
    assert all(item["redacted"] is True for item in body["events"])
    assert all("source_object_id" not in item for item in body["events"])
    assert all("raw_object_ref" not in item for item in body["events"])
    assert len(list((tmp_path / "gmail").glob("*/*/message.json"))) == 5

    for unsafe_marker in (
        unsafe_error_marker,
        unsafe_body_marker,
        "offline-message-",
        "offline-thread-",
        "offline-history-",
        SAFE_GMAIL_QUERY,
    ):
        assert unsafe_marker not in response.text
