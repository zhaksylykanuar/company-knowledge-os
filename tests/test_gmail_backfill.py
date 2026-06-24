import base64
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

import app.api.gmail as gmail_api
from app.core.config import settings as app_settings
from app.db.base import AsyncSessionLocal, engine
from app.db.models import AuditLog
from app.db.source_control_models import SourceControlState, SourceRunRequest
from app.integrations.source_registry import validate_source_event_contract
from app.main import app
from app.services.raw_storage import sha256_text
from app.services.source_control import ACTION_BACKFILL, ACTION_PREVIEW_SYNC

SAFE_GMAIL_QUERY = "label:founderos-test"
BROAD_GMAIL_QUERY = "in:inbox OR in:sent"
SAFE_GMAIL_LIMIT = 7


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


def _gmail_body_data(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def _trap_connector(monkeypatch, message: str) -> None:
    def fail_connector_call(*args: object, **kwargs: object) -> None:
        raise AssertionError(message)

    monkeypatch.setattr(gmail_api, "list_messages", fail_connector_call)
    monkeypatch.setattr(gmail_api, "get_message", fail_connector_call)


async def test_gmail_backfill_route_records_preview_request_without_connector(
    monkeypatch,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    request_key = f"gmail-preview-{marker}"
    private_configured_query = "PRIVATE_CONFIGURED_GMAIL_QUERY_DO_NOT_RETURN"
    monkeypatch.setattr(app_settings, "api_auth_enabled", False)
    monkeypatch.setattr(app_settings, "google_gmail_backfill_enabled", False)
    monkeypatch.setattr(app_settings, "google_gmail_backfill_query", private_configured_query)
    _trap_connector(monkeypatch, "Gmail request wrapper must not call connector")

    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/gmail/backfill",
                params={
                    "request_key": request_key,
                    "max_results": SAFE_GMAIL_LIMIT,
                    "persist": "false",
                },
            )

        assert response.status_code == 202
        body = response.json()
        request = body["source_control_request"]
        assert body["provider"] == "gmail"
        assert body["mode"] == "source_control_request"
        assert body["redacted"] is True
        assert body["persist"] is False
        assert body["max_results"] == SAFE_GMAIL_LIMIT
        assert body["status"] == "requested"
        assert body["source_type"] == "gmail"
        assert body["action_type"] == ACTION_PREVIEW_SYNC
        assert request["request_key"] == request_key
        assert request["external_side_effect"] is False
        assert request["result_summary"]["mode"] == "request_only"
        assert request["input_snapshot"]["external_side_effect"] is False
        assert request["input_snapshot"]["input"] == {
            "max_results": SAFE_GMAIL_LIMIT,
            "persist_requested": False,
            "query_provided": False,
            "uses_configured_query": True,
            "allow_live_provider_execution": False,
            "live_provider_ack_supplied": False,
            "allow_production_operation": False,
            "production_ack_supplied": False,
            "legacy_route": "/api/v1/gmail/backfill",
        }
        assert private_configured_query not in response.text

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(SourceRunRequest).where(SourceRunRequest.request_key == request_key)
            )
        assert row is not None
        assert row.source_type == "gmail"
        assert row.action_type == ACTION_PREVIEW_SYNC
        assert row.external_side_effect is False
    finally:
        await _cleanup(marker)


async def test_gmail_backfill_route_maps_persist_to_backfill_without_ack_or_connector(
    monkeypatch,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    request_key = f"gmail-backfill-{marker}"
    monkeypatch.setattr(app_settings, "api_auth_enabled", False)
    monkeypatch.setattr(app_settings, "google_gmail_backfill_enabled", False)
    _trap_connector(monkeypatch, "Gmail backfill request must not call connector")

    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/gmail/backfill",
                params={
                    "request_key": request_key,
                    "max_results": 1,
                    "persist": "true",
                    "query": SAFE_GMAIL_QUERY,
                },
            )

        assert response.status_code == 202
        body = response.json()
        request = body["source_control_request"]
        assert body["action_type"] == ACTION_BACKFILL
        assert body["persist"] is True
        assert request["source_type"] == "gmail"
        assert request["action_type"] == ACTION_BACKFILL
        assert request["external_side_effect"] is False
        assert request["input_snapshot"]["input"]["persist_requested"] is True
        assert request["input_snapshot"]["input"]["query_provided"] is True
        assert request["input_snapshot"]["input"]["uses_configured_query"] is False
        assert SAFE_GMAIL_QUERY not in response.text
    finally:
        await _cleanup(marker)


