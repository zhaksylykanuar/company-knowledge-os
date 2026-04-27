import pytest
from sqlalchemy import func, select

from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.integrations.connector_ingestion import ingest_connector_payload_to_source_event
from app.integrations.payload_mapper import ConnectorPayloadValidationError
from tests.integration_fixture_loader import load_integration_fixture
from tests.test_integration_fixture_normalization import FIXTURE_REFS


@pytest.mark.asyncio
@pytest.mark.parametrize(("source_system", "fixture_name"), FIXTURE_REFS)
async def test_connector_ingestion_persists_fixture_to_ingested_event_and_source_event(
    source_system: str,
    fixture_name: str,
) -> None:
    fixture = load_integration_fixture(source_system, fixture_name)

    async with AsyncSessionLocal() as session:
        result = await ingest_connector_payload_to_source_event(session, fixture)

        assert result.ingested_event_created is True
        assert result.source_event_created is True

        assert result.ingested_event.event_id.startswith("evt_")
        assert result.ingested_event.source_system == fixture["source_system"]
        assert result.ingested_event.event_type == fixture["event_type"]
        assert result.ingested_event.source_object_id == fixture["source_object_id"]
        assert result.ingested_event.idempotency_key == fixture["idempotency_key"]
        assert result.ingested_event.raw_object_ref == fixture["raw_object_ref"]
        assert result.ingested_event.payload == fixture["payload"]

        assert result.source_event.ingested_event_id == result.ingested_event.event_id
        assert result.source_event.source_system == fixture["source_system"]
        assert result.source_event.source_object_type == fixture["source_object_type"]
        assert result.source_event.source_object_id == fixture["source_object_id"]
        assert result.source_event.event_type == fixture["event_type"]
        assert result.source_event.raw_object_ref == fixture["raw_object_ref"]
        assert result.source_event.evidence_refs == [
            {
                "kind": "ingested_event",
                "event_id": result.ingested_event.event_id,
                "source_system": fixture["source_system"],
                "source_object_id": fixture["source_object_id"],
                "raw_object_ref": fixture["raw_object_ref"],
            }
        ]

        await session.rollback()


@pytest.mark.asyncio
async def test_connector_ingestion_is_idempotent_for_same_payload() -> None:
    fixture = load_integration_fixture("github", "pull_request_opened.json")

    async with AsyncSessionLocal() as session:
        first = await ingest_connector_payload_to_source_event(session, fixture)
        second = await ingest_connector_payload_to_source_event(session, fixture)

        assert first.ingested_event.event_id == second.ingested_event.event_id
        assert first.source_event.source_event_id == second.source_event.source_event_id

        assert first.ingested_event_created is True
        assert first.source_event_created is True
        assert second.ingested_event_created is False
        assert second.source_event_created is False

        ingested_count = await session.scalar(
            select(func.count(IngestedEvent.id)).where(
                IngestedEvent.event_id == first.ingested_event.event_id
            )
        )
        source_event_count = await session.scalar(
            select(func.count(SourceEvent.id)).where(
                SourceEvent.ingested_event_id == first.ingested_event.event_id
            )
        )

        assert ingested_count == 1
        assert source_event_count == 1

        await session.rollback()


@pytest.mark.asyncio
async def test_connector_ingestion_rejects_invalid_payload_before_db_write() -> None:
    fixture = load_integration_fixture("github", "pull_request_opened.json")
    fixture.pop("raw_object_ref")

    async with AsyncSessionLocal() as session:
        before_count = await session.scalar(select(func.count(IngestedEvent.id)))

        with pytest.raises(ConnectorPayloadValidationError) as exc_info:
            await ingest_connector_payload_to_source_event(session, fixture)

        after_count = await session.scalar(select(func.count(IngestedEvent.id)))

        assert "missing connector payload fields: raw_object_ref" in str(exc_info.value)
        assert after_count == before_count

        await session.rollback()
