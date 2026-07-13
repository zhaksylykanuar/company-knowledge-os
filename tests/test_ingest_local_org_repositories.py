"""Focused tests for scripts/ingest_local_org_repositories.py (offline org ingest)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.canonical_models import SOURCE_RECORD_PROVIDER_GITHUB, Repository
from app.db.identity_models import Membership, User, Workspace
from app.services.github_repository_read_service import (
    GitHubRepositoryFilters,
    list_workspace_github_repositories,
)
from app.services.identity_service import get_user_by_email
from app.services.repository_source_inventory import INVENTORY_CANONICAL_REPOSITORIES
from scripts.create_admin_user import provision_admin_user
from scripts.ingest_local_org_repositories import (
    _target_org_from_env_files,
    ingest,
    load_org_repositories,
)

ORG = "qtwin-io"


def _write_repos(path: Path) -> None:
    payload = [
        {"full_name": f"{ORG}/base-collector", "name": "base-collector", "private": True},
        {
            "full_name": f"{ORG}/ssap-frontend",
            "name": "ssap-frontend",
            "private": False,
            "default_branch": "main",
            "archived": False,
        },
        # A repo from a different owner must be ignored by the org filter.
        {"full_name": "azhaks-cpo/personal-thing", "name": "personal-thing", "private": True},
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")


async def _provision(email: str) -> str:
    async with AsyncSessionLocal() as session:
        result = await provision_admin_user(
            session, email=email, password="pw-ingest", name="Ingest Owner"
        )
        await session.commit()
        return result["workspace_id"]


async def _cleanup(email: str) -> None:
    async with AsyncSessionLocal() as session:
        user = await get_user_by_email(session, email=email)
        if user is None:
            return
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.created_by_user_id == user.id)
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(
                delete(Repository).where(Repository.workspace_id.in_(workspace_ids))
            )
        await session.execute(delete(Membership).where(Membership.user_id == user.id))
        await session.execute(
            delete(Workspace).where(Workspace.created_by_user_id == user.id)
        )
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


def test_load_org_repositories_filters_to_org_owner(tmp_path: Path) -> None:
    source = tmp_path / "repos.json"
    _write_repos(source)
    repos = load_org_repositories(source, org=ORG)
    full_names = {repo["full_name"] for repo in repos}
    assert full_names == {f"{ORG}/base-collector", f"{ORG}/ssap-frontend"}
    by_name = {repo["full_name"]: repo for repo in repos}
    assert by_name[f"{ORG}/base-collector"]["visibility"] == "private"
    assert by_name[f"{ORG}/ssap-frontend"]["visibility"] == "public"


def test_target_org_reads_loaded_env_file_order_without_secret_values(
    tmp_path: Path,
) -> None:
    env = tmp_path / ".env"
    env_local = tmp_path / ".env.local"
    env.write_text(
        "FOS_GITHUB_TARGET_ORG=old-org\n"
        "FOS_GITHUB_READONLY_TOKEN=must-not-matter\n",
        encoding="utf-8",
    )
    env_local.write_text("FOS_GITHUB_TARGET_ORG=qtwin-io\n", encoding="utf-8")

    assert _target_org_from_env_files((env, env_local)) == "qtwin-io"


async def test_ingest_promotes_org_repos_to_canonical_and_is_idempotent(
    tmp_path: Path,
) -> None:
    marker = uuid4().hex[:10]
    email = f"ingest-{marker}@example.test"
    source = tmp_path / "repos.json"
    _write_repos(source)
    try:
        workspace_id = await _provision(email)

        first = await ingest(
            source=source,
            org=ORG,
            workspace_id=workspace_id,
            owner_email=None,
            dry_run=False,
        )
        assert first["status"] == "ok"
        assert first["repository_count"] == 2
        assert first["created"] == 2
        assert first["updated"] == 0

        second = await ingest(
            source=source,
            org=ORG,
            workspace_id=workspace_id,
            owner_email=None,
            dry_run=False,
        )
        assert second["created"] == 0
        assert second["updated"] == 2

        async with AsyncSessionLocal() as session:
            result = await list_workspace_github_repositories(
                session=session,
                workspace_id=first["workspace_id"],
                filters=GitHubRepositoryFilters(limit=50),
            )
        full_names = {repo["full_name"] for repo in result.repositories}
        assert full_names == {f"{ORG}/base-collector", f"{ORG}/ssap-frontend"}
        assert all(
            repo["metadata"]["source_class"] == INVENTORY_CANONICAL_REPOSITORIES
            for repo in result.repositories
        )
        assert result.is_live is False
    finally:
        await _cleanup(email)


async def test_ingest_dry_run_writes_nothing(tmp_path: Path) -> None:
    marker = uuid4().hex[:10]
    email = f"ingest-{marker}@example.test"
    source = tmp_path / "repos.json"
    _write_repos(source)
    try:
        workspace_id = await _provision(email)
        result = await ingest(
            source=source,
            org=ORG,
            workspace_id=workspace_id,
            owner_email=None,
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert result["repository_count"] == 2
        async with AsyncSessionLocal() as session:
            rows = list(
                (
                    await session.execute(
                        select(Repository).where(
                            Repository.workspace_id == result["workspace_id"],
                            Repository.provider == SOURCE_RECORD_PROVIDER_GITHUB,
                        )
                    )
                ).scalars()
            )
        assert rows == []
    finally:
        await _cleanup(email)
