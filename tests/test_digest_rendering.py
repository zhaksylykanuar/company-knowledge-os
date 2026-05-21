import builtins

from app.services.digest_rendering import (
    render_persisted_attention_digest_text,
    render_source_activity_digest_text,
)


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


def _persisted_attention_item(
    suffix: str,
    *,
    source: str = "github",
    priority: str = "medium",
    action: str = "Review persisted attention item",
) -> dict:
    return {
        "id": f"atri_render_{suffix}",
        "triage_result_id": f"atri_render_{suffix}",
        "activity_item_id": f"nact_render_{suffix}",
        "source": source,
        "source_object_id": f"source-object-{suffix}",
        "attention_class": "requires_my_attention",
        "priority": priority,
        "show_in_digest": True,
        "confidence": 0.91,
        "title": f"Persisted attention title {suffix}",
        "safe_summary": f"Safe persisted attention summary {suffix}.",
        "reason": "Reason should remain out of normal rendered text.",
        "recommended_action": action,
        "owner": "me",
        "deadline": "2126-01-02",
        "project": "company-knowledge-os",
        "activity_created_at": "2126-01-01T09:00:00+00:00",
        "triage_created_at": "2126-01-01T10:00:00+00:00",
        "evidence": "1 triage evidence ref",
        "evidence_refs": [
            {
                "kind": "source_event",
                "source_event_id": f"sevt_render_{suffix}",
                "source_system": source,
                "source_object_type": "pull_request",
                "source_object_id": f"safe-object-{suffix}",
                "raw_object_ref": f"raw://render/{suffix}.json",
                "raw_payload": "PRIVATE_RAW_PAYLOAD_DO_NOT_RENDER",
                "provider_payload": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_RENDER",
                "prompt": "PRIVATE_PROMPT_DO_NOT_RENDER",
            }
        ],
        "activity_evidence_refs": [
            {
                "kind": "normalized_activity_item",
                "source_event_id": f"sevt_activity_{suffix}",
            }
        ],
        "activity_available": True,
    }


def _persisted_attention_digest() -> dict:
    return {
        "section_title": "Persisted attention digest",
        "available": True,
        "window": {
            "start_at": "2126-01-01T00:00:00+00:00",
            "end_at": "2126-01-02T00:00:00+00:00",
        },
        "section_labels": {
            "work_actions": "Work actions requiring my attention",
            "manual_actions": "Manual actions",
            "waiting_external_reply": "Waiting for external reply",
            "work_info": "Important project updates",
            "review_optional": "Review optional",
        },
        "counts": {
            "total": 6,
            "visible": 5,
            "hidden": 1,
            "shown": 5,
            "by_attention_class": {
                "important_info": 1,
                "manual_action": 1,
                "requires_my_attention": 1,
                "review_optional": 1,
                "waiting_on_external": 1,
            },
            "by_priority": {
                "high": 1,
                "low": 2,
                "medium": 2,
            },
            "by_show_in_digest": {
                "false": 1,
                "true": 5,
            },
            "by_source": {
                "github": 3,
                "jira": 2,
            },
        },
        "groups": {
            "work_actions": [
                _persisted_attention_item(
                    "work",
                    source="github",
                    priority="high",
                    action="Review the pull request",
                )
            ],
            "manual_actions": [
                _persisted_attention_item(
                    "manual",
                    source="jira",
                    action="Complete the manual Jira update",
                )
            ],
            "waiting_external_reply": [
                _persisted_attention_item(
                    "waiting",
                    source="gmail",
                    action="Wait for the external reply",
                )
            ],
            "work_info": [
                _persisted_attention_item(
                    "info",
                    source="drive",
                    priority="low",
                    action="Review the project update",
                )
            ],
            "review_optional": [
                _persisted_attention_item(
                    "optional",
                    source="github",
                    priority="low",
                    action="Review if time permits",
                )
            ],
        },
        "hidden_low_priority_summary": {
            "total": 1,
            "counts": {"no-action low-priority items": 1},
            "items": [
                {
                    "title": "Hidden private item should not render",
                    "safe_summary": "Hidden private summary should not render",
                }
            ],
        },
        "data_quality_notes": [
            "1 visible attention items were rendered without normalized activity enrichment."
        ],
        "metadata": {
            "source_model": "attention_triage_results",
            "enrichment_model": "normalized_activity_items",
            "group_limit": 20,
            "truncated": False,
            "llm_used": False,
            "read_model_only": True,
            "source_activity_digest_replaced": False,
        },
    }


def _empty_persisted_attention_digest() -> dict:
    digest = _persisted_attention_digest()
    digest["counts"] = {
        "total": 0,
        "visible": 0,
        "hidden": 0,
        "shown": 0,
        "by_attention_class": {},
        "by_priority": {},
        "by_show_in_digest": {},
        "by_source": {},
    }
    digest["groups"] = {
        "work_actions": [],
        "manual_actions": [],
        "waiting_external_reply": [],
        "work_info": [],
        "review_optional": [],
    }
    digest["hidden_low_priority_summary"] = {"total": 0, "counts": {}}
    digest["data_quality_notes"] = []
    return digest


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


