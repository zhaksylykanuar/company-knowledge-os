import builtins
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.gmail_models import EmailThreadState
from app.db.models import IngestedEvent
from app.services.digest import _visible_source_events, build_source_activity_digest


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


async def _cleanup_digest_fixture(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_event_id.like(f"sevt_digest_{unique}_%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.event_id.like(f"evt_digest_{unique}_%")
            )
        )
        await session.execute(
            delete(EmailThreadState).where(
                EmailThreadState.thread_key.like(f"gmail:test:{unique}:%")
            )
        )
        await session.commit()


async def _insert_source_event(
    *,
    unique: str,
    suffix: str,
    source_system: str,
    source_object_type: str,
    event_type: str,
    event_time: datetime,
    title: str,
    summary: str | None = None,
    payload: dict | None = None,
    source_object_id: str | None = None,
    source_url: str | None = None,
    metadata_json: dict | None = None,
) -> str:
    event_id = f"evt_digest_{unique}_{suffix}"
    source_event_id = f"sevt_digest_{unique}_{suffix}"
    raw_object_ref = f"raw://digest-test/{unique}/{suffix}.json"
    object_id = source_object_id or f"object-{unique}-{suffix}"

    async with AsyncSessionLocal() as session:
        session.add(
            IngestedEvent(
                event_id=event_id,
                event_type=event_type,
                source_system=source_system,
                source_object_id=object_id,
                idempotency_key=f"idem_digest_{unique}_{suffix}",
                correlation_id=f"corr_digest_{unique}_{suffix}",
                trace_id=f"trace_digest_{unique}_{suffix}",
                raw_object_ref=raw_object_ref,
                payload=payload or {},
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=source_event_id,
                source_event_key=f"{source_system}:{source_object_type}:{unique}:{suffix}",
                ingested_event_id=event_id,
                event_type=event_type,
                source_system=source_system,
                source_object_type=source_object_type,
                source_object_id=object_id,
                source_event_ts=event_time,
                actor_external_id=f"actor-{unique}",
                title=title,
                summary=summary,
                source_url=source_url,
                raw_object_ref=raw_object_ref,
                evidence_refs=[
                    {
                        "kind": "ingested_event",
                        "event_id": event_id,
                        "source_system": source_system,
                        "source_object_id": object_id,
                        "raw_object_ref": raw_object_ref,
                    }
                ],
                metadata_json=metadata_json
                or {
                    "trace_id": f"trace_digest_{unique}_{suffix}",
                    "correlation_id": f"corr_digest_{unique}_{suffix}",
                },
                schema_version="1.0",
            )
        )
        await session.commit()

    return source_event_id


async def _insert_email_thread_state(
    *,
    unique: str,
    suffix: str,
    status: str,
    last_message_at: datetime,
    stored_days_without_reply: int | None,
    messages_count: int,
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            EmailThreadState(
                source="gmail",
                thread_key=f"gmail:test:{unique}:{suffix}",
                provider_thread_id=None,
                subject_normalized="fake digest thread",
                subject_display="Fake digest thread",
                participants_json=[
                    {"participant_key": "fake-me", "is_me": True},
                    {"participant_key": "fake-external", "is_me": False},
                ],
                first_message_at=last_message_at,
                last_message_at=last_message_at,
                last_message_from="fake-external",
                last_message_direction="from_external",
                last_message_summary="Fake latest message needs a reply.",
                thread_summary="Fake thread summary for operator review.",
                status=status,
                days_without_reply=stored_days_without_reply,
                messages_count=messages_count,
                evidence_refs=[
                    {
                        "kind": "gmail_message",
                        "source_system": "gmail",
                        "message_id": "fake-message-id",
                        "raw_object_ref": "raw://fake/thread/message.json",
                    }
                ],
                metadata_json={
                    "last_message_from_display": "external sender",
                    "last_message_to_display": ["me"],
                    "participants_display": "me, 1 external participant",
                },
                computed_at=_utc(2125, 1, 1),
            )
        )
        await session.commit()


