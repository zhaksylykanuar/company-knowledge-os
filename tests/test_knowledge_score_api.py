from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_score_knowledge_endpoint_accepts_source_document_filter() -> None:
    source_document_id = f"missing-score-doc-{uuid4().hex}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/knowledge/score",
            json={"source_document_id": source_document_id},
        )

    assert response.status_code == 202

    payload = response.json()

    assert payload["processed"] is True
    assert payload["source_document_id"] == source_document_id
    assert payload["scores_created"] == 0
    assert payload["scores_updated"] == 0
    assert payload["tasks_scored"] == 0
    assert payload["risks_scored"] == 0
    assert payload["decisions_scored"] == 0
