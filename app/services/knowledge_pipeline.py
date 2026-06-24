from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.agents.runner import RuleBasedAgentRunner
from app.db.base import AsyncSessionLocal
from app.db.score_models import KnowledgeScore
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.extraction_processor import process_document_chunks
from app.services.knowledge_ingestion import ingest_text
from app.services.knowledge_score_processor import process_knowledge_scores

EXTRACTED_ITEMS_PREVIEW_LIMIT = 10
EVIDENCE_SNIPPET_LENGTH = 240


async def ingest_text_and_process(
    *,
    title: str,
    text: str,
    source_type: str = "manual",
    project_key: str | None = None,
    client_key: str | None = None,
    people: list[str] | None = None,
    tags: list[str] | None = None,
    allow_production_operation: bool = False,
    production_operation_ack: str | None = None,
) -> dict[str, Any]:
    ingestion = await ingest_text(
        title=title,
        text=text,
        source_type=source_type,
        project_key=project_key,
        client_key=client_key,
        people=people,
        tags=tags,
        allow_production_operation=allow_production_operation,
        production_operation_ack=production_operation_ack,
    )

    document_id = ingestion["document_id"]
    extraction = await process_document_chunks(
        document_id,
        runner=RuleBasedAgentRunner(),
    )
    score_result = await process_knowledge_scores(source_document_id=document_id)
    evidence_summary = await build_evidence_summary(document_id)
    extracted_items_preview = await build_extracted_items_preview(document_id)

    return {
        "processed": True,
        "document_id": document_id,
        "raw_ref": ingestion.get("raw_ref"),
        "chunks_created": ingestion.get("chunks_created", 0),
        "extraction_counts": {
            "tasks": extraction["tasks_created"],
            "risks": extraction["risks_created"],
            "decisions": extraction["decisions_created"],
            "total": (
                extraction["tasks_created"]
                + extraction["risks_created"]
                + extraction["decisions_created"]
            ),
        },
        "score_counts": {
            "created": score_result["scores_created"],
            "updated": score_result["scores_updated"],
            "tasks": score_result["tasks_scored"],
            "risks": score_result["risks_scored"],
            "decisions": score_result["decisions_scored"],
            "total": (
                score_result["tasks_scored"]
                + score_result["risks_scored"]
                + score_result["decisions_scored"]
            ),
        },
        "evidence_summary": evidence_summary,
        "extracted_items_preview": extracted_items_preview,
        "next_steps": {
            "search": "GET /api/v1/knowledge/search?q=<query>",
            "ask": "POST /api/v1/knowledge/ask",
            "attention": "GET /api/v1/knowledge/attention",
            "export": (
                "uv run python scripts/export_obsidian_vault.py "
                "--refresh-scores --source-document-id "
                f"{document_id}"
            ),
        },
    }


