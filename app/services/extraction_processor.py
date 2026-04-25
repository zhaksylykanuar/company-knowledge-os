from sqlalchemy import select

from app.agents.evidence_validator import validate_evidence
from app.agents.runner import get_agent_runner
from app.db.base import AsyncSessionLocal
from app.db.source_models import DocumentChunk
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask


async def process_document_chunks(source_document_id: str) -> dict:
    """
    Process all chunks for one source document and persist extracted facts.

    This is the first real extraction processor for FounderOS.
    It works on already-ingested document_chunks from Drive/manual/Gmail.
    """

    runner = get_agent_runner()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DocumentChunk).where(DocumentChunk.source_document_id == source_document_id)
        )
        chunks = list(result.scalars().all())

        total_tasks = 0
        total_decisions = 0
        total_risks = 0

        for chunk in chunks:
            extraction = await runner.extract(
                source_document_id=chunk.source_document_id,
                chunk_id=chunk.chunk_id,
                raw_object_ref=chunk.raw_object_ref,
                text=chunk.text,
            )

            validate_evidence(extraction)

            for task in extraction.tasks:
                session.add(
                    ExtractedTask(
                        title=task.title,
                        item_type="task",
                        owner=task.owner,
                        due_date=task.due_date,
                        confidence=task.confidence,
                        source_event_id=chunk.chunk_id,
                        evidence_refs=[ref.model_dump() for ref in task.evidence_refs],
                    )
                )
                total_tasks += 1

            for decision in extraction.decisions:
                session.add(
                    ExtractedDecision(
                        title=decision.title,
                        decision=decision.decision,
                        owner=decision.owner,
                        confidence=decision.confidence,
                        source_event_id=chunk.chunk_id,
                        evidence_refs=[ref.model_dump() for ref in decision.evidence_refs],
                    )
                )
                total_decisions += 1

            for risk in extraction.risks:
                session.add(
                    ExtractedRisk(
                        title=risk.title,
                        severity=risk.severity,
                        confidence=risk.confidence,
                        source_event_id=chunk.chunk_id,
                        evidence_refs=[ref.model_dump() for ref in risk.evidence_refs],
                    )
                )
                total_risks += 1

        await session.commit()

    return {
        "source_document_id": source_document_id,
        "chunks_processed": len(chunks),
        "tasks_created": total_tasks,
        "decisions_created": total_decisions,
        "risks_created": total_risks,
    }