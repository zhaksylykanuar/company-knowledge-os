import builtins

from app.services.digest_rendering import render_source_activity_digest_text


def _metadata(entry_count: int = 0) -> dict:
    return {
        "generated_at": "2125-01-03T00:00:00+00:00",
        "entry_limit": 20,
        "entry_count": entry_count,
        "truncated": False,
        "source_model": "source_events",
        "debug_evidence": False,
        "debug_triage": False,
        "llm_used": False,
    }


def _source_event_data_quality() -> dict:
    return {
        "hidden_mock_example_event_count": 0,
        "notes": [],
    }


def _empty_digest() -> dict:
    return {
        "digest_type": "source_activity",
        "window": {
            "start_at": "2120-01-01T00:00:00+00:00",
            "end_at": "2120-01-02T00:00:00+00:00",
        },
        "counts": {
            "total": 0,
            "by_source_system": {},
            "by_event_type": {},
            "by_source_object_type": {},
        },
        "entries": [],
        "metadata": _metadata(),
        "source_event_data_quality": _source_event_data_quality(),
    }


def _non_empty_digest(raw_body: str = "Full raw source body should not render.") -> dict:
    return {
        "digest_type": "source_activity",
        "window": {
            "start_at": "2121-01-01T00:00:00+00:00",
            "end_at": "2121-01-02T00:00:00+00:00",
        },
        "counts": {
            "total": 2,
            "by_source_system": {
                "gmail": 1,
                "drive": 1,
            },
            "by_event_type": {
                "gmail.message.ingested": 1,
                "drive.file.ingested": 1,
            },
            "by_source_object_type": {
                "message": 1,
                "file": 1,
            },
        },
        "entries": [
            {
                "source_event_id": "sevt_digest_render_1",
                "source_system": "gmail",
                "source_object_type": "message",
                "source_object_id": "gmail-object-1",
                "event_type": "gmail.message.ingested",
                "event_time": "2121-01-01T12:00:00+00:00",
                "actor_external_id": "actor-1",
                "title": "Digest-safe subject",
                "source_url": "",
                "summary": raw_body,
                "payload": {"text": raw_body},
                "evidence": "1 event",
                "seen_count": 1,
                "evidence_refs": [
                    {
                        "kind": "source_event",
                        "source_event_id": "sevt_digest_render_1",
                        "source_system": "gmail",
                        "source_object_type": "message",
                        "source_object_id": "gmail-object-1",
                        "event_type": "gmail.message.ingested",
                        "raw_object_ref": "raw://digest-render/1.json",
                        "quote": raw_body,
                    }
                ],
            }
        ],
        "metadata": _metadata(entry_count=1) | {"entry_limit": 1, "truncated": True},
        "source_event_data_quality": _source_event_data_quality(),
    }


def _digest_with_duplicate_entry() -> dict:
    digest = _non_empty_digest()
    digest["entries"][0]["evidence"] = "3 events"
    digest["entries"][0]["seen_count"] = 3
    digest["entries"][0]["repeated_count"] = 3
    return digest


def _digest_with_data_quality_note() -> dict:
    digest = _empty_digest()
    digest["source_event_data_quality"] = {
        "hidden_mock_example_event_count": 2,
        "notes": ["Hidden 2 mock/example source events from production activity."],
    }
    return digest


