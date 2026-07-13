#!/usr/bin/env python
"""Ingest the local GitHub *organization* repository snapshot into canonical rows.

Why this exists
---------------
The ``/github`` repository list is served by
``app.services.github_repository_read_service.list_workspace_github_repositories``
which resolves its rows with this precedence:

    canonical Repository rows  ->  retained source_events  ->  discovery
    snapshot  ->  legacy seed catalog

When a workspace has no canonical ``Repository`` rows it falls back to whatever
``source_events`` happen to exist, which can be stale/unrelated rows (the "wrong
repos"). The correct organization repositories already exist locally in
``.local/repos.json`` (and the discovery snapshot), so this script promotes them
into canonical rows for a workspace. Canonical is the highest-precedence source,
so this fixes the list *without deleting* any existing event history.

Safety posture (matches AGENTS.md / CLAUDE.md):
  * Offline only: never calls GitHub or any provider, never reads tokens.
  * Reads a local names-only repository list (rejects sensitive-looking keys).
  * Idempotent upsert on the existing canonical identity
    (workspace_id, provider, full_name); re-running updates in place.
  * No secrets are printed. Output is a safe JSON summary.

Usage:
  uv run python scripts/ingest_local_org_repositories.py \
      --owner-email founder@example.com --org qtwin-io

  # If --org is omitted, the script reads FOS_GITHUB_TARGET_ORG from the real
  # environment first, then from .env.local/.env. It never reads or prints
  # GitHub tokens.
  uv run python scripts/ingest_local_org_repositories.py \
      --owner-email founder@example.com

  uv run python scripts/ingest_local_org_repositories.py \
      --workspace-id <uuid> --org qtwin-io --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import AsyncSessionLocal  # noqa: E402
from app.db.canonical_models import (  # noqa: E402
    SOURCE_RECORD_PROVIDER_GITHUB,
    Repository,
)
from app.services.identity_service import (  # noqa: E402
    get_user_by_email,
    list_workspaces_for_user,
)

_FULL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SENSITIVE_MARKERS = ("token", "secret", "password", "credential", "authorization")
_ALLOWED_VISIBILITY = {"public", "private", "internal"}
_TARGET_ORG_ENV_KEYS = ("FOS_GITHUB_TARGET_ORG", "FOUNDEROS_GITHUB_TARGET_ORG")


class IngestError(RuntimeError):
    """Raised when the local snapshot cannot be ingested safely."""


def _reject_sensitive_keys(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if any(marker in str(key).casefold() for marker in _SENSITIVE_MARKERS):
                raise IngestError(f"refusing to read sensitive-looking key at {path}.{key}")
            _reject_sensitive_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, path=f"{path}[{index}]")


def _safe_text(value: Any, *, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _parse_dt(value: Any) -> datetime | None:
    text = _safe_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_org_repositories(source: Path, *, org: str) -> list[dict[str, Any]]:
    """Load + normalize the local repo list, filtered to a single org owner."""

    org = org.strip()
    if not org:
        raise IngestError(
            "github organization is required; pass --org or set FOS_GITHUB_TARGET_ORG"
        )
    if not source.exists():
        raise IngestError(f"repository list not found: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestError(f"invalid JSON in {source}: {exc}") from exc
    if not isinstance(raw, list):
        raise IngestError("repository list must be a JSON array")
    _reject_sensitive_keys(raw, path="repos")

    org_prefix = f"{org.strip().casefold()}/"
    normalized: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise IngestError(f"repository item #{index + 1} must be an object")
        full_name = _safe_text(item.get("full_name"), limit=500)
        if full_name is None:
            owner = item.get("owner")
            owner_login = owner.get("login") if isinstance(owner, dict) else owner
            name = _safe_text(item.get("name"), limit=255)
            owner_login = _safe_text(owner_login, limit=255)
            if owner_login and name:
                full_name = f"{owner_login}/{name}"
        if not full_name or not _FULL_NAME_RE.fullmatch(full_name):
            continue
        if not full_name.casefold().startswith(org_prefix):
            continue
        private = bool(item.get("private"))
        visibility = _safe_text(item.get("visibility"), limit=20)
        if visibility not in _ALLOWED_VISIBILITY:
            visibility = "private" if private else "public"
        normalized[full_name] = {
            "full_name": full_name,
            "name": _safe_text(item.get("name"), limit=255) or full_name.split("/", 1)[1],
            "visibility": visibility,
            "archived": bool(item.get("archived")),
            "default_branch": _safe_text(item.get("default_branch"), limit=255),
            "source_url": _safe_text(item.get("html_url"), limit=1000)
            or f"https://github.com/{full_name}",
            "last_activity_at": _parse_dt(item.get("pushed_at"))
            or _parse_dt(item.get("updated_at")),
            "language": _safe_text(item.get("language"), limit=100),
        }
    return [normalized[key] for key in sorted(normalized)]


async def _resolve_workspace_id(
    session: AsyncSession,
    *,
    workspace_id: str | None,
    owner_email: str | None,
) -> UUID:
    if workspace_id:
        return UUID(workspace_id)
    if not owner_email:
        raise IngestError("either --workspace-id or --owner-email is required")
    user = await get_user_by_email(session, email=owner_email)
    if user is None:
        raise IngestError(f"no user found for email: {owner_email}")
    memberships = await list_workspaces_for_user(session, user_id=user.id)
    if not memberships:
        raise IngestError(f"user {owner_email} owns no workspace")
    return memberships[0].workspace.id


async def _upsert_repository(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    repo: dict[str, Any],
    snapshot_ref: str,
) -> bool:
    """Idempotent upsert keyed on (workspace_id, provider, full_name)."""

    full_name = repo["full_name"]
    metadata = {
        "source": {"kind": "local_org_snapshot", "ref": snapshot_ref},
        "evidence_refs": [
            {"kind": "local_org_snapshot", "source": "repository_inventory", "ref": snapshot_ref}
        ],
        "metadata": {
            "owner": full_name.split("/", 1)[0],
            "language": repo.get("language"),
            "ingested_offline": True,
        },
    }
    values = {
        Repository.workspace_id: workspace_id,
        Repository.provider: SOURCE_RECORD_PROVIDER_GITHUB,
        Repository.external_id: full_name,  # stable local id (no numeric id offline)
        Repository.name: repo["name"],
        Repository.full_name: full_name,
        Repository.default_branch: repo.get("default_branch"),
        Repository.visibility: repo["visibility"],
        Repository.archived: bool(repo.get("archived")),
        Repository.source_url: repo.get("source_url"),
        Repository.last_activity_at: repo.get("last_activity_at"),
        Repository.repo_metadata: metadata,
    }
    inserted = (
        await session.execute(
            pg_insert(Repository)
            .values(values)
            .on_conflict_do_nothing()
            .returning(Repository.id)
        )
    ).first()
    if inserted is not None:
        return True

    existing = await session.scalar(
        select(Repository)
        .where(Repository.workspace_id == workspace_id)
        .where(Repository.provider == SOURCE_RECORD_PROVIDER_GITHUB)
        .where(Repository.full_name == full_name)
    )
    if existing is None:
        raise IngestError(f"upsert conflict could not be resolved for {full_name}")
    update_values = {
        Repository.name: repo["name"],
        Repository.default_branch: repo.get("default_branch"),
        Repository.visibility: repo["visibility"],
        Repository.archived: bool(repo.get("archived")),
        Repository.source_url: repo.get("source_url"),
        Repository.last_activity_at: repo.get("last_activity_at"),
        Repository.repo_metadata: metadata,
    }
    await session.execute(
        update(Repository).where(Repository.id == existing.id).values(update_values)
    )
    return False


async def ingest(
    *,
    source: Path,
    org: str,
    workspace_id: str | None,
    owner_email: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    repos = load_org_repositories(source, org=org)
    if not repos:
        raise IngestError(
            f"no repositories for org {org!r} found in {source} (check --org / --source)"
        )
    snapshot_ref = str(source)
    async with AsyncSessionLocal() as session:
        ws_id = await _resolve_workspace_id(
            session, workspace_id=workspace_id, owner_email=owner_email
        )
        if dry_run:
            return {
                "status": "dry_run",
                "workspace_id": str(ws_id),
                "org": org,
                "repository_count": len(repos),
                "full_names": [r["full_name"] for r in repos],
            }
        created = 0
        updated = 0
        for repo in repos:
            was_created = await _upsert_repository(
                session, workspace_id=ws_id, repo=repo, snapshot_ref=snapshot_ref
            )
            created += int(was_created)
            updated += int(not was_created)
        await session.commit()
    return {
        "status": "ok",
        "workspace_id": str(ws_id),
        "org": org,
        "repository_count": len(repos),
        "created": created,
        "updated": updated,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline ingest of local org repo snapshot into canonical rows."
    )
    parser.add_argument("--source", default=".local/repos.json")
    parser.add_argument(
        "--org",
        default=_default_target_org(),
        help=(
            "Organization owner login to ingest. Defaults to FOS_GITHUB_TARGET_ORG "
            "from environment, .env.local, or .env."
        ),
    )
    parser.add_argument("--workspace-id", default=None)
    parser.add_argument("--owner-email", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _default_target_org() -> str | None:
    for key in _TARGET_ORG_ENV_KEYS:
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
    return _target_org_from_env_files((Path(".env"), Path(".env.local")))


def _target_org_from_env_files(paths: tuple[Path, ...]) -> str | None:
    """Read only the non-secret target-org key from local env files."""

    found: str | None = None
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        for raw_line in path.read_text(errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() not in _TARGET_ORG_ENV_KEYS:
                continue
            value = value.strip().strip('"').strip("'")
            if value:
                found = value
    return found


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = asyncio.run(
            ingest(
                source=Path(args.source),
                org=args.org,
                workspace_id=args.workspace_id,
                owner_email=args.owner_email,
                dry_run=args.dry_run,
            )
        )
    except IngestError as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
