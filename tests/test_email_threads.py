from datetime import datetime, timezone

from app.services.email_threads import (
    MESSAGE_DIRECTION_FROM_EXTERNAL,
    MESSAGE_DIRECTION_FROM_ME,
    MESSAGE_DIRECTION_UNKNOWN,
    THREAD_STATUS_HIDDEN,
    THREAD_STATUS_INFORMATIONAL,
    THREAD_STATUS_MANUAL_ACTION_REQUIRED,
    THREAD_STATUS_NEEDS_MY_REPLY,
    THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY,
    TRIAGE_ACTION_MANUAL_ACTION_REQUIRED,
    TRIAGE_ACTION_NO_ACTION_REQUIRED,
    TRIAGE_ACTION_REPLY_REQUIRED,
    TRIAGE_ACTION_REVIEW_OPTIONAL,
    TRIAGE_ACTION_WAITING_EXTERNAL_REPLY,
    TRIAGE_CATEGORY_AUTOMATED_NOTIFICATION,
    TRIAGE_CATEGORY_CALENDAR_UPDATE,
    TRIAGE_CATEGORY_MANUAL_ACTION,
    TRIAGE_CATEGORY_NEWSLETTER,
    TRIAGE_CATEGORY_SECURITY_ALERT,
    TRIAGE_CATEGORY_SOCIAL_NETWORK,
    TRIAGE_CATEGORY_WORK_ACTION,
    TRIAGE_CATEGORY_WORK_INFO,
    TRIAGE_CATEGORY_WORK_WAITING,
    TRIAGE_PRIORITY_HIGH,
    TRIAGE_PRIORITY_HIDDEN,
    TRIAGE_PRIORITY_MEDIUM,
    EmailMessageSnapshot,
    build_email_thread_state_candidates,
    compute_days_without_reply,
    normalize_email_address,
    normalize_email_subject,
    parse_email_addresses,
)


NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)
ME = "founder@example.test"
EXTERNAL = "partner@example.test"


def _msg(
    message_id: str,
    *,
    subject: str = "Project update",
    provider_thread_id: str | None = None,
    from_address: str | None = EXTERNAL,
    to: str = ME,
    cc: str | None = None,
    message_at: datetime | None = None,
    message_id_header: str | None = None,
    in_reply_to: tuple[str, ...] = (),
    references: tuple[str, ...] = (),
    snippet: str | None = None,
    body_preview: str | None = None,
    headers: dict[str, str] | None = None,
) -> EmailMessageSnapshot:
    return EmailMessageSnapshot(
        message_id=message_id,
        provider_thread_id=provider_thread_id,
        subject=subject,
        from_address=normalize_email_address(from_address),
        to_addresses=parse_email_addresses(to),
        cc_addresses=parse_email_addresses(cc),
        message_at=message_at or NOW,
        raw_object_ref=f"raw://gmail/{message_id}/message.json",
        source_document_id=f"gmail-doc-{message_id}",
        message_id_header=message_id_header,
        in_reply_to=in_reply_to,
        references=references,
        label_ids=(),
        snippet=snippet,
        body_preview=body_preview,
        headers=headers or {},
    )


def test_normalize_email_subject_removes_reply_and_forward_prefixes() -> None:
    assert normalize_email_subject("Re: Project Update") == "project update"
    assert normalize_email_subject("Fwd: Project Update") == "project update"
    assert normalize_email_subject("FW: Project Update") == "project update"
    assert normalize_email_subject("Re: Fwd: RE:   Project   Update") == "project update"


def test_groups_by_gmail_thread_id() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg("m1", provider_thread_id="thread-1"),
            _msg("m2", provider_thread_id="thread-1", subject="Re: Project update"),
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert len(candidates) == 1
    assert candidates[0].provider_thread_id == "thread-1"
    assert candidates[0].messages_count == 2
    assert candidates[0].metadata_json["grouping_strategy"] == "gmail_thread_id"


