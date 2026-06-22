from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete

from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.services.repository_source_inventory import (
    INVENTORY_DISCOVERY_SNAPSHOT,
    INVENTORY_LEGACY_SEED,
    INVENTORY_SOURCE_EVENTS,
    load_repository_source_inventory,
    load_repository_source_inventory_snapshot,
)


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(IngestedEvent.__table__.create, checkfirst=True)
        await conn.run_sync(SourceEvent.__table__.create, checkfirst=True)


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceEvent).where(SourceEvent.source_event_id.like(f"%{marker}%"))
        )
        await session.execute(
            delete(IngestedEvent).where(IngestedEvent.event_id.like(f"%{marker}%"))
        )
        await session.commit()


def _write_discovery(path: Path, repos: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(repos), encoding="utf-8")


def test_repository_inventory_uses_discovery_before_legacy_seed(tmp_path) -> None:
    raw_path = tmp_path / "discovery" / "github" / "snap-1" / "raw" / "repos.json"
    _write_discovery(
        raw_path,
        [
            {
                "name": "source-event-ready",
                "full_name": "org/source-event-ready",
                "updated_at": "2026-06-20T00:00:00+00:00",
            },
            {
                "name": "live-only-repo",
                "full_name": "org/live-only-repo",
                "updated_at": "2026-06-20T01:00:00+00:00",
            },
        ],
    )

    inventory = load_repository_source_inventory_snapshot(
        workspace_path=tmp_path,
        raw_path=raw_path,
        now=datetime(2026, 6, 21, tzinfo=timezone.utc),
    )

    assert inventory["source_class"] == INVENTORY_DISCOVERY_SNAPSHOT
    assert inventory["operational_repo_count"] == 2
    assert inventory["legacy_seed_repo_count"] == 19
    assert inventory["fallback_used"] is False
    assert inventory["source_snapshot"]["snapshot_key"] == "snap-1"
    assert inventory["catalog_drift"]["operational_count"] == 2
    assert "live-only-repo" in inventory["catalog_drift"]["in_operational_not_in_legacy_seed"]
    assert inventory["repo_mapping_policy"] == "repo_is_component_or_evidence_not_jira_project"


def test_repository_inventory_falls_back_to_legacy_seed_when_no_observation(
    tmp_path,
) -> None:
    inventory = load_repository_source_inventory_snapshot(workspace_path=tmp_path)

    assert inventory["source_class"] == INVENTORY_LEGACY_SEED
    assert inventory["operational_repo_count"] == inventory["legacy_seed_repo_count"]
    assert inventory["legacy_seed_repo_count"] == 19
    assert inventory["fallback_used"] is True


async def test_repository_inventory_prefers_source_events_over_discovery(
    tmp_path,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    raw_path = tmp_path / "discovery" / "github" / "snap-2" / "raw" / "repos.json"
    _write_discovery(
        raw_path,
        [
            {
                "name": f"discovery-only-{marker}",
                "full_name": f"org/discovery-only-{marker}",
                "updated_at": "2026-06-20T00:00:00+00:00",
            }
        ],
    )
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                IngestedEvent(
                    event_id=f"ie-repo-inventory-{marker}",
                    event_type="github.pull_request.synchronized",
                    source_system="github",
                    source_object_id=f"org/source-event-repo-{marker}#pull/1",
                    idempotency_key=f"repo-inventory-{marker}",
                    correlation_id=f"corr-repo-inventory-{marker}",
                    trace_id=f"trace-repo-inventory-{marker}",
                    raw_object_ref=f"raw://github/repo-inventory/{marker}",
                    payload={"source_object_type": "pull_request"},
                    status="received",
                )
            )
            await session.flush()
            session.add(
                SourceEvent(
                    source_event_id=f"sevt-repo-inventory-{marker}",
                    source_event_key=f"sevt-key-repo-inventory-{marker}",
                    ingested_event_id=f"ie-repo-inventory-{marker}",
                    event_type="github.pull_request.synchronized",
                    source_system="github",
                    source_object_type="pull_request",
                    source_object_id=f"org/source-event-repo-{marker}#pull/1",
                    title="Source event repo PR",
                    raw_object_ref=f"raw://github/repo-inventory/{marker}",
                    evidence_refs=[],
                    metadata_json={},
                    created_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
                )
            )
            await session.commit()

        async with AsyncSessionLocal() as session:
            inventory = await load_repository_source_inventory(
                session=session,
                workspace_path=tmp_path,
                raw_path=raw_path,
                now=datetime(2026, 6, 21, tzinfo=timezone.utc),
        )

        assert inventory["source_class"] == INVENTORY_SOURCE_EVENTS
        assert inventory["operational_repo_count"] >= 1
        assert inventory["source_event_repo_count"] >= 1
        repo_keys = {item["repo_key"] for item in inventory["repositories"]}
        assert f"source-event-repo-{marker}" in repo_keys
        assert f"discovery-only-{marker}" not in repo_keys
    finally:
        await _cleanup(marker)
