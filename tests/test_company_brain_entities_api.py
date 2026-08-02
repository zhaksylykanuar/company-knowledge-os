from __future__ import annotations

from uuid import uuid4

from tests.test_company_brain_github_api import (
    _async_client,
    _bootstrap_payload,
    _bootstrap_workspace,
    _cleanup,
    _headers,
    _seed_company_brain_rows,
    _set_auth,
)


async def test_workspace_entities_returns_empty_state(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/company-brain/entities",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["mode"] == "github_first_canonical"
        assert body["source"] == "canonical_company_brain_entities"
        assert body["summary"] == {
            "total": 0,
            "by_entity_type": [],
            "by_source_provider": [],
        }
        assert body["entities"] == []
        assert body["evidence"] == []
        assert body["is_live"] is False
        assert body["llm_used"] is False
        assert body["capabilities"] == {
            "live_github_oauth": False,
            "live_provider_sync": False,
            "local_sync": True,
            "llm_briefing": False,
        }
        assert any("No canonical entities" in warning for warning in body["warnings"])
    finally:
        await _cleanup(marker)


async def test_workspace_entities_projects_canonical_rows_with_evidence(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        await _seed_company_brain_rows(workspace_id, marker)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/company-brain/entities",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200, response.text
        body = response.json()

        entity_types = {entity["entity_type"] for entity in body["entities"]}
        assert "repository" in entity_types
        assert "issue" in entity_types
        assert "pull_request" in entity_types

        # Every entity carries a stable key and a source provider; no LLM/live use.
        assert all(entity["key"] for entity in body["entities"])
        assert body["is_live"] is False
        assert body["llm_used"] is False

        # Summary counts are consistent with the projected entities.
        assert body["summary"]["total"] == len(body["entities"])
        type_counts = {
            row["entity_type"]: row["count"]
            for row in body["summary"]["by_entity_type"]
        }
        assert type_counts.get("repository", 0) >= 1

        # The repository entity mirrors the canonical repository row + evidence.
        repository_entity = next(
            entity
            for entity in body["entities"]
            if entity["entity_type"] == "repository"
        )
        assert repository_entity["source_provider"] == "github"
        assert repository_entity["title"] == "qtwin-io/founderos-api"
        assert repository_entity["source_refs"], "repository entity should carry evidence"
        assert body["evidence"], "aggregate evidence should be non-empty"

        # No raw provider payloads / secret-like values leak into the projection.
        serialized = response.text
        assert "SHOULD_NOT_LEAK" not in serialized
        assert "SHOULD_NOT_RENDER" not in serialized
    finally:
        await _cleanup(marker)


async def test_workspace_entities_projects_local_connector_records(monkeypatch) -> None:
    from datetime import datetime, timezone
    from uuid import UUID

    from app.db.base import AsyncSessionLocal
    from app.db.canonical_models import SourceRecord

    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        now = datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc)
        async with AsyncSessionLocal() as session:
            session.add_all(
                [
                    SourceRecord(
                        workspace_id=UUID(workspace_id),
                        provider="gmail",
                        external_id=f"gmail-{marker}",
                        record_type="message",
                        source_url="https://mail.google.com/mail/u/0/#inbox/msg",
                        payload={
                            "normalized_message": {
                                "message_id": f"gmail-{marker}",
                                "subject": "Customer escalation",
                                "unread": True,
                            }
                        },
                        payload_hash=f"gmail-hash-{marker}",
                        observed_at=now,
                        source_updated_at=now,
                    ),
                    SourceRecord(
                        workspace_id=UUID(workspace_id),
                        provider="drive",
                        external_id=f"drive-{marker}",
                        record_type="file",
                        source_url="https://drive.google.com/file/d/file-1/view",
                        payload={
                            "normalized_file": {
                                "file_id": f"drive-{marker}",
                                "name": "Q3 plan",
                                "shared": True,
                            }
                        },
                        payload_hash=f"drive-hash-{marker}",
                        observed_at=now,
                        source_updated_at=now,
                    ),
                ]
            )
            await session.commit()

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/company-brain/entities",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        providers = {row["source_provider"] for row in body["summary"]["by_source_provider"]}
        assert "gmail" in providers
        assert "drive" in providers
        entity_types = {entity["entity_type"] for entity in body["entities"]}
        assert "email_message" in entity_types
        assert "drive_file" in entity_types
    finally:
        await _cleanup(marker)