def test_groups_by_message_id_relationships_when_thread_id_missing() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg("m1", message_id_header="root@example.test"),
            _msg(
                "m2",
                subject="Re: Project update",
                from_address=ME,
                to=EXTERNAL,
                message_id_header="reply@example.test",
                in_reply_to=("root@example.test",),
            ),
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert len(candidates) == 1
    assert candidates[0].messages_count == 2
    assert candidates[0].metadata_json["grouping_strategy"] == "message_headers"


def test_groups_by_normalized_subject_and_overlapping_participants_fallback() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg("m1", subject="Launch Plan", provider_thread_id=None),
            _msg(
                "m2",
                subject="Re: launch plan",
                provider_thread_id=None,
                from_address=ME,
                to=EXTERNAL,
            ),
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert len(candidates) == 1
    assert candidates[0].subject_normalized == "launch plan"
    assert candidates[0].messages_count == 2
    assert candidates[0].metadata_json["grouping_strategy"] == "subject_participants"


def test_external_me_external_conversation_builds_one_thread_needing_my_reply() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-1",
                from_address=EXTERNAL,
                to=ME,
                message_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
            ),
            _msg(
                "m2",
                provider_thread_id="thread-1",
                from_address=ME,
                to=EXTERNAL,
                message_at=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
            ),
            _msg(
                "m3",
                provider_thread_id="thread-1",
                from_address=EXTERNAL,
                to=ME,
                message_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
                snippet="Fake external follow-up needs an operator reply.",
            ),
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert len(candidates) == 1
    assert candidates[0].messages_count == 3
    assert candidates[0].last_message_direction == MESSAGE_DIRECTION_FROM_EXTERNAL
    assert candidates[0].status == THREAD_STATUS_NEEDS_MY_REPLY
    assert candidates[0].triage_category == TRIAGE_CATEGORY_WORK_ACTION
    assert candidates[0].triage_action_type == TRIAGE_ACTION_REPLY_REQUIRED
    assert candidates[0].show_in_digest is True
    assert candidates[0].days_without_reply == 1
    assert candidates[0].last_message_summary == "Fake external follow-up needs an operator reply."
    assert "Stored Gmail thread" not in candidates[0].thread_summary
    assert candidates[0].metadata_json["last_message_from_display"] == "external sender"
    assert candidates[0].metadata_json["last_message_to_display"] == ["me"]
    assert candidates[0].metadata_json["participants_display"] == "me, 1 external participant"


def test_external_then_me_conversation_waits_for_external_reply() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-1",
                from_address=EXTERNAL,
                to=ME,
                message_at=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
            ),
            _msg(
                "m2",
                provider_thread_id="thread-1",
                from_address=ME,
                to=EXTERNAL,
                message_at=datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
            ),
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert candidates[0].last_message_direction == MESSAGE_DIRECTION_FROM_ME
    assert candidates[0].status == THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY
    assert candidates[0].triage_category == TRIAGE_CATEGORY_WORK_WAITING
    assert candidates[0].triage_action_type == TRIAGE_ACTION_WAITING_EXTERNAL_REPLY
    assert candidates[0].days_without_reply == 1


def test_external_client_question_triages_as_reply_required() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-client-question",
                from_address="client@example.test",
                snippet="Can you review the fake launch proposal today?",
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    candidate = candidates[0]
    assert candidate.triage_category == TRIAGE_CATEGORY_WORK_ACTION
    assert candidate.triage_action_type == TRIAGE_ACTION_REPLY_REQUIRED
    assert candidate.triage_priority == TRIAGE_PRIORITY_HIGH
    assert candidate.show_in_digest is True
    assert candidate.status == THREAD_STATUS_NEEDS_MY_REPLY


def test_newsletter_with_list_unsubscribe_is_hidden() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-newsletter",
                from_address="updates@example.test",
                subject="Fake newsletter",
                snippet="Fake digest of updates.",
                headers={"List-Unsubscribe": "<mailto:unsubscribe@example.test>"},
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    candidate = candidates[0]
    assert candidate.triage_category == TRIAGE_CATEGORY_NEWSLETTER
    assert candidate.triage_action_type == TRIAGE_ACTION_REVIEW_OPTIONAL
    assert candidate.triage_priority == TRIAGE_PRIORITY_HIDDEN
    assert candidate.show_in_digest is False
    assert candidate.status == THREAD_STATUS_HIDDEN


