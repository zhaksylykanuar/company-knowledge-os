from uuid import uuid4

from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.score_models import KnowledgeScore
from app.db.source_models import DocumentChunk, SourceDocument
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.knowledge_attention import get_attention_dashboard
from app.services.knowledge_score_processor import process_knowledge_scores


async def _cleanup_attention_fixture(source_document_id: str) -> None:
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


async def _insert_attention_fixture(
    *,
    unique: str,
    source_document_id: str,
    chunk_id: str,
) -> None:
    evidence_refs = [
        {
            "source_document_id": source_document_id,
            "chunk_id": chunk_id,
            "quote": f"QAZTWIN attention evidence quote {unique}",
        }
    ]

    async with AsyncSessionLocal() as session:
        session.add(
            SourceDocument(
                source_document_id=source_document_id,
                source_system="test",
                source_object_id=f"attention-object-{unique}",
                title=f"ABC Manufacturing QAZTWIN attention note {unique}",
                source_url=f"test://attention-source/{unique}",
                mime_type="text/plain",
                raw_object_ref=f"raw://attention/{unique}",
                content_hash=f"attention-doc-hash-{unique}",
                modified_at=None,
                metadata_json={},
            )
        )
        session.add(
            DocumentChunk(
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                source_system="test",
                source_object_id=f"attention-object-{unique}",
                raw_object_ref=f"raw://attention/{unique}",
                text=(
                    f"Client ABC Manufacturing discussed QAZTWIN onboarding {unique}. "
                    "TODO: send proposal to client next week. "
                    "Risk: client is worried about IT security and SCADA access. "
                    "Decision: start with read-only data collection."
                ),
                start_char=0,
                end_char=260,
                content_hash=f"attention-chunk-hash-{unique}",
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


async def test_get_attention_dashboard_reads_existing_scores_only() -> None:
    unique = f"attention-{uuid4().hex}"
    source_document_id = f"test-doc-{unique}"
    chunk_id = f"test-chunk-{unique}"

    await _cleanup_attention_fixture(source_document_id)

    try:
        await _insert_attention_fixture(
            unique=unique,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )
        await process_knowledge_scores(source_document_id=source_document_id)

        dashboard = await get_attention_dashboard(
            limit=10,
            source_document_id=source_document_id,
        )

        assert dashboard["answer_type"] == "attention_dashboard"
        assert dashboard["metadata"]["scoring_required"] is False
        assert dashboard["metadata"]["scored_item_count"] == 3

        assert {item["item_type"] for item in dashboard["top_items"]} == {
            "task",
            "risk",
            "decision",
        }

        for item in dashboard["top_items"]:
            assert item["source_document_id"] == source_document_id
            assert item["chunk_id"] == chunk_id
            assert item["evidence_refs"]
            assert item["attention_score"] > 0
            assert item["reasons"]

        assert dashboard["top_tasks"]
        assert dashboard["top_risks"]
        assert dashboard["recent_decisions"]

        assert dashboard["sources"]
        assert dashboard["sources"][0]["source_document_id"] == source_document_id
        assert dashboard["sources"][0]["chunk_id"] == chunk_id

    finally:
        await _cleanup_attention_fixture(source_document_id)


async def test_get_attention_dashboard_requires_existing_scores() -> None:
    unique = f"attention-noscore-{uuid4().hex}"
    source_document_id = f"test-doc-{unique}"
    chunk_id = f"test-chunk-{unique}"

    await _cleanup_attention_fixture(source_document_id)

    try:
        await _insert_attention_fixture(
            unique=unique,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )

        dashboard = await get_attention_dashboard(
            limit=10,
            source_document_id=source_document_id,
        )

        assert dashboard["top_items"] == []
        assert dashboard["top_tasks"] == []
        assert dashboard["top_risks"] == []
        assert dashboard["recent_decisions"] == []
        assert dashboard["sources"] == []
        assert dashboard["metadata"]["scoring_required"] is True
        assert dashboard["metadata"]["scored_item_count"] == 0

    finally:
        await _cleanup_attention_fixture(source_document_id)
