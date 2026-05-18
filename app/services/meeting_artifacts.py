from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_EVIDENCE_QUOTE_CHARS = 300

IssueType = Literal["Task", "Story", "Bug", "Risk"]
DraftStatus = Literal["draft"]
DraftPriority = Literal["low", "medium", "high"]
RiskSeverity = Literal["low", "medium", "high"]
KBNoteType = Literal["meeting_note", "decision_log", "engineering_note", "product_note"]

_MARKER_RE = re.compile(
    r"^\s*(?:[-*]\s*)?"
    r"(?P<marker>Summary|Decision|Action|TODO|Risk|Question|Jira|KB|Unsupported|Claim)"
    r"\s*:\s*(?P<body>.*)$",
    re.IGNORECASE,
)
_METADATA_RE_TEMPLATE = r"(?:^|[;,\?])\s*{key}\s*(?:=|:)\s*([^;,\?]+)"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MeetingTranscriptInput(_StrictModel):
    source_document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    raw_object_ref: str = Field(min_length=1)
    transcript_text: str = Field(min_length=1)
    title: str | None = None
    meeting_at: datetime | None = None
    participants: list[str] = Field(default_factory=list)
    project: str | None = None
    source_url: str | None = None
    related_jira_keys: list[str] = Field(default_factory=list)
    related_prs: list[str] = Field(default_factory=list)
    related_files: list[str] = Field(default_factory=list)

    @field_validator(
        "participants",
        "related_jira_keys",
        "related_prs",
        "related_files",
        mode="before",
    )
    @classmethod
    def _clean_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        return _unique_strings(str(item).strip() for item in value if str(item).strip())


class MeetingEvidenceRef(_StrictModel):
    source_document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    raw_object_ref: str = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=MAX_EVIDENCE_QUOTE_CHARS)
    source_url: str | None = None
    line_number: int | None = Field(default=None, ge=1)
    marker: str | None = None


class MeetingDecision(_StrictModel):
    title: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    owner: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[MeetingEvidenceRef] = Field(min_length=1)


class MeetingActionItem(_StrictModel):
    title: str = Field(min_length=1)
    owner: str | None = None
    due_date: str | None = None
    status: DraftStatus = "draft"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[MeetingEvidenceRef] = Field(min_length=1)


class MeetingRisk(_StrictModel):
    title: str = Field(min_length=1)
    severity: RiskSeverity = "medium"
    mitigation: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[MeetingEvidenceRef] = Field(min_length=1)


class MeetingOpenQuestion(_StrictModel):
    question: str = Field(min_length=1)
    owner: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[MeetingEvidenceRef] = Field(min_length=1)


