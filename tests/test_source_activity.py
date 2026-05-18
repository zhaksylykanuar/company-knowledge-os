from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.attention_triage import (
    AttentionContext,
    AttentionTriageAgent,
    MockAttentionTriageProvider,
    NormalizedActivityItem,
)
from app.services.source_activity import (
    DriveDocumentActivityInput,
    GitHubPullRequestActivityInput,
    JiraIssueActivityInput,
    SourceActivityMappingError,
    drive_document_event_to_activity_item,
    github_pr_event_to_activity_item,
    jira_issue_event_to_activity_item,
    source_event_to_activity_item,
)


NOW = datetime(2026, 5, 15, 9, 30, tzinfo=timezone.utc)


def _triage_result(
    *,
    confidence: float,
    show_in_digest: bool,
    attention_class: str = "no_action_required",
    priority: str = "low",
) -> dict:
    return {
        "attention_class": attention_class,
        "priority": priority,
        "show_in_digest": show_in_digest,
        "confidence": confidence,
        "reason": "mock source activity triage",
        "recommended_action": "no action required",
        "owner": None,
        "deadline": None,
        "evidence": [{"kind": "source_activity", "source_object_id": "fake"}],
    }


def test_github_pr_review_requested_maps_to_activity_item() -> None:
    activity = github_pr_event_to_activity_item(
        GitHubPullRequestActivityInput(
            source_object_id="qaztwin/company-knowledge-os/pull/101",
            event_type="github.pull_request.synchronized",
            title="Normalize QAZ-47 source events",
            summary="Safe pull request summary.",
            source_url="https://github.example.test/qaztwin/company-knowledge-os/pull/101",
            actor="fake-author",
            repository_full_name="qaztwin/company-knowledge-os",
            pull_request_number=101,
            requested_reviewers=("fake-reviewer",),
            requested_teams=("platform",),
            created_at=NOW,
            source_event_id="sevt_github_101",
            raw_payload_ref="raw://github/events/101.json",
        )
    )

    assert isinstance(activity, NormalizedActivityItem)
    assert activity.source == "github"
    assert activity.activity_type == "pull_request.review_requested"
    assert activity.source_object_id == "qaztwin/company-knowledge-os/pull/101"
    assert activity.created_at == NOW
    assert activity.related_prs == [
        "https://github.example.test/qaztwin/company-knowledge-os/pull/101",
        "qaztwin/company-knowledge-os#101",
    ]
    assert activity.related_people == ["fake-author", "fake-reviewer", "team:platform"]
    assert activity.related_jira_keys == ["QAZ-47"]
    assert activity.evidence_refs == [
        {
            "kind": "source_activity",
            "source": "github",
            "source_object_id": "qaztwin/company-knowledge-os/pull/101",
            "event_type": "github.pull_request.synchronized",
            "source_event_id": "sevt_github_101",
            "raw_payload_ref": "raw://github/events/101.json",
            "source_url": "https://github.example.test/qaztwin/company-knowledge-os/pull/101",
        }
    ]


def test_github_unrelated_pr_maps_without_assigning_relevance() -> None:
    activity = github_pr_event_to_activity_item(
        {
            "source_object_id": "other/repo/pull/8",
            "event_type": "github.pull_request.opened",
            "title": "Unrelated cleanup",
            "summary": "Safe low relevance PR summary.",
            "source_url": "https://github.example.test/other/repo/pull/8",
            "actor": "fake-author",
            "repository_full_name": "other/repo",
            "pull_request_number": 8,
            "created_at": NOW,
        }
    )

    assert activity.source == "github"
    assert activity.activity_type == "pull_request.updated"
    assert activity.related_people == ["fake-author"]
    assert activity.project == "other/repo"
    assert not hasattr(activity, "owner")
    assert not hasattr(activity, "relevance")


def test_jira_assigned_issue_maps_to_activity_item() -> None:
    activity = jira_issue_event_to_activity_item(
        JiraIssueActivityInput(
            source_object_id="QAZ-204",
            event_type="jira.issue.updated",
            title="QAZ-204 Finish source normalization",
            summary="Safe Jira issue summary.",
            source_url="https://jira.example.test/browse/QAZ-204",
            actor="fake-reporter",
            issue_key="QAZ-204",
            assignee="fake-user",
            project_key="QAZ",
            created_at=NOW,
        )
    )

    assert activity.source == "jira"
    assert activity.activity_type == "issue.assigned"
    assert activity.related_jira_keys == ["QAZ-204"]
    assert activity.related_people == ["fake-reporter", "fake-user"]
    assert activity.project == "QAZ"


def test_jira_blocked_issue_maps_blocker_summary() -> None:
    activity = jira_issue_event_to_activity_item(
        {
            "source_object_id": "QAZ-205",
            "event_type": "jira.issue.status_changed",
            "title": "QAZ-205 Release checklist blocked",
            "summary": "Safe Jira status update.",
            "source_url": "https://jira.example.test/browse/QAZ-205",
            "actor": "fake-manager",
            "issue_key": "QAZ-205",
            "status": "Blocked",
            "blocked": True,
            "blocked_reason": "Waiting for fake approval.",
            "created_at": NOW,
        }
    )

    assert activity.activity_type == "issue.blocked"
    assert activity.related_jira_keys == ["QAZ-205"]
    assert activity.safe_summary == "Safe Jira status update. Blocker: Waiting for fake approval."


