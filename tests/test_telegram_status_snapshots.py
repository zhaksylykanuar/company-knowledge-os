from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import SourceEvent
from app.db.graph_models import EntityAliasRecord, EntityLinkRecord, EntityRecord
from app.db.models import IngestedEvent
from app.db.status_models import StatusSnapshotRecord
from app.services.entity_resolution import ENTITY_TYPE_PROJECT, normalize_alias
from app.services.jira_graph_mapping import (
    ENTITY_TYPE_JIRA_PROJECT,
    RELATION_BELONGS_TO,
    jira_entity_id,
)
from app.services.telegram_founder_bot import (
    _ProjectEntity,
    _render_all_project_snapshots,
    build_status_reply_text,
)
from scripts.sync_jira_issues import build_issue_connector_payload, ingest_issue_payloads

NOW = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
PROJECT_ALPHA_ID = "project:a5-2-alpha"
PROJECT_BETA_ID = "project:a5-2-beta"


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(IngestedEvent.__table__.create, checkfirst=True)
        await conn.run_sync(SourceEvent.__table__.create, checkfirst=True)
        await conn.run_sync(EntityRecord.__table__.create, checkfirst=True)
        await conn.run_sync(EntityAliasRecord.__table__.create, checkfirst=True)
        await conn.run_sync(EntityLinkRecord.__table__.create, checkfirst=True)
        await conn.run_sync(StatusSnapshotRecord.__table__.create, checkfirst=True)


async def _cleanup(organization_id: str) -> None:
    project_ids = [PROJECT_ALPHA_ID, PROJECT_BETA_ID]
    jira_ids = [jira_entity_id("ALPHA"), jira_entity_id("BETA")]
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(StatusSnapshotRecord).where(
                StatusSnapshotRecord.organization_id == organization_id
            )
        )
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_object_id.like("ALPHA-%")
                | SourceEvent.source_object_id.like("BETA-%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.source_object_id.like("ALPHA-%")
                | IngestedEvent.source_object_id.like("BETA-%")
            )
        )
        await session.execute(
            delete(EntityLinkRecord).where(
                EntityLinkRecord.from_entity_id.in_(jira_ids)
                | EntityLinkRecord.to_entity_id.in_(project_ids)
            )
        )
        await session.execute(
            delete(EntityAliasRecord).where(
                EntityAliasRecord.entity_id.in_([*project_ids, *jira_ids])
            )
        )
        await session.execute(
            delete(EntityRecord).where(
                EntityRecord.entity_id.in_([*project_ids, *jira_ids])
            )
        )
        await session.commit()


async def _seed_project(
    *,
    project_entity_id: str,
    project_name: str,
    jira_key: str,
) -> None:
    source_id = jira_entity_id(jira_key)
    async with AsyncSessionLocal() as session:
        session.add(
            EntityRecord(
                entity_id=project_entity_id,
                entity_type=ENTITY_TYPE_PROJECT,
                canonical_name=project_name,
                attrs={"test": "a5-2"},
            )
        )
        session.add(
            EntityAliasRecord(
                entity_id=project_entity_id,
                alias=project_name,
                normalized_alias=normalize_alias(project_name),
                source="test",
                confidence=1.0,
                confirmed_by_user=True,
            )
        )
        session.add(
            EntityRecord(
                entity_id=source_id,
                entity_type=ENTITY_TYPE_JIRA_PROJECT,
                canonical_name=jira_key,
                attrs={"jira_key": jira_key},
            )
        )
        session.add(
            EntityLinkRecord(
                link_id=f"{source_id}->{RELATION_BELONGS_TO}->{project_entity_id}",
                from_entity_id=source_id,
                to_entity_id=project_entity_id,
                relation=RELATION_BELONGS_TO,
                evidence_refs=[{"kind": "test", "jira_key": jira_key}],
                confidence=1.0,
            )
        )
        await session.commit()


