from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.services.source_events import normalize_ingested_event_to_source_event
from tests.integration_fixture_loader import load_integration_fixture


FIXTURE_REFS = [
    ("github", "pull_request_opened.json"),
    ("jira", "issue_status_changed.json"),
    ("telegram", "command_received.json"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("source_system", "fixture_name"), FIXTURE_REFS)
async def test_connector_fixture_normalizes_to_traceable_source_event(
    source_system: str,
    fixture_name: str,
) -> None:
    fixture = load_integration_fixture(source_system, fixture_name)
    suffix = uuid4().hex

    event_id = f"evt_fixture_{source_system}_{suffix}"
    raw_object_ref = f'{fixture["raw_object_ref"]}?test_run={suffix}'

    async with AsyncSessionLocal() as session:
        ingested_event = IngestedEvent(
            event_id=event_id,
            event_type=fixture["event_type"],
            source_system=fixture["source_system"],
            source_object_id=f'{fixture["source_object_id"]}#{suffix}',
            idempotency_key=f'{fixture["idempotency_key"]}-{suffix}',
            correlation_id=f"corr_fixture_{suffix}",
            trace_id=f"trace_fixture_{suffix}",
            raw_object_ref=raw_object_ref,
            payload=fixture["payload"],
        )
        session.add(ingested_event)
        await session.flush()

        source_event = await normalize_ingested_event_to_source_event(session, ingested_event)

        assert source_event.ingested_event_id == event_id
        assert source_event.source_system == fixture["source_system"]
        assert source_event.source_object_type == fixture["source_object_type"]
        assert source_event.event_type == fixture["event_type"]
        assert source_event.source_object_id == f'{fixture["source_object_id"]}#{suffix}'
        assert source_event.raw_object_ref == raw_object_ref
        assert source_event.evidence_refs == [
            {
                "kind": "ingested_event",
                "event_id": event_id,
                "source_system": fixture["source_system"],
                "source_object_id": f'{fixture["source_object_id"]}#{suffix}',
                "raw_object_ref": raw_object_ref,
            }
        ]

        matching_count = await session.scalar(
            select(func.count(SourceEvent.id)).where(SourceEvent.ingested_event_id == event_id)
        )
        assert matching_count == 1

        await session.rollback()
