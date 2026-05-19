from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import IngestedEvent
from app.services.attention_triage import NormalizedActivityItem
from app.services.normalized_activity import (
    NormalizedActivityValidationError,
    get_normalized_activity_item,
    record_normalized_activity_item,
)


class _FailingSession:
    def add(self, _record: object) -> None:
        raise AssertionError("invalid activity should fail before session.add")

    async def flush(self) -> None:
        raise AssertionError("invalid activity should fail before session.flush")


async def _ensure_normalized_activity_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(IngestedEvent.__table__.create, checkfirst=True)
        await conn.run_sync(SourceEvent.__table__.create, checkfirst=True)
        await conn.run_sync(NormalizedActivityItemRecord.__table__.create, checkfirst=True)


async def _cleanup_normalized_activity_fixture(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(f"nact_test_{unique}%")
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.source_object_id.like(
                    f"github:test:activity:{unique}%"
                )
            )
        )
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_event_id.like(f"sevt_activity_{unique}%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.event_id.like(f"evt_activity_{unique}%")
            )
        )
        await session.commit()


def _activity(**overrides: object) -> NormalizedActivityItem:
    defaults = {
        "source": "github",
        "source_object_id": "github:test:activity",
        "activity_type": "pull_request.review_requested",
        "title": "Review persistence foundation",
        "actor": "github:fake-user",
        "created_at": datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        "project": "company-knowledge-os",
        "safe_summary": "Review the normalized activity item persistence slice.",
        "related_people": ["github:fake-user", "fake-reviewer"],
        "related_jira_keys": ["FOS-52"],
        "related_prs": ["https://example.test/company-knowledge-os/pull/52"],
        "related_files": ["https://example.test/company-knowledge-os/file.py"],
        "evidence_refs": [
            {
                "kind": "source_event",
                "source_event_id": "sevt_fake",
                "raw_object_ref": "raw://github/events/fake.json",
            }
        ],
    }
    defaults.update(overrides)
    return NormalizedActivityItem.model_validate(defaults)


async def _insert_source_event(unique: str) -> str:
    event_id = f"evt_activity_{unique}"
    source_event_id = f"sevt_activity_{unique}"
    async with AsyncSessionLocal() as session:
        session.add(
            IngestedEvent(
                event_id=event_id,
                event_type="github.pull_request.opened",
                source_system="github",
                source_object_id=f"github:test:activity:{unique}",
                idempotency_key=f"idem_activity_{unique}",
                correlation_id=f"corr_activity_{unique}",
                trace_id=f"trace_activity_{unique}",
                raw_object_ref=f"raw://github/events/activity-{unique}.json",
                payload={
                    "source_object_type": "pull_request",
                    "title": "Review persistence foundation",
                    "source_url": "https://example.test/company-knowledge-os/pull/52",
                },
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=source_event_id,
                source_event_key=f"github:pull_request:{unique}",
                ingested_event_id=event_id,
                event_type="github.pull_request.opened",
                source_system="github",
                source_object_type="pull_request",
                source_object_id=f"github:test:activity:{unique}",
                title="Review persistence foundation",
                raw_object_ref=f"raw://github/events/activity-{unique}.json",
                evidence_refs=[
                    {
                        "kind": "ingested_event",
                        "event_id": event_id,
                        "source_system": "github",
                        "source_object_id": f"github:test:activity:{unique}",
                    }
                ],
                metadata_json={
                    "correlation_id": f"corr_activity_{unique}",
                    "trace_id": f"trace_activity_{unique}",
                },
                schema_version="1.0",
            )
        )
        await session.commit()
    return source_event_id


