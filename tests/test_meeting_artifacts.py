from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services import meeting_artifacts
from app.services.meeting_artifacts import (
    KBUpdateDraft,
    MeetingEvidenceRef,
    MeetingTranscriptInput,
    process_meeting_transcript,
    validate_meeting_summary_payload,
)


def _input(*, transcript_text: str | None = None, title: str = "FOS-048 planning") -> MeetingTranscriptInput:
    return MeetingTranscriptInput(
        source_document_id="doc_meeting_1",
        chunk_id="doc_meeting_1_chunk_0",
        raw_object_ref="raw://meeting/doc_meeting_1/content.txt",
        source_url="https://meetings.example.test/doc_meeting_1",
        title=title,
        participants=["fake-founder", "fake-engineer"],
        project="FounderOS",
        related_jira_keys=["QAZ-48"],
        transcript_text=transcript_text
        or """
        Summary: Team reviewed the provider-free meeting draft pipeline.
        Decision: Keep FOS-048 draft-only until human approval exists; owner: fake-founder
        Action: Prepare test coverage for meeting drafts; owner: fake-engineer; due: 2026-05-20
        TODO: Review approval boundary copy; owner: fake-founder; deadline: 2026-05-21
        Risk: Drafts could be mistaken for executed Jira work; severity: high; mitigation: keep status draft
        Question: Who approves Jira draft tickets? owner: fake-founder
        Jira: Add explicit approval gate; type: Story; project_key: QAZ; priority: high; acceptance: Approval is required|No Jira API call is made
        KB: Document meeting draft behavior; note_type: engineering_note; path: 05-knowledge/meeting-drafts.md
        """,
    )


def test_valid_transcript_produces_summary_and_evidence() -> None:
    result = process_meeting_transcript(_input())

    assert result.summary == "Team reviewed the provider-free meeting draft pipeline."
    assert result.evidence_refs
    assert result.evidence_refs[0].marker == "summary"
    assert result.unsupported_claims_rejected == []


def test_decision_line_creates_decision_with_evidence_refs() -> None:
    result = process_meeting_transcript(_input())

    decision = result.decisions[0]
    assert decision.title == "Keep FOS-048 draft-only until human approval exists"
    assert decision.decision == "Keep FOS-048 draft-only until human approval exists"
    assert decision.owner == "fake-founder"
    assert decision.evidence_refs[0].marker == "decision"
    assert decision.evidence_refs[0].source_document_id == "doc_meeting_1"


def test_action_and_todo_lines_create_action_items_with_explicit_owner_and_deadline() -> None:
    result = process_meeting_transcript(_input())

    assert [item.title for item in result.action_items] == [
        "Prepare test coverage for meeting drafts",
        "Review approval boundary copy",
    ]
    assert result.action_items[0].owner == "fake-engineer"
    assert result.action_items[0].due_date == "2026-05-20"
    assert result.action_items[1].owner == "fake-founder"
    assert result.action_items[1].due_date == "2026-05-21"
    assert all(item.status == "draft" for item in result.action_items)
    assert all(item.evidence_refs for item in result.action_items)


def test_action_item_creates_jira_draft_ticket_with_acceptance_criteria_and_evidence() -> None:
    result = process_meeting_transcript(_input())

    action_ticket = result.jira_draft_tickets[0]
    assert action_ticket.title == "Prepare test coverage for meeting drafts"
    assert action_ticket.issue_type == "Task"
    assert action_ticket.project_key is None
    assert action_ticket.acceptance_criteria == [
        "Complete: Prepare test coverage for meeting drafts"
    ]
    assert action_ticket.source_refs == [
        "doc_meeting_1",
        "doc_meeting_1_chunk_0",
        "raw://meeting/doc_meeting_1/content.txt",
        "https://meetings.example.test/doc_meeting_1",
        "QAZ-48",
    ]
    assert action_ticket.evidence_refs[0].marker == "action"
    assert action_ticket.status == "draft"


