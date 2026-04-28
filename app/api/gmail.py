import base64
import binascii
import re
from html.parser import HTMLParser

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.gmail_models import GmailAttachment, GmailMessage, GmailThread
from app.db.models import AuditLog, IngestedEvent
from app.db.source_models import DocumentChunk, SourceDocument
from app.events.schemas import EventEnvelope
from app.services.chunking import chunk_text
from app.services.raw_storage import raw_storage_root, safe_path_part, sha256_text, write_json

router = APIRouter(prefix="/v1/gmail", tags=["gmail"])


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


def list_messages(query: str = "in:inbox OR in:sent", max_results: int = 20) -> list[dict]:
    from app.connectors.gmail import list_messages as _list_messages

    return _list_messages(query=query, max_results=max_results)


def get_message(message_id: str) -> dict:
    from app.connectors.gmail import get_message as _get_message

    return _get_message(message_id)


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
    wanted = {"subject", "from", "to", "cc", "date"}
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


def save_gmail_raw_message(msg: dict) -> str:
    message_id = safe_path_part(msg["id"])
    history_id = safe_path_part(msg.get("historyId", "unknown"))
    path = raw_storage_root() / "gmail" / message_id / history_id / "message.json"
    write_json(path, msg)
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
    max_results: int = Query(10, ge=1, le=100),
    query: str = Query("in:inbox OR in:sent"),
    persist: bool = Query(True),
) -> dict:
    refs = list_messages(query=query, max_results=max_results)
    events = []
    saved = 0
    duplicates = 0

    for ref in refs:
        msg = get_message(ref["id"])
        event = build_gmail_event(msg)

        if not persist:
            events.append(event.model_dump(mode="json"))
            continue

        async with AsyncSessionLocal() as session:
            existing = await session.scalar(
                select(IngestedEvent).where(IngestedEvent.idempotency_key == event.idempotency_key)
            )
            if existing:
                duplicates += 1
                events.append(
                    {
                        "accepted": True,
                        "duplicate": True,
                        "event_id": existing.event_id,
                        "source_object_id": event.source_object_id,
                    }
                )
                continue

            raw_ref = save_gmail_raw_message(msg)
            event.raw_object_ref = raw_ref
            event.payload = {**event.payload, "raw_object_ref": raw_ref}
            source_document, document_chunks, _readable_text = build_gmail_document_records(
                msg, raw_ref
            )

            session.add(
                IngestedEvent(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    source_system=event.source_system,
                    source_object_id=event.source_object_id,
                    idempotency_key=event.idempotency_key,
                    correlation_id=event.correlation_id,
                    trace_id=event.trace_id,
                    raw_object_ref=event.raw_object_ref,
                    payload=event.payload,
                )
            )
            if msg.get("threadId"):
                existing_thread = await session.scalar(
                    select(GmailThread).where(GmailThread.thread_id == msg["threadId"])
                )
                if not existing_thread:
                    session.add(
                        GmailThread(
                            thread_id=msg["threadId"],
                            history_id=msg.get("historyId"),
                            raw_object_ref=raw_ref,
                            metadata_json={"message_id": msg["id"]},
                        )
                    )

            existing_message = await session.scalar(
                select(GmailMessage).where(GmailMessage.message_id == msg["id"])
            )
            if not existing_message:
                session.add(
                    GmailMessage(
                        message_id=msg["id"],
                        thread_id=msg.get("threadId"),
                        history_id=msg.get("historyId"),
                        snippet=msg.get("snippet"),
                        label_ids=msg.get("labelIds", []),
                        raw_object_ref=raw_ref,
                        payload=event.payload,
                    )
                )

            if source_document is not None:
                existing_doc = await session.scalar(
                    select(SourceDocument).where(
                        SourceDocument.source_document_id == source_document.source_document_id
                    )
                )
                if not existing_doc:
                    session.add(source_document)
                    for chunk in document_chunks:
                        session.add(chunk)

            for attachment in iter_attachment_metadata(msg):
                existing_attachment = await session.scalar(
                    select(GmailAttachment).where(
                        GmailAttachment.message_id == attachment["message_id"],
                        GmailAttachment.attachment_id == attachment["attachment_id"],
                    )
                )
                if existing_attachment:
                    continue
                session.add(
                    GmailAttachment(
                        message_id=attachment["message_id"],
                        attachment_id=attachment["attachment_id"],
                        filename=attachment.get("filename"),
                        mime_type=attachment.get("mime_type"),
                        size=attachment.get("size"),
                        metadata_json=attachment,
                    )
                )
                session.add(
                    AuditLog(
                        event_type="gmail.attachment.detected",
                        actor="system",
                        correlation_id=event.correlation_id,
                        trace_id=event.trace_id,
                        payload=attachment,
                    )
                )
            session.add(
                AuditLog(
                    event_type=event.event_type,
                    actor="system",
                    correlation_id=event.correlation_id,
                    trace_id=event.trace_id,
                    after_ref=event.event_id,
                    payload={"idempotency_key": event.idempotency_key, "message_id": msg["id"]},
                )
            )
            await session.commit()

            saved += 1
            events.append(
                {
                    "accepted": True,
                    "duplicate": False,
                    "event_id": event.event_id,
                    "source_object_id": event.source_object_id,
                    "thread_id": msg.get("threadId"),
                }
            )

    return {"discovered": len(refs), "saved": saved, "duplicates": duplicates, "events": events}
