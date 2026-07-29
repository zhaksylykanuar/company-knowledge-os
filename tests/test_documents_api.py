from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.document_models import Document, DocumentVersion
from app.db.identity_models import (
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.main import app
from app.services.document_service import markdown_to_text


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_workspace(marker: str, *, suffix: str = "") -> tuple[User, Workspace]:
    async with AsyncSessionLocal() as session:
        user = User(email=f"docs-{marker}{suffix}@example.test", name="Docs Owner")
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name=f"Docs {marker}{suffix}",
            slug=f"docs-{marker}{suffix}",
            created_by_user_id=user.id,
        )
        session.add(workspace)
        await session.flush()
        session.add(
            Membership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=MEMBERSHIP_ROLE_OWNER,
            )
        )
        await session.commit()
        return user, workspace


async def _seed_viewer(workspace: Workspace, marker: str) -> User:
    async with AsyncSessionLocal() as session:
        user = User(email=f"docs-{marker}-viewer@example.test", name="Docs Viewer")
        session.add(user)
        await session.flush()
        session.add(
            Membership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=MEMBERSHIP_ROLE_VIEWER,
            )
        )
        await session.commit()
        return user


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"docs-{marker}%"))
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(User.email.like(f"docs-{marker}%@example.test"))
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(
                delete(DocumentVersion).where(
                    DocumentVersion.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Document).where(Document.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
            )
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


def test_markdown_to_text_strips_markup_deterministically() -> None:
    body = "# Launch\n\nHello **world** [site](https://x) ![img](https://y)\n\n```py\ncode\n```"
    text = markdown_to_text(body)
    assert "Launch" in text
    assert "Hello world site" in text
    assert "**" not in text and "#" not in text
    assert "https://x" not in text  # link target dropped, link text kept
    assert "code" in text


async def test_create_and_get_document_derives_body_text(monkeypatch) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        async with _client() as client:
            created = await client.post(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "title": "Launch Plan",
                    "body_markdown": "# Launch\n\nShip **beta** to first users.",
                    "tags": ["launch", "launch", " beta "],
                    "status": "published",
                },
            )
            assert created.status_code == 201, created.text
            document = created.json()["document"]
            document_id = document["id"]
            assert document["title"] == "Launch Plan"
            assert document["status"] == "published"
            assert document["tags"] == ["launch", "beta"]
            assert "Ship beta to first users." in document["body_text"]
            assert "**" not in document["body_text"]
            assert document["created_by_user_id"]
            assert created.json()["boundary"] == {
                "provider_calls": False,
                "external_writes": False,
                "llm": False,
                "reads_secrets": False,
            }

            fetched = await client.get(
                f"/api/v1/workspaces/{workspace.id}/documents/{document_id}",
                headers=_headers(),
                params={"owner_email": user.email},
            )
            assert fetched.status_code == 200
            assert fetched.json()["document"]["body_markdown"].startswith("# Launch")
    finally:
        await _cleanup(marker)


async def test_update_document_reprojects_body_text(monkeypatch) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        async with _client() as client:
            created = await client.post(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email},
                json={"title": "Draft", "body_markdown": "old body"},
            )
            document_id = created.json()["document"]["id"]

            updated = await client.patch(
                f"/api/v1/workspaces/{workspace.id}/documents/{document_id}",
                headers=_headers(),
                params={"owner_email": user.email},
                json={"body_markdown": "new **content** here", "status": "archived"},
            )
            assert updated.status_code == 200, updated.text
            body = updated.json()["document"]
            assert body["status"] == "archived"
            assert "new content here" in body["body_text"]
            assert body["title"] == "Draft"  # unchanged partial update
    finally:
        await _cleanup(marker)


async def test_document_versions_capture_create_and_update_history(monkeypatch) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        viewer = await _seed_viewer(workspace, marker)
        async with _client() as client:
            created = await client.post(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "title": "Launch Plan",
                    "body_markdown": "first **draft**",
                    "tags": ["launch"],
                    "status": "draft",
                },
            )
            assert created.status_code == 201, created.text
            document_id = created.json()["document"]["id"]

            updated = await client.patch(
                f"/api/v1/workspaces/{workspace.id}/documents/{document_id}",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "title": "Launch Plan v2",
                    "body_markdown": "second **draft**",
                    "tags": ["launch", "beta"],
                    "status": "published",
                },
            )
            assert updated.status_code == 200, updated.text

            versions = await client.get(
                f"/api/v1/workspaces/{workspace.id}/documents/{document_id}/versions",
                headers=_headers(),
                params={"owner_email": viewer.email},
            )
            assert versions.status_code == 200, versions.text

        payload = versions.json()
        assert payload["count"] == 2
        assert payload["boundary"] == {
            "provider_calls": False,
            "external_writes": False,
            "llm": False,
            "reads_secrets": False,
        }
        assert [version["version_number"] for version in payload["versions"]] == [2, 1]
        latest, first = payload["versions"]
        assert latest["title"] == "Launch Plan v2"
        assert latest["status"] == "published"
        assert latest["tags"] == ["launch", "beta"]
        assert "second draft" in latest["body_text"]
        assert first["title"] == "Launch Plan"
        assert first["status"] == "draft"
        assert first["tags"] == ["launch"]
        assert "first draft" in first["body_text"]
        assert first["created_by_user_id"] == str(user.id)
    finally:
        await _cleanup(marker)