def test_visible_source_events_suppresses_raw_gmail_when_thread_state_exists() -> None:
    gmail_event = SourceEvent(
        source_event_id="sevt_digest_fake_gmail",
        source_event_key="gmail:message:fake",
        ingested_event_id="evt_digest_fake_gmail",
        event_type="gmail.message.ingested",
        source_system="gmail",
        source_object_type="message",
        source_object_id="fake-gmail-object",
        title="Fake Gmail source event",
        raw_object_ref="raw://fake/gmail.json",
        schema_version="1.0",
    )
    drive_event = SourceEvent(
        source_event_id="sevt_digest_fake_drive",
        source_event_key="drive:file:fake",
        ingested_event_id="evt_digest_fake_drive",
        event_type="drive.file.ingested",
        source_system="drive",
        source_object_type="file",
        source_object_id="fake-drive-object",
        title="Fake Drive source event",
        raw_object_ref="raw://fake/drive.json",
        schema_version="1.0",
    )

    visible_events = _visible_source_events(
        [gmail_event, drive_event],
        email_thread_intelligence={
            "metadata": {"raw_gmail_entries_suppressed": True},
            "groups": {
                "needs_my_reply": [
                    {
                        "status": "needs_my_reply",
                        "evidence_refs": [{"kind": "gmail_message"}],
                    }
                ],
            },
        },
    )

    assert visible_events == [drive_event]


def test_visible_source_events_keeps_raw_gmail_when_thread_state_empty() -> None:
    gmail_event = SourceEvent(
        source_event_id="sevt_digest_fake_gmail_fallback",
        source_event_key="gmail:message:fake-fallback",
        ingested_event_id="evt_digest_fake_gmail_fallback",
        event_type="gmail.message.ingested",
        source_system="gmail",
        source_object_type="message",
        source_object_id="fake-gmail-object-fallback",
        title="Fake Gmail fallback source event",
        raw_object_ref="raw://fake/gmail-fallback.json",
        schema_version="1.0",
    )

    visible_events = _visible_source_events(
        [gmail_event],
        email_thread_intelligence={
            "metadata": {"raw_gmail_entries_suppressed": False},
            "groups": {
                "needs_my_reply": [],
                "waiting_for_external_reply": [],
                "informational": [],
            },
        },
    )

    assert visible_events == [gmail_event]


async def test_build_source_activity_digest_returns_empty_digest_for_empty_window() -> None:
    digest = await build_source_activity_digest(
        start_at=_utc(2098, 1, 1),
        end_at=_utc(2098, 1, 2),
        generated_at=_utc(2098, 1, 2),
    )

    assert digest["digest_type"] == "source_activity"
    assert digest["window"] == {
        "start_at": "2098-01-01T00:00:00+00:00",
        "end_at": "2098-01-02T00:00:00+00:00",
    }
    assert digest["counts"] == {
        "total": 0,
        "by_source_system": {},
        "by_event_type": {},
        "by_source_object_type": {},
    }
    assert digest["entries"] == []
    assert digest["metadata"] == {
        "generated_at": "2098-01-02T00:00:00+00:00",
        "entry_limit": 20,
        "entry_count": 0,
        "truncated": False,
        "source_model": "source_events",
        "debug_evidence": False,
        "llm_used": False,
        "source_event_scan_limit": 200,
        "source_event_scan_count": 0,
        "duplicate_source_events_collapsed": False,
    }
    assert digest["source_event_data_quality"] == {
        "hidden_mock_example_event_count": 0,
        "notes": [],
    }


async def test_build_source_activity_digest_rejects_naive_window() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await build_source_activity_digest(
            start_at=datetime(2098, 1, 1),
            end_at=_utc(2098, 1, 2),
        )


async def test_build_source_activity_digest_rejects_naive_generated_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await build_source_activity_digest(
            start_at=_utc(2098, 1, 1),
            end_at=_utc(2098, 1, 2),
            generated_at=datetime(2098, 1, 2),
        )