def test_explicit_jira_line_creates_project_scoped_draft_without_calling_jira() -> None:
    result = process_meeting_transcript(_input())

    explicit_ticket = next(ticket for ticket in result.jira_draft_tickets if ticket.title == "Add explicit approval gate")
    assert explicit_ticket.issue_type == "Story"
    assert explicit_ticket.project_key == "QAZ"
    assert explicit_ticket.priority == "high"
    assert explicit_ticket.acceptance_criteria == [
        "Approval is required",
        "No Jira API call is made",
    ]
    assert explicit_ticket.status == "draft"


def test_risk_line_creates_risk_with_severity_mitigation_and_evidence() -> None:
    result = process_meeting_transcript(_input())

    risk = result.risks[0]
    assert risk.title == "Drafts could be mistaken for executed Jira work"
    assert risk.severity == "high"
    assert risk.mitigation == "keep status draft"
    assert risk.evidence_refs[0].marker == "risk"


def test_question_line_creates_open_question_with_evidence_refs() -> None:
    result = process_meeting_transcript(_input())

    question = result.open_questions[0]
    assert question.question == "Who approves Jira draft tickets?"
    assert question.owner == "fake-founder"
    assert question.evidence_refs[0].marker == "question"


def test_kb_update_drafts_are_inert_with_paths_source_refs_and_evidence_refs() -> None:
    result = process_meeting_transcript(_input())

    meeting_note = result.knowledge_base_updates[0]
    decision_log = next(update for update in result.knowledge_base_updates if update.note_type == "decision_log")
    explicit_kb = next(update for update in result.knowledge_base_updates if update.title == "Document meeting draft behavior")

    assert meeting_note.note_type == "meeting_note"
    assert meeting_note.suggested_path == "03-meetings/fos-048-planning.md"
    assert meeting_note.source_refs
    assert meeting_note.evidence_refs
    assert decision_log.suggested_path.startswith("04-decisions/")
    assert explicit_kb.note_type == "engineering_note"
    assert explicit_kb.suggested_path == "05-knowledge/meeting-drafts.md"
    assert all(update.status == "draft" for update in result.knowledge_base_updates)


def test_no_hallucinated_owner_deadline_or_project_key_when_transcript_lacks_evidence() -> None:
    result = process_meeting_transcript(
        _input(
            transcript_text="""
            Summary: Team discussed a small draft-only slice.
            Action: Prepare the next implementation note.
            Jira: Capture the approval boundary.
            """,
        )
    )

    assert result.action_items[0].owner is None
    assert result.action_items[0].due_date is None
    assert all(ticket.project_key is None for ticket in result.jira_draft_tickets)


def test_empty_transcript_and_blank_source_identifiers_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MeetingTranscriptInput(
            source_document_id="doc_1",
            chunk_id="chunk_1",
            raw_object_ref="raw://meeting/doc_1/content.txt",
            transcript_text="   ",
        )

    with pytest.raises(ValidationError):
        MeetingTranscriptInput(
            source_document_id=" ",
            chunk_id="chunk_1",
            raw_object_ref="raw://meeting/doc_1/content.txt",
            transcript_text="Summary: Safe summary.",
        )

    with pytest.raises(ValidationError):
        MeetingTranscriptInput(
            source_document_id="doc_1",
            chunk_id=" ",
            raw_object_ref="raw://meeting/doc_1/content.txt",
            transcript_text="Summary: Safe summary.",
        )

    with pytest.raises(ValidationError):
        MeetingTranscriptInput(
            source_document_id="doc_1",
            chunk_id="chunk_1",
            raw_object_ref=" ",
            transcript_text="Summary: Safe summary.",
        )


def test_strict_payload_validation_rejects_missing_evidence_refs() -> None:
    payload = {
        "summary": "Safe summary.",
        "decisions": [
            {
                "title": "Use draft-only behavior",
                "decision": "Use draft-only behavior",
                "owner": None,
                "confidence": 0.8,
                "evidence_refs": [],
            }
        ],
        "action_items": [],
        "risks": [],
        "open_questions": [],
        "jira_draft_tickets": [],
        "knowledge_base_updates": [],
        "unsupported_claims_rejected": [],
        "evidence_refs": [],
    }

    with pytest.raises(ValidationError):
        validate_meeting_summary_payload(payload)


