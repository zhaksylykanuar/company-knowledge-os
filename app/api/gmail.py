import base64
import binascii
import re
from html.parser import HTMLParser
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, status

from app.db.base import AsyncSessionLocal
from app.db.source_models import DocumentChunk, SourceDocument
from app.events.schemas import EventEnvelope
from app.services.chunking import chunk_text
from app.services.raw_storage import raw_storage_root, safe_path_part, sha256_text, write_json
from app.services.source_control import ACTION_BACKFILL, ACTION_PREVIEW_SYNC, request_source_action

router = APIRouter(prefix="/api/v1/gmail", tags=["gmail"])

BROAD_GMAIL_BACKFILL_QUERY = "in:inbox OR in:sent"
GMAIL_BACKFILL_DEFAULT_MAX_RESULTS = 10
GMAIL_BACKFILL_MAX_RESULTS = 50


def _normalize_gmail_query(query: str) -> str:
    return " ".join(query.casefold().split())


def _validate_gmail_query_text(query: str | None) -> str:
    cleaned_query = query.strip() if isinstance(query, str) else ""
    if not cleaned_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail backfill requires an explicit safe query.",
        )

    if _normalize_gmail_query(cleaned_query) == _normalize_gmail_query(
        BROAD_GMAIL_BACKFILL_QUERY
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail backfill query is too broad; choose a narrower query.",
        )

    return cleaned_query


class _ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"br", "div", "li", "p", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"div", "li", "p", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line).strip()


