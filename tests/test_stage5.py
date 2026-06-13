from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.api.auth import settings
from app.db.agent_models import AgentProposal, AgentRunLog
from app.db.base import AsyncSessionLocal, engine
from app.db.gmail_models import EmailThreadState
from app.db.graph_models import (
    EntityAliasRecord,
    EntityLinkRecord,
    EntityRecord,
    EntitySourceAccount,
)
from app.db.second_opinion_models import SecondOpinionFinding
from app.main import app
from app.services.agent_proposals import create_proposal
from app.services.evidence_trail import _run_provenance
from app.services.inbox import build_inbox
from app.services.run_context import set_run_id
from app.services.sales_signal_agent import scan_sales_signals
from app.services.sales_view import build_sales_signals
from app.services.second_opinion import FINDING_EXECUTION_MISMATCH, upsert_finding


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
            EntityRecord.__table__,
            EntityAliasRecord.__table__,
            EntityLinkRecord.__table__,
            EntitySourceAccount.__table__,
            AgentProposal.__table__,
            AgentRunLog.__table__,
            SecondOpinionFinding.__table__,
            EmailThreadState.__table__,
        ):
            await conn.run_sync(table.create, checkfirst=True)


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        for model, col in (
            (AgentProposal, AgentProposal.proposal_id),
            (AgentRunLog, AgentRunLog.run_id),
            (SecondOpinionFinding, SecondOpinionFinding.finding_key),
            (EmailThreadState, EmailThreadState.thread_key),
            (EntityLinkRecord, EntityLinkRecord.link_id),
            (EntitySourceAccount, EntitySourceAccount.account_id),
            (EntityAliasRecord, EntityAliasRecord.entity_id),
            (EntityRecord, EntityRecord.entity_id),
        ):
            await session.execute(delete(model).where(col.like(f"%{marker}%")))
        await session.commit()
    set_run_id(None)


# --- run_id traceability ------------------------------------------------


async def test_run_id_stamps_finding_proposal_and_trail() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    run_id = f"run-{marker}"
    key = f"trace:{marker}"
    prop = f"prop:{marker}"
    try:
        set_run_id(run_id)
        async with AsyncSessionLocal() as session:
            # An agent_run_log so the trail can resolve provenance.
            session.add(
                AgentRunLog(
                    run_id=run_id,
                    agent="second_opinion",
                    agent_version="v9",
                    run_started_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
                    input_watermark="42",
                    created=1,
                )
            )
            await upsert_finding(
                session,
                finding_key=key,
                entity_id=None,
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="d",
                observed_state="o",
                summary="s",
                severity="low",
                confidence=0.7,
                evidence_refs=[{"source_id": "X"}],
            )
            await create_proposal(
                session,
                proposal_id=prop,
                agent="graph_gardener",
                kind="graph_orphan_node",
                title="orphan",
                payload={},
                confidence=0.5,
            )
            await session.commit()

            finding = await session.scalar(
                select(SecondOpinionFinding).where(
                    SecondOpinionFinding.finding_key == key
                )
            )
            proposal = await session.scalar(
                select(AgentProposal).where(AgentProposal.proposal_id == prop)
            )
            provenance = await _run_provenance(session, run_id)

        assert finding.last_run_id == run_id
        assert proposal.run_id == run_id
        assert provenance["run_id"] == run_id
        assert provenance["agent_version"] == "v9"
        assert provenance["input_watermark"] == "42"
    finally:
        await _cleanup(marker)


# --- inbox gardener grouping --------------------------------------------


async def test_inbox_groups_gardener_and_identity_proposals() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        async with AsyncSessionLocal() as session:
            await create_proposal(
                session,
                proposal_id=f"gardener:graph_orphan_node:person:x-{marker}",
                dedupe_key=f"g-{marker}",
                agent="graph_gardener",
                kind="graph_orphan_node",
                title="orphan node",
                payload={"entity_id": f"person:x-{marker}"},
                confidence=0.5,
            )
            await create_proposal(
                session,
                proposal_id=f"merge:a-{marker}+b-{marker}",
                dedupe_key=f"m-{marker}",
                agent="entity_identity",
                kind="entity_merge_proposal",
                title="merge?",
                payload={"keep": f"a-{marker}", "merge": f"b-{marker}"},
                confidence=0.7,
            )
            await session.commit()
            inbox = await build_inbox(session)

        gardener = [
            p
            for p in inbox["gardener_proposals"]
            if marker in p["proposal_id"]
        ]
        identity = [
            p
            for p in inbox["identity_proposals"]
            if marker in p["proposal_id"]
        ]
        assert len(gardener) == 1
        assert len(identity) == 1
        # Gardener card carries why + consequences + reject note.
        assert gardener[0]["why"]
        assert gardener[0]["consequences"]
        assert "не всплывёт снова" in gardener[0]["reject_note"]
        assert "gardener_proposals" in inbox["counts"]
        assert "identity_proposals" in inbox["counts"]
    finally:
        await _cleanup(marker)


# --- sales read model ---------------------------------------------------


async def test_sales_view_builds_accounts_no_finance() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    domain = f"buyer-{marker}.com"
    now = datetime(2026, 6, 13, tzinfo=timezone.utc)
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                EmailThreadState(
                    source="gmail",
                    thread_key=f"sv-{marker}",
                    subject_display="Deal",
                    participants_json=[f"lead@{domain}", "me@qtwin.io"],
                    last_message_from=f"lead@{domain}",
                    last_message_at=now - timedelta(days=25),
                    status="informational",
                    messages_count=3,
                )
            )
            await session.commit()
            await scan_sales_signals(session, now=now)
            await session.commit()

            view = await build_sales_signals(session)
        mine = [a for a in view["accounts"] if domain in (a["domain"] or "")]
        assert len(mine) == 1
        account = mine[0]
        assert account["warmth"] in {"cooling", "cold"}
        assert account["contacts"]
        assert account["deal_id"]
        # No money fields anywhere in the read model.
        import json

        blob = json.dumps(view).lower()
        assert "amount" not in blob
        assert "revenue" not in blob
        assert "$" not in blob
    finally:
        await _cleanup(marker)
        await _cleanup(marker.replace("-", ""))


async def test_sales_signals_endpoint_founder_only(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        ok = await client.get("/v1/founder/sales-signals")
        assert ok.status_code == 200
        assert "accounts" in ok.json()
        blocked = await client.get(
            "/v1/founder/sales-signals", params={"view": "team"}
        )
        assert blocked.status_code == 403


# --- command center unassigned bucket -----------------------------------


async def test_command_center_has_unassigned_bucket(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        response = await client.get("/v1/founder/command-center")
    assert response.status_code == 200
    team = response.json()["team"]
    assert "unassigned" in team
    bucket = team["unassigned"]
    assert "unassigned_work_count" in bucket
    assert "stale_unassigned_work" in bucket
    assert "high_priority_unassigned" in bucket
    # Unassigned is a bucket, never a person row.
    assert not any(
        "unassign" in str(p.get("name", "")).lower() for p in team["people"]
    )