async def test_gmail_backfill_route_redacts_operator_acks(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    request_key = f"gmail-acks-{marker}"
    private_live_ack = "PRIVATE_LIVE_ACK_DO_NOT_RETURN"
    private_prod_ack = "PRIVATE_PROD_ACK_DO_NOT_RETURN"
    monkeypatch.setattr(app_settings, "api_auth_enabled", False)
    _trap_connector(monkeypatch, "Gmail ack capture must not call connector")

    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/gmail/backfill",
                params={
                    "request_key": request_key,
                    "persist": "true",
                    "query": SAFE_GMAIL_QUERY,
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


async def test_gmail_backfill_route_is_idempotent_by_request_key(monkeypatch) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    request_key = f"gmail-idempotent-{marker}"
    monkeypatch.setattr(app_settings, "api_auth_enabled", False)
    _trap_connector(monkeypatch, "Gmail idempotency request must not call connector")

    try:
        async with _client() as client:
            first = await client.post(
                "/api/v1/gmail/backfill",
                params={
                    "request_key": request_key,
                    "max_results": 1,
                    "persist": "false",
                },
            )
            second = await client.post(
                "/api/v1/gmail/backfill",
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


async def test_gmail_backfill_route_rejects_invalid_explicit_query_before_request(
    monkeypatch,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    monkeypatch.setattr(app_settings, "api_auth_enabled", False)
    monkeypatch.setattr(app_settings, "google_gmail_backfill_enabled", False)
    _trap_connector(monkeypatch, "invalid Gmail query must not call connector")

    try:
        async with _client() as client:
            blank = await client.post(
                "/api/v1/gmail/backfill",
                params={
                    "request_key": f"gmail-blank-{marker}",
                    "max_results": 1,
                    "persist": "false",
                    "query": "  ",
                },
            )
            broad = await client.post(
                "/api/v1/gmail/backfill",
                params={
                    "request_key": f"gmail-broad-{marker}",
                    "max_results": 1,
                    "persist": "false",
                    "query": BROAD_GMAIL_QUERY,
                },
            )
            too_large = await client.post(
                "/api/v1/gmail/backfill",
                params={
                    "request_key": f"gmail-limit-{marker}",
                    "max_results": gmail_api.GMAIL_BACKFILL_MAX_RESULTS + 1,
                    "persist": "false",
                },
            )

        assert blank.status_code == 400
        assert blank.json() == {"detail": "Gmail backfill requires an explicit safe query."}
        assert broad.status_code == 400
        assert broad.json() == {
            "detail": "Gmail backfill query is too broad; choose a narrower query."
        }
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


def test_gmail_backfill_event_contract() -> None:
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


def test_build_gmail_document_records_creates_document_and_chunks() -> None:
    readable_text = "Hello from Gmail body.\nDecision: use the document chunk path."
    msg = {
        "id": "m1",
        "threadId": "t1",
        "historyId": "h1",
        "internalDate": "1767225600000",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "FounderOS weekly update"},
                {"name": "From", "value": "founder@example.com"},
                {"name": "To", "value": "team@example.com"},
            ],
            "body": {"data": _gmail_body_data(readable_text)},
        },
    }
    raw_ref = "raw://gmail/m1/h1/message.json"

    source_document, chunks, extracted_text = gmail_api.build_gmail_document_records(
        msg, raw_ref
    )

    assert extracted_text == readable_text
    assert source_document is not None
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
