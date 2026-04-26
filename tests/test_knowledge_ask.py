from uuid import uuid4

from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.source_models import DocumentChunk, SourceDocument
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.knowledge_qa import ask_knowledge


async def _cleanup_ask_fixture(source_document_id: str) -> None:
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


async def _insert_ask_fixture(
    *,
    unique: str,
    source_document_id: str,
    chunk_id: str,
) -> None:
    evidence_refs = [
        {
            "source_document_id": source_document_id,
            "chunk_id": chunk_id,
            "quote": f"QAZTWIN ask evidence quote {unique}",
        }
    ]

    async with AsyncSessionLocal() as session:
        session.add(
            SourceDocument(
                source_document_id=source_document_id,
                source_system="test",
                source_object_id=f"qa-object-{unique}",
                title=f"ABC Manufacturing QAZTWIN ask note {unique}",
                source_url=f"test://qa-source/{unique}",
                mime_type="text/plain",
                raw_object_ref=f"raw://qa/{unique}",
                content_hash=f"qa-doc-hash-{unique}",
                modified_at=None,
                metadata_json={},
            )
        )
        session.add(
            DocumentChunk(
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                source_system="test",
                source_object_id=f"qa-object-{unique}",
                raw_object_ref=f"raw://qa/{unique}",
                text=(
                    f"Client ABC Manufacturing discussed QAZTWIN onboarding {unique}. "
                    "TODO: send proposal to client next week. "
                    "Risk: client is worried about IT security and SCADA access. "
                    "Decision: start with read-only data collection."
                ),
                start_char=0,
                end_char=220,
                content_hash=f"qa-chunk-hash-{unique}",
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


async def test_ask_knowledge_returns_relevant_risks_with_sources() -> None:
    unique = f"qa-{uuid4().hex}"
    source_document_id = f"test-doc-{unique}"
    chunk_id = f"test-chunk-{unique}"

    await _cleanup_ask_fixture(source_document_id)

    try:
        await _insert_ask_fixture(
            unique=unique,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )

        result = await ask_knowledge(
            question=f"какие риски по {unique}?",
            limit=10,
        )

        matching_risks = [
            item
            for item in result["relevant_risks"]
            if item["source_document_id"] == source_document_id
        ]

        matching_sources = [
            source
            for source in result["sources"]
            if source["source_document_id"] == source_document_id
        ]

        assert result["answer_type"] == "risks"
        assert matching_risks
        assert matching_sources
        assert matching_risks[0]["chunk_id"] == chunk_id
        assert matching_risks[0]["evidence_refs"]

    finally:
        await _cleanup_ask_fixture(source_document_id)


async def test_ask_knowledge_uses_recent_fallback_for_generic_promises() -> None:
    unique = f"qa-{uuid4().hex}"
    source_document_id = f"test-doc-{unique}"
    chunk_id = f"test-chunk-{unique}"

    await _cleanup_ask_fixture(source_document_id)

    try:
        await _insert_ask_fixture(
            unique=unique,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )

        result = await ask_knowledge(
            question="что я обещал клиенту?",
            limit=5,
        )

        matching_tasks = [
            item
            for item in result["relevant_tasks"]
            if item["source_document_id"] == source_document_id
        ]

        assert result["answer_type"] == "tasks"
        assert result["search"]["used_recent_fallback"] is True
        assert matching_tasks
        assert matching_tasks[0]["chunk_id"] == chunk_id
        assert matching_tasks[0]["evidence_refs"]

    finally:
        await _cleanup_ask_fixture(source_document_id)


async def test_ask_knowledge_uses_recent_fallback_for_generic_decisions() -> None:
    unique = f"qa-{uuid4().hex}"
    source_document_id = f"test-doc-{unique}"
    chunk_id = f"test-chunk-{unique}"

    await _cleanup_ask_fixture(source_document_id)

    try:
        await _insert_ask_fixture(
            unique=unique,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )

        result = await ask_knowledge(
            question="какие решения были приняты?",
            limit=5,
        )

        matching_decisions = [
            item
            for item in result["relevant_decisions"]
            if item["source_document_id"] == source_document_id
        ]

        assert result["answer_type"] == "decisions"
        assert result["search"]["used_recent_fallback"] is True
        assert matching_decisions
        assert matching_decisions[0]["chunk_id"] == chunk_id
        assert matching_decisions[0]["evidence_refs"]

    finally:
        await _cleanup_ask_fixture(source_document_id)
