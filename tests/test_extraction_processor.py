from app.agents.schemas import (
    EvidenceRef,
    ExtractedDecision as AgentExtractedDecision,
    ExtractedRisk as AgentExtractedRisk,
    ExtractedTask as AgentExtractedTask,
    ExtractionResult,
)
from app.db.source_models import DocumentChunk
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services import extraction_processor


class FakeScalarResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def all(self) -> list[object]:
        return self.items


class FakeExecuteResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.items)


class FakeAsyncSession:
    def __init__(self, chunks: list[DocumentChunk], added: list[object]) -> None:
        self.chunks = chunks
        self.added = added

    async def __aenter__(self) -> "FakeAsyncSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, statement) -> FakeExecuteResult:
        return FakeExecuteResult(self.chunks)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        return None


class FakeRunner:
    async def extract(
        self,
        *,
        source_document_id: str,
        chunk_id: str,
        raw_object_ref: str,
        text: str,
    ) -> ExtractionResult:
        evidence_ref = EvidenceRef(
            source_document_id=source_document_id,
            chunk_id=chunk_id,
            raw_object_ref=raw_object_ref,
            quote=text,
        )

        return ExtractionResult(
            tasks=[
                AgentExtractedTask(
                    title="TODO send proposal",
                    confidence=0.9,
                    evidence_refs=[evidence_ref],
                )
            ],
            risks=[
                AgentExtractedRisk(
                    title="Risk client access concern",
                    severity="medium",
                    confidence=0.8,
                    evidence_refs=[evidence_ref],
                )
            ],
            decisions=[
                AgentExtractedDecision(
                    title="Decision use read-only first",
                    decision="Use read-only access first",
                    confidence=0.95,
                    evidence_refs=[evidence_ref],
                )
            ],
        )


def _fake_session_factory(
    *,
    chunks: list[DocumentChunk],
    added: list[object],
):
    def factory() -> FakeAsyncSession:
        return FakeAsyncSession(chunks=chunks, added=added)

    return factory


async def test_process_document_chunks_keeps_document_provenance_out_of_source_event_id(
    monkeypatch,
) -> None:
    added: list[object] = []
    chunk = DocumentChunk(
        source_document_id="doc_123",
        chunk_id="doc_123_chunk_0",
        source_system="manual",
        source_object_id="doc_123",
        raw_object_ref="raw://manual/doc_123/content.txt",
        text="TODO send proposal. Risk client access concern. Decision use read-only first.",
        start_char=0,
        end_char=75,
        content_hash="chunk-hash",
        metadata_json={"chunk_index": 0},
    )

    monkeypatch.setattr(
        extraction_processor,
        "AsyncSessionLocal",
        _fake_session_factory(chunks=[chunk], added=added),
    )
    monkeypatch.setattr(
        extraction_processor,
        "get_agent_runner",
        lambda: FakeRunner(),
    )

    result = await extraction_processor.process_document_chunks("doc_123")

    task = next(item for item in added if isinstance(item, ExtractedTask))
    risk = next(item for item in added if isinstance(item, ExtractedRisk))
    decision = next(item for item in added if isinstance(item, ExtractedDecision))
    expected_evidence_refs = [
        {
            "source_document_id": chunk.source_document_id,
            "chunk_id": chunk.chunk_id,
            "raw_object_ref": chunk.raw_object_ref,
            "source_url": None,
            "quote": chunk.text,
        }
    ]

    assert result == {
        "source_document_id": "doc_123",
        "chunks_processed": 1,
        "tasks_created": 1,
        "decisions_created": 1,
        "risks_created": 1,
    }

    for item in (task, risk, decision):
        assert item.source_event_id is None
        assert item.source_document_id == chunk.source_document_id
        assert item.chunk_id == chunk.chunk_id
        assert item.evidence_refs == expected_evidence_refs
