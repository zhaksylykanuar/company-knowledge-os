from app.db.source_models import DocumentChunk, SourceDocument
from app.services import knowledge_ingestion
from app.services.production_operation_guard import PRODUCTION_OPERATION_ACK
from app.services.raw_storage import sha256_text


class FakeAsyncSession:
    def __init__(self, added: list[object]) -> None:
        self.added = added

    async def __aenter__(self) -> "FakeAsyncSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    def add_all(self, items: list[object]) -> None:
        self.added.extend(items)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


def _fake_session_factory(added: list[object]):
    def factory() -> FakeAsyncSession:
        return FakeAsyncSession(added)

    return factory


async def test_ingest_text_uses_sha256_content_hashes(monkeypatch, tmp_path) -> None:
    added: list[object] = []
    text = "TODO send proposal to client next week.\nDecision: use read-only access first."

    monkeypatch.setattr(knowledge_ingestion.settings, "raw_storage_dir", str(tmp_path))
    monkeypatch.setattr(
        knowledge_ingestion,
        "AsyncSessionLocal",
        _fake_session_factory(added),
    )

    result = await knowledge_ingestion.ingest_text(
        title="Manual note",
        text=text,
        allow_production_operation=True,
        production_operation_ack=PRODUCTION_OPERATION_ACK,
    )

    source_document = next(item for item in added if isinstance(item, SourceDocument))
    chunks = [item for item in added if isinstance(item, DocumentChunk)]

    assert result["chunks_created"] == 1
    assert source_document.content_hash == sha256_text(text)
    assert chunks[0].content_hash == sha256_text(chunks[0].text)


async def test_manual_ingestion_hashes_are_stable_sha256(monkeypatch, tmp_path) -> None:
    first_added: list[object] = []
    second_added: list[object] = []
    text = "Same manual text should produce the same deterministic content hash."

    monkeypatch.setattr(knowledge_ingestion.settings, "raw_storage_dir", str(tmp_path))

    monkeypatch.setattr(
        knowledge_ingestion,
        "AsyncSessionLocal",
        _fake_session_factory(first_added),
    )
    await knowledge_ingestion.ingest_text(
        title="First note",
        text=text,
        allow_production_operation=True,
        production_operation_ack=PRODUCTION_OPERATION_ACK,
    )

    monkeypatch.setattr(
        knowledge_ingestion,
        "AsyncSessionLocal",
        _fake_session_factory(second_added),
    )
    await knowledge_ingestion.ingest_text(
        title="Second note",
        text=text,
        allow_production_operation=True,
        production_operation_ack=PRODUCTION_OPERATION_ACK,
    )

    first_document = next(item for item in first_added if isinstance(item, SourceDocument))
    second_document = next(item for item in second_added if isinstance(item, SourceDocument))

    assert first_document.content_hash == second_document.content_hash
    assert first_document.content_hash == sha256_text(text)
    assert len(first_document.content_hash) == 64
    assert all(char in "0123456789abcdef" for char in first_document.content_hash)
