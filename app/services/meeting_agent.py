"""Meeting agent: lift transcripts/notes into the knowledge graph.

Reuses the deterministic, evidence-strict meeting extractor
(``meeting_artifacts``): documents whose chunks carry marker lines
(Decision:/Action:/Risk:/…) become ``meeting`` nodes with decisions
(``decided_in``), action items (tasks with owners and deadlines,
``next_step_of``) and risks (``affects`` the recognized project).
Idempotent by document id; everything carries evidence refs.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.source_models import DocumentChunk, SourceDocument
from app.services.entity_resolution import (
    ENTITY_TYPE_PROJECT,
    resolve_entities_in_text,
)
from app.services.knowledge_graph import (
    ENTITY_DECISION,
    ENTITY_MEETING,
    ENTITY_RISK,
    ENTITY_TASK,
    REL_AFFECTS,
    REL_DECIDED_IN,
    REL_MENTIONS,
    REL_NEXT_STEP_OF,
    upsert_entity,
    upsert_link,
)
from app.services.meeting_artifacts import (
    MeetingTranscriptInput,
    process_meeting_transcript,
)

AGENT_NAME = "meeting_agent"
_MARKER_HINTS = ("decision:", "action:", "todo:", "risk:", "question:")
_MAX_TRANSCRIPT_CHARS = 20_000


def _looks_like_meeting(text: str) -> bool:
    lowered = text.casefold()
    return sum(1 for marker in _MARKER_HINTS if marker in lowered) >= 1


async def _document_text(
    session: AsyncSession, source_document_id: str
) -> tuple[str, DocumentChunk | None]:
    chunks = list(
        (
            await session.execute(
                select(DocumentChunk)
                .where(DocumentChunk.source_document_id == source_document_id)
                .order_by(DocumentChunk.start_char)
            )
        ).scalars()
    )
    if not chunks:
        return "", None
    text = "\n".join(chunk.text for chunk in chunks)[:_MAX_TRANSCRIPT_CHARS]
    return text, chunks[0]


async def scan_meetings(session: AsyncSession) -> dict[str, int]:
    counts = {
        "meetings": 0,
        "decisions": 0,
        "action_items": 0,
        "risks": 0,
        "links_created": 0,
    }

    documents = (
        await session.execute(
            select(SourceDocument).order_by(SourceDocument.id)
        )
    ).scalars()

    for document in documents:
        text, first_chunk = await _document_text(
            session, document.source_document_id
        )
        if first_chunk is None or not _looks_like_meeting(text):
            continue

        result = process_meeting_transcript(
            MeetingTranscriptInput(
                source_document_id=document.source_document_id,
                chunk_id=first_chunk.chunk_id,
                raw_object_ref=document.raw_object_ref,
                transcript_text=text,
                title=document.title,
            )
        )
        if not (result.decisions or result.action_items or result.risks):
            continue

        # Short stable id: full document ids make link_ids exceed 120 chars.
        doc_key = hashlib.sha1(
            document.source_document_id.encode("utf-8")
        ).hexdigest()[:16]
        meeting_id = f"meeting:{doc_key}"
        created = await upsert_entity(
            session,
            entity_id=meeting_id,
            entity_type=ENTITY_MEETING,
            canonical_name=(document.title or document.source_document_id)[:255],
            attrs={
                "source_document_id": document.source_document_id,
                "summary": result.summary[:500],
                "open_questions": [q.question for q in result.open_questions][:10],
                "rejected_claims": list(result.unsupported_claims_rejected)[:10],
            },
        )
        if created:
            counts["meetings"] += 1

        projects = []
        try:
            projects = await resolve_entities_in_text(
                session,
                f"{document.title or ''} {text[:500]}",
                entity_type=ENTITY_TYPE_PROJECT,
            )
        except Exception:
            projects = []
        for project in projects[:1]:
            if await upsert_link(
                session,
                from_entity_id=meeting_id,
                relation=REL_MENTIONS,
                to_entity_id=project.entity_id,
                evidence_refs=[
                    {
                        "kind": "alias_match",
                        "alias": project.matched_alias,
                        "source_document_id": document.source_document_id,
                    }
                ],
                confidence=0.8,
            ):
                counts["links_created"] += 1

        def _evidence(item: Any) -> list[dict[str, Any]]:
            ref = getattr(item, "evidence_refs", None) or []
            return [refitem.model_dump() for refitem in ref][:3]

        for index, decision in enumerate(result.decisions):
            entity_id = f"decision:{meeting_id.split(':', 1)[1]}:{index}"
            if await upsert_entity(
                session,
                entity_id=entity_id,
                entity_type=ENTITY_DECISION,
                canonical_name=decision.decision[:255],
                attrs={"source_document_id": document.source_document_id},
            ):
                counts["decisions"] += 1
            if await upsert_link(
                session,
                from_entity_id=entity_id,
                relation=REL_DECIDED_IN,
                to_entity_id=meeting_id,
                evidence_refs=_evidence(decision),
                confidence=0.85,
            ):
                counts["links_created"] += 1

        for index, action in enumerate(result.action_items):
            entity_id = f"task:{meeting_id.split(':', 1)[1]}:{index}"
            if await upsert_entity(
                session,
                entity_id=entity_id,
                entity_type=ENTITY_TASK,
                canonical_name=action.title[:255],
                attrs={
                    "owner": action.owner,
                    "due_date": action.due_date,
                    "status": "open",
                    "source_document_id": document.source_document_id,
                },
            ):
                counts["action_items"] += 1
            if await upsert_link(
                session,
                from_entity_id=entity_id,
                relation=REL_NEXT_STEP_OF,
                to_entity_id=meeting_id,
                evidence_refs=_evidence(action),
                confidence=0.85,
            ):
                counts["links_created"] += 1

        for index, risk in enumerate(result.risks):
            entity_id = f"risk:{meeting_id.split(':', 1)[1]}:{index}"
            if await upsert_entity(
                session,
                entity_id=entity_id,
                entity_type=ENTITY_RISK,
                canonical_name=risk.title[:255],
                attrs={
                    "severity": risk.severity,
                    "source_document_id": document.source_document_id,
                },
            ):
                counts["risks"] += 1
            for project in projects[:1]:
                if await upsert_link(
                    session,
                    from_entity_id=entity_id,
                    relation=REL_AFFECTS,
                    to_entity_id=project.entity_id,
                    evidence_refs=_evidence(risk),
                    confidence=0.7,
                ):
                    counts["links_created"] += 1

    return counts
