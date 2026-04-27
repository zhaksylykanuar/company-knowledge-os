from uuid import uuid4

from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.score_models import KnowledgeScore
from app.db.source_models import DocumentChunk, SourceDocument
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.knowledge_score_processor import process_knowledge_scores
from app.services.obsidian_exporter import (
    collect_obsidian_entities,
    export_obsidian_vault,
)


async def _cleanup_obsidian_fixture(source_document_id: str) -> None:
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


async def _insert_obsidian_fixture(
    *,
    unique: str,
    source_document_id: str,
    chunk_id: str,
) -> None:
    evidence_refs = [
        {
            "source_document_id": source_document_id,
            "chunk_id": chunk_id,
            "quote": f"Obsidian exporter evidence quote {unique}",
        }
    ]

    async with AsyncSessionLocal() as session:
        session.add(
            SourceDocument(
                source_document_id=source_document_id,
                source_system="test",
                source_object_id=f"obsidian-object-{unique}",
                title=f"ABC Manufacturing QAZTWIN obsidian note {unique}",
                source_url=f"test://obsidian-source/{unique}",
                mime_type="text/plain",
                raw_object_ref=f"raw://obsidian/{unique}",
                content_hash=f"obsidian-doc-hash-{unique}",
                modified_at=None,
                metadata_json={},
            )
        )
        session.add(
            DocumentChunk(
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                source_system="test",
                source_object_id=f"obsidian-object-{unique}",
                raw_object_ref=f"raw://obsidian/{unique}",
                text=(
                    f"Client ABC Manufacturing discussed QAZTWIN onboarding {unique}. "
                    "TODO: send proposal to client next week. "
                    "Risk: client is worried about IT security and SCADA access. "
                    "Decision: start with read-only data collection."
                ),
                start_char=0,
                end_char=260,
                content_hash=f"obsidian-chunk-hash-{unique}",
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


async def test_collect_obsidian_entities_reads_extracted_entities_and_scores() -> None:
    unique = f"obsidian-{uuid4().hex}"
    source_document_id = f"test-doc-{unique}"
    chunk_id = f"test-chunk-{unique}"

    await _cleanup_obsidian_fixture(source_document_id)

    try:
        await _insert_obsidian_fixture(
            unique=unique,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )
        await process_knowledge_scores(source_document_id=source_document_id)

        entities = await collect_obsidian_entities(
            source_document_id=source_document_id
        )
        entities_by_type = {entity.entity_type: entity for entity in entities}

        assert set(entities_by_type) == {"task", "risk", "decision"}

        for entity in entities:
            assert entity.source_document_id == source_document_id
            assert entity.chunk_id == chunk_id
            assert entity.evidence_refs
            assert entity.evidence_refs[0]["chunk_id"] == chunk_id
            assert entity.score is not None
            assert entity.score["attention_score"] > 0
            assert entity.score["reasons"]

        assert entities_by_type["risk"].metadata["severity"] == "high"
        assert entities_by_type["task"].metadata["status"] == "open"
        assert entities_by_type["decision"].metadata["decision"].startswith(
            "Start with read-only data collection"
        )

    finally:
        await _cleanup_obsidian_fixture(source_document_id)


async def test_export_obsidian_vault_writes_markdown_files_from_postgres(tmp_path) -> None:
    unique = f"obsidian-{uuid4().hex}"
    source_document_id = f"test-doc-{unique}"
    chunk_id = f"test-chunk-{unique}"

    await _cleanup_obsidian_fixture(source_document_id)

    try:
        await _insert_obsidian_fixture(
            unique=unique,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
        )
        await process_knowledge_scores(source_document_id=source_document_id)

        result = await export_obsidian_vault(
            vault_path=tmp_path,
            source_document_id=source_document_id,
        )

        assert result["exported"] is True
        assert result["source_document_id"] == source_document_id
        assert result["entity_count"] == 3
        assert result["index_count"] == 4
        assert result["exported_count"] == 7
        assert len(result["files"]) == 7

        assert "FounderOS.md" in result["files"]
        assert "Tasks/_Index.md" in result["files"]
        assert "Risks/_Index.md" in result["files"]
        assert "Decisions/_Index.md" in result["files"]

        entity_files = [
            path
            for path in result["files"]
            if (
                path.startswith(("Tasks/", "Risks/", "Decisions/"))
                and not path.endswith("_Index.md")
            )
        ]

        assert len(entity_files) == 3

        for relative_path in result["files"]:
            assert (tmp_path / relative_path).exists()

        for relative_path in entity_files:
            output_path = tmp_path / relative_path
            markdown = output_path.read_text()

            assert "Generated from Postgres source of truth" in markdown
            assert "## Evidence refs" in markdown
            assert "## Score" in markdown
            assert chunk_id in markdown

        assert "# FounderOS Vault Export" in (tmp_path / "FounderOS.md").read_text()
        assert chunk_id in (tmp_path / "Tasks/_Index.md").read_text()
        assert chunk_id in (tmp_path / "Risks/_Index.md").read_text()
        assert chunk_id in (tmp_path / "Decisions/_Index.md").read_text()

    finally:
        await _cleanup_obsidian_fixture(source_document_id)