def _digest_with_email_threads() -> dict:
    return {
        "digest_type": "source_activity",
        "window": {
            "start_at": "2125-01-01T00:00:00+00:00",
            "end_at": "2125-01-02T00:00:00+00:00",
        },
        "counts": {
            "total": 2,
            "by_source_system": {"gmail": 2},
            "by_event_type": {"gmail.message.ingested": 2},
            "by_source_object_type": {"message": 2},
        },
        "email_thread_intelligence": {
            "section_title": "Email triage",
            "available": True,
            "counts": {
                "total": 7,
                "active": 3,
                "by_status": {
                    "needs_my_reply": 1,
                    "manual_action_required": 1,
                    "waiting_for_external_reply": 1,
                    "informational": 1,
                },
                "by_category": {
                    "work_action": 1,
                    "manual_action": 1,
                    "work_waiting": 1,
                    "work_info": 1,
                    "newsletter": 1,
                    "social_network": 1,
                    "calendar_update": 1,
                },
                "by_action_type": {
                    "reply_required": 1,
                    "manual_action_required": 1,
                    "waiting_external_reply": 1,
                    "review_optional": 3,
                    "no_action_required": 1,
                },
                "by_priority": {
                    "high": 1,
                    "medium": 2,
                    "low": 1,
                    "hidden": 3,
                },
                "by_show_in_digest": {
                    "true": 4,
                    "false": 3,
                },
            },
            "groups": {
                "work_actions": [
                    {
                        "subject": "Fake customer follow-up",
                        "status": "needs_my_reply",
                        "attention_class": "requires_my_attention",
                        "category": "work_action",
                        "action_type": "reply_required",
                        "priority": "high",
                        "show_in_digest": True,
                        "recommended_action": "reply to the email thread",
                        "last_message_at": "2125-01-01T12:00:00+00:00",
                        "last_message_from": "external sender",
                        "last_message_to": "me",
                        "last_message_direction": "from_external",
                        "participants": "me, 1 external participant",
                        "days_without_reply": 4,
                        "messages_count": 3,
                        "summary": "3-message thread. Latest: Fake customer asks for next steps.",
                        "last_message_summary": "Fake customer asks for next steps.",
                        "evidence": "1 thread, 3 messages",
                        "evidence_refs": [
                            {
                                "kind": "gmail_message",
                                "source_system": "gmail",
                                "source_object_type": "message",
                                "source_object_id": "fake-message-1",
                                "raw_object_ref": "raw://fake-gmail/thread-1/message.json",
                                "quote": "Fixture-only body must not render.",
                            }
                        ],
                        "triage": {
                            "category": "work_action",
                            "action_type": "reply_required",
                            "priority": "high",
                            "show_in_digest": True,
                            "reason": "external_work_request",
                            "confidence": 0.78,
                            "attention_class": "requires_my_attention",
                            "attention_priority": "high",
                            "attention_show_in_digest": True,
                            "attention_reason": "external_work_request",
                            "attention_confidence": 0.78,
                            "recommended_action": "reply to the email thread",
                        },
                    }
                ],
                "manual_actions": [
                    {
                        "subject": "Fake badge ready",
                        "status": "manual_action_required",
                        "attention_class": "manual_action",
                        "category": "manual_action",
                        "action_type": "manual_action_required",
                        "priority": "medium",
                        "show_in_digest": True,
                        "recommended_action": "complete the manual email action",
                        "last_message_at": "2125-01-01T11:00:00+00:00",
                        "last_message_from": "external sender",
                        "last_message_to": "me",
                        "last_message_direction": "from_external",
                        "participants": "me, 1 external participant",
                        "days_without_reply": 1,
                        "messages_count": 1,
                        "summary": "Fake badge is ready for pickup.",
                        "last_message_summary": "Fake badge is ready for pickup.",
                        "evidence": "1 thread, 1 message",
                        "evidence_refs": [
                            {
                                "kind": "gmail_message",
                                "source_system": "gmail",
                                "source_object_id": "fake-message-3",
                            }
                        ],
                    }
                ],
                "waiting_external_reply": [
                    {
                        "subject": "Fake proposal",
                        "status": "waiting_for_external_reply",
                        "attention_class": "waiting_on_external",
                        "category": "work_waiting",
                        "action_type": "waiting_external_reply",
                        "priority": "medium",
                        "show_in_digest": True,
                        "recommended_action": "wait for an external reply",
                        "last_message_at": "2125-01-01T10:00:00+00:00",
                        "last_message_from": "me",
                        "last_message_to": "external participant",
                        "last_message_direction": "from_me",
                        "participants": "me, 1 external participant",
                        "days_without_reply": 2,
                        "messages_count": 2,
                        "summary": "2-message thread. Latest: Fake outbound proposal was sent.",
                        "last_message_summary": "Fake outbound proposal was sent.",
                        "evidence": "1 thread, 2 messages",
                        "evidence_refs": [
                            {
                                "kind": "gmail_message",
                                "source_system": "gmail",
                                "source_object_type": "message",
                                "source_object_id": "fake-message-2",
                            }
                        ],
                    }
                ],
                "work_info": [
                    {
                        "subject": "Fake project update",
                        "status": "informational",
                        "attention_class": "important_info",
                        "category": "work_info",
                        "action_type": "review_optional",
                        "priority": "low",
                        "show_in_digest": True,
                        "recommended_action": "review the project update",
                        "last_message_at": "2125-01-01T09:00:00+00:00",
                        "last_message_from": "external sender",
                        "last_message_to": "me",
                        "last_message_direction": "from_external",
                        "participants": "me, 1 external participant",
                        "days_without_reply": 1,
                        "messages_count": 1,
                        "summary": "Fake project status changed.",
                        "last_message_summary": "Fake project status changed.",
                        "evidence": "1 thread, 1 message",
                    }
                ],
                "review_optional": [],
            },
            "hidden_low_priority_summary": {
                "total": 3,
                "counts": {
                    "calendar auto-updates": 1,
                    "newsletter emails": 1,
                    "social network notifications": 1,
                },
            },
            "data_quality_notes": [
                "Raw Gmail source events are summarized in counts because EmailThreadState rows are available."
            ],
            "metadata": {
                "source_model": "email_thread_states",
                "raw_gmail_entries_suppressed": True,
                "debug_triage": False,
            },
        },
        "entries": [],
        "metadata": _metadata() | {"debug_triage": False},
        "source_event_data_quality": _source_event_data_quality(),
    }


