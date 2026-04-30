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
