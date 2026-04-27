from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_attention_endpoint_returns_scoring_required_when_no_scores() -> None:
    source_document_id = f"missing-attention-score-doc-{uuid4().hex}"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/knowledge/attention",
            params={
                "limit": 10,
                "source_document_id": source_document_id,
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert body["answer_type"] == "attention_dashboard"
    assert body["top_items"] == []
    assert body["top_tasks"] == []
    assert body["top_risks"] == []
    assert body["recent_decisions"] == []
    assert body["sources"] == []
    assert body["metadata"]["limit"] == 10
    assert body["metadata"]["scoring_required"] is True
    assert body["metadata"]["scored_item_count"] == 0
    assert "POST /v1/knowledge/score" in body["summary"]