async def test_empty_or_idempotent_patch_does_not_append_document_version(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        async with _client() as client:
            created = await client.post(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "title": "Launch Plan",
                    "body_markdown": "first **draft**",
                    "tags": ["launch", "beta"],
                    "status": "draft",
                },
            )
            assert created.status_code == 201, created.text
            document_id = created.json()["document"]["id"]

            empty_patch = await client.patch(
                f"/api/v1/workspaces/{workspace.id}/documents/{document_id}",
                headers=_headers(),
                params={"owner_email": user.email},
                json={},
            )
            assert empty_patch.status_code == 200, empty_patch.text
            assert empty_patch.json()["document"]["title"] == "Launch Plan"

            idempotent_patch = await client.patch(
                f"/api/v1/workspaces/{workspace.id}/documents/{document_id}",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "title": " Launch Plan ",
                    "body_markdown": "first **draft**",
                    "tags": ["launch", "beta", "launch"],
                    "status": "DRAFT",
                },
            )
            assert idempotent_patch.status_code == 200, idempotent_patch.text

            versions = await client.get(
                f"/api/v1/workspaces/{workspace.id}/documents/{document_id}/versions",
                headers=_headers(),
                params={"owner_email": user.email},
            )
            assert versions.status_code == 200, versions.text
            assert versions.json()["count"] == 1
            assert [
                version["version_number"] for version in versions.json()["versions"]
            ] == [1]

            changed_patch = await client.patch(
                f"/api/v1/workspaces/{workspace.id}/documents/{document_id}",
                headers=_headers(),
                params={"owner_email": user.email},
                json={"body_markdown": "second **draft**"},
            )
            assert changed_patch.status_code == 200, changed_patch.text

            changed_versions = await client.get(
                f"/api/v1/workspaces/{workspace.id}/documents/{document_id}/versions",
                headers=_headers(),
                params={"owner_email": user.email},
            )
            assert changed_versions.status_code == 200, changed_versions.text
            assert changed_versions.json()["count"] == 2
            assert [
                version["version_number"]
                for version in changed_versions.json()["versions"]
            ] == [2, 1]
    finally:
        await _cleanup(marker)


async def test_list_and_search_documents(monkeypatch) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        async with _client() as client:
            for title, body in (
                ("Hiring Plan", "We need to hire two engineers."),
                ("Runway Notes", "Cash runway is eighteen months."),
            ):
                res = await client.post(
                    f"/api/v1/workspaces/{workspace.id}/documents",
                    headers=_headers(),
                    params={"owner_email": user.email},
                    json={"title": title, "body_markdown": body},
                )
                assert res.status_code == 201

            listed = await client.get(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email},
            )
            assert listed.status_code == 200
            payload = listed.json()
            assert payload["count"] == 2
            assert "body_markdown" not in payload["documents"][0]
            assert "excerpt" in payload["documents"][0]

            search = await client.get(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email, "search": "runway"},
            )
            assert search.status_code == 200
            search_payload = search.json()
            assert search_payload["count"] == 1
            assert search_payload["documents"][0]["title"] == "Runway Notes"
    finally:
        await _cleanup(marker)


async def test_viewer_cannot_write_but_can_read(monkeypatch) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        viewer = await _seed_viewer(workspace, marker)
        async with _client() as client:
            created = await client.post(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email},
                json={"title": "Owner doc", "body_markdown": "content"},
            )
            document_id = created.json()["document"]["id"]

            viewer_read = await client.get(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": viewer.email},
            )
            assert viewer_read.status_code == 200
            assert viewer_read.json()["count"] == 1

            viewer_write = await client.post(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": viewer.email},
                json={"title": "Viewer doc", "body_markdown": "x"},
            )
            assert viewer_write.status_code == 403

            viewer_delete = await client.delete(
                f"/api/v1/workspaces/{workspace.id}/documents/{document_id}",
                headers=_headers(),
                params={"owner_email": viewer.email},
            )
            assert viewer_delete.status_code == 403
    finally:
        await _cleanup(marker)


