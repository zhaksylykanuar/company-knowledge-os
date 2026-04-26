from uuid import uuid4

from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.score_models import KnowledgeScore
from app.db.source_models import DocumentChunk, SourceDocument
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.knowledge_score_processor import process_knowledge_scores


async def _cleanup_score_fixture(source_document_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(KnowledgeScore).where(
                KnowledgeScore.source_document_id == source_document_id
            )
        )
        await session.execute(
            delete(ExtractedTask).where(
                ExtractedTask.source_document_id == source_document_id
            )
        )
        await session.execute(
            delete(ExtractedRisk).where(
                ExtractedRisk.source_document_id == source_document_id
            )
        )
        await session.execute(
            delete(ExtractedDecision).where(
                ExtractedDecision.source_document_id == source_document_id
            )
        )
        await session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.source_document_id == source_document_id
            )
        )
        await session.execute(
            delete(SourceDocument).where(
                SourceDocument.source_document_id == source_document_id
            )
        )
        await session.commit()


async def _insert_score_fixture(
    *,
    unique: str,
    source_document_id: str,
    chunk_id: str,
) -> None:
    evidence_refs = [
        {
            "source_document_id": source_document_id,
            "chunk_id": chunk_id,
            "quote": f"QAZTWIN score evidence quote {unique}",
        }
    ]

    async with AsyncSessionLocal() as session:
        session.add(
            SourceDocument(
                source_document_id=source_document_id,
                source_system="test",
                source_object_id=f"score-object-{unique}",
                title=f"ABC Manufacturing QAZTWIN score note {unique}",
                source_url=f"test://score-source/{unique}",
                mime_type="text/plain",
                raw_object_ref=f"raw://score/{unique}",
                content_hash=f"score-doc-hash-{unique}",
                modified_at=None,
                metadata_json={},
            )
        )
        session.add(
            DocumentChunk(
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                source_system="test",
                source_object_id=f"score-object-{unique}",
                raw_object_ref=f"raw://score/{unique}",
                text=(
                    f"Client ABC Manufacturing discussed QAZTWIN onboarding {unique}. "
                    "TODO: send proposal to client next week. "
                    "Risk: client is worried about IT security and SCADA access. "
                    "Decision: start with read-only data collection."
                ),
                start_char=0,
                end_char=260,
                content_hash=f"score-chunk-hash-{unique}",
                metadata_json={},
            )
        )
        session.add(
            ExtractedTask(
                title=f"TODO: send proposal to ABC Manufacturing {unique}",
                status="open",
                item_type="task",
                owner=None,
                due_date="2026-04-27",
                confidence=0.9,
                source_event_id=chunk_id,
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                evidence_refs=evidence_refs,
            )
        )
        session.add(
            ExtractedRisk(
                title=(
                    "Risk: client is worried about IT security "
                    f"and SCADA access {unique}"
                ),
                severity="high",
                confidence=0.8,
                source_event_id=chunk_id,
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                evidence_refs=evidence_refs,
            )
        )
        session.add(
            ExtractedDecision(
                title=f"Decision: start with read-only data collection {unique}",
                decision=(
                    "Start with read-only data collection before write actions "
                    f"{unique}"
                ),
                owner=None,
                confidence=0.95,
                source_event_id=chunk_id,
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                evidence_refs=evidence_refs,
            )
        )
        await session.commit()


async def _load_scores(source_document_id: str) -> list[KnowledgeScore]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KnowledgeScore).where(
                KnowledgeScore.source_document_id == source_document_id
            )
        )
        return list(result.scalars().all())


async def test_process_knowledge_scores_creates_explainable_scores() -> None:
    unique = f"score-{uuid4().hex}"
    source_document_id = f"test-doc-{unique}"
    chunk_id = f"test-chunk-{unique}"

    await _cleanup_score_fixture(source_document_id)

    try:
        await _insert_score_fixture(
            unique=unique,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )

        result = await process_knowledge_scores(
            source_document_id=source_document_id
        )

        scores = await _load_scores(source_document_id)
        scores_by_type = {score.entity_type: score for score in scores}

        assert result["source_document_id"] == source_document_id
        assert result["scores_created"] == 3
        assert result["scores_updated"] == 0
        assert result["tasks_scored"] == 1
        assert result["risks_scored"] == 1
        assert result["decisions_scored"] == 1

        assert set(scores_by_type) == {"task", "risk", "decision"}

        for score in scores:
            assert score.source_document_id == source_document_id
            assert score.chunk_id == chunk_id
            assert score.attention_score > 0
            assert score.reasons
            assert score.evidence_refs
            assert score.evidence_refs[0]["chunk_id"] == chunk_id

        risk_reason_codes = {
            reason["code"] for reason in scores_by_type["risk"].reasons
        }
        assert "high_severity_risk" in risk_reason_codes
        assert "security_or_access_context" in risk_reason_codes

    finally:
        await _cleanup_score_fixture(source_document_id)


async def test_process_knowledge_scores_is_idempotent() -> None:
    unique = f"score-{uuid4().hex}"
    source_document_id = f"test-doc-{unique}"
    chunk_id = f"test-chunk-{unique}"

    await _cleanup_score_fixture(source_document_id)

    try:
        await _insert_score_fixture(
            unique=unique,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )

        first_result = await process_knowledge_scores(
            source_document_id=source_document_id
        )
        second_result = await process_knowledge_scores(
            source_document_id=source_document_id
        )

        scores = await _load_scores(source_document_id)

        assert first_result["scores_created"] == 3
        assert first_result["scores_updated"] == 0

        assert second_result["scores_created"] == 0
        assert second_result["scores_updated"] == 3

        assert len(scores) == 3

    finally:
        await _cleanup_score_fixture(source_document_id)