async def build_evidence_summary(source_document_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        tasks = list(
            (
                await session.execute(
                    select(ExtractedTask).where(
                        ExtractedTask.source_document_id == source_document_id
                    )
                )
            )
            .scalars()
            .all()
        )
        risks = list(
            (
                await session.execute(
                    select(ExtractedRisk).where(
                        ExtractedRisk.source_document_id == source_document_id
                    )
                )
            )
            .scalars()
            .all()
        )
        decisions = list(
            (
                await session.execute(
                    select(ExtractedDecision).where(
                        ExtractedDecision.source_document_id == source_document_id
                    )
                )
            )
            .scalars()
            .all()
        )

    items = [*tasks, *risks, *decisions]
    evidence_refs = [
        evidence_ref
        for item in items
        for evidence_ref in (item.evidence_refs or [])
        if isinstance(evidence_ref, dict)
    ]
    source_chunk_ids = sorted(
        {
            str(evidence_ref["chunk_id"])
            for evidence_ref in evidence_refs
            if evidence_ref.get("chunk_id")
        }
    )

    return {
        "extracted_entity_count": len(items),
        "all_extracted_entities_have_evidence_refs": all(
            bool(item.evidence_refs) for item in items
        ),
        "source_chunk_ids": source_chunk_ids,
        "sample_evidence_refs": evidence_refs[:3],
    }


async def build_extracted_items_preview(
    source_document_id: str,
    *,
    limit: int = EXTRACTED_ITEMS_PREVIEW_LIMIT,
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        tasks = list(
            (
                await session.execute(
                    select(ExtractedTask)
                    .where(ExtractedTask.source_document_id == source_document_id)
                    .order_by(ExtractedTask.id)
                )
            )
            .scalars()
            .all()
        )
        risks = list(
            (
                await session.execute(
                    select(ExtractedRisk)
                    .where(ExtractedRisk.source_document_id == source_document_id)
                    .order_by(ExtractedRisk.id)
                )
            )
            .scalars()
            .all()
        )
        decisions = list(
            (
                await session.execute(
                    select(ExtractedDecision)
                    .where(ExtractedDecision.source_document_id == source_document_id)
                    .order_by(ExtractedDecision.id)
                )
            )
            .scalars()
            .all()
        )
        scores = list(
            (
                await session.execute(
                    select(KnowledgeScore).where(
                        KnowledgeScore.source_document_id == source_document_id
                    )
                )
            )
            .scalars()
            .all()
        )

    scores_by_entity = {
        (score.entity_type, score.entity_id): score
        for score in scores
    }

    preview_items = []
    for kind, item in (
        *[("task", task) for task in tasks],
        *[("risk", risk) for risk in risks],
        *[("decision", decision) for decision in decisions],
    ):
        evidence_refs = _safe_evidence_refs(item.evidence_refs)
        if not evidence_refs:
            continue

        preview_items.append(
            _preview_item(
                kind=kind,
                item=item,
                evidence_refs=evidence_refs,
                score=scores_by_entity.get((kind, str(item.id))),
            )
        )

        if len(preview_items) >= limit:
            break

    return preview_items


def _preview_item(
    *,
    kind: str,
    item: Any,
    evidence_refs: list[dict[str, Any]],
    score: KnowledgeScore | None,
) -> dict[str, Any]:
    first_ref = evidence_refs[0]
    preview = {
        "kind": kind,
        "id": item.id,
        "title": item.title,
        "source_document_id": item.source_document_id or first_ref.get("source_document_id"),
        "chunk_id": item.chunk_id or first_ref.get("chunk_id"),
        "evidence_refs": evidence_refs,
        "evidence_snippet": _evidence_snippet(evidence_refs),
        "score": _score_preview(score),
    }

    if kind == "task":
        preview["metadata"] = {
            "status": item.status,
            "owner": item.owner,
            "due_date": item.due_date,
            "confidence": item.confidence,
        }
    if kind == "risk":
        preview["metadata"] = {
            "severity": item.severity,
            "confidence": item.confidence,
        }
    if kind == "decision":
        preview["metadata"] = {
            "decision": item.decision,
            "owner": item.owner,
            "confidence": item.confidence,
        }

    return preview


def _safe_evidence_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]


def _evidence_snippet(evidence_refs: list[dict[str, Any]]) -> str | None:
    for evidence_ref in evidence_refs:
        quote = evidence_ref.get("quote")
        if isinstance(quote, str) and quote.strip():
            return _shorten_text(quote)

    return None


def _shorten_text(value: str, *, max_length: int = EVIDENCE_SNIPPET_LENGTH) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_length:
        return cleaned

    return f"{cleaned[: max_length - 3].rstrip()}..."


def _score_preview(score: KnowledgeScore | None) -> dict[str, Any] | None:
    if score is None:
        return None

    return {
        "importance_score": score.importance_score,
        "urgency_score": score.urgency_score,
        "risk_score": score.risk_score,
        "confidence_score": score.confidence_score,
        "attention_score": score.attention_score,
        "reasons": score.reasons or [],
    }