def test_unexpected_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MeetingEvidenceRef(
            source_document_id="doc_1",
            chunk_id="chunk_1",
            raw_object_ref="raw://meeting/doc_1/content.txt",
            quote="Summary: Safe summary.",
            unexpected="not allowed",
        )

    with pytest.raises(ValidationError):
        validate_meeting_summary_payload(
            {
                "summary": "Safe summary.",
                "decisions": [],
                "action_items": [],
                "risks": [],
                "open_questions": [],
                "jira_draft_tickets": [],
                "knowledge_base_updates": [],
                "unsupported_claims_rejected": [],
                "evidence_refs": [],
                "unexpected": "not allowed",
            }
        )


def test_evidence_quote_is_bounded_and_does_not_copy_full_transcript() -> None:
    long_action = "Action: " + ("Prepare bounded evidence quote. " * 40)
    transcript = "\n".join(
        [
            "Summary: Short summary.",
            long_action,
            "Question: Confirm bounded evidence?",
        ]
    )

    result = process_meeting_transcript(_input(transcript_text=transcript))
    quotes = [
        ref.quote
        for item in [*result.action_items, *result.open_questions]
        for ref in item.evidence_refs
    ]

    assert all(len(quote) <= 300 for quote in quotes)
    assert transcript not in quotes
    assert result.action_items[0].evidence_refs[0].quote != transcript


def test_no_jira_kb_db_or_provider_dependencies_are_required(monkeypatch) -> None:
    def fail_write_text(self, data, *args, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("meeting draft pipeline must not write files")

    monkeypatch.setattr(Path, "write_text", fail_write_text)
    result = process_meeting_transcript(_input())

    assert result.jira_draft_tickets
    assert result.knowledge_base_updates

    source = inspect.getsource(meeting_artifacts)
    forbidden_tokens = [
        "AsyncSessionLocal",
        "OpenAI",
        "requests",
        "httpx",
        "client.",
        "write_text(",
        "export_obsidian",
        "raw_storage",
        "AttentionTriageAgent",
    ]
    for token in forbidden_tokens:
        assert token not in source


def test_all_output_statuses_remain_draft() -> None:
    result = process_meeting_transcript(_input())

    statuses = [
        *(item.status for item in result.action_items),
        *(item.status for item in result.jira_draft_tickets),
        *(item.status for item in result.knowledge_base_updates),
    ]
    assert statuses
    assert set(statuses) == {"draft"}


def test_validate_meeting_summary_payload_accepts_schema_valid_draft() -> None:
    evidence = {
        "source_document_id": "doc_1",
        "chunk_id": "chunk_1",
        "raw_object_ref": "raw://meeting/doc_1/content.txt",
        "source_url": None,
        "quote": "Decision: Use draft-only behavior.",
        "line_number": 1,
        "marker": "decision",
    }
    payload = {
        "summary": "Safe summary.",
        "decisions": [
            {
                "title": "Use draft-only behavior",
                "decision": "Use draft-only behavior",
                "owner": None,
                "confidence": 0.8,
                "evidence_refs": [evidence],
            }
        ],
        "action_items": [],
        "risks": [],
        "open_questions": [],
        "jira_draft_tickets": [],
        "knowledge_base_updates": [
            {
                "title": "Use draft-only behavior",
                "note_type": "decision_log",
                "suggested_path": "04-decisions/use-draft-only-behavior.md",
                "summary": "Use draft-only behavior",
                "source_refs": ["doc_1", "chunk_1", "raw://meeting/doc_1/content.txt"],
                "evidence_refs": [evidence],
                "status": "draft",
            }
        ],
        "unsupported_claims_rejected": [],
        "evidence_refs": [],
    }

    result = validate_meeting_summary_payload(payload)

    assert result.decisions[0].evidence_refs[0].quote == "Decision: Use draft-only behavior."
    assert isinstance(result.knowledge_base_updates[0], KBUpdateDraft)
