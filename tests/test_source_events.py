from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.services.source_events import (
    SourceEventContractValidationError,
    normalize_ingested_event_to_source_event,
)


@pytest.mark.asyncio
async def test_normalize_ingested_event_to_source_event_is_raw_event_first_and_traceable() -> None:
    suffix = uuid4().hex
    event_id = f"evt_test_{suffix}"
    idempotency_key = f"idem_test_{suffix}"

    async with AsyncSessionLocal() as session:
        ingested_event = IngestedEvent(
            event_id=event_id,
            event_type="github.pull_request.opened",
            source_system="github",
            source_object_id="company-knowledge-os/pull/123",
            idempotency_key=idempotency_key,
            correlation_id=f"corr_{suffix}",
            trace_id=f"trace_{suffix}",
            raw_object_ref=f"raw://github/events/{suffix}.json",
            payload={
                "source_object_type": "pull_request",
                "title": "Add source event foundation",
                "summary": "A pull request was opened for source event normalization.",
                "actor_external_id": "github:user-123",
                "source_url": "https://example.invalid/company-knowledge-os/pull/123",
            },
        )
        session.add(ingested_event)
        await session.flush()

        source_event = await normalize_ingested_event_to_source_event(session, ingested_event)

        assert source_event.ingested_event_id == event_id
        assert source_event.source_system == "github"
        assert source_event.source_object_type == "pull_request"
        assert source_event.source_object_id == "company-knowledge-os/pull/123"
        assert source_event.event_type == "github.pull_request.opened"
        assert source_event.raw_object_ref == ingested_event.raw_object_ref
        assert source_event.title == "Add source event foundation"
        assert source_event.actor_external_id == "github:user-123"
        assert source_event.evidence_refs == [
            {
                "kind": "ingested_event",
                "event_id": event_id,
                "source_system": "github",
                "source_object_id": "company-knowledge-os/pull/123",
                "raw_object_ref": f"raw://github/events/{suffix}.json",
            }
        ]

        await session.commit()

    async with AsyncSessionLocal() as session:
        ingested_event = await session.scalar(
            select(IngestedEvent).where(IngestedEvent.event_id == event_id)
        )
        assert ingested_event is not None

        source_event_again = await normalize_ingested_event_to_source_event(
            session,
            ingested_event,
        )
        assert source_event_again.ingested_event_id == event_id

        matching_count = await session.scalar(
            select(func.count(SourceEvent.id)).where(SourceEvent.ingested_event_id == event_id)
        )
        assert matching_count == 1

        await session.rollback()


@pytest.mark.asyncio
async def test_normalize_ingested_event_rejects_contract_invalid_event_before_source_event_creation() -> None:
    suffix = uuid4().hex
    event_id = f"evt_test_invalid_{suffix}"

    async with AsyncSessionLocal() as session:
        ingested_event = IngestedEvent(
            event_id=event_id,
            event_type="github.pull_request.opened",
            source_system="github",
            source_object_id="company-knowledge-os/pull/456",
            idempotency_key=f"idem_test_invalid_{suffix}",
            correlation_id=f"corr_invalid_{suffix}",
            trace_id=f"trace_invalid_{suffix}",
            raw_object_ref=f"raw://github/events/invalid-{suffix}.json",
            payload={
                "source_object_type": "pull_request",
                "title": "Missing source URL",
            },
        )
        session.add(ingested_event)
        await session.flush()

        with pytest.raises(SourceEventContractValidationError) as exc_info:
            await normalize_ingested_event_to_source_event(session, ingested_event)

        assert "missing required payload field: source_url" in str(exc_info.value)

        matching_count = await session.scalar(
            select(func.count(SourceEvent.id)).where(SourceEvent.ingested_event_id == event_id)
        )
        assert matching_count == 0

        await session.rollback()
