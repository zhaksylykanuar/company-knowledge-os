from __future__ import annotations

from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog
from app.db.second_opinion_models import SecondOpinionFinding
from app.main import app
from app.services.evidence_trail import (
    _source_ids_from_evidence,
    build_finding_trail,
)
from app.services.inbox_audit import (
    ACTION_FINDING_STATUS,
    list_inbox_actions,
    record_inbox_action,
)
from app.services.second_opinion import (
    FINDING_EXECUTION_MISMATCH,
    set_finding_status,
    snooze_finding,
    upsert_finding,
)
from app.services.visibility import (
    SCOPE_FOUNDER,
    SCOPE_INVESTOR,
    SCOPE_TEAM,
    redact_finding,
)


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
            delete(AuditLog).where(AuditLog.correlation_id.like(f"%{marker}%"))
        )
        await session.commit()


def test_source_ids_extraction() -> None:
    ids = _source_ids_from_evidence(
        [
            {"source_id": "QS-154"},
            {"issue_key": "QT-98"},
            {"pr_id": "42"},
            {"unrelated": "x"},
            "not-a-dict",
        ]
    )
    assert ids == ["QS-154", "QT-98", "42"]


def test_visibility_redaction_per_scope() -> None:
    finding = {
        "finding_key": "k",
        "finding_type": FINDING_EXECUTION_MISMATCH,
        "summary": "s",
        "severity": "high",
        "status": "open",
        "created_at": "2026-06-12T00:00:00+00:00",
        "note": "internal note",
        "source_refs": [{"kind": "status_snapshot"}],
        "evidence_refs": [{"id": "x"}],
        "declared_state": "d",
        "observed_state": "o",
        "visibility_scope": "team",
    }
    # Founder sees everything verbatim.
    assert redact_finding(finding, SCOPE_FOUNDER) is finding
    # Team sees the team-scoped item but loses note + source_refs.
    team = redact_finding(finding, SCOPE_TEAM)
    assert team is not None
    assert "note" not in team and "source_refs" not in team
    assert team["declared_state"] == "d"
    # Investor cannot see a team-scoped finding at all.
    assert redact_finding(finding, SCOPE_INVESTOR) is None
    # An investor-scoped finding is reduced to curated fields only.
    investor_item = {**finding, "visibility_scope": "investor"}
    curated = redact_finding(investor_item, SCOPE_INVESTOR)
    assert curated is not None
    assert "evidence_refs" not in curated and "declared_state" not in curated
    assert set(curated) == {
        "finding_key",
        "finding_type",
        "summary",
        "severity",
        "status",
        "created_at",
    }


async def test_evidence_trail_resolves_chain_and_history() -> None:
    marker = uuid4().hex[:8]
    key = f"trail:{marker}"
    try:
        async with AsyncSessionLocal() as session:
            await upsert_finding(
                session,
                finding_key=key,
                entity_id="project:qtwin",
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="Jira: In Progress",
                observed_state="Нет кода",
                summary="trail test",
                severity="medium",
                confidence=0.7,
                confidence_factors={"evidence_count": 1},
                evidence_refs=[{"source_id": f"QS-{marker}", "type": "test"}],
                source_refs=[{"kind": "status_snapshot", "snapshot_id": 1}],
            )
            # A decision writes audit history that the trail surfaces.
            await set_finding_status(
                session,
                finding_key=key,
                status="dismissed",
                note="not real",
                reviewer_id="founder-test",
            )
            await session.commit()

            trail = await build_finding_trail(session, finding_key=key)
        assert trail is not None
        assert trail["finding"]["finding_key"] == key
        assert trail["reasoning"]
        assert trail["confidence_explanation"]["hint"]
        assert trail["suggested_action"]
        assert len(trail["evidence_chain"]) == 1
        assert trail["evidence_chain"][0]["source_ids"] == [f"QS-{marker}"]
        # Decision history captures the dismiss with previous/next state.
        history = trail["decision_history"]
        assert any(
            item["action"] == ACTION_FINDING_STATUS
            and item["next_state"]["status"] == "dismissed"
            and item["previous_state"]["status"] == "open"
            and item["actor"] == "founder-test"
            for item in history
        )
    finally:
        await _cleanup(marker)


