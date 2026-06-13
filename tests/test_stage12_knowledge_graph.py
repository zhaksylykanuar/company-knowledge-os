from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import Text, cast, select

from app.db.base import AsyncSessionLocal
from app.db.graph_models import EntityRecord
from app.main import app
from app.services.evidence_graph_lift import run_evidence_pipeline
from tests.test_stage12_evidence_pipeline import (
    _cleanup,
    _ensure_tables,
    _insert_normalized,
)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_project_graph(marker: str) -> tuple[str, str, str]:
    activity_item_id, source_event_id = await _insert_normalized(marker)
    async with AsyncSessionLocal() as session:
        await run_evidence_pipeline(
            session,
            activity_item_ids=[activity_item_id],
            run_id=f"evidence_pipeline_{marker}",
        )
        await session.commit()
        project_id = await session.scalar(
            select(EntityRecord.entity_id).where(
                EntityRecord.entity_type == "project",
                cast(EntityRecord.attrs, Text).like(f"%{activity_item_id}%"),
            )
        )
    assert project_id == "project:project-alpha"
    return project_id, activity_item_id, source_event_id


async def test_knowledge_graph_global_local_filters_and_hidden_count() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        project_id, _, source_event_id = await _seed_project_graph(marker)
        async with _client() as client:
            global_response = await client.get(
                "/v1/knowledge/graph",
                params={"view": "founder", "limit": 80},
            )
            local_response = await client.get(
                "/v1/knowledge/graph",
                params={
                    "view": "founder",
                    "focus_node_id": project_id,
                    "depth": 1,
                    "limit": 80,
                },
            )
            filtered_response = await client.get(
                "/v1/knowledge/graph",
                params={
                    "view": "founder",
                    "node_type": "project",
                    "source_type": "github",
                    "min_confidence": 0.8,
                    "limit": 80,
                },
            )
            capped_response = await client.get(
                "/v1/knowledge/graph",
                params={"view": "founder", "limit": 1},
            )
        assert global_response.status_code == 200
        payload = global_response.json()
        assert payload["mode"] == "global"
        assert payload["nodes"]
        assert payload["edges"]
        assert payload["clusters"]
        assert payload["legend"]["dashed_edge"] == "disputed or low confidence"
        assert "finance_visible" not in payload["redaction_manifest"]
        assert any(node["node_id"] == project_id for node in payload["nodes"])
        assert source_event_id in json.dumps(payload, sort_keys=True)
        assert "external_tokens" in payload["redaction_manifest"]["excluded_sections"]

        assert local_response.status_code == 200
        local = local_response.json()
        assert local["mode"] == "local"
        assert local["focus_node"]["node_id"] == project_id
        assert all(
            edge["source_node_id"] == project_id
            or edge["target_node_id"] == project_id
            or edge["source_node_id"] in {node["node_id"] for node in local["nodes"]}
            for edge in local["edges"]
        )

        assert filtered_response.status_code == 200
        filtered = filtered_response.json()
        assert filtered["nodes"]
        assert all(node["node_type"] == "project" for node in filtered["nodes"])
        assert all("github" in node["source_types"] for node in filtered["nodes"])

        assert capped_response.status_code == 200
        capped = capped_response.json()
        assert capped["stats"]["hidden_count"] >= 0
        assert len(capped["nodes"]) == 1

    finally:
        await _cleanup(marker)


async def test_knowledge_node_note_redacts_raw_refs_by_view() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        project_id, activity_item_id, source_event_id = await _seed_project_graph(marker)
        encoded_project = project_id.replace(":", "%3A")
        async with _client() as client:
            founder_response = await client.get(
                f"/v1/knowledge/nodes/{encoded_project}",
                params={"view": "founder"},
            )
            team_response = await client.get(
                f"/v1/knowledge/nodes/{encoded_project}",
                params={"view": "team"},
            )
            source_response = await client.get(
                f"/v1/knowledge/nodes/source_event%3A{source_event_id}",
                params={"view": "team"},
            )
            investor_source_response = await client.get(
                f"/v1/knowledge/nodes/source_event%3A{source_event_id}",
                params={"view": "investor"},
            )

        assert founder_response.status_code == 200
        founder = founder_response.json()
        assert founder["title"] == "Project Alpha"
        assert founder["type"] == "project"
        assert founder["properties"]["source_refs"]
        assert founder["evidence"]["source_event_ids"] == [source_event_id]
        assert activity_item_id in founder["evidence"]["normalized_event_ids"]
        assert founder["backlinks"] or founder["outgoing_links"]
        assert founder["local_graph"]["focus_node"]["node_id"] == project_id

        assert team_response.status_code == 200
        team_blob = json.dumps(team_response.json(), sort_keys=True)
        assert "raw://" not in team_blob
        assert "raw_object_ref" not in team_blob
        assert source_response.status_code == 200
        source_blob = json.dumps(source_response.json(), sort_keys=True)
        assert "raw://" not in source_blob
        assert "raw_object_ref" not in source_blob
        assert investor_source_response.status_code == 404
    finally:
        await _cleanup(marker)


async def test_obsidian_preview_is_founder_only_markdown_preview_without_file_write() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    try:
        await _seed_project_graph(marker)
        async with _client() as client:
            response = await client.post(
                "/v1/knowledge/export/obsidian-preview",
                params={"view": "founder", "limit": 40},
            )
            team_response = await client.post(
                "/v1/knowledge/export/obsidian-preview",
                params={"view": "team", "limit": 40},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["vault_name"] == "FounderOS Knowledge Vault"
        assert payload["manifest"]["file_write_performed"] is False
        assert payload["files"]
        project_file = next(
            file for file in payload["files"] if file["title"] == "Project Alpha"
        )
        assert project_file["path"] == "Projects/Project Alpha.md"
        assert project_file["body"].startswith("# Project Alpha")
        assert project_file["frontmatter"]["node_type"] == "project"
        assert project_file["content_hash"]
        blob = json.dumps(payload, sort_keys=True)
        assert "raw://" not in blob
        assert "external_tokens" in blob
        assert team_response.status_code == 403
    finally:
        await _cleanup(marker)


async def test_knowledge_graph_hides_archived_nodes_by_default() -> None:
    await _ensure_tables()
    marker = uuid4().hex[:8]
    entity_id = f"knowledge_note:archived-project-alpha-{marker}"
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                EntityRecord(
                    entity_id=entity_id,
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
            await session.commit()
        async with _client() as client:
            hidden_response = await client.get(
                "/v1/knowledge/graph",
                params={"view": "founder", "q": marker, "limit": 20},
            )
            visible_response = await client.get(
                "/v1/knowledge/graph",
                params={
                    "view": "founder",
                    "q": marker,
                    "include_archived": "true",
                    "limit": 20,
                },
            )
        assert hidden_response.status_code == 200
        assert all(
            node["node_id"] != entity_id for node in hidden_response.json()["nodes"]
        )
        assert visible_response.status_code == 200
        assert any(
            node["node_id"] == entity_id
            and node["archived"] is True
            for node in visible_response.json()["nodes"]
        )
    finally:
        await _cleanup(marker)


async def test_stage12_obsidian_ui_static_markers_present() -> None:
    html = Path("app/static/founder_ui.html").read_text(encoding="utf-8")
    assert "/v1/knowledge/graph" in html
    assert "/v1/knowledge/nodes/" in html
    assert "/v1/knowledge/export/obsidian-preview" in html
    assert "Obsidian preview" in html
    assert "local graph" in html