@pytest.mark.asyncio
async def test_record_normalized_activity_item_persists_and_reads_back_valid_item() -> None:
    await _ensure_normalized_activity_tables()
    unique = uuid4().hex
    await _cleanup_normalized_activity_fixture(unique)
    source_event_id = await _insert_source_event(unique)
    activity_item_id = f"nact_test_{unique}"
    expected = _activity(
        source_object_id=f"github:test:activity:{unique}",
        evidence_refs=[
            {
                "kind": "source_event",
                "source_event_id": source_event_id,
                "raw_object_ref": f"raw://github/events/activity-{unique}.json",
            }
        ],
    )

    try:
        async with AsyncSessionLocal() as session:
            stored = await record_normalized_activity_item(
                session,
                activity=expected,
                source_event_id=source_event_id,
                activity_item_id=activity_item_id,
            )
            await session.commit()

        assert stored.activity_item_id == activity_item_id
        assert stored.source_event_id == source_event_id
        assert stored.source == "github"
        assert stored.source_object_id == f"github:test:activity:{unique}"
        assert stored.activity_type == "pull_request.review_requested"
        assert stored.activity_created_at == expected.created_at
        assert stored.evidence_refs == expected.evidence_refs
        assert stored.to_normalized_activity_item() == expected

        async with AsyncSessionLocal() as session:
            read_back = await get_normalized_activity_item(
                session,
                activity_item_id=activity_item_id,
            )
            record = await session.scalar(
                select(NormalizedActivityItemRecord).where(
                    NormalizedActivityItemRecord.activity_item_id == activity_item_id
                )
            )

        assert read_back is not None
        assert read_back.source_event_id == source_event_id
        assert read_back.evidence_refs == expected.evidence_refs
        assert read_back.to_normalized_activity_item() == expected
        assert record is not None
        assert not hasattr(record, "provider_payload")
        assert not hasattr(record, "raw_payload")
        assert not hasattr(record, "raw_text")
        assert not hasattr(record, "prompt")

    finally:
        await _cleanup_normalized_activity_fixture(unique)


@pytest.mark.asyncio
async def test_invalid_normalized_activity_payload_fails_before_persistence() -> None:
    unique = uuid4().hex
    invalid_payload = {
        "source": "github",
        "source_object_id": f"github:test:activity:{unique}",
        "activity_type": "pull_request.review_requested",
        "title": "Invalid activity",
        "evidence_refs": [{"kind": "source_event", "source_event_id": "sevt_fake"}],
        "provider_payload": {"raw": "must not be persisted"},
    }

    with pytest.raises(NormalizedActivityValidationError, match="invalid"):
        await record_normalized_activity_item(
            _FailingSession(),  # type: ignore[arg-type]
            activity=invalid_payload,
        )


@pytest.mark.asyncio
async def test_invalid_normalized_activity_payload_does_not_create_db_record() -> None:
    await _ensure_normalized_activity_tables()
    unique = uuid4().hex
    await _cleanup_normalized_activity_fixture(unique)

    invalid_payload = {
        "source": "github",
        "source_object_id": f"github:test:activity:{unique}",
        "activity_type": "pull_request.review_requested",
        "evidence_refs": [{"kind": "source_event", "source_event_id": "sevt_fake"}],
        "provider_payload": {"raw": "must not be persisted"},
    }

    try:
        async with AsyncSessionLocal() as session:
            with pytest.raises(NormalizedActivityValidationError, match="invalid"):
                await record_normalized_activity_item(session, activity=invalid_payload)

            count = await session.scalar(
                select(func.count(NormalizedActivityItemRecord.id)).where(
                    NormalizedActivityItemRecord.source_object_id
                    == f"github:test:activity:{unique}"
                )
            )
            assert count == 0
            await session.rollback()

    finally:
        await _cleanup_normalized_activity_fixture(unique)


@pytest.mark.asyncio
async def test_normalized_activity_persistence_preserves_empty_evidence_without_fabrication() -> None:
    await _ensure_normalized_activity_tables()
    unique = uuid4().hex
    await _cleanup_normalized_activity_fixture(unique)

    try:
        async with AsyncSessionLocal() as session:
            stored = await record_normalized_activity_item(
                session,
                activity_item_id=f"nact_test_{unique}",
                activity=_activity(
                    source_object_id=f"github:test:activity:{unique}",
                    evidence_refs=[],
                ),
            )
            await session.commit()

        assert stored.evidence_refs == []

        async with AsyncSessionLocal() as session:
            read_back = await get_normalized_activity_item(
                session,
                activity_item_id=f"nact_test_{unique}",
            )

        assert read_back is not None
        assert read_back.evidence_refs == []

    finally:
        await _cleanup_normalized_activity_fixture(unique)


@pytest.mark.asyncio
async def test_normalized_activity_source_event_id_is_optional() -> None:
    await _ensure_normalized_activity_tables()
    unique = uuid4().hex
    await _cleanup_normalized_activity_fixture(unique)

    try:
        async with AsyncSessionLocal() as session:
            stored = await record_normalized_activity_item(
                session,
                activity_item_id=f"nact_test_{unique}",
                activity=_activity(source_object_id=f"github:test:activity:{unique}"),
            )
            await session.commit()

        assert stored.source_event_id is None

    finally:
        await _cleanup_normalized_activity_fixture(unique)
