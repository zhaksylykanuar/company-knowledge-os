from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.api.auth import API_AUTH_FAILURE_DETAIL
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.score_models import KnowledgeScore
from app.db.source_models import DocumentChunk, SourceDocument
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.main import app
from app.services.production_operation_guard import PRODUCTION_OPERATION_ACK


def _set_auth(monkeypatch, *, enabled: bool, key: SecretStr | str | None) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", key)
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _pipeline_payload(unique: str, *, text: str | None = None) -> dict[str, object]:
    return {
        "title": f"FOS-009 manual note {unique}",
        "text": text
        or (
            f"Client QAZTWIN {unique} needs follow up. "
            "TODO send proposal to client by next week. "
            "Risk: client is worried about security access. "
            "Decision: start with read-only data collection."
        ),
        "source_type": "manual",
        "project_key": "fos-009",
        "client_key": "test-client",
        "people": ["test-user"],
        "tags": ["test", "fos-009"],
        "allow_production_operation": True,
        "confirm_production_operation": PRODUCTION_OPERATION_ACK,
    }


async def _cleanup_pipeline_fixture(source_document_id: str | None) -> None:
    if source_document_id is None:
        return

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


async def _load_extracted_entities(source_document_id: str) -> list[object]:
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

    return [*tasks, *risks, *decisions]


async def test_ingest_text_process_endpoint_processes_manual_text_with_evidence_and_scores(
    monkeypatch,
    tmp_path,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)
    monkeypatch.setattr(settings, "enable_llm", False)
    monkeypatch.setattr(settings, "raw_storage_dir", str(tmp_path))
    document_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/knowledge/ingest-text-process",
            json=_pipeline_payload(f"pipeline-{uuid4().hex}"),
        )

    try:
        assert response.status_code == 202
        payload = response.json()
        document_id = payload["document_id"]

        assert payload["processed"] is True
        assert payload["raw_ref"] == f"raw://manual/{document_id}/content.txt"
        assert payload["chunks_created"] >= 1
        assert payload["extraction_counts"] == {
            "tasks": 1,
            "risks": 1,
            "decisions": 1,
            "total": 3,
        }
        assert payload["score_counts"]["created"] == 3
        assert payload["score_counts"]["total"] == 3
        assert payload["evidence_summary"]["extracted_entity_count"] == 3
        assert payload["evidence_summary"]["all_extracted_entities_have_evidence_refs"] is True
        assert payload["evidence_summary"]["source_chunk_ids"]
        assert payload["evidence_summary"]["sample_evidence_refs"]
        assert len(payload["extracted_items_preview"]) == 3
        assert {
            item["kind"] for item in payload["extracted_items_preview"]
        } == {"task", "risk", "decision"}
        for item in payload["extracted_items_preview"]:
            assert item["title"]
            assert item["source_document_id"] == document_id
            assert item["chunk_id"]
            assert item["evidence_refs"]
            assert item["evidence_snippet"]
            assert item["score"] is not None
            assert item["score"]["attention_score"] > 0
            assert item["score"]["reasons"]

        assert payload["next_steps"]["search"] == "GET /api/v1/knowledge/search?q=<query>"
        assert payload["next_steps"]["ask"] == "POST /api/v1/knowledge/ask"
        assert payload["next_steps"]["attention"] == "GET /api/v1/knowledge/attention"

        extracted_entities = await _load_extracted_entities(document_id)
        assert len(extracted_entities) == 3
        for entity in extracted_entities:
            assert entity.evidence_refs
            first_ref = entity.evidence_refs[0]
            assert first_ref["source_document_id"] == document_id
            assert first_ref["chunk_id"]
            assert first_ref["raw_object_ref"] == payload["raw_ref"]
            assert first_ref["quote"]

    finally:
        await _cleanup_pipeline_fixture(document_id)


async def test_ingest_text_process_endpoint_reports_zero_counts_without_signals(
    monkeypatch,
    tmp_path,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)
    monkeypatch.setattr(settings, "enable_llm", False)
    monkeypatch.setattr(settings, "raw_storage_dir", str(tmp_path))
    document_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/knowledge/ingest-text-process",
            json=_pipeline_payload(
                f"pipeline-empty-{uuid4().hex}",
                text="Meeting notes only. General context without action signals.",
            ),
        )

    try:
        assert response.status_code == 202
        payload = response.json()
        document_id = payload["document_id"]

        assert payload["chunks_created"] == 1
        assert payload["extraction_counts"] == {
            "tasks": 0,
            "risks": 0,
            "decisions": 0,
            "total": 0,
        }
        assert payload["score_counts"]["total"] == 0
        assert payload["score_counts"]["created"] == 0
        assert payload["evidence_summary"] == {
            "extracted_entity_count": 0,
            "all_extracted_entities_have_evidence_refs": True,
            "source_chunk_ids": [],
            "sample_evidence_refs": [],
        }
        assert payload["extracted_items_preview"] == []

    finally:
        await _cleanup_pipeline_fixture(document_id)


async def test_existing_ingest_text_endpoint_remains_unchanged(monkeypatch, tmp_path) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)
    monkeypatch.setattr(settings, "raw_storage_dir", str(tmp_path))
    document_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/knowledge/ingest-text",
            json=_pipeline_payload(f"existing-ingest-{uuid4().hex}"),
        )

    try:
        assert response.status_code == 202
        payload = response.json()
        document_id = payload["document_id"]

        assert payload["accepted"] is True
        assert "chunks_created" in payload
        assert "raw_ref" in payload
        assert "extraction_counts" not in payload
        assert "score_counts" not in payload
        assert "extracted_items_preview" not in payload

    finally:
        await _cleanup_pipeline_fixture(document_id)


async def test_ingest_text_process_endpoint_auth_and_health_behavior(
    monkeypatch,
    tmp_path,
) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "enable_llm", False)
    monkeypatch.setattr(settings, "raw_storage_dir", str(tmp_path))
    document_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health_response = await client.get("/health")
        missing_key_response = await client.post(
            "/api/v1/knowledge/ingest-text-process",
            json=_pipeline_payload(f"auth-missing-{uuid4().hex}"),
        )
        valid_key_response = await client.post(
            "/api/v1/knowledge/ingest-text-process",
            headers={"X-FounderOS-API-Key": "test-api-key"},
            json=_pipeline_payload(f"auth-valid-{uuid4().hex}"),
        )

    try:
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "ok"

        assert missing_key_response.status_code == 401
        assert missing_key_response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
        assert "test-api-key" not in missing_key_response.text

        assert valid_key_response.status_code == 202
        payload = valid_key_response.json()
        document_id = payload["document_id"]
        assert payload["processed"] is True
        assert payload["extraction_counts"]["total"] == 3
        assert payload["extracted_items_preview"]

    finally:
        await _cleanup_pipeline_fixture(document_id)