async def test_finding_actions_write_audit_trail() -> None:
    marker = uuid4().hex[:8]
    key = f"audit:{marker}"
    try:
        async with AsyncSessionLocal() as session:
            await upsert_finding(
                session,
                finding_key=key,
                entity_id="project:test",
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="d",
                observed_state="o",
                summary="audit test",
                severity="low",
                confidence=0.6,
                evidence_refs=[{"source_id": "x"}],
            )
            await snooze_finding(
                session, finding_key=key, days=5, reviewer_id="founder-test"
            )
            await set_finding_status(
                session,
                finding_key=key,
                status="resolved",
                reviewer_id="founder-test",
            )
            await session.commit()

            actions = await list_inbox_actions(session, target_id=key)
        action_names = {a["action"] for a in actions}
        assert "finding_snooze" in action_names
        assert "finding_status" in action_names
        # Every audit row records who and reversibility.
        assert all(a["actor"] == "founder-test" for a in actions)
        assert all(a["reversible"] is True for a in actions)
    finally:
        await _cleanup(marker)


async def test_record_inbox_action_shape() -> None:
    marker = uuid4().hex[:8]
    target = f"manual:{marker}"
    try:
        async with AsyncSessionLocal() as session:
            await record_inbox_action(
                session,
                action="finding_status",
                actor="founder",
                target_id=target,
                previous_state={"status": "open"},
                next_state={"status": "resolved"},
                reversible=False,
                details={"reason": "done"},
            )
            await session.commit()
            actions = await list_inbox_actions(session, target_id=target)
        assert len(actions) == 1
        assert actions[0]["reversible"] is False
        assert actions[0]["details"] == {"reason": "done"}
    finally:
        await _cleanup(marker)


async def test_second_opinion_feed_view_redaction_via_api(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    marker = uuid4().hex[:8]
    team_key = f"view:{marker}:team"
    inv_key = f"view:{marker}:inv"
    try:
        async with AsyncSessionLocal() as session:
            await upsert_finding(
                session,
                finding_key=team_key,
                entity_id=f"project:test-{marker}",
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="d",
                observed_state="o",
                summary="team finding",
                severity="high",
                confidence=0.8,
                evidence_refs=[{"source_id": "x"}],
                source_refs=[{"kind": "status_snapshot"}],
                visibility_scope="team",
            )
            await upsert_finding(
                session,
                finding_key=inv_key,
                entity_id=f"project:test-{marker}",
                finding_type=FINDING_EXECUTION_MISMATCH,
                declared_state="d",
                observed_state="o",
                summary="investor finding",
                severity="high",
                confidence=0.8,
                evidence_refs=[{"source_id": "x"}],
                source_refs=[{"kind": "status_snapshot"}],
                visibility_scope="investor",
            )
            await session.commit()

        async with _client() as client:
            # Investor view: only the investor-scoped item, curated fields.
            inv = await client.get(
                "/api/v1/founder/second-opinion",
                params={"status": "open", "limit": 200, "view": "investor"},
            )
            assert inv.status_code == 200
            inv_findings = [
                f for f in inv.json()["findings"] if marker in f["finding_key"]
            ]
            assert len(inv_findings) == 1
            assert inv_findings[0]["finding_key"] == inv_key
            assert "evidence_refs" not in inv_findings[0]
            assert "source_refs" not in inv_findings[0]

            # Team view: sees the team item, no source_refs leaked.
            team = await client.get(
                "/api/v1/founder/second-opinion",
                params={"status": "open", "limit": 200, "view": "team"},
            )
            team_findings = [
                f for f in team.json()["findings"] if marker in f["finding_key"]
            ]
            keys = {f["finding_key"] for f in team_findings}
            assert team_key in keys
            assert inv_key not in keys
            assert all("source_refs" not in f for f in team_findings)

            # Founder view: both, full fidelity.
            founder = await client.get(
                "/api/v1/founder/second-opinion",
                params={"status": "open", "limit": 200, "view": "founder"},
            )
            founder_keys = {
                f["finding_key"]
                for f in founder.json()["findings"]
                if marker in f["finding_key"]
            }
            assert {team_key, inv_key} <= founder_keys

            # Unknown view is rejected.
            bad = await client.get(
                "/api/v1/founder/second-opinion", params={"view": "ceo"}
            )
            assert bad.status_code == 400
    finally:
        await _cleanup(marker)


async def test_trail_and_inbox_require_founder_view(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        # Trail (raw evidence) is founder-only.
        trail = await client.get(
            "/api/v1/founder/second-opinion/anything/trail",
            params={"view": "team"},
        )
        assert trail.status_code == 403
        # Inbox is founder-only.
        inbox = await client.get("/api/v1/inbox", params={"view": "investor"})
        assert inbox.status_code == 403
        # Graph tree is blocked for investors.
        tree = await client.get("/api/v1/graph/tree", params={"view": "investor"})
        assert tree.status_code == 403