async def test_document_validation_and_not_found(monkeypatch) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        async with _client() as client:
            blank_title = await client.post(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email},
                json={"title": "   ", "body_markdown": "x"},
            )
            assert blank_title.status_code == 422

            bad_status = await client.post(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email},
                json={"title": "ok", "status": "weird"},
            )
            assert bad_status.status_code == 400
            assert bad_status.json() == {"detail": "unknown document status"}

            missing = await client.get(
                f"/api/v1/workspaces/{workspace.id}/documents/{uuid4()}",
                headers=_headers(),
                params={"owner_email": user.email},
            )
            assert missing.status_code == 404
            assert missing.json() == {"detail": "document not found"}
    finally:
        await _cleanup(marker)


async def test_document_workspace_isolation(monkeypatch) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user_a, workspace_a = await _seed_workspace(marker, suffix="-a")
        user_b, workspace_b = await _seed_workspace(marker, suffix="-b")
        async with _client() as client:
            created = await client.post(
                f"/api/v1/workspaces/{workspace_a.id}/documents",
                headers=_headers(),
                params={"owner_email": user_a.email},
                json={"title": "A-only", "body_markdown": "secret to A"},
            )
            document_id = created.json()["document"]["id"]

            cross = await client.get(
                f"/api/v1/workspaces/{workspace_b.id}/documents/{document_id}",
                headers=_headers(),
                params={"owner_email": user_b.email},
            )
            assert cross.status_code == 404

            b_list = await client.get(
                f"/api/v1/workspaces/{workspace_b.id}/documents",
                headers=_headers(),
                params={"owner_email": user_b.email},
            )
            assert b_list.status_code == 200
            assert b_list.json()["count"] == 0
    finally:
        await _cleanup(marker)


async def test_cross_workspace_document_version_fails_at_commit() -> None:
    marker = uuid4().hex[:10]
    await _cleanup(marker)
    try:
        _user_a, workspace_a = await _seed_workspace(marker, suffix="-a")
        _user_b, workspace_b = await _seed_workspace(marker, suffix="-b")
        async with AsyncSessionLocal() as session:
            document = Document(
                workspace_id=workspace_a.id,
                title="Workspace A document",
                body_markdown="private",
                body_text="private",
                status="draft",
            )
            session.add(document)
            await session.commit()
            document_id = document.id

        async with AsyncSessionLocal() as session:
            session.add(
                DocumentVersion(
                    workspace_id=workspace_b.id,
                    document_id=document_id,
                    version_number=1,
                    title="Invalid cross-workspace version",
                    body_markdown="private",
                    body_text="private",
                    status="draft",
                )
            )
            with pytest.raises(
                IntegrityError,
                match="fk_document_versions_workspace_document",
            ):
                await session.commit()
            await session.rollback()

        async with AsyncSessionLocal() as session:
            constraint_names = set(
                (
                    await session.execute(
                        text(
                            """
                            select conname
                            from pg_constraint
                            where conname in (
                              'uq_documents_workspace_id_id',
                              'fk_document_versions_workspace_document'
                            )
                            """
                        )
                    )
                ).scalars()
            )
        assert constraint_names == {
            "uq_documents_workspace_id_id",
            "fk_document_versions_workspace_document",
        }
    finally:
        await _cleanup(marker)


async def test_published_document_appears_in_company_brain(monkeypatch) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        async with _client() as client:
            await client.post(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "title": "Company Handbook",
                    "body_markdown": "Our operating principles.",
                    "status": "published",
                },
            )
            archived = await client.post(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers=_headers(),
                params={"owner_email": user.email},
                json={
                    "title": "Old Handbook",
                    "body_markdown": "Outdated.",
                    "status": "archived",
                },
            )
            assert archived.status_code == 201

            brain = await client.get(
                f"/api/v1/workspaces/{workspace.id}/company-brain",
                headers=_headers(),
                params={"owner_email": user.email},
            )
            assert brain.status_code == 200, brain.text
            notes = brain.json()["documents"]["notes"]
            titles = {note["title"] for note in notes}
            assert "Company Handbook" in titles
            assert "Old Handbook" not in titles
            handbook = next(n for n in notes if n["title"] == "Company Handbook")
            assert "operating principles" in handbook["excerpt"]
            assert handbook["source_refs"][0]["kind"] == "internal_document"
            assert any(
                ref["kind"] == "internal_document" for ref in brain.json()["evidence"]
            )
    finally:
        await _cleanup(marker)
