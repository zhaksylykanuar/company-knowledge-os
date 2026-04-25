import json
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.source_models import SourceDocument, DocumentChunk
from app.services.chunking import chunk_text


def _now():
    return datetime.now(timezone.utc)


def _build_raw_path(doc_id: str) -> Path:
    base = Path(settings.raw_storage_dir)
    path = base / "manual" / doc_id
    path.mkdir(parents=True, exist_ok=True)
    return path


async def ingest_text(
    *,
    title: str,
    text: str,
    source_type: str = "manual",
    project_key: str | None = None,
    client_key: str | None = None,
    people: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    """
    Главная функция ingestion:
    - сохраняет raw
    - создаёт source_document
    - создаёт document_chunks
    """

    doc_id = f"doc_{uuid4().hex}"

    # 1. RAW STORAGE
    raw_dir = _build_raw_path(doc_id)

    content_file = raw_dir / "content.txt"
    meta_file = raw_dir / "metadata.json"

    content_file.write_text(text, encoding="utf-8")

    metadata = {
        "title": title,
        "source_type": source_type,
        "project_key": project_key,
        "client_key": client_key,
        "people": people or [],
        "tags": tags or [],
        "created_at": _now().isoformat(),
    }

    meta_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    raw_ref = f"raw://manual/{doc_id}/content.txt"

    # 2. DB: source_document
    async with AsyncSessionLocal() as session:
        doc = SourceDocument(
            source_document_id=doc_id,
            source_system="manual",
            source_object_id=doc_id,
            title=title,
            source_url=None,
            raw_object_ref=raw_ref,
            content_hash=str(abs(hash(text))),
            modified_at=_now().isoformat(),
            metadata_json=metadata,
        )
        session.add(doc)
        await session.flush()  # чтобы получить doc.id

        # 3. CHUNKING
        chunks = chunk_text(text)

        chunk_rows = []
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{idx}"

            chunk_rows.append(
                DocumentChunk(
                    source_document_id=doc_id,
                    chunk_id=chunk_id,
                    source_system="manual",
                    source_object_id=doc_id,
                    raw_object_ref=raw_ref,
                    text=chunk.text,
                    start_char=chunk.start_char,
                    end_char=chunk.end_char,
                    content_hash=str(abs(hash(chunk.text))),
                    metadata_json={"chunk_index": idx},
                )
            )

        session.add_all(chunk_rows)
        await session.commit()

    return {
        "document_id": doc_id,
        "chunks_created": len(chunk_rows),
        "raw_ref": raw_ref,
    }