def test_linkedin_notification_is_hidden_social_network() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-social",
                from_address="notifications@linkedin.example.test",
                subject="Fake LinkedIn notification",
                snippet="Someone viewed your fake profile.",
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    candidate = candidates[0]
    assert candidate.triage_category == TRIAGE_CATEGORY_SOCIAL_NETWORK
    assert candidate.triage_action_type == TRIAGE_ACTION_REVIEW_OPTIONAL
    assert candidate.triage_priority == TRIAGE_PRIORITY_HIDDEN
    assert candidate.show_in_digest is False
    assert candidate.status == THREAD_STATUS_HIDDEN


def test_google_calendar_update_is_hidden_no_action() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-calendar",
                from_address="calendar@example.test",
                subject="Invitation: Fake planning sync",
                snippet="Google Calendar fake event update.",
                headers={"Content-Type": "text/calendar"},
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    candidate = candidates[0]
    assert candidate.triage_category == TRIAGE_CATEGORY_CALENDAR_UPDATE
    assert candidate.triage_action_type == TRIAGE_ACTION_NO_ACTION_REQUIRED
    assert candidate.triage_priority == TRIAGE_PRIORITY_HIDDEN
    assert candidate.show_in_digest is False
    assert candidate.status == THREAD_STATUS_HIDDEN


def test_security_alert_no_action_needed_is_hidden() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-security-ok",
                from_address="security@example.test",
                subject="Security alert",
                snippet="New sign-in detected. If this was you, no action is required.",
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    candidate = candidates[0]
    assert candidate.triage_category == TRIAGE_CATEGORY_SECURITY_ALERT
    assert candidate.triage_action_type == TRIAGE_ACTION_NO_ACTION_REQUIRED
    assert candidate.triage_priority == TRIAGE_PRIORITY_HIDDEN
    assert candidate.show_in_digest is False
    assert candidate.status == THREAD_STATUS_HIDDEN


def test_suspicious_security_alert_requires_manual_action() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-security-risk",
                from_address="security@example.test",
                subject="Security alert",
                snippet="Suspicious login detected for a fake account. Review immediately.",
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    candidate = candidates[0]
    assert candidate.triage_category == TRIAGE_CATEGORY_SECURITY_ALERT
    assert candidate.triage_action_type == TRIAGE_ACTION_MANUAL_ACTION_REQUIRED
    assert candidate.triage_priority == TRIAGE_PRIORITY_HIGH
    assert candidate.show_in_digest is True
    assert candidate.status == THREAD_STATUS_MANUAL_ACTION_REQUIRED


def test_badge_ticket_access_ready_requires_manual_action_not_reply() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-badge",
                from_address="no-reply@example.test",
                subject="Your fake badge is ready",
                snippet="Your badge is ready for pickup.",
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    candidate = candidates[0]
    assert candidate.triage_category == TRIAGE_CATEGORY_MANUAL_ACTION
    assert candidate.triage_action_type == TRIAGE_ACTION_MANUAL_ACTION_REQUIRED
    assert candidate.triage_priority == TRIAGE_PRIORITY_MEDIUM
    assert candidate.show_in_digest is True
    assert candidate.status == THREAD_STATUS_MANUAL_ACTION_REQUIRED


def test_no_reply_external_email_does_not_become_needs_my_reply() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-automated",
                from_address="no-reply@example.test",
                subject="Fake report ready",
                snippet="Your fake report has been generated.",
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    candidate = candidates[0]
    assert candidate.last_message_direction == MESSAGE_DIRECTION_FROM_EXTERNAL
    assert candidate.triage_category == TRIAGE_CATEGORY_AUTOMATED_NOTIFICATION
    assert candidate.triage_action_type == TRIAGE_ACTION_NO_ACTION_REQUIRED
    assert candidate.status == THREAD_STATUS_HIDDEN
    assert candidate.status != THREAD_STATUS_NEEDS_MY_REPLY


