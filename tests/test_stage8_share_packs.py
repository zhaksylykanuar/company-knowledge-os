from __future__ import annotations

import json
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.models import AuditLog
from app.db.second_opinion_models import SecondOpinionFinding
from app.db.share_pack_models import SharePack
from app.main import app
from app.services import share_packs as sp
from app.services.inbox_audit import list_inbox_actions
from app.services.second_opinion import (
    FINDING_OWNERSHIP_GAP,
    set_finding_note,
    upsert_finding,
)

_FINANCE_TERMS = ("mrr", "runway", "revenue")
_RAW_KEYS = ('"evidence_refs":', '"source_refs":', '"note":', "raw_object_ref")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _set_auth(monkeypatch, *, enabled: bool) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(
        settings, "api_auth_key", SecretStr("test-api-key") if enabled else None
    )
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


async def _cleanup_packs(pack_ids: list[str]) -> None:
    if not pack_ids:
        return
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AuditLog).where(AuditLog.correlation_id.in_(pack_ids))
        )
        await session.execute(
            delete(SharePack).where(SharePack.pack_id.in_(pack_ids))
        )
        await session.commit()


async def _cleanup_findings(marker: str) -> None:
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


# --- snapshot consistency + idempotency ---------------------------------


async def test_generate_idempotent_and_freezes_snapshot() -> None:
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            g1 = await sp.generate_pack(session, pack_type=sp.PACK_INVESTOR_UPDATE)
            await session.commit()
            created.append(g1["pack_id"])
            g2 = await sp.generate_pack(session, pack_type=sp.PACK_INVESTOR_UPDATE)
            await session.commit()
        # Same content (hash) -> same pack, not a duplicate.
        assert g2["idempotent"] is True
        assert g2["pack_id"] == g1["pack_id"]
        # Frozen snapshot is recorded at generation.
        async with AsyncSessionLocal() as session:
            row = await sp.get_pack(session, pack_id=g1["pack_id"])
        assert row.source_snapshot is not None
        assert "frozen_at" in row.source_snapshot
        # Reading twice is stable (content not recomputed under the founder).
        async with AsyncSessionLocal() as session:
            a = await sp.read_pack(session, pack_id=g1["pack_id"])
            b = await sp.read_pack(session, pack_id=g1["pack_id"])
        assert a["content_hash"] == b["content_hash"]
    finally:
        await _cleanup_packs(created)


# --- export safety / leak tests -----------------------------------------


async def test_investor_pack_never_includes_raw_refs_or_notes() -> None:
    marker = uuid4().hex[:8]
    created: list[str] = []
    try:
        # A founder-scoped finding with a note + source refs.
        async with AsyncSessionLocal() as session:
            await upsert_finding(
                session,
                finding_key=f"s8inv:{marker}",
                entity_id=f"project:s8-{marker}",
                finding_type=FINDING_OWNERSHIP_GAP,
                declared_state="d",
                observed_state="o",
                summary=f"founder only secret {marker}",
                severity="high",
                confidence=0.9,
                evidence_refs=[{"source_id": f"QS-{marker}"}],
                source_refs=[{"kind": "status_snapshot"}],
                visibility_scope="founder",
            )
            await set_finding_note(
                session,
                finding_key=f"s8inv:{marker}",
                note=f"internal note {marker}",
                reviewer_id="founder",
            )
            await session.commit()
            g = await sp.generate_pack(session, pack_type=sp.PACK_INVESTOR_UPDATE)
            await session.commit()
            created.append(g["pack_id"])
            preview = await sp.build_pack_preview(session, pack_id=g["pack_id"])
        # No raw source-event refs for an investor pack, ever.
        assert g["included_source_event_ids"] == []
        # The founder-only finding (its summary/note) never reaches the pack.
        blob = json.dumps(g, ensure_ascii=False) + json.dumps(preview, ensure_ascii=False)
        assert f"founder only secret {marker}" not in blob
        assert f"internal note {marker}" not in blob
        for key in _RAW_KEYS:
            assert key not in blob
        # The manifest proves what is hidden.
        m = g["redaction_manifest"]
        assert m["finance_visible"] is False and m["raw_refs_visible"] is False
        assert m["internal_notes_visible"] is False
        assert m["personal_team_details_visible"] is False
        assert set(m["hidden_source_types"]) >= {"gmail", "telegram"}
    finally:
        await _cleanup_packs(created)
        await _cleanup_findings(marker)