def list_messages(
    *,
    query: str,
    max_results: int,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> list[dict]:
    from app.connectors.gmail import list_messages as _list_messages

    return _list_messages(
        query=query,
        max_results=max_results,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )


def get_message(
    message_id: str,
    *,
    allow_live_provider_execution: bool = False,
    provider_execution_ack: str | None = None,
) -> dict:
    from app.connectors.gmail import get_message as _get_message

    return _get_message(
        message_id,
        allow_live_provider_execution=allow_live_provider_execution,
        provider_execution_ack=provider_execution_ack,
    )


def extract_subject(msg: dict) -> str | None:
    for header in ((msg.get("payload") or {}).get("headers") or []):
        if not isinstance(header, dict):
            continue
        name = header.get("name")
        value = header.get("value")
        if isinstance(name, str) and name.lower() == "subject":
            if isinstance(value, str) and value.strip():
                return value.strip()
            return None
    return None


def extract_gmail_headers(msg: dict) -> dict[str, str]:
    wanted = {
        "subject",
        "from",
        "to",
        "cc",
        "date",
        "message-id",
        "in-reply-to",
        "references",
    }
    headers: dict[str, str] = {}
    for header in ((msg.get("payload") or {}).get("headers") or []):
        if not isinstance(header, dict):
            continue
        name = header.get("name")
        value = header.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        normalized = name.lower()
        if normalized in wanted and value.strip() and normalized not in headers:
            headers[normalized] = value.strip()
    return headers


def _decode_gmail_body_data(data: object) -> str | None:
    if not isinstance(data, str) or not data.strip():
        return None
    padded = data + ("=" * ((4 - len(data) % 4) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        return None
    text = decoded.decode("utf-8", errors="replace").strip()
    return text or None


def _html_to_readable_text(html: str) -> str | None:
    parser = _ReadableHtmlParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return None
    text = parser.get_text()
    return text or None


def _is_attachment_part(part: dict) -> bool:
    filename = part.get("filename")
    if isinstance(filename, str) and filename.strip():
        return True
    body = part.get("body") or {}
    return isinstance(body, dict) and bool(body.get("attachmentId"))


def _iter_decoded_body_parts(part: dict, mime_type: str) -> list[str]:
    if not isinstance(part, dict) or _is_attachment_part(part):
        return []

    found: list[str] = []
    part_mime_type = part.get("mimeType")
    body = part.get("body") or {}
    if part_mime_type == mime_type and isinstance(body, dict):
        decoded = _decode_gmail_body_data(body.get("data"))
        if decoded:
            found.append(decoded)

    for child in part.get("parts", []) or []:
        found.extend(_iter_decoded_body_parts(child, mime_type))
    return found


def extract_readable_gmail_body_text(msg: dict) -> str | None:
    payload = msg.get("payload") or {}
    plain_parts = _iter_decoded_body_parts(payload, "text/plain")
    if plain_parts:
        text = "\n\n".join(part.strip() for part in plain_parts if part.strip()).strip()
        return text or None

    html_parts = _iter_decoded_body_parts(payload, "text/html")
    readable_html_parts = [
        readable for part in html_parts if (readable := _html_to_readable_text(part)) is not None
    ]
    text = "\n\n".join(readable_html_parts).strip()
    return text or None


def build_gmail_document_metadata(msg: dict, raw_ref: str) -> dict:
    headers = extract_gmail_headers(msg)
    metadata = {
        "message_id": msg["id"],
        "thread_id": msg.get("threadId"),
        "history_id": msg.get("historyId"),
        "label_ids": msg.get("labelIds", []),
        "raw_object_ref": raw_ref,
    }
    for header_name in ("subject", "from", "to", "cc", "date"):
        if header_name in headers:
            metadata[header_name] = headers[header_name]
    return metadata


def build_gmail_document_records(
    msg: dict, raw_ref: str
) -> tuple[SourceDocument | None, list[DocumentChunk], str | None]:
    readable_text = extract_readable_gmail_body_text(msg)
    if readable_text is None:
        return None, [], None

    content_hash = sha256_text(readable_text)
    source_document_id = f"gmail:{msg['id']}:{content_hash[:12]}"
    payload = msg.get("payload") or {}
    metadata = build_gmail_document_metadata(msg, raw_ref)
    subject = metadata.get("subject")

    source_document = SourceDocument(
        source_document_id=source_document_id,
        source_system="gmail",
        source_object_id=msg["id"],
        title=subject,
        source_url=None,
        mime_type=payload.get("mimeType"),
        raw_object_ref=raw_ref,
        content_hash=content_hash,
        modified_at=str(msg["internalDate"]) if msg.get("internalDate") is not None else None,
        metadata_json=metadata,
    )

    document_chunks = []
    for index, chunk in enumerate(chunk_text(readable_text)):
        chunk_metadata = {
            "message_id": msg["id"],
            "thread_id": msg.get("threadId"),
            "chunk_index": index,
        }
        if subject:
            chunk_metadata["subject"] = subject
        document_chunks.append(
            DocumentChunk(
                source_document_id=source_document_id,
                chunk_id=chunk.chunk_id,
                source_system="gmail",
                source_object_id=msg["id"],
                raw_object_ref=raw_ref,
                text=chunk.text,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                content_hash=sha256_text(chunk.text),
                metadata_json=chunk_metadata,
            )
        )

    return source_document, document_chunks, readable_text


def build_gmail_event(msg: dict) -> EventEnvelope:
    history_id = msg.get("historyId", "unknown")
    subject = extract_subject(msg)
    payload = {
        "source_object_type": "message",
        "id": msg["id"],
        "threadId": msg.get("threadId"),
        "historyId": history_id,
        "labelIds": msg.get("labelIds", []),
        "snippet": msg.get("snippet", ""),
    }

    if subject is not None:
        payload["subject"] = subject

    return EventEnvelope(
        event_type="gmail.message.ingested",
        source_system="gmail",
        source_object_id=msg["id"],
        idempotency_key=f"gmail:message:{msg['id']}:{history_id}",
        raw_object_ref=f"raw://gmail/{msg['id']}/{history_id}/message.json",
        payload=payload,
    )


def save_gmail_raw_message(
    msg: dict,
    *,
    allow_production_operation: bool = False,
    production_operation_ack: str | None = None,
) -> str:
    message_id = safe_path_part(msg["id"])
    history_id = safe_path_part(msg.get("historyId", "unknown"))
    path = raw_storage_root() / "gmail" / message_id / history_id / "message.json"
    write_json(
        path,
        msg,
        allow_production_operation=allow_production_operation,
        production_operation_ack=production_operation_ack,
    )
    return f"raw://gmail/{message_id}/{history_id}/message.json"


def iter_attachment_metadata(msg: dict) -> list[dict]:
    found: list[dict] = []

    def visit(part: dict) -> None:
        body = part.get("body", {}) or {}
        attachment_id = body.get("attachmentId")
        if attachment_id:
            found.append(
                {
                    "message_id": msg["id"],
                    "attachment_id": attachment_id,
                    "filename": part.get("filename"),
                    "mime_type": part.get("mimeType"),
                    "size": body.get("size"),
                }
            )
        for child in part.get("parts", []) or []:
            visit(child)

    visit(msg.get("payload") or {})
    return found


@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED)
async def gmail_backfill(
    max_results: int = Query(
        GMAIL_BACKFILL_DEFAULT_MAX_RESULTS,
        ge=1,
        le=GMAIL_BACKFILL_MAX_RESULTS,
    ),
    query: str | None = Query(None),
    persist: bool = Query(False),
    allow_production_operation: bool = Query(False),
    confirm_production_operation: str | None = Query(None),
    allow_live_provider_execution: bool = Query(False),
    confirm_live_provider_execution: str | None = Query(None),
    request_key: str | None = Query(None),
) -> dict:
    if query is not None:
        _validate_gmail_query_text(query)
    action_type = ACTION_BACKFILL if persist else ACTION_PREVIEW_SYNC
    safe_request_key = request_key or f"legacy-gmail-{action_type}-{uuid4().hex}"
    input_payload = {
        "max_results": max_results,
        "persist_requested": persist,
        "query_provided": query is not None,
        "uses_configured_query": query is None,
        "allow_live_provider_execution": bool(allow_live_provider_execution),
        "live_provider_ack_supplied": confirm_live_provider_execution is not None,
        "allow_production_operation": bool(allow_production_operation),
        "production_ack_supplied": confirm_production_operation is not None,
        "legacy_route": "/api/v1/gmail/backfill",
    }
    async with AsyncSessionLocal() as session:
        request = await request_source_action(
            session,
            source_type="gmail",
            action_type=action_type,
            request_key=safe_request_key,
            requested_by="legacy_gmail_backfill_route",
            input_payload=input_payload,
        )
        await session.commit()
    return {
        "provider": "gmail",
        "mode": "source_control_request",
        "redacted": True,
        "persist": persist,
        "max_results": max_results,
        "status": request["status"],
        "request_id": request["request_id"],
        "source_type": request["source_type"],
        "action_type": request["action_type"],
        "source_control_request": request,
    }
