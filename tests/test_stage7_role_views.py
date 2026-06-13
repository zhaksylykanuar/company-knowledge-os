from __future__ import annotations

import json
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.api.auth import settings
from app.db.agent_models import AgentProposal
from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog
from app.db.second_opinion_models import SecondOpinionFinding
from app.main import app
from app.services.curated_updates import (
    KIND_FOUNDER_WEEKLY,
    KIND_INVESTOR_UPDATE,
    build_update_draft,
)
from app.services.inbox_audit import list_inbox_actions
from app.services.role_views import build_investor_view, build_team_workspace
from app.services.second_opinion import (
    FINDING_OWNERSHIP_GAP,
    set_finding_note,
    upsert_finding,
)

# Forbidden substrings that must never appear in an investor-facing payload.
_FINANCE_TERMS = ('"mrr"', '"runway"', '"revenue"', "выручк", "mrr ", "runway ")
_RAW_KEYS = ('"evidence_refs"', '"source_refs"', '"note":', "raw_object_ref")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _set_auth(monkeypatch, *, enabled: bool) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(
        settings, "api_auth_key", SecretStr("test-api-key") if enabled else None
    )
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SecondOpinionFinding).where(
                SecondOpinionFinding.finding_key.like(f"%{marker}%")
            )
        )
        await session.execute(
            delete(AgentProposal).where(AgentProposal.proposal_id.like(f"%{marker}%"))
        )
        await session.execute(
            delete(AuditLog).where(AuditLog.correlation_id.like(f"%{marker}%"))
        )
        await session.commit()


# --- visibility / view gating -------------------------------------------


@pytest.mark.parametrize(
    "path,view,expected",
    [
        ("/v1/team/workspace", "team", 200),
        ("/v1/team/workspace", "founder", 200),
        ("/v1/team/workspace", "investor", 403),
        ("/v1/investor/view", "investor", 200),
        ("/v1/investor/view", "founder", 200),
        ("/v1/investor/view", "team", 403),
        ("/v1/operating-rhythm/weekly", "team", 200),
        ("/v1/operating-rhythm/weekly", "founder", 200),
        ("/v1/operating-rhythm/weekly", "investor", 403),
        ("/v1/operating-rhythm/daily", "team", 200),
        ("/v1/operating-rhythm/daily", "investor", 403),
        ("/v1/operating-rhythm/decision", "founder", 200),
        ("/v1/operating-rhythm/decision", "team", 403),
        ("/v1/operating-rhythm/decision", "investor", 403),
        ("/v1/operating-rhythm/bogus", "founder", 400),
        ("/v1/updates/founder_weekly", "founder", 200),
        ("/v1/updates/investor_update", "team", 403),
        ("/v1/updates/bogus", "founder", 400),
        ("/v1/team/workspace", "ceo", 400),
    ],
)
async def test_role_view_gating(monkeypatch, path: str, view: str, expected: int) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        response = await client.get(path, params={"view": view})
    assert response.status_code == expected, (path, view, response.text)


