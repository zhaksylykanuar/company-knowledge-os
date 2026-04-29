import builtins
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.services.digest import build_source_activity_digest


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
) -> str:
    event_id = f"evt_digest_{unique}_{suffix}"
    source_event_id = f"sevt_digest_{unique}_{suffix}"
    raw_object_ref = f"raw://digest-test/{unique}/{suffix}.json"

    async with AsyncSessionLocal() as session:
        session.add(
            IngestedEvent(
                event_id=event_id,
                event_type=event_type,
                source_system=source_system,
                source_object_id=f"object-{unique}-{suffix}",
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
                source_object_id=f"object-{unique}-{suffix}",
                source_event_ts=event_time,
                actor_external_id=f"actor-{unique}",
                title=title,
                summary=summary,
                source_url=f"https://example.invalid/{unique}/{suffix}",
                raw_object_ref=raw_object_ref,
                evidence_refs=[
                    {
                        "kind": "ingested_event",
                        "event_id": event_id,
                        "source_system": source_system,
                        "source_object_id": f"object-{unique}-{suffix}",
                        "raw_object_ref": raw_object_ref,
                    }
                ],
                metadata_json={
                    "trace_id": f"trace_digest_{unique}_{suffix}",
                    "correlation_id": f"corr_digest_{unique}_{suffix}",
                },
                schema_version="1.0",
            )
        )
        await session.commit()

    return source_event_id


async def test_build_source_activity_digest_returns_empty_digest_for_empty_window() -> None:
    digest = await build_source_activity_digest(
        start_at=_utc(2098, 1, 1),
        end_at=_utc(2098, 1, 2),
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
    assert digest["metadata"]["llm_used"] is False


async def test_build_source_activity_digest_rejects_naive_window() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await build_source_activity_digest(
            start_at=datetime(2098, 1, 1),
            end_at=_utc(2098, 1, 2),
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
        assert matching_entries[0]["evidence_refs"]
        assert matching_entries[0]["evidence_refs"][0]["kind"] == "source_event"
        assert matching_entries[0]["evidence_refs"][0]["source_event_id"] == inside_id

    finally:
        await _cleanup_digest_fixture(unique)


async def test_build_source_activity_digest_omits_raw_body_text_and_does_not_import_openai(
    monkeypatch,
) -> None:
    unique = uuid4().hex
    raw_body = (
        "Full raw message body should stay out of the digest response. "
        "It may contain long customer context that belongs in raw storage."
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
        )

        serialized = json.dumps(digest, sort_keys=True)

        assert raw_body not in serialized
        assert digest["metadata"]["llm_used"] is False

    finally:
        await _cleanup_digest_fixture(unique)