async def test_investor_pack_excludes_stamina_and_gardener_sections() -> None:
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            g = await sp.generate_pack(session, pack_type=sp.PACK_INVESTOR_UPDATE)
            await session.commit()
            created.append(g["pack_id"])
        section_keys = {s["key"] for s in g["sections"]}
        # No team-stamina / gardener-hygiene sections in an investor pack.
        assert not section_keys & {"team_load", "ownership_gaps", "gardener", "stamina"}
        excluded = g["redaction_manifest"]["excluded_sections"]
        assert "personal_stamina" in excluded
        assert "graph_hygiene" in excluded
        assert "finance" in excluded
    finally:
        await _cleanup_packs(created)


async def test_investor_export_blocked_when_finance_leaks() -> None:
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            g = await sp.generate_pack(session, pack_type=sp.PACK_INVESTOR_UPDATE)
            await session.commit()
            pid = g["pack_id"]
            created.append(pid)
            key = g["sections"][0]["key"]
            # Inject a finance term into a section.
            edited = await sp.edit_section(
                session, pack_id=pid, section_key=key, text="Runway 8 месяцев, MRR $50k"
            )
            await session.commit()
            # Re-approve at the edited content, then try to export.
            await sp.approve_pack(
                session, pack_id=pid, content_hash=edited["content_hash"]
            )
            await session.commit()
            with pytest.raises(ValueError) as exc:
                await sp.export_pack(session, pack_id=pid)
        assert "redaction manifest failed" in str(exc.value).lower()
        # The warning is surfaced as critical on the read model.
        async with AsyncSessionLocal() as session:
            row = await sp.read_pack(session, pack_id=pid)
        assert any(
            w["severity"] == "critical" and w["code"] == "finance_leak"
            for w in row["warnings"]
        )
        assert row["is_exportable"] is False
    finally:
        await _cleanup_packs(created)


@pytest.mark.parametrize(
    "pack_type,injected,code",
    [
        (sp.PACK_TEAM_WEEKLY_BRIEF, "Runway 8 месяцев, MRR $50k", "finance_leak"),
        (sp.PACK_INVESTOR_UPDATE, "Команда выгорела, перегруз", "stamina_leak"),
        (sp.PACK_INVESTOR_UPDATE, "internal note: не показывать", "internal_note_leak"),
        (sp.PACK_INVESTOR_UPDATE, "запустить graph gardener", "hygiene_leak"),
    ],
)
async def test_non_founder_export_blocked_on_injected_forbidden_content(
    pack_type: str, injected: str, code: str
) -> None:
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            g = await sp.generate_pack(session, pack_type=pack_type)
            await session.commit()
            pid = g["pack_id"]
            created.append(pid)
            edited = await sp.edit_section(
                session, pack_id=pid, section_key=g["sections"][0]["key"], text=injected
            )
            await session.commit()
            await sp.approve_pack(
                session, pack_id=pid, content_hash=edited["content_hash"]
            )
            await session.commit()
            with pytest.raises(ValueError):
                await sp.export_pack(session, pack_id=pid)
            row = await sp.read_pack(session, pack_id=pid)
        assert any(
            w["severity"] == "critical" and w["code"] == code for w in row["warnings"]
        )
        assert row["is_exportable"] is False
    finally:
        await _cleanup_packs(created)


