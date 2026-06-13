from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Text, cast, delete, select

from app.core.config import Settings, settings
from app.db.base import AsyncSessionLocal
from app.db.graph_models import EntityRecord
from app.db.models import AuditLog
from app.main import app
from app.services.evidence_graph_lift import run_evidence_pipeline
from app.services.obsidian_vault import (
    generate_obsidian_vault_plan,
    note_relative_path_for_node,
    obsidian_bridge_config,
    obsidian_open_uri,
    safe_relative_path,
    safe_vault_join,
    sanitize_markdown_content,
    sync_obsidian_vault,
)
from tests.test_stage12_evidence_pipeline import (
    _cleanup,
    _ensure_tables,
    _insert_normalized,
)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _enable_bridge(monkeypatch, tmp_path: Path | None) -> None:
    monkeypatch.setattr(settings, "enable_obsidian_bridge", True)
    monkeypatch.setattr(settings, "obsidian_bridge_vault_name", "FounderOS Knowledge Vault")
    monkeypatch.setattr(
        settings,
        "obsidian_bridge_vault_path",
        str(tmp_path) if tmp_path is not None else None,
    )
    monkeypatch.setattr(settings, "obsidian_bridge_sync_mode", "manual")


async def _seed_project(marker: str) -> str:
    activity_item_id, _ = await _insert_normalized(marker)
    async with AsyncSessionLocal() as session:
        await run_evidence_pipeline(
            session,
            activity_item_ids=[activity_item_id],
            run_id=f"evidence_pipeline_{marker}",
        )
        await session.commit()
    return activity_item_id


async def test_obsidian_bridge_status_disabled_missing_and_configured(
    monkeypatch,
    tmp_path: Path,
) -> None:
    await _ensure_tables()
    monkeypatch.setattr(settings, "enable_obsidian_bridge", False)
    async with _client() as client:
        disabled = await client.get("/v1/knowledge/obsidian/status")
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["vault_path"] is None

    _enable_bridge(monkeypatch, None)
    async with _client() as client:
        missing = await client.get("/v1/knowledge/obsidian/status")
    assert missing.status_code == 200
    assert missing.json()["status"] == "missing_path"
    assert (
        missing.json()["recommended_relative_path"]
        == ".local/obsidian/FounderOS Knowledge Vault"
    )
    assert "FounderOS Knowledge Vault" in missing.json()["recommended_vault_path"]

    _enable_bridge(monkeypatch, tmp_path)
    async with _client() as client:
        configured = await client.get("/v1/knowledge/obsidian/status")
        team = await client.get("/v1/knowledge/obsidian/status", params={"view": "team"})
    assert configured.status_code == 200
    assert configured.json()["status"] == "configured"
    assert configured.json()["vault_path_configured"] is True
    assert team.status_code == 403