def test_render_persisted_attention_digest_text_renders_all_visible_sections() -> None:
    rendered = render_persisted_attention_digest_text(_persisted_attention_digest())

    assert "Persisted attention digest" in rendered
    assert (
        "Window: 2126-01-01T00:00:00+00:00 to 2126-01-02T00:00:00+00:00"
        in rendered
    )
    assert "Total attention items: 6" in rendered
    assert "Visible items: 5" in rendered
    assert "Hidden items: 1" in rendered
    assert "Work actions requiring my attention:" in rendered
    assert "Manual actions:" in rendered
    assert "Waiting for external reply:" in rendered
    assert "Important project updates:" in rendered
    assert "Review optional:" in rendered
    assert rendered.index("Work actions requiring my attention:") < rendered.index(
        "Manual actions:"
    )
    assert rendered.index("Manual actions:") < rendered.index("Waiting for external reply:")
    assert rendered.index("Waiting for external reply:") < rendered.index(
        "Important project updates:"
    )
    assert rendered.index("Important project updates:") < rendered.index(
        "Review optional:"
    )
    assert "1. Persisted attention title work" in rendered
    assert "Source: github" in rendered
    assert "Priority: high" in rendered
    assert "Action: Review the pull request" in rendered
    assert "Owner/deadline: me, 2126-01-02" in rendered
    assert "Project: company-knowledge-os" in rendered
    assert "Summary: Safe persisted attention summary work." in rendered
    assert "Evidence: 1 triage evidence ref" in rendered
    assert (
        "Persisted attention data quality note: 1 visible attention items were rendered without normalized activity enrichment."
        in rendered
    )
    assert "does not infer decisions, tasks, or risks" in rendered


def test_render_persisted_attention_digest_text_hidden_summary_is_count_only() -> None:
    rendered = render_persisted_attention_digest_text(_persisted_attention_digest())

    assert "Hidden low-priority summary:" in rendered
    assert "- 1 no-action low-priority items" in rendered
    assert "Hidden private item should not render" not in rendered
    assert "Hidden private summary should not render" not in rendered


def test_render_persisted_attention_digest_text_renders_empty_state() -> None:
    rendered = render_persisted_attention_digest_text(_empty_persisted_attention_digest())

    assert "Persisted attention digest" in rendered
    assert "Total attention items: 0" in rendered
    assert "No persisted attention items found for this window." in rendered
    assert "Work actions requiring my attention:" in rendered
    assert "- None" in rendered
    assert "Hidden low-priority summary: 0 hidden" in rendered


def test_render_persisted_attention_digest_text_debug_evidence_uses_safe_keys() -> None:
    rendered = render_persisted_attention_digest_text(
        _persisted_attention_digest(),
        debug_evidence=True,
    )

    assert "Debug evidence refs:" in rendered
    assert "kind=source_event" in rendered
    assert "source_event_id=sevt_render_work" in rendered
    assert "source_system=github" in rendered
    assert "source_object_id=safe-object-work" in rendered
    assert "raw_object_ref=raw://render/work.json" in rendered
    assert "Debug activity evidence refs:" in rendered
    assert "kind=normalized_activity_item" in rendered
    assert "PRIVATE_RAW_PAYLOAD_DO_NOT_RENDER" not in rendered
    assert "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_RENDER" not in rendered
    assert "PRIVATE_PROMPT_DO_NOT_RENDER" not in rendered
    assert "raw_payload=" not in rendered
    assert "provider_payload=" not in rendered
    assert "prompt=" not in rendered


def test_render_persisted_attention_digest_text_omits_raw_provider_prompt_payloads() -> None:
    digest = _persisted_attention_digest()
    digest["groups"]["work_actions"][0] |= {
        "raw_text": "PRIVATE_RAW_TEXT_DO_NOT_RENDER",
        "raw_payload": {"body": "PRIVATE_RAW_PAYLOAD_DO_NOT_RENDER"},
        "provider_payload": {"body": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_RENDER"},
        "prompt": "PRIVATE_PROMPT_DO_NOT_RENDER",
        "source_payload": {"body": "PRIVATE_SOURCE_PAYLOAD_DO_NOT_RENDER"},
    }

    rendered = render_persisted_attention_digest_text(digest)

    assert "PRIVATE_RAW_TEXT_DO_NOT_RENDER" not in rendered
    assert "PRIVATE_RAW_PAYLOAD_DO_NOT_RENDER" not in rendered
    assert "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_RENDER" not in rendered
    assert "PRIVATE_PROMPT_DO_NOT_RENDER" not in rendered
    assert "PRIVATE_SOURCE_PAYLOAD_DO_NOT_RENDER" not in rendered
    assert "raw_text" not in rendered
    assert "raw_payload" not in rendered
    assert "provider_payload" not in rendered
    assert "prompt" not in rendered
    assert "source_payload" not in rendered


def test_render_persisted_attention_digest_text_leaves_source_activity_renderer_unchanged() -> None:
    rendered = render_source_activity_digest_text(_non_empty_digest())

    assert "Source activity digest" in rendered
    assert "Persisted attention digest" not in rendered
    assert "Entries: 1 shown, limit 1" in rendered
