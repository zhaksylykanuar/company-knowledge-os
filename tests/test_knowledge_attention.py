from app.services.knowledge_attention import compute_attention_dashboard


def _attention_item(
    *,
    item_type: str,
    entity_id: str,
    title: str,
    attention_score: float,
    source_document_id: str,
    chunk_id: str,
    created_at: str = "2026-04-27T00:00:00+00:00",
    metadata: dict | None = None,
) -> dict:
    return {
        "item_type": item_type,
        "entity_id": entity_id,
        "title": title,
        "source_document_id": source_document_id,
        "chunk_id": chunk_id,
        "source_title": "QazTwin test note",
        "attention_score": attention_score,
        "importance_score": attention_score,
        "urgency_score": 0.2,
        "risk_score": 0.3,
        "confidence_score": 0.9,
        "reasons": ["test_reason"],
        "metadata": metadata or {},
        "created_at": created_at,
        "evidence_refs": [
            {
                "source_document_id": source_document_id,
                "chunk_id": chunk_id,
                "raw_object_ref": "raw://test",
                "source_url": "https://example.test/source",
                "quote": title,
            }
        ],
    }


def test_compute_attention_dashboard_groups_evidence_backed_items() -> None:
    items = [
        _attention_item(
            item_type="task",
            entity_id="task_entity_1",
            title="TODO: send proposal to client next week",
            attention_score=0.45,
            source_document_id="doc-task",
            chunk_id="chunk-task",
            metadata={"status": "open"},
        ),
        _attention_item(
            item_type="risk",
            entity_id="risk_entity_1",
            title="Risk: client is worried about IT security",
            attention_score=0.95,
            source_document_id="doc-risk",
            chunk_id="chunk-risk",
        ),
        _attention_item(
            item_type="decision",
            entity_id="decision_entity_1",
            title="Decision: start with read-only collection",
            attention_score=0.65,
            source_document_id="doc-decision",
            chunk_id="chunk-decision",
            created_at="2026-04-27T01:00:00+00:00",
        ),
    ]

    dashboard = compute_attention_dashboard(
        items,
        limit=2,
        generated_at="2026-04-27T02:00:00+00:00",
    )

    assert dashboard["answer_type"] == "attention_dashboard"
    assert dashboard["generated_at"] == "2026-04-27T02:00:00+00:00"
    assert dashboard["metadata"]["limit"] == 2
    assert dashboard["metadata"]["scoring_required"] is False
    assert dashboard["metadata"]["scored_item_count"] == 3
    assert dashboard["metadata"]["dropped_item_count"] == 0

    assert [item["entity_id"] for item in dashboard["top_items"]] == [
        "risk_entity_1",
        "decision_entity_1",
    ]
    assert [item["entity_id"] for item in dashboard["top_tasks"]] == ["task_entity_1"]
    assert [item["entity_id"] for item in dashboard["top_risks"]] == ["risk_entity_1"]
    assert [item["entity_id"] for item in dashboard["recent_decisions"]] == [
        "decision_entity_1"
    ]

    assert dashboard["top_items"][0]["evidence_refs"]
    assert dashboard["top_items"][0]["source_document_id"] == "doc-risk"
    assert dashboard["top_items"][0]["chunk_id"] == "chunk-risk"
    assert dashboard["sources"]


def test_compute_attention_dashboard_drops_items_without_evidence() -> None:
    items = [
        {
            "item_type": "risk",
            "entity_id": "risk_unsupported",
            "title": "Unsupported risk should not enter dashboard",
            "attention_score": 1.0,
            "evidence_refs": [],
        }
    ]

    dashboard = compute_attention_dashboard(
        items,
        generated_at="2026-04-27T02:00:00+00:00",
    )

    assert dashboard["top_items"] == []
    assert dashboard["top_tasks"] == []
    assert dashboard["top_risks"] == []
    assert dashboard["recent_decisions"] == []
    assert dashboard["sources"] == []
    assert dashboard["metadata"]["scoring_required"] is True
    assert dashboard["metadata"]["scored_item_count"] == 0
    assert dashboard["metadata"]["dropped_item_count"] == 1
    assert "No evidence-backed scored items found" in dashboard["summary"]