async def test_approve_audit_records_actual_previous_status() -> None:
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            g = await sp.generate_pack(session, pack_type=sp.PACK_FOUNDER_WEEKLY_REVIEW)
            await session.commit()
            pid = g["pack_id"]
            created.append(pid)
            # Approve, edit (back to draft), re-approve — the second approve's
            # audit must record the true prior status (draft), not a guess.
            await sp.approve_pack(session, pack_id=pid, content_hash=g["content_hash"])
            await session.commit()
            edited = await sp.edit_section(
                session, pack_id=pid, section_key=g["sections"][0]["key"], text="x"
            )
            await session.commit()
            await sp.approve_pack(
                session, pack_id=pid, content_hash=edited["content_hash"]
            )
            await session.commit()
            actions = await list_inbox_actions(session, target_id=pid, limit=50)
        approvals = [a for a in actions if a["action"] == "pack_approved"]
        assert approvals
        assert all(
            a["previous_state"]["status"] in {"draft", "pending_approval"}
            for a in approvals
        )
    finally:
        await _cleanup_packs(created)


async def test_team_pack_excludes_founder_only_findings() -> None:
    marker = uuid4().hex[:8]
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            await upsert_finding(
                session,
                finding_key=f"s8team:{marker}:f",
                entity_id=f"project:s8-{marker}",
                finding_type=FINDING_OWNERSHIP_GAP,
                declared_state="d",
                observed_state="o",
                summary=f"founder conclusion {marker}",
                severity="high",
                confidence=0.9,
                evidence_refs=[{"source_id": "x"}],
                visibility_scope="founder",
            )
            await session.commit()
            g = await sp.generate_pack(session, pack_type=sp.PACK_TEAM_WEEKLY_BRIEF)
            await session.commit()
            created.append(g["pack_id"])
        assert f"s8team:{marker}:f" not in g["included_finding_ids"]
        assert g["included_source_event_ids"] == []
        assert f"founder conclusion {marker}" not in json.dumps(g, ensure_ascii=False)
    finally:
        await _cleanup_packs(created)
        await _cleanup_findings(marker)


async def test_revoked_pack_cannot_export() -> None:
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            g = await sp.generate_pack(session, pack_type=sp.PACK_FOUNDER_WEEKLY_REVIEW)
            await session.commit()
            pid = g["pack_id"]
            created.append(pid)
            await sp.approve_pack(session, pack_id=pid, content_hash=g["content_hash"])
            await sp.revoke_pack(session, pack_id=pid)
            await session.commit()
            with pytest.raises(ValueError):
                await sp.export_pack(session, pack_id=pid)
    finally:
        await _cleanup_packs(created)


async def test_changed_draft_cannot_export_with_old_approval() -> None:
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            g = await sp.generate_pack(session, pack_type=sp.PACK_FOUNDER_WEEKLY_REVIEW)
            await session.commit()
            pid = g["pack_id"]
            created.append(pid)
            await sp.approve_pack(session, pack_id=pid, content_hash=g["content_hash"])
            await session.commit()
            # Editing resets approval; the old approval can't authorize export.
            await sp.edit_section(
                session, pack_id=pid, section_key=g["sections"][0]["key"], text="changed"
            )
            await session.commit()
            row = await sp.read_pack(session, pack_id=pid)
            assert row["status"] == "draft"
            assert row["section_diff"]["has_diff"] is True
            with pytest.raises(ValueError):
                await sp.export_pack(session, pack_id=pid)
    finally:
        await _cleanup_packs(created)


# --- audit completeness + idempotency -----------------------------------


async def test_lifecycle_audit_completeness() -> None:
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            g = await sp.generate_pack(session, pack_type=sp.PACK_FOUNDER_WEEKLY_REVIEW)
            await session.commit()
            pid = g["pack_id"]
            created.append(pid)
            await sp.edit_section(
                session, pack_id=pid, section_key=g["sections"][0]["key"], text="e"
            )
            await sp.set_section_included(
                session, pack_id=pid, section_key=g["sections"][1]["key"], included=False
            )
            await session.commit()
            row = await sp.read_pack(session, pack_id=pid)
            await sp.approve_pack(session, pack_id=pid, content_hash=row["content_hash"])
            await sp.export_pack(session, pack_id=pid)
            await sp.revoke_pack(session, pack_id=pid)
            await session.commit()
            actions = await list_inbox_actions(session, target_id=pid, limit=50)
        names = {a["action"] for a in actions}
        assert {
            "pack_generated",
            "pack_section_edited",
            "pack_section_toggled",
            "pack_approved",
            "pack_exported",
            "pack_revoked",
        } <= names
    finally:
        await _cleanup_packs(created)