async def test_action_center_ctas_are_founder_only(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        review = await client.post(
            "/v1/founder/action-center/review",
            params={"view": "team"},
            json={"action_ref": {"kind": "task", "issue_key": "X-1"}},
        )
        owner = await client.post(
            "/v1/founder/action-center/assign-owner-proposal",
            params={"view": "investor"},
            json={"issue_key": "X-1"},
        )
    assert review.status_code == 403
    assert owner.status_code == 403


# --- redaction ----------------------------------------------------------


async def test_investor_view_has_no_finance_or_raw_refs() -> None:
    async with AsyncSessionLocal() as session:
        view = await build_investor_view(session)
    blob = json.dumps(view, ensure_ascii=False, default=str).lower()
    for term in _RAW_KEYS:
        assert term not in blob, f"raw leak: {term}"
    for term in _FINANCE_TERMS:
        assert term not in blob, f"finance leak: {term}"
    assert view["role"] == "investor"
    assert view["redaction"]["finance"] == "excluded"
    # Key risks are categories + counts only — never a raw finding summary.
    for risk in view["key_risks"]:
        assert set(risk) == {"category", "count", "severity"}


async def test_investor_key_risks_hide_raw_summaries() -> None:
    marker = uuid4().hex[:8]
    secret = f"СЕКРЕТНАЯ-ФОРМУЛИРОВКА-{marker}"
    key = f"s7inv:{marker}"
    try:
        async with AsyncSessionLocal() as session:
            # Investor-scoped so it contributes to the curated key_risks;
            # its raw summary/note/refs must still never surface.
            await upsert_finding(
                session,
                finding_key=key,
                entity_id=f"project:s7-{marker}",
                finding_type=FINDING_OWNERSHIP_GAP,
                declared_state="d",
                observed_state="o",
                summary=secret,
                severity="high",
                confidence=0.9,
                evidence_refs=[{"source_id": "x"}],
                source_refs=[{"kind": "status_snapshot"}],
                visibility_scope="investor",
            )
            await set_finding_note(
                session,
                finding_key=key,
                note="внутренняя заметка",
                reviewer_id="founder-test",
            )
            await session.commit()
            view = await build_investor_view(session)
        blob = json.dumps(view, ensure_ascii=False, default=str)
        # The raw summary, note and source refs must not surface anywhere.
        assert secret not in blob
        assert "внутренняя заметка" not in blob
        # But the risk category IS reflected (high-level, count only).
        categories = [r["category"] for r in view["key_risks"]]
        assert "Пробелы в ответственности" in categories
    finally:
        await _cleanup(marker)


async def test_investor_key_risks_exclude_non_investor_findings() -> None:
    from app.services.second_opinion import FINDING_VALIDATION_GAP

    marker = uuid4().hex[:8]
    founder_key = f"s7excl:{marker}:f"
    inv_key = f"s7excl:{marker}:i"
    category = "Непроверенные гипотезы"

    def _count(view: dict) -> int:
        for risk in view["key_risks"]:
            if risk["category"] == category:
                return risk["count"]
        return 0

    async def _seed(key: str, scope: str) -> None:
        async with AsyncSessionLocal() as session:
            await upsert_finding(
                session,
                finding_key=key,
                entity_id=f"project:s7-{marker}",
                finding_type=FINDING_VALIDATION_GAP,
                declared_state="d",
                observed_state="o",
                summary=f"{scope} validation gap {marker}",
                severity="high",
                confidence=0.8,
                evidence_refs=[{"source_id": "x"}],
                visibility_scope=scope,
            )
            await session.commit()

    try:
        async with AsyncSessionLocal() as session:
            baseline = _count(await build_investor_view(session))
        await _seed(founder_key, "founder")
        async with AsyncSessionLocal() as session:
            after_founder = _count(await build_investor_view(session))
        # A founder-scoped finding must NOT change the investor's risk counts.
        assert after_founder == baseline
        await _seed(inv_key, "investor")
        async with AsyncSessionLocal() as session:
            after_investor = _count(await build_investor_view(session))
        # An investor-scoped finding is the only thing that does.
        assert after_investor == baseline + 1
    finally:
        await _cleanup(marker)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/v1/founder/second-opinion/k/status", {"status": "resolved"}),
        ("post", "/v1/founder/second-opinion/k/snooze", {"days": 7}),
        ("post", "/v1/founder/second-opinion/k/note", {"note": "x"}),
        ("post", "/v1/inbox/proposals/p/decision", {"decision": "accepted"}),
        ("post", "/v1/graph/links/l/review", {"decision": "confirm"}),
    ],
)
async def test_mutation_endpoints_are_founder_only(
    monkeypatch, method: str, path: str, body: dict
) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        team = await client.post(path, params={"view": "team"}, json=body)
        investor = await client.post(path, params={"view": "investor"}, json=body)
    assert team.status_code == 403, (path, team.text)
    assert investor.status_code == 403, (path, investor.text)


async def test_team_workspace_redacts_founder_only_findings() -> None:
    marker = uuid4().hex[:8]
    team_key = f"s7tw:{marker}:team"
    founder_key = f"s7tw:{marker}:founder"
    try:
        async with AsyncSessionLocal() as session:
            for key, scope, summary in (
                (team_key, "team", f"team gap {marker}"),
                (founder_key, "founder", f"founder secret gap {marker}"),
            ):
                await upsert_finding(
                    session,
                    finding_key=key,
                    entity_id=f"project:s7-{marker}",
                    finding_type=FINDING_OWNERSHIP_GAP,
                    declared_state="d",
                    observed_state="o",
                    summary=summary,
                    severity="high",
                    confidence=0.8,
                    evidence_refs=[{"source_id": "x"}],
                    source_refs=[{"kind": "status_snapshot"}],
                    visibility_scope=scope,
                )
                await set_finding_note(
                    session,
                    finding_key=key,
                    note="private note",
                    reviewer_id="founder-test",
                )
            await session.commit()
            workspace = await build_team_workspace(session)

        assert workspace["role"] == "team"
        gaps = workspace["ownership_gaps"]
        decisions = workspace["decisions_needed"]
        seen = {f["finding_key"] for f in gaps} | {f["finding_key"] for f in decisions}
        # Team-scoped finding is visible; founder-scoped one is not.
        assert team_key in seen
        assert founder_key not in seen
        # Working evidence stays, but private note + source refs are stripped.
        for finding in gaps + decisions:
            assert "note" not in finding
            assert "source_refs" not in finding
        blob = json.dumps(workspace, ensure_ascii=False, default=str)
        assert "private note" not in blob
        assert f"founder secret gap {marker}" not in blob
    finally:
        await _cleanup(marker)