def test_obsidian_settings_read_founderos_aliases(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FOUNDEROS_ENABLE_OBSIDIAN_BRIDGE", "true")
    monkeypatch.setenv("FOUNDEROS_OBSIDIAN_VAULT_NAME", "FounderOS Knowledge Vault")
    monkeypatch.setenv("FOUNDEROS_OBSIDIAN_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("FOUNDEROS_OBSIDIAN_SYNC_MODE", "manual")
    cfg = Settings(_env_file=None)
    assert cfg.enable_obsidian_bridge is True
    assert cfg.obsidian_bridge_vault_name == "FounderOS Knowledge Vault"
    assert cfg.obsidian_bridge_vault_path == str(tmp_path)
    assert cfg.obsidian_bridge_sync_mode == "manual"
    assert obsidian_bridge_config(cfg).status == "configured"


def test_obsidian_path_safety_and_deterministic_duplicates(tmp_path: Path) -> None:
    readable = note_relative_path_for_node(
        {
            "node_id": "person:amir-bikchentaev",
            "node_type": "person",
            "title": "Амир Бикчентаев",
        },
        used_paths=set(),
    )
    assert readable.as_posix() == "People/Амир Бикчентаев.md"
    used: set[str] = set()
    first = note_relative_path_for_node(
        {"node_id": "project:alpha", "node_type": "project", "title": "Project Alpha"},
        used_paths=used,
    )
    second = note_relative_path_for_node(
        {"node_id": "project:alpha-copy", "node_type": "project", "title": "Project Alpha"},
        used_paths=used,
    )
    assert first.as_posix() == "Projects/Project Alpha.md"
    assert second.as_posix().startswith("Projects/Project Alpha -- ")
    with pytest.raises(ValueError):
        safe_relative_path("../outside.md")
    with pytest.raises(ValueError):
        safe_vault_join(tmp_path, "/tmp/outside.md")
    with pytest.raises(ValueError):
        safe_vault_join(tmp_path, "../outside.md")


async def test_obsidian_generator_markdown_frontmatter_wikilinks_and_no_secrets() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    secret_marker = f"{marker}_secret"
    try:
        await _seed_project(marker)
        async with AsyncSessionLocal() as session:
            session.add(
                EntityRecord(
                    entity_id=f"knowledge_note:{secret_marker}",
                    entity_type="knowledge_note",
                    canonical_name="Project Alpha secret note",
                    attrs={
                        "summary": "OPENAI_API_KEY should not appear raw://private",
                        "source_types": ["manual"],
                        "source_refs": [{"raw_object_ref": "raw://private/body"}],
                        "evidence_count": 1,
                        "confidence": 0.9,
                    },
                    created_by_run_id=f"evidence_pipeline_{secret_marker}",
                    updated_by_run_id=f"evidence_pipeline_{secret_marker}",
                )
            )
            await session.commit()
            plan = await generate_obsidian_vault_plan(session)
        project_note = next(note for note in plan.notes if note.node_id == "project:project-alpha")
        assert project_note.path == "Projects/Project Alpha.md"
        assert "type: \"project\"" in project_note.markdown
        assert "#founderos/project" in project_note.markdown
        assert "#source/github" in project_note.markdown
        assert "[[People/Person A|Person A]]" in project_note.markdown
        assert project_note.content_hash
        second_plan = await _plan_again()
        second_project = next(
            note for note in second_plan.notes if note.node_id == "project:project-alpha"
        )
        assert second_project.content_hash == project_note.content_hash
        blob = "\n".join(note.markdown for note in plan.notes)
        assert "OPENAI_API_KEY" not in blob
        assert "raw://" not in blob
        assert "***redacted***" in blob
    finally:
        await _cleanup(marker)
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(EntityRecord).where(
                    cast(EntityRecord.attrs, Text).like(f"%{secret_marker}%")
                    | EntityRecord.entity_id.like(f"%{secret_marker}%")
                )
            )
            await session.commit()


async def _plan_again():
    async with AsyncSessionLocal() as session:
        return await generate_obsidian_vault_plan(session)


async def test_obsidian_sync_dry_run_real_idempotent_and_audited(
    monkeypatch,
    tmp_path: Path,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    _enable_bridge(monkeypatch, tmp_path)
    try:
        await _seed_project(marker)
        async with AsyncSessionLocal() as session:
            dry = await sync_obsidian_vault(session, dry_run=True)
            await session.commit()
        assert dry["status"] == "succeeded"
        assert dry["dry_run"] is True
        assert not (tmp_path / "00 Index.md").exists()

        async with AsyncSessionLocal() as session:
            first = await sync_obsidian_vault(session, dry_run=False)
            await session.commit()
        assert first["notes_created"] > 0
        assert (tmp_path / "00 Index.md").exists()
        assert (tmp_path / "Projects" / "Project Alpha.md").exists()
        project_text = (tmp_path / "Projects" / "Project Alpha.md").read_text(
            encoding="utf-8"
        )
        assert "[[People/Person A|Person A]]" in project_text
        assert "raw://" not in project_text

        async with AsyncSessionLocal() as session:
            second = await sync_obsidian_vault(session, dry_run=False)
            audit_count = await session.scalar(
                select(AuditLog).where(AuditLog.event_type == "obsidian_vault_sync")
            )
            await session.commit()
        assert second["notes_created"] == 0
        assert second["notes_updated"] == 0
        assert second["notes_unchanged"] >= first["notes_created"]
        assert audit_count is not None

        async with AsyncSessionLocal() as session:
            project = await session.scalar(
                select(EntityRecord).where(EntityRecord.entity_id == "project:project-alpha")
            )
            assert project is not None
            project.attrs = {
                **(project.attrs or {}),
                "summary": f"Project Alpha updated {marker}",
            }
            session.add(
                EntityRecord(
                    entity_id=f"knowledge_note:archived-{marker}",
                    entity_type="knowledge_note",
                    canonical_name="Project Alpha archived note",
                    attrs={
                        "archived": True,
                        "source_types": ["manual"],
                        "source_refs": [{"marker": marker}],
                        "evidence_count": 1,
                        "confidence": 0.9,
                    },
                    created_by_run_id=f"evidence_pipeline_{marker}",
                    updated_by_run_id=f"evidence_pipeline_{marker}",
                )
            )
            changed = await sync_obsidian_vault(session, dry_run=False)
            await session.commit()
        assert changed["notes_updated"] >= 1
        assert changed["notes_archived"] >= 1
        archived_text = (
            tmp_path / "Projects" / "Project Alpha archived note.md"
        ).read_text(encoding="utf-8")
        assert 'status: "archived"' in archived_text
    finally:
        await _cleanup(marker)


async def test_obsidian_open_uris_and_preview_use_bridge_generator(
    monkeypatch,
    tmp_path: Path,
) -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    _enable_bridge(monkeypatch, tmp_path)
    try:
        await _seed_project(marker)
        async with _client() as client:
            vault = await client.get("/v1/knowledge/obsidian/open-vault")
            node = await client.get(
                "/v1/knowledge/obsidian/open-node/project%3Aproject-alpha"
            )
            missing = await client.get("/v1/knowledge/obsidian/open-node/missing")
            preview = await client.post("/v1/knowledge/export/obsidian-preview")
        assert vault.status_code == 200
        assert vault.json()["uri"] == obsidian_open_uri("FounderOS Knowledge Vault")
        assert node.status_code == 200
        assert (
            node.json()["uri"]
            == "obsidian://open?vault=FounderOS%20Knowledge%20Vault&file=Projects%2FProject%20Alpha"
        )
        assert str(tmp_path) not in node.text
        assert missing.status_code == 404
        assert preview.status_code == 200
        payload = preview.json()
        assert payload["manifest"]["source"] == "obsidian_bridge_generator"
        assert payload["manifest"]["file_write_performed"] is False
        assert any(file["path"] == "Projects/Project Alpha.md" for file in payload["files"])
    finally:
        await _cleanup(marker)


def test_obsidian_sync_script_requires_confirmation() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/sync_obsidian_vault.py", "--confirm-run", "WRONG"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["external_side_effect"] is False


def test_obsidian_markdown_sanitizer_removes_secret_like_content() -> None:
    payload = sanitize_markdown_content(
        {
            "jira_api_token": "LEAKED-JIRA",
            "email_body": "private raw email body",
            "summary": "raw://private/body OPENAI_API_KEY should be hidden",
            "nested": {"raw_object_ref": "raw://private/ref"},
        }
    )
    blob = json.dumps(payload)
    assert "LEAKED-JIRA" not in blob
    assert "private raw email body" not in blob
    assert "OPENAI_API_KEY" not in blob
    assert "raw://" not in blob


async def test_obsidian_bridge_ui_static_markers_present() -> None:
    html = Path("app/static/founder_ui.html").read_text(encoding="utf-8")
    assert "Obsidian Bridge" in html
    assert "/v1/knowledge/obsidian/status" in html
    assert "/v1/knowledge/obsidian/sync" in html
    assert "/v1/knowledge/obsidian/open-vault" in html
    assert "Web graph preview fallback / debug" in html
