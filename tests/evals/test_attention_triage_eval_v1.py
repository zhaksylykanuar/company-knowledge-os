from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from app.services.attention_triage import (
    AttentionContext,
    AttentionTriageAgent,
    AttentionTriageResult,
    MockAttentionTriageProvider,
    NormalizedActivityItem,
)


NOW = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class AttentionTriageEvalCase:
    case_id: str
    source: str
    activity_type: str
    title: str
    safe_summary: str
    provider_output: dict[str, Any] | str | None
    expected_attention_class: str
    expected_priority: str
    expected_show_in_digest: bool


def _context() -> AttentionContext:
    return AttentionContext(
        user_name="Eval Operator",
        company_name="Eval Company",
        user_role="founder",
        important_projects=["Product Alpha", "Client Delivery", "Infrastructure"],
        known_clients=["Client A", "Client B", "Partner C"],
        known_people=["Reviewer One", "External Sponsor"],
        active_jira_projects=["OPS", "CORE"],
        active_github_repos=["target-org/service-a", "target-org/frontend"],
        instructions="If uncertain, do not hide.",
    )


def _activity(case: AttentionTriageEvalCase) -> NormalizedActivityItem:
    return NormalizedActivityItem(
        source=case.source,
        source_object_id=f"eval:{case.case_id}",
        activity_type=case.activity_type,
        title=case.title,
        actor="me" if case.activity_type.endswith(".from_me") else "external",
        created_at=NOW,
        project="Product Alpha",
        safe_summary=case.safe_summary,
        related_people=["eval-user", "eval-counterparty"],
        related_jira_keys=["OPS-1"] if case.source == "jira" else [],
        related_prs=["pr-1"] if case.source == "github" else [],
        related_files=["file-1"] if case.source == "google_drive" else [],
        evidence_refs=[
            {
                "kind": "eval_source_activity",
                "source": case.source,
                "source_object_id": f"eval:{case.case_id}",
            }
        ],
    )


def _result(
    attention_class: str,
    priority: str,
    *,
    show_in_digest: bool = True,
    confidence: float = 0.90,
    owner: str | None = "unknown",
    recommended_action: str | None = None,
) -> dict[str, Any]:
    action_by_class = {
        "requires_my_attention": "reply or decide",
        "manual_action": "complete the manual action",
        "waiting_on_external": "wait for an external response",
        "important_info": "review the update",
        "review_optional": "review if relevant",
        "no_action_required": "no action required",
    }
    return {
        "attention_class": attention_class,
        "priority": priority,
        "show_in_digest": show_in_digest,
        "confidence": confidence,
        "reason": "eval expected classification",
        "recommended_action": recommended_action or action_by_class[attention_class],
        "owner": owner,
        "deadline": None,
        "evidence": [{"kind": "eval_source_activity", "source_object_id": "eval"}],
    }


