from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.integrations.payload_mapper import map_connector_payload_to_ingested_event
from app.services.source_events import normalize_ingested_event_to_source_event


@dataclass(frozen=True)
class ConnectorIngestionResult:
    ingested_event: IngestedEvent
    source_event: SourceEvent
    ingested_event_created: bool
    source_event_created: bool


async def ingest_connector_payload_to_source_event(
    session: AsyncSession,
    connector_payload: dict[str, Any],
) -> ConnectorIngestionResult:
    """Persist a connector payload through the raw-event-first internal boundary.

    This is deterministic and internal-only:
    connector payload dict -> IngestedEvent -> SourceEvent.

    The caller controls commit/rollback.
    """

    mapped = map_connector_payload_to_ingested_event(connector_payload)

    ingested_event = await session.scalar(
        select(IngestedEvent).where(IngestedEvent.event_id == mapped.event_id)
    )
    ingested_event_created = ingested_event is None

    if ingested_event is None:
        ingested_event = IngestedEvent(**mapped.to_ingested_event_kwargs())
        session.add(ingested_event)
        await session.flush()

    existing_source_event = await session.scalar(
        select(SourceEvent).where(SourceEvent.ingested_event_id == ingested_event.event_id)
    )

    source_event = await normalize_ingested_event_to_source_event(session, ingested_event)

    return ConnectorIngestionResult(
        ingested_event=ingested_event,
        source_event=source_event,
        ingested_event_created=ingested_event_created,
        source_event_created=existing_source_event is None,
    )