async def _ingest_issue(
    key: str,
    *,
    status: str = "In Progress",
    assignee: str | None = "Person A",
    updated: str = "2026-06-12T10:00:00+00:00",
    duedate: str | None = None,
    summary: str = "Project Alpha task",
) -> None:
    payload = build_issue_connector_payload(
        {
            "key": key,
            "fields": {
                "summary": summary,
                "status": {"name": status},
                "assignee": {"displayName": assignee} if assignee else None,
                "updated": updated,
                "duedate": duedate,
                "priority": {"name": "Medium"},
                "issuetype": {"name": "Task"},
            },
        },
        site="https://example.invalid",
        jira_project_key=key.split("-", 1)[0],
    )
    assert payload is not None
    await ingest_issue_payloads([payload])


async def _latest_snapshot_count(organization_id: str, entity_id: str) -> int:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(StatusSnapshotRecord)
            .where(StatusSnapshotRecord.organization_id == organization_id)
            .where(StatusSnapshotRecord.entity_id == entity_id)
        )
    return int(count or 0)


async def test_project_reply_starts_with_snapshot_block_and_keeps_detailed_body() -> None:
    organization_id = f"test-org-{uuid4().hex}"
    await _ensure_tables()
    await _cleanup(organization_id)
    try:
        await _seed_project(
            project_entity_id=PROJECT_ALPHA_ID,
            project_name="Project Alpha",
            jira_key="ALPHA",
        )
        await _ingest_issue("ALPHA-101", summary="Project Alpha login task")

        text = await build_status_reply_text(
            now=NOW,
            question_text="что по Project Alpha",
            organization_id=organization_id,
        )

        assert text is not None
        assert text.startswith("🟢 Snapshot: Project Alpha")
        assert "confidence: 0.90" in text
        assert "what_changed: first snapshot" in text
        assert "summary: Project Alpha: green; Jira ALPHA;" in text
        assert "📂 Project Alpha — статус по Jira (ALPHA)" in text
        assert "Всего: 1 задач (открытых 1, закрытых 0)" in text
        assert "[Показать всё] [Скрыть похожее]" in text
        assert await _latest_snapshot_count(organization_id, PROJECT_ALPHA_ID) == 1
    finally:
        await _cleanup(organization_id)


async def test_project_reply_uses_previous_snapshot_for_diff() -> None:
    organization_id = f"test-org-{uuid4().hex}"
    await _ensure_tables()
    await _cleanup(organization_id)
    try:
        await _seed_project(
            project_entity_id=PROJECT_ALPHA_ID,
            project_name="Project Alpha",
            jira_key="ALPHA",
        )
        await _ingest_issue("ALPHA-101", summary="Project Alpha login task")
        first = await build_status_reply_text(
            now=NOW,
            question_text="status Project Alpha",
            organization_id=organization_id,
        )
        assert first is not None
        assert "what_changed: first snapshot" in first

        await _ingest_issue(
            "ALPHA-102",
            assignee=None,
            updated="2026-05-20T10:00:00+00:00",
            summary="Project Alpha stale follow-up",
        )
        second = await build_status_reply_text(
            now=NOW,
            question_text="status Project Alpha",
            organization_id=organization_id,
        )

        assert second is not None
        assert second.startswith("🟡 Snapshot: Project Alpha")
        assert "what_changed:" in second
        assert "status_color: green -> yellow" in second
        assert "current_work added: ALPHA-102" in second
        assert "📂 Project Alpha — статус по Jira (ALPHA)" in second
        assert await _latest_snapshot_count(organization_id, PROJECT_ALPHA_ID) == 2
    finally:
        await _cleanup(organization_id)


