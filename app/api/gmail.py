from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.gmail_models import GmailAttachment, GmailMessage, GmailThread
from app.db.models import AuditLog, IngestedEvent
from app.events.schemas import EventEnvelope
from app.services.raw_storage import raw_storage_root, safe_path_part, write_json

router = APIRouter(prefix="/v1/gmail", tags=["gmail"])


def list_messages(query: str = "in:inbox OR in:sent", max_results: int = 20) -> list[dict]:
    from app.connectors.gmail import list_messages as _list_messages

    return _list_messages(query=query, max_results=max_results)


def get_message(message_id: str) -> dict:
    from app.connectors.gmail import get_message as _get_message

    return _get_message(message_id)


def build_gmail_event(msg: dict) -> EventEnvelope:
    history_id = msg.get("historyId", "unknown")
    return EventEnvelope(
        event_type="gmail.message.discovered",
        source_system="gmail",
        source_object_id=msg["id"],
        idempotency_key=f"gmail:message:{msg['id']}:{history_id}",
        raw_object_ref=f"raw://gmail/{msg['id']}/{history_id}/message.json",
        payload={
            "id": msg["id"],
            "threadId": msg.get("threadId"),
            "historyId": history_id,
            "labelIds": msg.get("labelIds", []),
            "snippet": msg.get("snippet", ""),
        },
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
                    event_type="gmail.message.discovered",
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
