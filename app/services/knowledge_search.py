from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select

from app.db.base import AsyncSessionLocal
from app.db.source_models import DocumentChunk, SourceDocument
from app.db.score_models import KnowledgeScore
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



def _score_payload(score: KnowledgeScore | None) -> dict[str, Any] | None:
    if score is None:
        return None

    return {
        "entity_type": score.entity_type,
        "entity_id": score.entity_id,
        "importance_score": score.importance_score,
        "urgency_score": score.urgency_score,
        "risk_score": score.risk_score,
        "confidence_score": score.confidence_score,
        "attention_score": score.attention_score,
        "reasons": score.reasons or [],
        "evidence_refs": score.evidence_refs or [],
    }

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
        "score": None,
    }


def _extracted_result(
    *,
    result_type: str,
    item: Any,
    document: SourceDocument | None,
    preview_text: str,
    metadata: dict[str, Any],
    score: KnowledgeScore | None = None,
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
        "score": _score_payload(score),
    }



async def _score_maps(
    session: Any,
    *,
    task_ids: list[str],
    risk_ids: list[str],
    decision_ids: list[str],
) -> dict[str, dict[str, KnowledgeScore]]:
    score_maps: dict[str, dict[str, KnowledgeScore]] = {
        "task": {},
        "risk": {},
        "decision": {},
    }
    filters = []

    if task_ids:
        filters.append(
            (KnowledgeScore.entity_type == "task")
            & KnowledgeScore.entity_id.in_(task_ids)
        )

    if risk_ids:
        filters.append(
            (KnowledgeScore.entity_type == "risk")
            & KnowledgeScore.entity_id.in_(risk_ids)
        )

    if decision_ids:
        filters.append(
            (KnowledgeScore.entity_type == "decision")
            & KnowledgeScore.entity_id.in_(decision_ids)
        )

    if not filters:
        return score_maps

    rows = await session.execute(select(KnowledgeScore).where(or_(*filters)))

    for score in rows.scalars().all():
        if score.entity_type in score_maps:
            score_maps[score.entity_type][score.entity_id] = score

    return score_maps

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

        chunk_row_items = chunk_rows.all()
        task_row_items = task_rows.all()
        risk_row_items = risk_rows.all()
        decision_row_items = decision_rows.all()

        score_maps = await _score_maps(
            session,
            task_ids=[str(task.id) for task, _document in task_row_items],
            risk_ids=[str(risk.id) for risk, _document in risk_row_items],
            decision_ids=[
                str(decision.id) for decision, _document in decision_row_items
            ],
        )

        chunks = [_chunk_result(chunk, document) for chunk, document in chunk_row_items]

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
                score=score_maps["task"].get(str(task.id)),
            )
            for task, document in task_row_items
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
                score=score_maps["risk"].get(str(risk.id)),
            )
            for risk, document in risk_row_items
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
                score=score_maps["decision"].get(str(decision.id)),
            )
            for decision, document in decision_row_items
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