async def test_approve_and_export_idempotent_no_duplicate_audit() -> None:
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            g = await sp.generate_pack(session, pack_type=sp.PACK_FOUNDER_WEEKLY_REVIEW)
            await session.commit()
            pid = g["pack_id"]
            created.append(pid)
            h = g["content_hash"]
            a1 = await sp.approve_pack(session, pack_id=pid, content_hash=h)
            a2 = await sp.approve_pack(session, pack_id=pid, content_hash=h)
            e1 = await sp.export_pack(session, pack_id=pid)
            e2 = await sp.export_pack(session, pack_id=pid)
            await session.commit()
            actions = await list_inbox_actions(session, target_id=pid, limit=50)
        assert a1["idempotent"] is False and a2["idempotent"] is True
        assert e1["idempotent"] is False and e2["idempotent"] is True
        names = [a["action"] for a in actions]
        assert names.count("pack_approved") == 1
        assert names.count("pack_exported") == 1
    finally:
        await _cleanup_packs(created)


async def test_approve_rejects_stale_hash() -> None:
    created: list[str] = []
    try:
        async with AsyncSessionLocal() as session:
            g = await sp.generate_pack(session, pack_type=sp.PACK_FOUNDER_WEEKLY_REVIEW)
            await session.commit()
            created.append(g["pack_id"])
            with pytest.raises(ValueError):
                await sp.approve_pack(
                    session, pack_id=g["pack_id"], content_hash="deadbeefdeadbeef"
                )
    finally:
        await _cleanup_packs(created)


# --- visibility (API) ---------------------------------------------------


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/v1/share-packs", None),
        ("post", "/api/v1/share-packs/generate", {"pack_type": "investor_update"}),
    ],
)
async def test_share_pack_endpoints_are_founder_only(
    monkeypatch, method: str, path: str, body: dict | None
) -> None:
    _set_auth(monkeypatch, enabled=False)
    async with _client() as client:
        for v in ("team", "investor"):
            if method == "get":
                r = await client.get(path, params={"view": v})
            else:
                r = await client.post(path, params={"view": v}, json=body)
            assert r.status_code == 403, (path, v, r.text)
        # Unknown view is a 400.
        if method == "get":
            bad = await client.get(path, params={"view": "ceo"})
            assert bad.status_code == 400


async def test_share_pack_api_full_flow(monkeypatch) -> None:
    _set_auth(monkeypatch, enabled=False)
    created: list[str] = []
    try:
        async with _client() as client:
            g = (
                await client.post(
                    "/api/v1/share-packs/generate",
                    json={"pack_type": "founder_weekly_review"},
                )
            ).json()
            pid = g["pack_id"]
            created.append(pid)
            # Export before approval is refused.
            early = await client.post(
                f"/api/v1/share-packs/{pid}/export", json={}
            )
            assert early.status_code == 409
            approved = await client.post(
                f"/api/v1/share-packs/{pid}/approve",
                json={"content_hash": g["content_hash"]},
            )
            assert approved.status_code == 200
            exported = await client.post(f"/api/v1/share-packs/{pid}/export", json={})
            assert exported.status_code == 200
            assert exported.json()["exported"] is True
    finally:
        await _cleanup_packs(created)


# --- UI smoke -----------------------------------------------------------


def test_ui_wires_share_packs_and_notifications(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    _set_auth(monkeypatch, enabled=False)
    with TestClient(app) as client:
        page = client.get("/ui").text
    for marker in (
        'data-nav="spk"',
        'data-nav="ntf"',
        "/api/v1/share-packs",
        "/api/v1/founder/notification-center",
        "data-spkgen",
        "data-spkact",
        "Redaction manifest",
        'id="cc-packs"',
    ):
        assert marker in page, marker