def test_render_source_activity_digest_text_renders_empty_state() -> None:
    rendered = render_source_activity_digest_text(_empty_digest())

    assert "Source activity digest" in rendered
    assert "Generated at: 2125-01-03T00:00:00+00:00" in rendered
    assert "Window: 2120-01-01T00:00:00+00:00 to 2120-01-02T00:00:00+00:00" in rendered
    assert "Total events: 0" in rendered
    assert "Entries: none" in rendered
    assert "No source activity found for this window." in rendered
    assert "does not infer decisions, tasks, or risks" in rendered


def test_render_source_activity_digest_text_renders_counts_deterministically() -> None:
    rendered = render_source_activity_digest_text(_non_empty_digest())

    assert rendered.index("- drive: 1") < rendered.index("- gmail: 1")
    assert rendered.index("- drive.file.ingested: 1") < rendered.index(
        "- gmail.message.ingested: 1"
    )
    assert rendered.index("- file: 1") < rendered.index("- message: 1")


def test_render_source_activity_digest_text_renders_entries_with_short_evidence() -> None:
    rendered = render_source_activity_digest_text(_non_empty_digest())

    assert "Entries: 1 shown, limit 1" in rendered
    assert "Entries are truncated by the digest limit." in rendered
    assert "1. 2121-01-01T12:00:00+00:00 | gmail/message | gmail.message.ingested" in rendered
    assert "Title: Digest-safe subject" in rendered
    assert "Evidence: 1 event" in rendered
    assert "Source event:" not in rendered
    assert "Source object:" not in rendered
    assert "Debug evidence refs:" not in rendered
    assert "source_event_id=sevt_digest_render_1" not in rendered
    assert "raw_object_ref=raw://digest-render/1.json" not in rendered


def test_render_source_activity_digest_text_debug_evidence_includes_raw_refs() -> None:
    rendered = render_source_activity_digest_text(
        _non_empty_digest(),
        debug_evidence=True,
    )

    assert "Source event: sevt_digest_render_1" in rendered
    assert "Source object: gmail-object-1" in rendered
    assert "Debug evidence refs:" in rendered
    assert "kind=source_event" in rendered
    assert "source_event_id=sevt_digest_render_1" in rendered
    assert "raw_object_ref=raw://digest-render/1.json" in rendered


def test_render_source_activity_digest_text_renders_seen_count() -> None:
    rendered = render_source_activity_digest_text(_digest_with_duplicate_entry())

    assert "Evidence: 3 events" in rendered
    assert "Seen 3 times" in rendered


def test_render_source_activity_digest_text_renders_mock_data_quality_note() -> None:
    rendered = render_source_activity_digest_text(_digest_with_data_quality_note())

    assert (
        "Source event data quality note: Hidden 2 mock/example source events from production activity."
        in rendered
    )


def test_render_source_activity_digest_text_omits_raw_body_fields() -> None:
    raw_body = "Full raw source body should never be rendered from body-like fields."

    rendered = render_source_activity_digest_text(_non_empty_digest(raw_body=raw_body))

    assert raw_body not in rendered
    assert "quote=" not in rendered
    assert "payload" not in rendered
    assert "summary" not in rendered


def test_render_source_activity_digest_text_does_not_claim_inferred_items() -> None:
    rendered = render_source_activity_digest_text(_non_empty_digest())

    assert "Recommendations:" not in rendered
    assert "Tasks:" not in rendered
    assert "Risks:" not in rendered
    assert "Decisions:" not in rendered
    assert "Commitments:" not in rendered
    assert "does not infer decisions, tasks, or risks" in rendered