async def test_build_source_activity_digest_includes_only_events_inside_window() -> None:
    unique = uuid4().hex
    await _cleanup_digest_fixture(unique)

    try:
        inside_id = await _insert_source_event(
            unique=unique,
            suffix="inside",
            source_system="gmail",
            source_object_type="message",
            event_type="gmail.message.ingested",
            event_time=_utc(2099, 1, 1, 12),
            title="Digest-safe Gmail subject",
        )
        outside_id = await _insert_source_event(
            unique=unique,
            suffix="outside",
            source_system="drive",
            source_object_type="file",
            event_type="drive.file.ingested",
            event_time=_utc(2099, 1, 3, 12),
            title="Outside digest window",
        )

        digest = await build_source_activity_digest(
            start_at=_utc(2099, 1, 1),
            end_at=_utc(2099, 1, 2),
            generated_at=_utc(2099, 1, 2),
        )

        matching_entries = [
            entry
            for entry in digest["entries"]
            if entry["source_event_id"].startswith(f"sevt_digest_{unique}_")
        ]

        assert digest["counts"]["by_source_system"]["gmail"] >= 1
        assert "drive" not in {
            entry["source_system"]
            for entry in matching_entries
        }
        assert [entry["source_event_id"] for entry in matching_entries] == [inside_id]
        assert outside_id not in {
            entry["source_event_id"]
            for entry in digest["entries"]
        }
        assert matching_entries[0]["event_type"] == "gmail.message.ingested"
        assert matching_entries[0]["evidence"] == "1 event"
        assert "evidence_refs" not in matching_entries[0]

    finally:
        await _cleanup_digest_fixture(unique)


async def test_build_source_activity_digest_debug_evidence_includes_raw_refs() -> None:
    unique = uuid4().hex
    await _cleanup_digest_fixture(unique)

    try:
        inside_id = await _insert_source_event(
            unique=unique,
            suffix="debug",
            source_system="drive",
            source_object_type="file",
            event_type="drive.file.ingested",
            event_time=_utc(2099, 3, 1, 12),
            title="Digest-safe debug file",
        )

        digest = await build_source_activity_digest(
            start_at=_utc(2099, 3, 1),
            end_at=_utc(2099, 3, 2),
            generated_at=_utc(2099, 3, 2),
            debug_evidence=True,
        )

        matching_entries = [
            entry
            for entry in digest["entries"]
            if entry["source_event_id"] == inside_id
        ]

        assert matching_entries[0]["evidence_refs"]
        assert matching_entries[0]["evidence_refs"][0]["kind"] == "source_event"
        assert matching_entries[0]["evidence_refs"][0]["source_event_id"] == inside_id
        assert digest["metadata"]["debug_evidence"] is True

    finally:
        await _cleanup_digest_fixture(unique)


async def test_build_source_activity_digest_recomputes_email_days_from_generated_at() -> None:
    unique = uuid4().hex
    await _cleanup_digest_fixture(unique)

    try:
        await _insert_email_thread_state(
            unique=unique,
            suffix="needs",
            status="needs_my_reply",
            last_message_at=_utc(2125, 1, 1),
            stored_days_without_reply=999,
            messages_count=2,
        )

        digest = await build_source_activity_digest(
            start_at=_utc(2125, 1, 1),
            end_at=_utc(2125, 1, 2),
            generated_at=_utc(2125, 1, 4),
        )

        thread = digest["email_thread_intelligence"]["groups"]["needs_my_reply"][0]

        assert thread["subject"] == "Fake digest thread"
        assert thread["days_without_reply"] == 3
        assert thread["evidence"] == "1 thread, 2 messages"
        assert thread["last_message_from"] == "external sender"
        assert thread["last_message_to"] == "me"
        assert thread["participants"] == "me, 1 external participant"
        assert "evidence_refs" not in thread

    finally:
        await _cleanup_digest_fixture(unique)