async def test_status_without_project_builds_all_project_snapshots() -> None:
    organization_id = f"test-org-{uuid4().hex}"
    await _ensure_tables()
    await _cleanup(organization_id)
    try:
        await _seed_project(
            project_entity_id=PROJECT_ALPHA_ID,
            project_name="Project Alpha",
            jira_key="ALPHA",
        )
        await _seed_project(
            project_entity_id=PROJECT_BETA_ID,
            project_name="Project Beta",
            jira_key="BETA",
        )
        await _ingest_issue("ALPHA-101", summary="Project Alpha task")
        await _ingest_issue(
            "BETA-101",
            duedate="2026-06-01",
            summary="Project Beta release task",
        )

        text = await build_status_reply_text(
            now=NOW,
            question_text="/status",
            organization_id=organization_id,
        )

        assert text is not None
        assert text.startswith("📊 Project snapshots")
        assert "🟢 Project Alpha — confidence: 0.90 — changed: first snapshot" in text
        assert "🔴 Project Beta — confidence: 0.90 — changed: first snapshot" in text
        assert "Project Alpha: green; Jira ALPHA;" in text
        assert "Project Beta: red; Jira BETA;" in text
        assert await _latest_snapshot_count(organization_id, PROJECT_ALPHA_ID) == 1
        assert await _latest_snapshot_count(organization_id, PROJECT_BETA_ID) == 1
    finally:
        await _cleanup(organization_id)


async def test_status_without_project_suppresses_no_evidence_unknown_noise() -> None:
    organization_id = f"test-org-{uuid4().hex}"
    await _ensure_tables()
    await _cleanup(organization_id)
    try:
        await _seed_project(
            project_entity_id=PROJECT_ALPHA_ID,
            project_name="Project Alpha",
            jira_key="ALPHA",
        )
        await _seed_project(
            project_entity_id=PROJECT_BETA_ID,
            project_name="Project Beta",
            jira_key="BETA",
        )
        await _ingest_issue("ALPHA-101", summary="Project Alpha task")

        text = await build_status_reply_text(
            now=NOW,
            question_text="/status",
            organization_id=organization_id,
        )

        assert text is not None
        assert text.startswith("📊 Project snapshots")
        assert "🟢 Project Alpha — confidence: 0.90" in text
        assert "Project Alpha: green; Jira ALPHA;" in text
        assert "Project Beta" not in text
        assert "⚪" not in text
        assert await _latest_snapshot_count(organization_id, PROJECT_ALPHA_ID) == 1
        assert await _latest_snapshot_count(organization_id, PROJECT_BETA_ID) == 1
    finally:
        await _cleanup(organization_id)


def test_status_without_project_empty_state_has_no_gray_unknown_icon() -> None:
    text = _render_all_project_snapshots(
        [
            (
                _ProjectEntity("project:alpha", "Project Alpha"),
                type(
                    "Snapshot",
                    (),
                    {
                        "status_color": "unknown",
                        "confidence": 0.20,
                        "what_changed": ({"field": "snapshot", "change": "created"},),
                        "summary": "Project Alpha: unknown; Jira no Jira keys; 0 issues.",
                        "evidence_source_ids": (),
                    },
                )(),
            )
        ]
    )

    assert text.startswith("📊 Project snapshots")
    assert "No project snapshots with evidence yet." in text
    assert "⚪" not in text
    assert "unknown" not in text
    assert "Project Alpha:" not in text


async def test_project_specific_no_evidence_keeps_honest_unknown_snapshot() -> None:
    organization_id = f"test-org-{uuid4().hex}"
    await _ensure_tables()
    await _cleanup(organization_id)
    try:
        await _seed_project(
            project_entity_id=PROJECT_BETA_ID,
            project_name="Project Beta",
            jira_key="BETA",
        )

        text = await build_status_reply_text(
            now=NOW,
            question_text="status Project Beta",
            organization_id=organization_id,
        )

        assert text is not None
        assert text.startswith("⚪ Snapshot: Project Beta")
        assert "confidence: 0.20" in text
        assert "what_changed: first snapshot" in text
        assert "Project Beta: unknown; Jira BETA; 0 issues" in text
        assert "📂 Project Beta — статус по Jira (BETA)" in text
        assert "Задачи ещё не синхронизированы" in text
    finally:
        await _cleanup(organization_id)