def test_jira_unrelated_update_maps_safely() -> None:
    activity = jira_issue_event_to_activity_item(
        {
            "source_object_id": "OPS-99",
            "event_type": "jira.issue.commented",
            "title": "OPS-99 Low relevance update",
            "summary": "Safe comment summary.",
            "source_url": "https://jira.example.test/browse/OPS-99",
            "actor": "fake-commenter",
            "created_at": NOW,
        }
    )

    assert activity.source == "jira"
    assert activity.activity_type == "issue.updated"
    assert activity.related_jira_keys == ["OPS-99"]
    assert activity.related_people == ["fake-commenter"]


def test_drive_active_project_document_changed_maps_to_activity_item() -> None:
    activity = drive_document_event_to_activity_item(
        DriveDocumentActivityInput(
            source_object_id="drive:file:doc-123",
            event_type="drive.file.updated",
            title="QazTwin Launch Plan",
            summary="Safe document change summary.",
            source_url="https://drive.example.test/file/doc-123",
            actor="fake-editor",
            source_document_id="doc-123",
            modified_at=NOW,
            project="QazTwin Launch",
            topics=("launch", "planning"),
            source_event_id="sevt_drive_123",
        )
    )

    assert activity.source == "drive"
    assert activity.activity_type == "document.changed"
    assert activity.related_files == ["https://drive.example.test/file/doc-123", "doc-123"]
    assert activity.related_people == ["fake-editor"]
    assert activity.project == "QazTwin Launch"
    assert activity.evidence_refs[0]["source_event_id"] == "sevt_drive_123"
    assert activity.evidence_refs[0]["topics"] == ["launch", "planning"]


def test_source_event_read_model_like_input_dispatches_to_mapper() -> None:
    class ReadModelLike:
        source_event_id = "sevt_dispatch"
        source_system = "github"
        source_object_type = "pull_request"
        source_object_id = "qaztwin/company-knowledge-os/pull/102"
        event_type = "github.pull_request.opened"
        event_time = NOW
        title = "Dispatch source event"
        summary = "Safe dispatch summary."
        source_url = "https://github.example.test/qaztwin/company-knowledge-os/pull/102"
        raw_object_ref = "raw://github/events/102.json"
        payload_subset = {"actor_external_id": "fake-author"}

    activity = source_event_to_activity_item(ReadModelLike())

    assert activity.source == "github"
    assert activity.source_object_id == "qaztwin/company-knowledge-os/pull/102"
    assert activity.actor == "fake-author"
    assert activity.evidence_refs[0]["raw_payload_ref"] == "raw://github/events/102.json"


def test_all_mapped_items_validate_as_normalized_activity_items() -> None:
    items = [
        github_pr_event_to_activity_item(
            {
                "source_object_id": "org/repo/pull/1",
                "event_type": "github.pull_request.opened",
                "title": "Safe PR title",
            }
        ),
        jira_issue_event_to_activity_item(
            {
                "source_object_id": "QAZ-1",
                "event_type": "jira.issue.updated",
                "title": "QAZ-1 Safe issue title",
            }
        ),
        drive_document_event_to_activity_item(
            {
                "source_object_id": "drive:file:1",
                "event_type": "drive.file.updated",
                "name": "Safe document title",
            }
        ),
    ]

    assert all(isinstance(item, NormalizedActivityItem) for item in items)


def test_ambiguous_low_confidence_item_is_visible_review_optional() -> None:
    activity = drive_document_event_to_activity_item(
        {
            "source_object_id": "drive:file:ambiguous",
            "event_type": "drive.file.updated",
            "title": "Ambiguous project note",
            "summary": "Safe ambiguous update.",
        }
    )
    provider = MockAttentionTriageProvider(
        [
            _triage_result(
                confidence=0.30,
                show_in_digest=False,
            )
        ]
    )
    result = AttentionTriageAgent(provider).classify_activity(activity, AttentionContext())

    assert result.attention_class == "review_optional"
    assert result.show_in_digest is True
    assert result.priority == "low"
    assert provider.calls[0][0] == activity


def test_raw_private_payload_text_is_not_copied_to_safe_fields() -> None:
    activity = github_pr_event_to_activity_item(
        {
            "source_object_id": "org/repo/pull/44",
            "event_type": "github.pull_request.opened",
            "title": "Safe title",
            "summary": "Safe summary.",
            "source_url": "https://github.example.test/org/repo/pull/44",
            "raw_body": "PRIVATE_BODY_DO_NOT_COPY",
            "provider_payload": {"body": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_COPY"},
            "payload": {"body": "PRIVATE_NESTED_BODY_DO_NOT_COPY"},
        }
    )

    dumped = activity.model_dump_json()
    assert activity.safe_summary == "Safe summary."
    assert "PRIVATE_BODY_DO_NOT_COPY" not in dumped
    assert "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_COPY" not in dumped
    assert "PRIVATE_NESTED_BODY_DO_NOT_COPY" not in dumped


def test_missing_source_object_id_is_rejected() -> None:
    with pytest.raises(SourceActivityMappingError, match="source_object_id is required"):
        github_pr_event_to_activity_item(
            {
                "source_object_id": " ",
                "event_type": "github.pull_request.opened",
                "title": "Safe title",
            }
        )
