from uuid import uuid4

from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.source_models import DocumentChunk, SourceDocument
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.knowledge_search import search_knowledge


async def _cleanup_search_fixture(source_document_id: str) -> None:
    async with AsyncSessionLocal() as session:
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


async def _insert_search_fixture(
    *,
    unique: str,
    source_document_id: str,
    chunk_id: str,
) -> None:
    evidence_refs = [
        {
            "source_document_id": source_document_id,
            "chunk_id": chunk_id,
            "quote": f"QAZTWIN evidence quote {unique}",
        }
    ]

    async with AsyncSessionLocal() as session:
        session.add(
            SourceDocument(
                source_document_id=source_document_id,
                source_system="test",
                source_object_id=f"object-{unique}",
                title=f"ABC Manufacturing QAZTWIN note {unique}",
                source_url=f"test://source/{unique}",
                mime_type="text/plain",
                raw_object_ref=f"raw://{unique}",
                content_hash=f"doc-hash-{unique}",
                modified_at=None,
                metadata_json={},
            )
        )
        session.add(
            DocumentChunk(
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                source_system="test",
                source_object_id=f"object-{unique}",
                raw_object_ref=f"raw://{unique}",
                text=(
                    f"Client ABC Manufacturing discussed QAZTWIN onboarding {unique}. "
                    "SCADA integration must start read-only."
                ),
                start_char=0,
                end_char=120,
                content_hash=f"chunk-hash-{unique}",
                metadata_json={},
            )
        )
        session.add(
            ExtractedTask(
                title=f"TODO: send proposal to ABC Manufacturing {unique}",
                status="open",
                item_type="task",
                owner=None,
                due_date="next week",
                confidence=0.9,
                source_event_id=chunk_id,
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                evidence_refs=evidence_refs,
            )
        )
        session.add(
            ExtractedRisk(
                title=f"Risk: client is worried about IT security {unique}",
                severity="medium",
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
                decision=f"Start with read-only data collection before write actions {unique}",
                owner=None,
                confidence=0.95,
                source_event_id=chunk_id,
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                evidence_refs=evidence_refs,
            )
        )

        await session.commit()


async def test_search_knowledge_returns_chunks_and_extracted_items() -> None:
    unique = f"search-{uuid4().hex}"
    source_document_id = f"test-doc-{unique}"
    chunk_id = f"test-chunk-{unique}"

    await _cleanup_search_fixture(source_document_id)

    try:
        await _insert_search_fixture(
            unique=unique,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )

        result = await search_knowledge(query=unique, limit=20)
        matching_results = [
            item
            for item in result["results"]
            if item["source_document_id"] == source_document_id
        ]

        result_types = {item["result_type"] for item in matching_results}

        assert result["query"] == unique
        assert {"chunk", "task", "risk", "decision"}.issubset(result_types)
        assert len(matching_results) == 4

        for item in matching_results:
            assert item["source_document_id"] == source_document_id
            assert item["chunk_id"] == chunk_id
            assert item["evidence_refs"]

    finally:
        await _cleanup_search_fixture(source_document_id)


async def test_search_knowledge_empty_query_returns_no_results() -> None:
    result = await search_knowledge(query="   ")

    assert result["query"] == ""
    assert result["terms"] == []
    assert result["counts"]["total"] == 0
    assert result["results"] == []