GOLDEN_CASES: tuple[AttentionTriageEvalCase, ...] = (
    AttentionTriageEvalCase(
        "client_email_direct_question",
        "gmail",
        "email_thread.from_external",
        "Client asks for decision",
        "Client asks which delivery option to approve today.",
        _result("requires_my_attention", "high", owner="me", recommended_action="reply to the client"),
        "requires_my_attention",
        "high",
        True,
    ),
    AttentionTriageEvalCase(
        "client_email_contract_deadline",
        "gmail",
        "email_thread.from_external",
        "Contract deadline",
        "Client asks for contract confirmation before close of business.",
        _result("requires_my_attention", "high", owner="me", recommended_action="confirm contract decision"),
        "requires_my_attention",
        "high",
        True,
    ),
    AttentionTriageEvalCase(
        "client_email_support_escalation",
        "gmail",
        "email_thread.from_external",
        "Support escalation",
        "Customer reports a blocker affecting an active rollout.",
        _result("requires_my_attention", "high", owner="me", recommended_action="reply with escalation plan"),
        "requires_my_attention",
        "high",
        True,
    ),
    AttentionTriageEvalCase(
        "partner_email_waiting_on_them",
        "gmail",
        "email_thread.from_me",
        "Waiting on partner",
        "Last message was sent by the operator and needs partner response.",
        _result("waiting_on_external", "medium", owner="external"),
        "waiting_on_external",
        "medium",
        True,
    ),
    AttentionTriageEvalCase(
        "vendor_invoice_manual_action",
        "gmail",
        "email_thread.from_external",
        "Vendor invoice approval",
        "Vendor asks the operator to approve payment details.",
        _result("manual_action", "medium", owner="me", recommended_action="approve or reject the invoice"),
        "manual_action",
        "medium",
        True,
    ),
    AttentionTriageEvalCase(
        "meeting_follow_up_owner_me",
        "gmail",
        "email_thread.from_external",
        "Meeting follow-up",
        "Partner assigned the operator a follow-up action from the meeting.",
        _result("manual_action", "medium", owner="me"),
        "manual_action",
        "medium",
        True,
    ),
    AttentionTriageEvalCase(
        "marketing_promo_email",
        "gmail",
        "email_thread.from_external",
        "Marketing promotion",
        "Promotional announcement unrelated to active work.",
        _result("no_action_required", "low", show_in_digest=False, confidence=0.95, owner=None),
        "no_action_required",
        "low",
        False,
    ),
    AttentionTriageEvalCase(
        "newsletter_roundup",
        "gmail",
        "email_thread.from_external",
        "Newsletter roundup",
        "Industry newsletter with optional reading links.",
        _result("no_action_required", "low", show_in_digest=False, confidence=0.92, owner=None),
        "no_action_required",
        "low",
        False,
    ),
    AttentionTriageEvalCase(
        "webinar_invitation",
        "gmail",
        "email_thread.from_external",
        "Webinar invite",
        "Mass event invite with no operator action required.",
        _result("no_action_required", "low", show_in_digest=False, confidence=0.91, owner=None),
        "no_action_required",
        "low",
        False,
    ),
    AttentionTriageEvalCase(
        "social_network_digest",
        "other",
        "notification.system",
        "Social digest",
        "Social network digest unrelated to work delivery.",
        _result("no_action_required", "low", show_in_digest=False, confidence=0.94, owner=None),
        "no_action_required",
        "low",
        False,
    ),
    AttentionTriageEvalCase(
        "calendar_auto_decline_notice",
        "calendar",
        "event.system",
        "Calendar auto update",
        "Automated calendar update with no decision required.",
        _result("no_action_required", "low", show_in_digest=False, confidence=0.88, owner=None),
        "no_action_required",
        "low",
        False,
    ),
    AttentionTriageEvalCase(
        "ci_success_noise",
        "github",
        "check_run.system",
        "CI success",
        "Automated success notification for a routine check.",
        _result("no_action_required", "low", show_in_digest=False, confidence=0.90, owner=None),
        "no_action_required",
        "low",
        False,
    ),
    AttentionTriageEvalCase(
        "pr_review_requested_for_me",
        "github",
        "pull_request.from_external",
        "Review requested",
        "Pull request explicitly requests the operator's review.",
        _result("requires_my_attention", "high", owner="me", recommended_action="review the pull request"),
        "requires_my_attention",
        "high",
        True,
    ),
    AttentionTriageEvalCase(
        "pr_changes_requested_from_me",
        "github",
        "pull_request.from_external",
        "Changes requested",
        "Reviewer requested changes from the operator.",
        _result("requires_my_attention", "high", owner="me", recommended_action="address requested changes"),
        "requires_my_attention",
        "high",
        True,
    ),
    AttentionTriageEvalCase(
        "pr_assigned_ci_failed",
        "github",
        "pull_request.system",
        "Assigned PR failing",
        "Assigned pull request has a failing required check.",
        _result("manual_action", "high", owner="me", recommended_action="fix the failing check"),
        "manual_action",
        "high",
        True,
    ),
    AttentionTriageEvalCase(
        "pr_unrelated_project_update",
        "github",
        "pull_request.from_external",
        "Unrelated PR update",
        "Pull request update is in an active repo but not assigned to the operator.",
        _result("important_info", "low", owner="team"),
        "important_info",
        "low",
        True,
    ),
    AttentionTriageEvalCase(
        "release_tag_created",
        "github",
        "release.system",
        "Release created",
        "Release was created for an active service.",
        _result("important_info", "medium", owner="team"),
        "important_info",
        "medium",
        True,
    ),
    AttentionTriageEvalCase(
        "jira_assigned_blocker",
        "jira",
        "issue.from_external",
        "Assigned blocker",
        "Assigned issue is blocked and needs operator decision.",
        _result("manual_action", "high", owner="me", recommended_action="unblock the assigned issue"),
        "manual_action",
        "high",
        True,
    ),
    AttentionTriageEvalCase(
        "jira_client_bug_high",
        "jira",
        "issue.from_external",
        "Client bug",
        "Client-facing bug requires prioritization.",
        _result("requires_my_attention", "high", owner="me", recommended_action="prioritize the bug"),
        "requires_my_attention",
        "high",
        True,
    ),
    AttentionTriageEvalCase(
        "jira_status_change_info",
        "jira",
        "issue.system",
        "Status changed",
        "Issue status changed on an active project but no action is requested.",
        _result("important_info", "low", owner="team"),
        "important_info",
        "low",
        True,
    ),
    AttentionTriageEvalCase(
        "jira_waiting_external",
        "jira",
        "issue.from_me",
        "Waiting on vendor",
        "Operator asked vendor for information and is waiting.",
        _result("waiting_on_external", "medium", owner="external"),
        "waiting_on_external",
        "medium",
        True,
    ),
    AttentionTriageEvalCase(
        "drive_strategy_doc_changed",
        "google_drive",
        "document.system",
        "Strategy doc changed",
        "Important strategy document was updated by the team.",
        _result("important_info", "medium", owner="team"),
        "important_info",
        "medium",
        True,
    ),
    AttentionTriageEvalCase(
        "drive_random_archive_file",
        "google_drive",
        "document.system",
        "Archive file changed",
        "Old archive file was reformatted automatically.",
        _result("no_action_required", "low", show_in_digest=False, confidence=0.93, owner=None),
        "no_action_required",
        "low",
        False,
    ),
    AttentionTriageEvalCase(
        "security_alert_action_required",
        "security",
        "alert.system",
        "Security action",
        "Security alert requires password rotation approval.",
        _result("manual_action", "high", owner="me", recommended_action="approve the security action"),
        "manual_action",
        "high",
        True,
    ),
    AttentionTriageEvalCase(
        "security_info_no_action",
        "security",
        "alert.system",
        "Security info",
        "Informational security scan completed successfully.",
        _result("no_action_required", "low", show_in_digest=False, confidence=0.91, owner=None),
        "no_action_required",
        "low",
        False,
    ),
    AttentionTriageEvalCase(
        "ops_incident_update",
        "monitoring",
        "incident.from_external",
        "Incident update",
        "Production incident update asks for operator acknowledgement.",
        _result("requires_my_attention", "high", owner="me", recommended_action="acknowledge incident status"),
        "requires_my_attention",
        "high",
        True,
    ),
    AttentionTriageEvalCase(
        "billing_receipt_noise",
        "gmail",
        "email_thread.from_external",
        "Receipt",
        "Automated receipt for an already completed payment.",
        _result("no_action_required", "low", show_in_digest=False, confidence=0.89, owner=None),
        "no_action_required",
        "low",
        False,
    ),
    AttentionTriageEvalCase(
        "ambiguous_short_message",
        "gmail",
        "email_thread.from_external",
        "Quick question",
        "Message says 'can we discuss this?' with no project detail.",
        _result("review_optional", "low", owner=None),
        "review_optional",
        "low",
        True,
    ),
    AttentionTriageEvalCase(
        "ambiguous_forwarded_thread",
        "gmail",
        "email_thread.from_external",
        "Forwarded context",
        "Forwarded thread may be relevant but has no explicit request.",
        _result("review_optional", "low", owner=None),
        "review_optional",
        "low",
        True,
    ),
    AttentionTriageEvalCase(
        "ambiguous_medium_confidence_hidden",
        "gmail",
        "email_thread.from_external",
        "Possibly noise",
        "Provider is only medium-confident that the item is noise.",
        _result("no_action_required", "low", show_in_digest=False, confidence=0.70, owner=None),
        "review_optional",
        "low",
        True,
    ),
    AttentionTriageEvalCase(
        "ambiguous_low_confidence_work_item",
        "gmail",
        "email_thread.from_external",
        "Maybe client asks",
        "Provider is low-confident but action may require a reply.",
        _result(
            "requires_my_attention",
            "high",
            show_in_digest=False,
            confidence=0.30,
            owner="me",
            recommended_action="reply if this is a client request",
        ),
        "review_optional",
        "medium",
        True,
    ),
    AttentionTriageEvalCase(
        "unknown_source_visible_review",
        "unknown",
        "activity.from_external",
        "Unknown source event",
        "Unknown source cannot be safely hidden.",
        _result("review_optional", "low", owner=None),
        "review_optional",
        "low",
        True,
    ),
    AttentionTriageEvalCase(
        "invalid_json_falls_back",
        "gmail",
        "email_thread.from_external",
        "Invalid provider response",
        "Provider returns invalid JSON; fallback must keep visible.",
        "{invalid json",
        "review_optional",
        "low",
        True,
    ),
    AttentionTriageEvalCase(
        "invalid_schema_falls_back",
        "github",
        "pull_request.from_external",
        "Invalid schema",
        "Provider returns JSON that fails the strict schema.",
        '{"attention_class":"requires_my_attention"}',
        "review_optional",
        "low",
        True,
    ),
    AttentionTriageEvalCase(
        "provider_missing_output_falls_back",
        "gmail",
        "email_thread.from_external",
        "Provider missing output",
        "Mock provider has no output and should fall back conservatively.",
        None,
        "review_optional",
        "low",
        True,
    ),
)


def test_attention_triage_eval_v1_has_expected_size() -> None:
    assert 30 <= len(GOLDEN_CASES) <= 50


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[case.case_id for case in GOLDEN_CASES])
def test_attention_triage_eval_v1_golden_cases(case: AttentionTriageEvalCase) -> None:
    provider = (
        MockAttentionTriageProvider()
        if case.provider_output is None
        else MockAttentionTriageProvider([case.provider_output])
    )
    agent = AttentionTriageAgent(provider)

    result = agent.classify_activity(_activity(case), _context())

    assert isinstance(result, AttentionTriageResult)
    assert result.attention_class == case.expected_attention_class
    assert result.priority == case.expected_priority
    assert result.show_in_digest is case.expected_show_in_digest
    if case.expected_attention_class == "review_optional":
        assert result.show_in_digest is True


def test_attention_triage_eval_v1_uses_mock_provider_only() -> None:
    provider = MockAttentionTriageProvider([_result("review_optional", "low")])
    agent = AttentionTriageAgent(provider)

    result = agent.classify_activity(_activity(GOLDEN_CASES[0]), _context())

    assert result.attention_class == "review_optional"
    assert len(provider.calls) == 1