async def test_team_operating_rhythm_redacts_findings(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        weekly = await client.get(
            "/v1/operating-rhythm/weekly", params={"view": "team"}
        )
        daily = await client.get(
            "/v1/operating-rhythm/daily", params={"view": "team"}
        )
    assert weekly.status_code == 200 and daily.status_code == 200
    for body in (weekly.json(), daily.json()):
        blob = json.dumps(body, ensure_ascii=False)
        assert '"source_refs"' not in blob
        assert '"note":' not in blob
    # Team weekly never exposes the founder-only closed-decision audit detail.
    assert weekly.json()["closed"]["items"] == []


# --- audit + idempotency ------------------------------------------------


async def test_action_review_writes_audit(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    marker = uuid4().hex[:8]
    issue = f"S7-{marker}"
    try:
        async with _client() as client:
            response = await client.post(
                "/v1/founder/action-center/review",
                json={
                    "action_ref": {"kind": "task", "issue_key": issue},
                    "note": "looked at it",
                },
            )
        assert response.status_code == 200
        assert response.json()["reviewed"] is True
        async with AsyncSessionLocal() as session:
            actions = await list_inbox_actions(session, target_id=f"task:{issue}")
        assert any(a["action"] == "action_reviewed" for a in actions)
        assert all(a["actor"] == "founder" for a in actions)
    finally:
        await _cleanup(marker)


async def test_assign_owner_proposal_is_idempotent(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    marker = uuid4().hex[:8]
    issue = f"S7-{marker}"
    try:
        async with _client() as client:
            first = await client.post(
                "/v1/founder/action-center/assign-owner-proposal",
                json={"issue_key": issue, "suggested_owner": "alice"},
            )
            second = await client.post(
                "/v1/founder/action-center/assign-owner-proposal",
                json={"issue_key": issue, "suggested_owner": "alice"},
            )
        assert first.json() == {
            "proposal_id": f"ownership:{issue}",
            "created": True,
            "idempotent": False,
        }
        assert second.json()["created"] is False
        assert second.json()["idempotent"] is True
        async with AsyncSessionLocal() as session:
            proposals = (
                await session.execute(
                    select(AgentProposal.proposal_id).where(
                        AgentProposal.proposal_id == f"ownership:{issue}"
                    )
                )
            ).all()
            audits = await list_inbox_actions(
                session, target_id=f"ownership:{issue}"
            )
        # Exactly one proposal filed, one owner-assignment audit row.
        assert len(proposals) == 1
        assert sum(1 for a in audits if a["action"] == "owner_assignment_proposed") == 1
    finally:
        await _cleanup(marker)


async def test_curated_update_approve_is_idempotent_and_audited(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    try:
        async with _client() as client:
            draft = (
                await client.get(
                    f"/v1/updates/{KIND_FOUNDER_WEEKLY}", params={"view": "founder"}
                )
            ).json()
            content_hash = draft["content_hash"]
            assert draft["requires_approval"] is True and draft["approved"] is False
            first = await client.post(
                f"/v1/updates/{KIND_FOUNDER_WEEKLY}/approve",
                json={"content_hash": content_hash},
            )
            second = await client.post(
                f"/v1/updates/{KIND_FOUNDER_WEEKLY}/approve",
                json={"content_hash": content_hash},
            )
            bad = await client.post(
                f"/v1/updates/{KIND_FOUNDER_WEEKLY}/approve",
                json={"content_hash": "deadbeefdeadbeef"},
            )
        assert first.status_code == 200 and first.json()["idempotent"] is False
        assert first.json()["export_text"]
        assert second.status_code == 200 and second.json()["idempotent"] is True
        # A stale/changed hash cannot be approved.
        assert bad.status_code == 409
        target = f"update:{KIND_FOUNDER_WEEKLY}:{content_hash[:24]}"
        async with AsyncSessionLocal() as session:
            audits = await list_inbox_actions(session, target_id=target)
        assert sum(1 for a in audits if a["action"] == "update_approved") == 1
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(AuditLog).where(
                    AuditLog.correlation_id.like(f"update:{KIND_FOUNDER_WEEKLY}:%")
                )
            )
            await session.commit()


async def test_update_draft_marks_declared_vs_observed() -> None:
    async with AsyncSessionLocal() as session:
        draft = await build_update_draft(session, kind=KIND_INVESTOR_UPDATE)
    assert draft["redaction_level"] == "investor"
    assert "finance" in draft["excluded_sections"]
    for section in draft["sections"]:
        assert section["basis"] in {"observed", "declared", "mixed"}
        assert section["declared_vs_observed"]
        assert "evidence_coverage" in section


# --- UI smoke -----------------------------------------------------------


def test_ui_page_wires_role_views(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    _set_auth(monkeypatch, enabled=False)
    with TestClient(app) as client:
        page = client.get("/ui").text
    # Role switcher + new sections are wired into the static shell.
    for marker in (
        'id="role-switch"',
        'data-nav="tw"',
        'data-nav="orh"',
        'data-nav="upd"',
        "/v1/team/workspace",
        "/v1/investor/view",
        "/v1/operating-rhythm/",
        "/v1/updates/",
        "data-acreview",
        "data-acowner",
        "почему в группе",
    ):
        assert marker in page, marker
    assert "__FOS_API_HEADER_NAME__" not in page
