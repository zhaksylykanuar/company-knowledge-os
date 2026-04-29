from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.agents.runner import RuleBasedAgentRunner
from app.db.base import AsyncSessionLocal
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.extraction_processor import process_document_chunks
from app.services.knowledge_ingestion import ingest_text
from app.services.knowledge_score_processor import process_knowledge_scores


async def ingest_text_and_process(
    *,
    title: str,
    text: str,
    source_type: str = "manual",
    project_key: str | None = None,
    client_key: str | None = None,
    people: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    ingestion = await ingest_text(
        title=title,
        text=text,
        source_type=source_type,
        project_key=project_key,
        client_key=client_key,
        people=people,
        tags=tags,
    )

    document_id = ingestion["document_id"]
    extraction = await process_document_chunks(
        document_id,
        runner=RuleBasedAgentRunner(),
    )
    score_result = await process_knowledge_scores(source_document_id=document_id)
    evidence_summary = await build_evidence_summary(document_id)

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
        "next_steps": {
            "search": "GET /v1/knowledge/search?q=<query>",
            "ask": "POST /v1/knowledge/ask",
            "attention": "GET /v1/knowledge/attention",
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
