from datetime import datetime, timezone

from app.services.email_threads import (
    MESSAGE_DIRECTION_FROM_EXTERNAL,
    MESSAGE_DIRECTION_FROM_ME,
    MESSAGE_DIRECTION_UNKNOWN,
    THREAD_STATUS_INFORMATIONAL,
    THREAD_STATUS_NEEDS_MY_REPLY,
    THREAD_STATUS_WAITING_FOR_EXTERNAL_REPLY,
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
    assert candidates[0].days_without_reply == 1


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
