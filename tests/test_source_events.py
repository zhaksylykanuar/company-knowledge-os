from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.services.source_events import (
    SourceEventContractValidationError,
    normalize_ingested_event_to_source_event,
    project_source_event_read_model,
)


def test_project_source_event_read_model_preserves_traceable_fields() -> None:
    event_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    created_at = datetime(2026, 1, 2, 3, 5, 0, tzinfo=timezone.utc)
    evidence_refs = [
        {
            "kind": "ingested_event",
            "event_id": "evt_123",
            "source_system": "github",
            "source_object_id": "org/repo/pull/123",
            "raw_object_ref": "raw://github/events/123.json",
        }
    ]
    source_event = SourceEvent(
        source_event_id="sevt_123",
        source_event_key="github:pull_request:org/repo/pull/123:github.pull_request.opened:idem_123",
        ingested_event_id="evt_123",
        event_type="github.pull_request.opened",
        source_system="github",
        source_object_type="pull_request",
        source_object_id="org/repo/pull/123",
        source_event_ts=event_time,
        actor_external_id="github:user-123",
        title="Add source event read model",
        summary="A pull request was opened.",
        source_url="https://example.invalid/org/repo/pull/123",
        raw_object_ref="raw://github/events/123.json",
        evidence_refs=evidence_refs,
        metadata_json={
            "correlation_id": "corr_123",
            "trace_id": "trace_123",
            "unrelated": "not projected",
        },
        schema_version="1.0",
        created_at=created_at,
    )

    read_model = project_source_event_read_model(
        source_event,
        ingested_payload={
            "title": "Payload title",
            "summary": "Payload summary",
            "source_url": "https://example.invalid/org/repo/pull/123",
            "actor_external_id": "github:user-123",
            "raw_body": "not projected",
            "nested": {"not": "projected"},
        },
    )

    assert read_model.source_event_id == "sevt_123"
    assert read_model.source_system == "github"
    assert read_model.source_object_type == "pull_request"
    assert read_model.source_object_id == "org/repo/pull/123"
    assert read_model.event_type == "github.pull_request.opened"
    assert read_model.event_time == event_time
    assert read_model.title == "Add source event read model"
    assert read_model.summary == "A pull request was opened."
    assert read_model.source_url == "https://example.invalid/org/repo/pull/123"
    assert read_model.raw_object_ref == "raw://github/events/123.json"
    assert read_model.trace_id == "trace_123"
    assert read_model.correlation_id == "corr_123"
    assert read_model.evidence_refs == evidence_refs
    assert read_model.payload_subset == {
        "title": "Payload title",
        "summary": "Payload summary",
        "source_url": "https://example.invalid/org/repo/pull/123",
        "actor_external_id": "github:user-123",
    }

    evidence_refs[0]["event_id"] = "mutated"
    assert read_model.evidence_refs[0]["event_id"] == "evt_123"


def test_project_source_event_read_model_falls_back_to_created_at() -> None:
    created_at = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    source_event = SourceEvent(
        source_event_id="sevt_gmail",
        source_event_key="gmail:message:m1:gmail.message.ingested:idem_m1",
        ingested_event_id="evt_gmail",
        event_type="gmail.message.ingested",
        source_system="gmail",
        source_object_type="message",
        source_object_id="m1",
        source_event_ts=None,
        title="FounderOS weekly update",
        summary=None,
        source_url=None,
        raw_object_ref="raw://gmail/m1/h1/message.json",
        evidence_refs=[],
        metadata_json={},
        schema_version="1.0",
        created_at=created_at,
    )

    read_model = project_source_event_read_model(source_event)

    assert read_model.event_time == created_at
    assert read_model.trace_id is None
    assert read_model.correlation_id is None
    assert read_model.payload_subset == {}


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