def test_uncertain_work_like_email_is_review_optional_not_hidden() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-work-info",
                from_address="partner@example.test",
                subject="Fake project update",
                snippet="Fake project status update for awareness.",
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    candidate = candidates[0]
    assert candidate.triage_category == TRIAGE_CATEGORY_WORK_INFO
    assert candidate.triage_action_type == TRIAGE_ACTION_REVIEW_OPTIONAL
    assert candidate.show_in_digest is True
    assert candidate.status == THREAD_STATUS_INFORMATIONAL


def test_days_without_reply_calculation() -> None:
    assert (
        compute_days_without_reply(
            datetime(2026, 5, 10, 11, 0, tzinfo=timezone.utc),
            NOW,
        )
        == 3
    )


def test_candidate_days_without_reply_uses_provided_clock() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-1",
                from_address=EXTERNAL,
                to=ME,
                message_at=datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc),
            ),
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert candidates[0].days_without_reply == 4


def test_no_duplicate_thread_state_for_multiple_messages_in_same_conversation() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg("m1", provider_thread_id="thread-1"),
            _msg("m2", provider_thread_id="thread-1", subject="Re: Project update"),
            _msg("m3", provider_thread_id="thread-1", subject="Fwd: Project update"),
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert len(candidates) == 1
    assert candidates[0].messages_count == 3


def test_repeated_reply_forward_subjects_group_without_provider_thread_id() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg("m1", subject="Fake Launch Plan", provider_thread_id=None),
            _msg(
                "m2",
                subject="Re: fake launch plan",
                provider_thread_id=None,
                from_address=ME,
                to=EXTERNAL,
            ),
            _msg(
                "m3",
                subject="Fwd: RE: Fake Launch Plan",
                provider_thread_id=None,
                from_address=EXTERNAL,
                to=ME,
            ),
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert len(candidates) == 1
    assert candidates[0].subject_normalized == "fake launch plan"
    assert candidates[0].messages_count == 3


def test_missing_me_identity_keeps_direction_unknown_and_informational() -> None:
    candidates = build_email_thread_state_candidates(
        [_msg("m1", provider_thread_id="thread-1", from_address=EXTERNAL, to=ME)],
        me_addresses=set(),
        now=NOW,
    )

    assert candidates[0].last_message_direction == MESSAGE_DIRECTION_UNKNOWN
    assert candidates[0].status == THREAD_STATUS_INFORMATIONAL


def test_evidence_refs_are_present_without_private_summary_content() -> None:
    candidates = build_email_thread_state_candidates(
        [_msg("m1", provider_thread_id="thread-1")],
        me_addresses={ME},
        now=NOW,
    )

    assert candidates[0].evidence_refs
    assert candidates[0].evidence_refs[0]["kind"] == "gmail_message"
    assert candidates[0].last_message_summary == (
        "Latest message from external sender about Project update."
    )
    assert candidates[0].thread_summary == (
        "Latest message from external sender about Project update."
    )
    assert candidates[0].metadata_json["summary_uses_private_content"] is False


def test_summary_prefers_stored_snippet_and_truncates() -> None:
    long_snippet = " ".join(["Fake snippet content"] * 20)
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-1",
                snippet=long_snippet,
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert candidates[0].last_message_summary.startswith("Fake snippet content")
    assert len(candidates[0].last_message_summary) <= 180
    assert candidates[0].last_message_summary.endswith("...")
    assert "Stored Gmail thread" not in candidates[0].thread_summary
    assert candidates[0].metadata_json["summary_source"] == "stored_preview"


def test_summary_cleans_html_entities_zero_width_and_whitespace() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-clean",
                snippet="Fake&nbsp;client&#39;s\u200b update\n\nneeds\t review.",
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert candidates[0].last_message_summary == "Fake client's update needs review."


def test_summary_uses_body_preview_when_snippet_missing() -> None:
    candidates = build_email_thread_state_candidates(
        [
            _msg(
                "m1",
                provider_thread_id="thread-1",
                body_preview="Fake body preview from stored text.",
            )
        ],
        me_addresses={ME},
        now=NOW,
    )

    assert candidates[0].last_message_summary == "Fake body preview from stored text."
    assert candidates[0].metadata_json["summary_source"] == "stored_preview"