class JiraDraftTicket(_StrictModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    issue_type: IssueType = "Task"
    project_key: str | None = None
    priority: DraftPriority = "medium"
    labels: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    evidence_refs: list[MeetingEvidenceRef] = Field(min_length=1)
    status: DraftStatus = "draft"


class KBUpdateDraft(_StrictModel):
    title: str = Field(min_length=1)
    note_type: KBNoteType
    suggested_path: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    evidence_refs: list[MeetingEvidenceRef] = Field(min_length=1)
    status: DraftStatus = "draft"


class MeetingSummaryResult(_StrictModel):
    summary: str = Field(min_length=1)
    decisions: list[MeetingDecision] = Field(default_factory=list)
    action_items: list[MeetingActionItem] = Field(default_factory=list)
    risks: list[MeetingRisk] = Field(default_factory=list)
    open_questions: list[MeetingOpenQuestion] = Field(default_factory=list)
    jira_draft_tickets: list[JiraDraftTicket] = Field(default_factory=list)
    knowledge_base_updates: list[KBUpdateDraft] = Field(default_factory=list)
    unsupported_claims_rejected: list[str] = Field(default_factory=list)
    evidence_refs: list[MeetingEvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_evidence_backing(self) -> MeetingSummaryResult:
        for group_name in (
            "decisions",
            "action_items",
            "risks",
            "open_questions",
            "jira_draft_tickets",
            "knowledge_base_updates",
        ):
            for item in getattr(self, group_name):
                if not item.evidence_refs:
                    raise ValueError(f"{group_name} item has no evidence_refs")
        return self


def process_meeting_transcript(input: MeetingTranscriptInput) -> MeetingSummaryResult:
    """Create inert meeting, Jira, and KB drafts from explicit transcript markers."""

    parsed_lines = _marker_lines(input.transcript_text)
    summary_refs: list[MeetingEvidenceRef] = []
    summary_lines: list[str] = []
    decisions: list[MeetingDecision] = []
    action_items: list[MeetingActionItem] = []
    risks: list[MeetingRisk] = []
    open_questions: list[MeetingOpenQuestion] = []
    explicit_jira: list[JiraDraftTicket] = []
    explicit_kb: list[KBUpdateDraft] = []
    unsupported_claims_rejected: list[str] = []

    for marker, body, original_line, line_number in parsed_lines:
        evidence = _evidence_ref(input, original_line, line_number=line_number, marker=marker)

        if marker == "summary":
            summary_lines.append(body)
            summary_refs.append(evidence)
        elif marker == "decision":
            decisions.append(_decision_from_line(body, evidence))
        elif marker in {"action", "todo"}:
            action_items.append(_action_from_line(body, evidence))
        elif marker == "risk":
            risks.append(_risk_from_line(body, evidence))
        elif marker == "question":
            open_questions.append(_question_from_line(body, evidence))
        elif marker == "jira":
            explicit_jira.append(_jira_from_line(body, evidence, source_refs=_source_refs(input)))
        elif marker == "kb":
            explicit_kb.append(_kb_from_line(body, evidence, source_refs=_source_refs(input)))
        elif marker in {"unsupported", "claim"}:
            unsupported_claims_rejected.append(body)

    source_refs = _source_refs(input)
    jira_drafts = [
        _jira_from_action(action, source_refs=source_refs)
        for action in action_items
    ]
    jira_drafts.extend(explicit_jira)

    kb_drafts: list[KBUpdateDraft] = []
    extracted_evidence = _result_evidence_refs(
        decisions=decisions,
        action_items=action_items,
        risks=risks,
        open_questions=open_questions,
        jira_draft_tickets=jira_drafts,
        explicit_refs=summary_refs,
    )
    summary = _summary_text(input, summary_lines=summary_lines)
    if extracted_evidence:
        kb_drafts.append(_meeting_note_draft(input, summary=summary, evidence_refs=extracted_evidence))
    kb_drafts.extend(_decision_log_draft(decision, source_refs=source_refs) for decision in decisions)
    kb_drafts.extend(explicit_kb)

    return MeetingSummaryResult(
        summary=summary,
        decisions=decisions,
        action_items=action_items,
        risks=risks,
        open_questions=open_questions,
        jira_draft_tickets=jira_drafts,
        knowledge_base_updates=kb_drafts,
        unsupported_claims_rejected=unsupported_claims_rejected,
        evidence_refs=summary_refs,
    )


def validate_meeting_summary_payload(payload: Mapping[str, Any]) -> MeetingSummaryResult:
    """Validate a future provider/mock JSON payload without calling a provider."""

    return MeetingSummaryResult.model_validate(dict(payload))


def _marker_lines(transcript_text: str) -> list[tuple[str, str, str, int]]:
    lines: list[tuple[str, str, str, int]] = []
    for index, line in enumerate(transcript_text.splitlines(), start=1):
        cleaned = " ".join(line.strip().split())
        if not cleaned:
            continue
        match = _MARKER_RE.match(cleaned)
        if match is None:
            continue
        body = match.group("body").strip()
        if not body:
            continue
        lines.append((match.group("marker").casefold(), body, cleaned, index))
    return lines


def _evidence_ref(
    input: MeetingTranscriptInput,
    line: str,
    *,
    line_number: int,
    marker: str,
) -> MeetingEvidenceRef:
    return MeetingEvidenceRef(
        source_document_id=input.source_document_id,
        chunk_id=input.chunk_id,
        raw_object_ref=input.raw_object_ref,
        source_url=input.source_url,
        quote=_truncate_quote(line),
        line_number=line_number,
        marker=marker,
    )


def _decision_from_line(body: str, evidence: MeetingEvidenceRef) -> MeetingDecision:
    title = _content_without_metadata(body)
    return MeetingDecision(
        title=title,
        decision=title,
        owner=_metadata_value(body, "owner"),
        confidence=0.70,
        evidence_refs=[evidence],
    )


def _action_from_line(body: str, evidence: MeetingEvidenceRef) -> MeetingActionItem:
    return MeetingActionItem(
        title=_content_without_metadata(body),
        owner=_metadata_value(body, "owner"),
        due_date=_metadata_value(body, "due", "due_date", "deadline"),
        confidence=0.70,
        evidence_refs=[evidence],
    )


def _risk_from_line(body: str, evidence: MeetingEvidenceRef) -> MeetingRisk:
    return MeetingRisk(
        title=_content_without_metadata(body),
        severity=_severity(body),
        mitigation=_metadata_value(body, "mitigation"),
        confidence=0.65,
        evidence_refs=[evidence],
    )


def _question_from_line(body: str, evidence: MeetingEvidenceRef) -> MeetingOpenQuestion:
    question = _content_without_metadata(body)
    if not question.endswith("?"):
        question = f"{question}?"
    return MeetingOpenQuestion(
        question=question,
        owner=_metadata_value(body, "owner"),
        confidence=0.65,
        evidence_refs=[evidence],
    )


def _jira_from_action(action: MeetingActionItem, *, source_refs: list[str]) -> JiraDraftTicket:
    return JiraDraftTicket(
        title=action.title,
        description=action.title,
        issue_type="Task",
        project_key=None,
        priority="medium",
        labels=[],
        acceptance_criteria=[f"Complete: {action.title}"],
        source_refs=source_refs,
        evidence_refs=action.evidence_refs,
    )


def _jira_from_line(
    body: str,
    evidence: MeetingEvidenceRef,
    *,
    source_refs: list[str],
) -> JiraDraftTicket:
    title = _content_without_metadata(body)
    return JiraDraftTicket(
        title=title,
        description=title,
        issue_type=_issue_type(body),
        project_key=_metadata_value(body, "project_key", "jira_project_key"),
        priority=_priority(body),
        labels=_metadata_list(body, "labels"),
        acceptance_criteria=_acceptance_criteria(body, fallback_title=title),
        source_refs=source_refs,
        evidence_refs=[evidence],
    )


def _kb_from_line(
    body: str,
    evidence: MeetingEvidenceRef,
    *,
    source_refs: list[str],
) -> KBUpdateDraft:
    title = _content_without_metadata(body)
    note_type = _note_type(body, fallback="engineering_note")
    suggested_path = _metadata_value(body, "path", "suggested_path") or _kb_path(
        note_type=note_type,
        title=title,
    )
    return KBUpdateDraft(
        title=title,
        note_type=note_type,
        suggested_path=suggested_path,
        summary=title,
        source_refs=source_refs,
        evidence_refs=[evidence],
    )


def _meeting_note_draft(
    input: MeetingTranscriptInput,
    *,
    summary: str,
    evidence_refs: list[MeetingEvidenceRef],
) -> KBUpdateDraft:
    title = _clean_string(input.title) or "Meeting notes"
    return KBUpdateDraft(
        title=title,
        note_type="meeting_note",
        suggested_path=_kb_path(note_type="meeting_note", title=title),
        summary=summary,
        source_refs=_source_refs(input),
        evidence_refs=evidence_refs,
    )


def _decision_log_draft(
    decision: MeetingDecision,
    *,
    source_refs: list[str],
) -> KBUpdateDraft:
    return KBUpdateDraft(
        title=decision.title,
        note_type="decision_log",
        suggested_path=_kb_path(note_type="decision_log", title=decision.title),
        summary=decision.decision,
        source_refs=source_refs,
        evidence_refs=decision.evidence_refs,
    )


def _summary_text(input: MeetingTranscriptInput, *, summary_lines: list[str]) -> str:
    if summary_lines:
        return _truncate_text(" ".join(summary_lines), max_chars=1000)
    if input.title:
        return f"Meeting draft for {input.title}."
    return "Meeting draft summary unavailable; no explicit Summary marker was provided."


def _result_evidence_refs(
    *,
    decisions: list[MeetingDecision],
    action_items: list[MeetingActionItem],
    risks: list[MeetingRisk],
    open_questions: list[MeetingOpenQuestion],
    jira_draft_tickets: list[JiraDraftTicket],
    explicit_refs: list[MeetingEvidenceRef],
) -> list[MeetingEvidenceRef]:
    refs: list[MeetingEvidenceRef] = [*explicit_refs]
    for group in (decisions, action_items, risks, open_questions, jira_draft_tickets):
        for item in group:
            refs.extend(item.evidence_refs)
    return _unique_evidence_refs(refs)


def _source_refs(input: MeetingTranscriptInput) -> list[str]:
    return _unique_strings(
        [
            input.source_document_id,
            input.chunk_id,
            input.raw_object_ref,
            input.source_url,
            *input.related_jira_keys,
            *input.related_prs,
            *input.related_files,
        ]
    )


def _content_without_metadata(value: str) -> str:
    content = _clean_string(value) or ""
    content = re.sub(
        r"(?:^|[;,\?])\s*"
        r"(owner|due|due_date|deadline|severity|mitigation|project_key|jira_project_key|"
        r"priority|labels|type|issue_type|acceptance|path|suggested_path|note_type)"
        r"\s*(?:=|:)\s*[^;,\?]+",
        "",
        content,
        flags=re.IGNORECASE,
    )
    content = re.sub(r"\s+", " ", content).strip(" ;,")
    return content or (_clean_string(value) or "Untitled draft")


def _metadata_value(value: str, *keys: str) -> str | None:
    for key in keys:
        pattern = _METADATA_RE_TEMPLATE.format(key=re.escape(key))
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match is not None:
            return _clean_string(match.group(1))
    return None


def _metadata_list(value: str, key: str) -> list[str]:
    raw_value = _metadata_value(value, key)
    if raw_value is None:
        return []
    return _unique_strings(part.strip() for part in re.split(r"[|/]", raw_value))


def _acceptance_criteria(value: str, *, fallback_title: str) -> list[str]:
    criteria = _metadata_list(value, "acceptance")
    if criteria:
        return criteria
    return [f"Draft reviewed by a human approver for: {fallback_title}"]


def _priority(value: str) -> DraftPriority:
    parsed = (_metadata_value(value, "priority") or "").casefold()
    if parsed in {"low", "medium", "high"}:
        return parsed  # type: ignore[return-value]
    return "medium"


def _severity(value: str) -> RiskSeverity:
    parsed = (_metadata_value(value, "severity") or "").casefold()
    if parsed in {"low", "medium", "high"}:
        return parsed  # type: ignore[return-value]
    if parsed == "critical":
        return "high"
    return "medium"


def _issue_type(value: str) -> IssueType:
    parsed = (_metadata_value(value, "type", "issue_type") or "").casefold()
    if parsed == "story":
        return "Story"
    if parsed == "bug":
        return "Bug"
    if parsed == "risk":
        return "Risk"
    return "Task"


def _note_type(value: str, *, fallback: KBNoteType) -> KBNoteType:
    parsed = (_metadata_value(value, "note_type", "type") or "").casefold()
    if parsed in {"meeting_note", "decision_log", "engineering_note", "product_note"}:
        return parsed  # type: ignore[return-value]
    return fallback


def _kb_path(*, note_type: KBNoteType, title: str) -> str:
    directory = {
        "meeting_note": "03-meetings",
        "decision_log": "04-decisions",
        "engineering_note": "05-knowledge",
        "product_note": "05-knowledge",
    }[note_type]
    return f"{directory}/{_slug(title)}.md"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.casefold()).strip("-")
    return cleaned[:80].strip("-") or "meeting-draft"


def _truncate_quote(value: str) -> str:
    return _truncate_text(value, max_chars=MAX_EVIDENCE_QUOTE_CHARS)


def _truncate_text(value: str, *, max_chars: int) -> str:
    cleaned = " ".join(value.strip().split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip()


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _unique_strings(values: Any) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_string(value)
        if cleaned is None or cleaned in seen:
            continue
        unique.append(cleaned)
        seen.add(cleaned)
    return unique


def _unique_evidence_refs(values: list[MeetingEvidenceRef]) -> list[MeetingEvidenceRef]:
    unique: list[MeetingEvidenceRef] = []
    seen: set[tuple[str, str, str, int | None, str | None]] = set()
    for ref in values:
        key = (
            ref.source_document_id,
            ref.chunk_id,
            ref.quote,
            ref.line_number,
            ref.marker,
        )
        if key in seen:
            continue
        unique.append(ref)
        seen.add(key)
    return unique