async def test_build_source_activity_digest_deduplicates_repeated_github_pr_events() -> None:
    unique = uuid4().hex
    await _cleanup_digest_fixture(unique)

    try:
        for suffix in ("one", "two", "three"):
            await _insert_source_event(
                unique=unique,
                suffix=suffix,
                source_system="github",
                source_object_type="pull_request",
                source_object_id=f"fake-pr-{unique}",
                event_type="github.pull_request.opened",
                event_time=_utc(2099, 4, 1, 12),
                title="Fake PR opened",
            )

        digest = await build_source_activity_digest(
            start_at=_utc(2099, 4, 1),
            end_at=_utc(2099, 4, 2),
            generated_at=_utc(2099, 4, 2),
            limit=10,
        )

        matching_entries = [
            entry
            for entry in digest["entries"]
            if entry["source_system"] == "github"
            and entry["source_object_type"] == "pull_request"
            and entry["event_type"] == "github.pull_request.opened"
            and entry["source_object_id"] == f"fake-pr-{unique}"
        ]

        assert len(matching_entries) == 1
        assert matching_entries[0]["seen_count"] == 3
        assert matching_entries[0]["repeated_count"] == 3
        assert matching_entries[0]["evidence"] == "3 events"
        assert digest["metadata"]["duplicate_source_events_collapsed"] is True

    finally:
        await _cleanup_digest_fixture(unique)


async def test_build_source_activity_digest_hides_mock_example_events() -> None:
    unique = uuid4().hex
    await _cleanup_digest_fixture(unique)

    try:
        await _insert_source_event(
            unique=unique,
            suffix="visible",
            source_system="github",
            source_object_type="pull_request",
            source_object_id=f"fake-visible-pr-{unique}",
            event_type="github.pull_request.opened",
            event_time=_utc(2099, 5, 1, 12),
            title="Visible fake PR event",
        )
        await _insert_source_event(
            unique=unique,
            suffix="example",
            source_system="github",
            source_object_type="pull_request",
            source_object_id=f"fake-example-pr-{unique}",
            event_type="github.pull_request.opened",
            event_time=_utc(2099, 5, 1, 12),
            title="Hidden example PR event",
            source_url="https://example.invalid/fake-pr",
        )

        digest = await build_source_activity_digest(
            start_at=_utc(2099, 5, 1),
            end_at=_utc(2099, 5, 2),
            generated_at=_utc(2099, 5, 2),
            limit=10,
        )

        titles = {entry["title"] for entry in digest["entries"]}

        assert "Visible fake PR event" in titles
        assert "Hidden example PR event" not in titles
        assert digest["source_event_data_quality"]["hidden_mock_example_event_count"] == 1
        assert digest["source_event_data_quality"]["notes"] == [
            "Hidden 1 mock/example source events from production activity."
        ]

    finally:
        await _cleanup_digest_fixture(unique)


async def test_build_source_activity_digest_omits_raw_body_text_and_does_not_import_openai(
    monkeypatch,
) -> None:
    unique = uuid4().hex
    raw_body = (
        "Full raw message body should stay out of the digest response. "
        "It may contain long fixture context that belongs in raw storage."
    )
    await _cleanup_digest_fixture(unique)

    try:
        await _insert_source_event(
            unique=unique,
            suffix="body",
            source_system="telegram",
            source_object_type="message",
            event_type="telegram.message.received",
            event_time=_utc(2099, 2, 1, 12),
            title="Founder note received",
            summary=raw_body,
            payload={"text": raw_body},
        )

        real_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "openai" or name.startswith("openai."):
                raise AssertionError("digest builder must not import OpenAI")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", guarded_import)

        digest = await build_source_activity_digest(
            start_at=_utc(2099, 2, 1),
            end_at=_utc(2099, 2, 2),
            generated_at=_utc(2099, 2, 2),
        )

        serialized = json.dumps(digest, sort_keys=True)

        assert raw_body not in serialized
        assert digest["metadata"]["llm_used"] is False

    finally:
        await _cleanup_digest_fixture(unique)
