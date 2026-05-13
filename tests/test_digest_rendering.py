import builtins

from app.services.digest_rendering import render_source_activity_digest_text


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
        "metadata": {
            "entry_limit": 20,
            "entry_count": 0,
            "truncated": False,
            "source_model": "source_events",
            "llm_used": False,
        },
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
                "source_url": "https://example.invalid/source/1",
                "summary": raw_body,
                "payload": {"text": raw_body},
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
        "metadata": {
            "entry_limit": 1,
            "entry_count": 1,
            "truncated": True,
            "source_model": "source_events",
            "llm_used": False,
        },
    }


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
            "section_title": "Email threads requiring attention",
            "available": True,
            "counts": {
                "total": 2,
                "active": 2,
                "by_status": {
                    "needs_my_reply": 1,
                    "waiting_for_external_reply": 1,
                },
            },
            "groups": {
                "needs_my_reply": [
                    {
                        "status": "needs_my_reply",
                        "last_message_at": "2125-01-01T12:00:00+00:00",
                        "last_message_direction": "from_external",
                        "days_without_reply": 4,
                        "messages_count": 3,
                        "summary": "Fake customer follow-up needs a response.",
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
                    }
                ],
                "waiting_for_external_reply": [
                    {
                        "status": "waiting_for_external_reply",
                        "last_message_at": "2125-01-01T10:00:00+00:00",
                        "last_message_direction": "from_me",
                        "days_without_reply": 2,
                        "messages_count": 2,
                        "summary": "Fake outbound proposal is waiting.",
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
                "informational": [],
            },
            "data_quality_notes": [
                "Raw Gmail source events are summarized in counts because EmailThreadState rows are available."
            ],
            "metadata": {
                "source_model": "email_thread_states",
                "raw_gmail_entries_suppressed": True,
            },
        },
        "entries": [],
        "metadata": {
            "entry_limit": 20,
            "entry_count": 0,
            "truncated": False,
            "source_model": "source_events",
            "llm_used": False,
        },
    }


def test_render_source_activity_digest_text_renders_empty_state() -> None:
    rendered = render_source_activity_digest_text(_empty_digest())

    assert "Source activity digest" in rendered
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


def test_render_source_activity_digest_text_renders_entries_and_evidence_refs() -> None:
    rendered = render_source_activity_digest_text(_non_empty_digest())

    assert "Entries: 1 shown, limit 1" in rendered
    assert "Entries are truncated by the digest limit." in rendered
    assert "1. 2121-01-01T12:00:00+00:00 | gmail/message | gmail.message.ingested" in rendered
    assert "Title: Digest-safe subject" in rendered
    assert "Source event: sevt_digest_render_1" in rendered
    assert "Source object: gmail-object-1" in rendered
    assert "Source URL: https://example.invalid/source/1" in rendered
    assert "kind=source_event" in rendered
    assert "source_event_id=sevt_digest_render_1" in rendered
    assert "raw_object_ref=raw://digest-render/1.json" in rendered


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

    assert "Email threads requiring attention" in rendered
    assert "Needs my reply:" in rendered
    assert "Waiting for external reply:" in rendered
    assert rendered.index("Needs my reply:") < rendered.index("Waiting for external reply:")
    assert "status=needs_my_reply" in rendered
    assert "direction=from_external" in rendered
    assert "Days without reply: 4" in rendered
    assert "Messages: 3" in rendered
    assert "Fake customer follow-up needs a response." in rendered
    assert "kind=gmail_message" in rendered
    assert "source_object_id=fake-message-1" in rendered
    assert "raw_object_ref=raw://fake-gmail/thread-1/message.json" in rendered
    assert "quote=" not in rendered


def test_render_source_activity_digest_text_falls_back_when_email_threads_empty() -> None:
    digest = _non_empty_digest()
    digest["email_thread_intelligence"] = {
        "section_title": "Email threads requiring attention",
        "available": True,
        "counts": {"total": 0, "active": 0, "by_status": {}},
        "groups": {
            "needs_my_reply": [],
            "waiting_for_external_reply": [],
            "informational": [],
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
