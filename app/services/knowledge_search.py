from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select

from app.db.base import AsyncSessionLocal
from app.db.source_models import DocumentChunk, SourceDocument
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask

DEFAULT_LIMIT = 20
MAX_TERMS = 8

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "about",
        "by",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "who",
        "was",
        "were",
        "with",
        "без",
        "были",
        "было",
        "в",
        "для",
        "и",
        "какие",
        "какой",
        "кто",
        "на",
        "о",
        "об",
        "по",
        "про",
        "с",
        "что",
    }
)

_WORD_RE = re.compile(r"[\w]+", re.UNICODE)


def _search_terms(query: str) -> list[str]:
    terms: list[str] = []

    for term in _WORD_RE.findall(query.lower()):
        if len(term) < 2:
            continue
        if term in _STOPWORDS:
            continue
        terms.append(term)

    if not terms and query.strip():
        terms.append(query.strip().lower())

    return list(dict.fromkeys(terms))[:MAX_TERMS]


def _preview(text: str, max_length: int = 240) -> str:
    cleaned = " ".join(text.split())

    if len(cleaned) <= max_length:
        return cleaned

    return f"{cleaned[: max_length - 1].rstrip()}…"


def _match_clause(columns: list[Any], terms: list[str]) -> Any:
    return or_(*(column.ilike(f"%{term}%") for term in terms for column in columns))


def _document_title(document: SourceDocument | None) -> str | None:
    if document is None:
        return None

    return document.title


def _first_evidence_value(evidence_refs: list[Any] | None, key: str) -> str | None:
    if not evidence_refs:
        return None

    first_ref = evidence_refs[0]
    if not isinstance(first_ref, dict):
        return None

    value = first_ref.get(key)
    if isinstance(value, str) and value:
        return value

    return None


def _chunk_evidence_refs(
    chunk: DocumentChunk,
    document: SourceDocument | None,
) -> list[dict[str, Any]]:
    return [
        {
            "source_document_id": chunk.source_document_id,
            "chunk_id": chunk.chunk_id,
            "raw_object_ref": chunk.raw_object_ref,
            "source_url": document.source_url if document else None,
            "quote": _preview(chunk.text, max_length=800),
        }
    ]


def _chunk_result(
    chunk: DocumentChunk,
    document: SourceDocument | None,
) -> dict[str, Any]:
    title = _document_title(document) or "Document chunk"

    return {
        "result_type": "chunk",
        "id": chunk.id,
        "source_document_id": chunk.source_document_id,
        "chunk_id": chunk.chunk_id,
        "source_title": _document_title(document),
        "title": title,
        "preview": _preview(chunk.text),
        "confidence": None,
        "metadata": {
            "source_system": chunk.source_system,
            "source_object_id": chunk.source_object_id,
        },
        "evidence_refs": _chunk_evidence_refs(chunk=chunk, document=document),
    }


