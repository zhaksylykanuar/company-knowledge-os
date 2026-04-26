from datetime import date
from types import SimpleNamespace

from app.services.knowledge_scoring import build_score_values, compute_knowledge_score


def test_scores_high_security_client_risk_with_evidence() -> None:
    score = compute_knowledge_score(
        entity_type="risk",
        title="Risk: client is worried about IT security and SCADA access.",
        severity="high",
        confidence=0.82,
        evidence_refs=[{"chunk_id": "chunk_1"}],
        today=date(2026, 4, 26),
    )

    assert score.importance_score == 1.0
    assert score.urgency_score == 0.35
    assert score.risk_score == 0.9
    assert score.confidence_score == 0.82
    assert score.attention_score == 0.73
    assert score.evidence_refs == [{"chunk_id": "chunk_1"}]

    reason_codes = {reason["code"] for reason in score.reasons}
    assert "high_severity_risk" in reason_codes
    assert "client_or_stakeholder_context" in reason_codes
    assert "security_or_access_context" in reason_codes


def test_scores_open_task_with_due_date_and_client_context() -> None:
    score = compute_knowledge_score(
        entity_type="task",
        title="TODO: send proposal to client next week.",
        status="open",
        due_date="2026-04-27",
        confidence=0.9,
        evidence_refs=[{"chunk_id": "chunk_2"}],
        today=date(2026, 4, 26),
    )

    assert score.importance_score == 0.6
    assert score.urgency_score == 0.85
    assert score.risk_score == 0.1
    assert score.confidence_score == 0.9
    assert score.attention_score == 0.52

    reason_codes = {reason["code"] for reason in score.reasons}
    assert "open_task" in reason_codes
    assert "due_date_soon" in reason_codes
    assert "client_or_stakeholder_context" in reason_codes
    assert "urgent_language" in reason_codes


def test_missing_evidence_caps_confidence_and_adds_reason() -> None:
    score = compute_knowledge_score(
        entity_type="decision",
        title="Decision: allow write actions later.",
        decision="allow write actions later",
        confidence=0.95,
        evidence_refs=[],
        today=date(2026, 4, 26),
    )

    assert score.confidence_score == 0.2

    reason_codes = {reason["code"] for reason in score.reasons}
    assert "missing_evidence_refs" in reason_codes
    assert "write_action_context" in reason_codes


def test_build_score_values_uses_existing_entity_fields_only() -> None:
    entity = SimpleNamespace(
        id=123,
        title="Decision: start with read-only SCADA data collection.",
        decision="start with read-only SCADA data collection",
        source_document_id="doc_1",
        chunk_id="chunk_3",
        confidence=0.88,
        evidence_refs=[{"chunk_id": "chunk_3"}],
    )

    values = build_score_values(
        entity_type="decision",
        entity=entity,
        today=date(2026, 4, 26),
    )

    assert values["entity_type"] == "decision"
    assert values["entity_id"] == "123"
    assert values["source_document_id"] == "doc_1"
    assert values["chunk_id"] == "chunk_3"
    assert values["evidence_refs"] == [{"chunk_id": "chunk_3"}]
    assert values["importance_score"] > 0
    assert values["attention_score"] > 0
    assert values["reasons"]