def test_render_source_activity_digest_text_renders_email_thread_section() -> None:
    rendered = render_source_activity_digest_text(_digest_with_email_threads())

    assert "Email triage" in rendered
    assert "Work actions requiring my attention:" in rendered
    assert "Manual actions:" in rendered
    assert "Waiting for external reply:" in rendered
    assert "Important project updates:" in rendered
    assert "Work info / recently relevant:" not in rendered
    assert rendered.index("Work actions requiring my attention:") < rendered.index(
        "Manual actions:"
    )
    assert rendered.index("Manual actions:") < rendered.index("Waiting for external reply:")
    assert rendered.index("Waiting for external reply:") < rendered.index(
        "Important project updates:"
    )
    assert "1. Fake customer follow-up" in rendered
    assert "Action: Reply required" in rendered
    assert "Priority: high" in rendered
    assert "Not answered for: 4 days" in rendered
    assert "1. Fake badge ready" in rendered
    assert "Action: Manual action required" in rendered
    assert "Priority: medium" in rendered
    assert "Waiting for external reply: 2 days" in rendered
    assert "1. Fake project update" in rendered
    assert "Summary: Fake project status changed." in rendered
    assert "Summary: 3-message thread. Latest: Fake customer asks for next steps." in rendered
    assert "Evidence: 1 thread, 3 messages" in rendered
    assert "Hidden low-priority email summary:" in rendered
    assert "- 1 calendar auto-updates" in rendered
    assert "- 1 newsletter emails" in rendered
    assert "- 1 social network notifications" in rendered
    assert "kind=gmail_message" not in rendered
    assert "source_object_id=fake-message-1" not in rendered
    assert "raw_object_ref=raw://fake-gmail/thread-1/message.json" not in rendered
    assert "quote=" not in rendered
    assert "Debug triage:" not in rendered


def test_render_source_activity_digest_text_debug_evidence_for_email_threads() -> None:
    rendered = render_source_activity_digest_text(
        _digest_with_email_threads(),
        debug_evidence=True,
    )

    assert "Debug evidence refs:" in rendered
    assert "kind=gmail_message" in rendered
    assert "source_object_id=fake-message-1" in rendered
    assert "raw_object_ref=raw://fake-gmail/thread-1/message.json" in rendered


def test_render_source_activity_digest_text_debug_triage_for_email_threads() -> None:
    rendered = render_source_activity_digest_text(
        _digest_with_email_threads(),
        debug_triage=True,
    )

    assert "Debug triage:" in rendered
    assert "category=work_action" in rendered
    assert "action_type=reply_required" in rendered
    assert "attention_class=requires_my_attention" in rendered
    assert "reason=external_work_request" in rendered
    assert "recommended_action=reply to the email thread" in rendered


def test_render_source_activity_digest_text_falls_back_when_email_threads_empty() -> None:
    digest = _non_empty_digest()
    digest["email_thread_intelligence"] = {
        "section_title": "Email threads requiring attention",
        "available": True,
        "counts": {
            "total": 0,
            "active": 0,
            "by_status": {},
            "by_category": {},
            "by_action_type": {},
            "by_priority": {},
            "by_show_in_digest": {},
        },
        "groups": {
            "work_actions": [],
            "manual_actions": [],
            "waiting_external_reply": [],
            "work_info": [],
            "review_optional": [],
        },
        "hidden_low_priority_summary": {
            "total": 0,
            "counts": {},
        },
        "data_quality_notes": [
            "EmailThreadState has no rows for this digest window; raw Gmail source events are shown as fallback."
        ],
        "metadata": {
            "source_model": "email_thread_states",
            "raw_gmail_entries_suppressed": False,
        },
    }

    rendered = render_source_activity_digest_text(digest)

    assert "Email threads requiring attention" not in rendered
    assert "Email thread data quality note:" in rendered
    assert "Entries: 1 shown, limit 1" in rendered
    assert "Digest-safe subject" in rendered


def test_render_source_activity_digest_text_does_not_import_external_services(
    monkeypatch,
) -> None:
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        blocked_prefixes = ("openai", "app.db", "app.api")
        if name == "openai" or name.startswith(blocked_prefixes):
            raise AssertionError(f"renderer must not import {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    rendered = render_source_activity_digest_text(_non_empty_digest())

    assert "Source activity digest" in rendered
