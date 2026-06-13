from __future__ import annotations

from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.api.auth import settings
from app.db.base import AsyncSessionLocal, engine
from app.db.declaration_models import FounderDeclaration
from app.db.models import AuditLog
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.source_models import DocumentChunk
from app.db.task_models import ExtractedRisk
from app.main import app
from app.services.action_center import build_action_center
from app.services.declarations import KEY_HYPOTHESES, set_declaration
from app.services.product_view import build_product_view
from app.services.second_opinion import FINDING_VALIDATION_GAP, upsert_finding


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _set_auth(monkeypatch, *, enabled: bool) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(
        settings, "api_auth_key", SecretStr("test-api-key") if enabled else None
    )
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        for table in (
            FounderDeclaration.__table__,
            SecondOpinionFinding.__table__,
            DocumentChunk.__table__,
            ExtractedRisk.__table__,
            AuditLog.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


# --- product view: hypotheses validation map ----------------------------


async def test_product_view_flags_validated_without_evidence() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        async with AsyncSessionLocal() as session:
            await set_declaration(
                session,
                key=KEY_HYPOTHESES,
                payload={
                    "items": [
                        {
                            "text": f"Гипотеза без подтверждения {marker} уникальное",
                            "status": "validated",
                        }
                    ]
                },
            )
            await session.commit()
            view = await build_product_view(session)
        mine = [h for h in view["hypotheses"] if marker in h["text"]]
        assert len(mine) == 1
        hyp = mine[0]
        assert hyp["declared_status"] == "validated"
        assert hyp["supporting_evidence_count"] == 0
        # validated + no supporting evidence -> flagged.
        assert hyp["flagged"] is True
        assert hyp["next_validation_action"]
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(FounderDeclaration).where(
                    FounderDeclaration.declaration_key == KEY_HYPOTHESES
                )
            )
            await session.commit()


# --- team view: operational load, no ranking ----------------------------


async def test_team_view_shape_no_ranking(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        response = await client.get("/v1/founder/team-load")
    assert response.status_code == 200
    body = response.json()
    # Operational risk fields, never a productivity/rank score.
    assert "unassigned" in body
    if body["people"]:
        person = body["people"][0]
        assert "open" in person and "stale" in person and "overdue" in person
        assert "rank" not in person
        assert "score" not in person
        assert "productivity" not in person
    # Unassigned is a bucket, not a person.
    assert not any("unassign" in p["name"].lower() for p in body["people"])


# --- action center: aggregates, read-only -------------------------------


async def test_action_center_aggregates_and_is_read_only() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    key = f"ac:{marker}"
    try:
        async with AsyncSessionLocal() as session:
            await upsert_finding(
                session,
                finding_key=key,
                entity_id=f"project:test-{marker}",
                finding_type=FINDING_VALIDATION_GAP,
                declared_state="d",
                observed_state="o",
                summary=f"ac finding {marker}",
                severity="high",
                confidence=0.8,
                evidence_refs=[{"source_id": "x"}],
            )
            await session.commit()

            audit_before = (
                await session.execute(select(func.count()).select_from(AuditLog))
            ).scalar()
            # High limit so the assertion does not depend on how many other
            # findings exist in the shared dev DB.
            center = await build_action_center(session, limit=1000)
            audit_after = (
                await session.execute(select(func.count()).select_from(AuditLog))
            ).scalar()

        mine = [a for a in center["actions"] if marker in str(a.get("title", ""))]
        assert mine
        action = mine[0]
        for field in (
            "title",
            "why_now",
            "affected_entity",
            "evidence_count",
            "severity",
            "source",
            "action_type",
            "cta",
            "action_ref",
        ):
            assert field in action
        assert action["source"] == "second_opinion"
        assert "by_source" in center["counts"]
        # The Action Center never mutates: no audit rows written.
        assert audit_before == audit_after
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(SecondOpinionFinding).where(
                    SecondOpinionFinding.finding_key == key
                )
            )
            await session.commit()


# --- execution view: real data shape ------------------------------------


async def test_execution_view_buckets_and_health(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        response = await client.get("/v1/founder/execution")
    assert response.status_code == 200
    body = response.json()
    for bucket in (
        "side_quests",
        "blocked_quests",
        "stale_quests",
        "ownerless_quests",
        "overdue_quests",
        "project_health",
    ):
        assert bucket in body
    # Health rings only for projects with total > 0 (no fake progress).
    for h in body["project_health"]:
        assert h["total"] > 0


# --- visibility enforcement ---------------------------------------------


async def test_execution_team_product_block_investor(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        for path in (
            "/v1/founder/execution",
            "/v1/founder/team-load",
            "/v1/founder/product",
        ):
            blocked = await client.get(path, params={"view": "investor"})
            assert blocked.status_code == 403, path
        # Action center and task detail are founder-only.
        ac = await client.get("/v1/founder/action-center", params={"view": "team"})
        assert ac.status_code == 403
        task = await client.get(
            "/v1/founder/execution/tasks/QS-1", params={"view": "team"}
        )
        assert task.status_code == 403