def _extracted_result(
    *,
    result_type: str,
    item: Any,
    document: SourceDocument | None,
    preview_text: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    evidence_refs = item.evidence_refs or []

    source_document_id = item.source_document_id or _first_evidence_value(
        evidence_refs,
        "source_document_id",
    )
    chunk_id = item.chunk_id or _first_evidence_value(evidence_refs, "chunk_id")

    return {
        "result_type": result_type,
        "id": item.id,
        "source_document_id": source_document_id,
        "chunk_id": chunk_id,
        "source_title": _document_title(document),
        "title": item.title,
        "preview": _preview(preview_text),
        "confidence": item.confidence,
        "metadata": metadata,
        "evidence_refs": evidence_refs,
    }


async def search_knowledge(query: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    cleaned_query = query.strip()
    terms = _search_terms(cleaned_query)

    if not cleaned_query or not terms:
        return {
            "query": cleaned_query,
            "terms": [],
            "counts": {
                "chunks": 0,
                "tasks": 0,
                "risks": 0,
                "decisions": 0,
                "total": 0,
            },
            "results": [],
        }

    results: list[dict[str, Any]] = []

    async with AsyncSessionLocal() as session:
        chunk_rows = await session.execute(
            select(DocumentChunk, SourceDocument)
            .outerjoin(
                SourceDocument,
                DocumentChunk.source_document_id == SourceDocument.source_document_id,
            )
            .where(
                _match_clause(
                    [
                        DocumentChunk.text,
                        DocumentChunk.chunk_id,
                        DocumentChunk.source_document_id,
                        SourceDocument.title,
                    ],
                    terms,
                )
            )
            .order_by(DocumentChunk.id.desc())
            .limit(limit)
        )

        task_rows = await session.execute(
            select(ExtractedTask, SourceDocument)
            .outerjoin(
                SourceDocument,
                ExtractedTask.source_document_id == SourceDocument.source_document_id,
            )
            .where(
                _match_clause(
                    [
                        ExtractedTask.title,
                        ExtractedTask.owner,
                        ExtractedTask.due_date,
                        ExtractedTask.source_event_id,
                        ExtractedTask.source_document_id,
                        ExtractedTask.chunk_id,
                        SourceDocument.title,
                    ],
                    terms,
                )
            )
            .order_by(ExtractedTask.id.desc())
            .limit(limit)
        )

        risk_rows = await session.execute(
            select(ExtractedRisk, SourceDocument)
            .outerjoin(
                SourceDocument,
                ExtractedRisk.source_document_id == SourceDocument.source_document_id,
            )
            .where(
                _match_clause(
                    [
                        ExtractedRisk.title,
                        ExtractedRisk.severity,
                        ExtractedRisk.source_event_id,
                        ExtractedRisk.source_document_id,
                        ExtractedRisk.chunk_id,
                        SourceDocument.title,
                    ],
                    terms,
                )
            )
            .order_by(ExtractedRisk.id.desc())
            .limit(limit)
        )

        decision_rows = await session.execute(
            select(ExtractedDecision, SourceDocument)
            .outerjoin(
                SourceDocument,
                ExtractedDecision.source_document_id == SourceDocument.source_document_id,
            )
            .where(
                _match_clause(
                    [
                        ExtractedDecision.title,
                        ExtractedDecision.decision,
                        ExtractedDecision.owner,
                        ExtractedDecision.source_event_id,
                        ExtractedDecision.source_document_id,
                        ExtractedDecision.chunk_id,
                        SourceDocument.title,
                    ],
                    terms,
                )
            )
            .order_by(ExtractedDecision.id.desc())
            .limit(limit)
        )

        chunks = [_chunk_result(chunk, document) for chunk, document in chunk_rows.all()]

        tasks = [
            _extracted_result(
                result_type="task",
                item=task,
                document=document,
                preview_text=task.title,
                metadata={
                    "status": task.status,
                    "item_type": task.item_type,
                    "owner": task.owner,
                    "due_date": task.due_date,
                },
            )
            for task, document in task_rows.all()
        ]

        risks = [
            _extracted_result(
                result_type="risk",
                item=risk,
                document=document,
                preview_text=risk.title,
                metadata={
                    "severity": risk.severity,
                },
            )
            for risk, document in risk_rows.all()
        ]

        decisions = [
            _extracted_result(
                result_type="decision",
                item=decision,
                document=document,
                preview_text=decision.decision,
                metadata={
                    "decision": decision.decision,
                    "owner": decision.owner,
                },
            )
            for decision, document in decision_rows.all()
        ]

    results.extend(chunks)
    results.extend(tasks)
    results.extend(risks)
    results.extend(decisions)

    return {
        "query": cleaned_query,
        "terms": terms,
        "counts": {
            "chunks": len(chunks),
            "tasks": len(tasks),
            "risks": len(risks),
            "decisions": len(decisions),
            "total": len(results),
        },
        "results": results,
    }
