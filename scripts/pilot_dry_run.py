#!/usr/bin/env python
"""Run a provider-free manual pilot readiness dry run with synthetic data only."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, get_args

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.attention_triage import (  # noqa: E402
    AttentionContext,
    AttentionTriageFeedback,
    AttentionTriageResult,
    DigestSection,
    apply_attention_confidence_policy,
)
from app.services.meeting_artifacts import (  # noqa: E402
    MeetingTranscriptInput,
    process_meeting_transcript,
)
from app.services.source_activity import (  # noqa: E402
    DriveDocumentActivityInput,
    GitHubPullRequestActivityInput,
    JiraIssueActivityInput,
    drive_document_event_to_activity_item,
    github_pr_event_to_activity_item,
    jira_issue_event_to_activity_item,
)

SAMPLE_TIME = datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc)


def build_report() -> dict[str, Any]:
    return {
        "attention_policy_sample": _attention_policy_sample(),
        "digest_sections_sample": _digest_sections_sample(),
        "source_normalization_sample": _source_normalization_sample(),
        "meeting_draft_sample": _meeting_draft_sample(),
        "feedback_context_shape_sample": _feedback_context_shape_sample(),
        "deferred_boundaries": _deferred_boundaries(),
        "safety": _safety(),
    }


def _attention_policy_sample() -> list[dict[str, Any]]:
    samples = [
        (
            "high_confidence_visible",
            AttentionTriageResult(
                attention_class="requires_my_attention",
                priority="high",
                show_in_digest=True,
                confidence=0.92,
                reason="synthetic direct owner request",
                recommended_action="reply to the synthetic pilot request",
                owner="me",
                deadline="2026-05-19",
                evidence=[_source_evidence("synthetic-attention-high")],
            ),
        ),
        (
            "medium_confidence_hidden",
            AttentionTriageResult(
                attention_class="no_action_required",
                priority="low",
                show_in_digest=False,
                confidence=0.62,
                reason="synthetic medium confidence hidden provider output",
                recommended_action="review if relevant",
                owner=None,
                deadline=None,
                evidence=[_source_evidence("synthetic-attention-medium")],
            ),
        ),
        (
            "low_confidence_hidden",
            AttentionTriageResult(
                attention_class="no_action_required",
                priority="low",
                show_in_digest=False,
                confidence=0.30,
                reason="synthetic low confidence hidden provider output",
                recommended_action="no action required",
                owner=None,
                deadline=None,
                evidence=[_source_evidence("synthetic-attention-low")],
            ),
        ),
    ]

    return [
        {
            "case": name,
            "input": {
                "attention_class": result.attention_class,
                "priority": result.priority,
                "show_in_digest": result.show_in_digest,
                "confidence": result.confidence,
            },
            "after_policy": _model_dump_jsonable(apply_attention_confidence_policy(result)),
        }
        for name, result in samples
    ]


def _digest_sections_sample() -> dict[str, Any]:
    section_order = list(get_args(DigestSection))
    sections: dict[str, Any] = {
        "Work actions requiring my attention": [
            _digest_item("synthetic-digest-reply", "Reply to synthetic customer question"),
        ],
        "Manual actions": [
            _digest_item("synthetic-digest-manual", "Complete synthetic approval checklist"),
        ],
        "Waiting for external reply": [
            _digest_item("synthetic-digest-waiting", "Wait for synthetic partner response"),
        ],
        "Important project updates": [
            _digest_item("synthetic-digest-update", "Synthetic launch plan changed"),
        ],
        "Review optional": [
            _digest_item("synthetic-digest-review", "Review optional synthetic context"),
        ],
        "Hidden low-priority summary": {
            "count": 2,
            "by_attention_class": {"no_action_required": 2},
            "details_included": False,
        },
    }
    return {
        "section_order": section_order,
        "sections": sections,
        "hidden_summary_counts_only": True,
    }


def _source_normalization_sample() -> dict[str, Any]:
    github = github_pr_event_to_activity_item(
        GitHubPullRequestActivityInput(
            source_object_id="synthetic/repo/pull/49",
            event_type="github.pull_request.review_requested",
            title="FOS-049A synthetic pilot readiness PR",
            summary="Safe synthetic PR summary.",
            source_url="https://example.test/synthetic/repo/pull/49",
            actor="synthetic-author",
            repository_full_name="synthetic/repo",
            pull_request_number=49,
            requested_reviewers=("synthetic-reviewer",),
            requested_teams=("pilot",),
            created_at=SAMPLE_TIME,
            source_event_id="synthetic-github-event-49",
            raw_payload_ref="raw://synthetic/github/pr-49.json",
        )
    )
    jira = jira_issue_event_to_activity_item(
        JiraIssueActivityInput(
            source_object_id="PILOT-49",
            event_type="jira.issue.status_changed",
            title="PILOT-49 Synthetic blocked launch checklist",
            summary="Safe synthetic Jira summary.",
            source_url="https://example.test/jira/browse/PILOT-49",
            actor="synthetic-reporter",
            issue_key="PILOT-49",
            assignee="synthetic-owner",
            project_key="PILOT",
            status="Blocked",
            blocked=True,
            blocked_reason="Waiting for synthetic approval.",
            created_at=SAMPLE_TIME,
            source_event_id="synthetic-jira-event-49",
            raw_payload_ref="raw://synthetic/jira/pilot-49.json",
        )
    )
    drive = drive_document_event_to_activity_item(
        DriveDocumentActivityInput(
            source_object_id="drive:file:synthetic-pilot-doc",
            event_type="drive.file.updated",
            title="Synthetic Pilot Runbook",
            summary="Safe synthetic document change summary.",
            source_url="https://example.test/drive/synthetic-pilot-doc",
            actor="synthetic-editor",
            source_document_id="synthetic-pilot-doc",
            modified_at=SAMPLE_TIME,
            project="Synthetic Pilot",
            topics=("pilot", "readiness"),
            source_event_id="synthetic-drive-event-49",
            raw_payload_ref="raw://synthetic/drive/pilot-doc.json",
        )
    )

    return {
        "github": _model_dump_jsonable(github),
        "jira": _model_dump_jsonable(jira),
        "drive": _model_dump_jsonable(drive),
    }


def _meeting_draft_sample() -> dict[str, Any]:
    result = process_meeting_transcript(
        MeetingTranscriptInput(
            source_document_id="synthetic-meeting-doc",
            chunk_id="synthetic-meeting-doc-chunk-1",
            raw_object_ref="raw://synthetic/meeting/fos-049a.txt",
            transcript_text=(
                "Summary: Team reviewed the synthetic pilot dry-run boundary.\n"
                "Decision: Keep pilot readiness output draft-only; owner: synthetic-founder\n"
                "Action: Prepare the manual pilot checklist; owner: synthetic-operator; due: 2026-05-19\n"
                "Risk: Operators could mistake dry-run drafts for executed work; severity: medium; mitigation: keep status draft\n"
                "Question: Who signs off before any real Jira or KB write? owner: synthetic-founder\n"
                "KB: Document pilot dry-run behavior; note_type: engineering_note; path: 05-knowledge/pilot-dry-run.md\n"
            ),
            title="FOS-049A synthetic pilot dry run",
            participants=["synthetic-founder", "synthetic-operator"],
            project="Synthetic Pilot",
            source_url="https://example.test/meetings/synthetic-fos-049a",
            related_jira_keys=["PILOT-49"],
        )
    )

    return {
        "summary": result.summary,
        "decisions_count": len(result.decisions),
        "action_items_count": len(result.action_items),
        "risks_count": len(result.risks),
        "open_questions_count": len(result.open_questions),
        "jira_draft_count": len(result.jira_draft_tickets),
        "kb_draft_count": len(result.knowledge_base_updates),
        "evidence_refs_count": _meeting_evidence_count(result),
        "all_statuses": sorted(
            {
                *(item.status for item in result.action_items),
                *(item.status for item in result.jira_draft_tickets),
                *(item.status for item in result.knowledge_base_updates),
            }
        ),
        "jira_and_kb_are_draft_only": True,
    }


def _feedback_context_shape_sample() -> dict[str, Any]:
    feedback = AttentionTriageFeedback(
        feedback_id="synthetic-feedback-049a",
        source_object_id="synthetic/repo/pull/49",
        triage_result_id=None,
        user_action="marked_important",
        created_at=SAMPLE_TIME,
    )
    context = AttentionContext(recent_feedback=[feedback])
    return {
        "synthetic": True,
        "persisted": False,
        "suitable_for_attention_context": True,
        "recent_feedback_count": len(context.recent_feedback),
        "recent_feedback": [_model_dump_jsonable(feedback)],
    }


def _deferred_boundaries() -> list[str]:
    return [
        "live API connectors/webhooks",
        "scheduled digest",
        "Telegram/Slack delivery",
        "feedback buttons/actions",
        "feedback-aware live triage wiring",
        "AttentionTriageResult persistence",
        "normalized_activity_items persistence",
        "human approval/action execution",
        "Jira creation after approval",
        "KB/Obsidian writes after approval",
        "PR review agent",
    ]


def _safety() -> dict[str, bool]:
    return {
        "provider_free": True,
        "external_api_calls": False,
        "db_writes": False,
        "ingestion": False,
        "migrations": False,
        "jira_writes": False,
        "kb_obsidian_writes": False,
        "uses_synthetic_data_only": True,
    }


def _meeting_evidence_count(result: Any) -> int:
    refs = list(result.evidence_refs)
    for group in (
        result.decisions,
        result.action_items,
        result.risks,
        result.open_questions,
        result.jira_draft_tickets,
        result.knowledge_base_updates,
    ):
        for item in group:
            refs.extend(item.evidence_refs)
    return len(refs)


def _digest_item(source_object_id: str, title: str) -> dict[str, str]:
    return {
        "source": "synthetic",
        "source_object_id": source_object_id,
        "title": title,
    }


def _source_evidence(source_object_id: str) -> dict[str, str]:
    return {
        "kind": "source_activity",
        "source": "synthetic",
        "source_object_id": source_object_id,
    }


def _model_dump_jsonable(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json")


def _render_text(report: dict[str, Any]) -> str:
    digest_sections = report["digest_sections_sample"]["section_order"]
    source_sample = report["source_normalization_sample"]
    meeting_sample = report["meeting_draft_sample"]
    safety = report["safety"]

    lines = [
        "FOS-049A Manual Pilot Dry Run",
        "",
        "attention_policy_sample:",
        f"- cases: {len(report['attention_policy_sample'])}",
        "",
        "digest_sections_sample:",
        *[f"- {section}" for section in digest_sections],
        "",
        "source_normalization_sample:",
        f"- github: {source_sample['github']['source_object_id']}",
        f"- jira: {source_sample['jira']['source_object_id']}",
        f"- drive: {source_sample['drive']['source_object_id']}",
        "",
        "meeting_draft_sample:",
        f"- summary: {meeting_sample['summary']}",
        f"- jira_draft_count: {meeting_sample['jira_draft_count']}",
        f"- kb_draft_count: {meeting_sample['kb_draft_count']}",
        "",
        "feedback_context_shape_sample:",
        f"- recent_feedback_count: {report['feedback_context_shape_sample']['recent_feedback_count']}",
        f"- persisted: {report['feedback_context_shape_sample']['persisted']}",
        "",
        "deferred_boundaries:",
        *[f"- {boundary}" for boundary in report["deferred_boundaries"]],
        "",
        "safety:",
        *[f"- {key}: {str(value).lower()}" for key, value in safety.items()],
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args(argv)

    report = build_report()
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
