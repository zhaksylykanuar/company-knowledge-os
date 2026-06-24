from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.repository_source_inventory import (
    INVENTORY_CANONICAL_REPOSITORIES,
    INVENTORY_DISCOVERY_SNAPSHOT,
    INVENTORY_LEGACY_SEED,
    INVENTORY_SOURCE_EVENTS,
    load_repository_source_inventory,
)

GITHUB_REPOSITORY_READ_SOURCE = "repository_inventory"

_VALID_VISIBILITIES = {"public", "private", "internal", "unknown"}


@dataclass(frozen=True)
class GitHubRepositoryFilters:
    search: str | None = None
    visibility: str | None = None
    archived: bool | None = None
    limit: int = 50


@dataclass(frozen=True)
class GitHubRepositoryListResult:
    repositories: list[dict[str, Any]]
    count: int
    source: str
    is_live: bool
    warnings: list[str]


async def list_workspace_github_repositories(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    filters: GitHubRepositoryFilters,
) -> GitHubRepositoryListResult:
    """Return workspace-scoped repository rows from local read models only.

    The repository inventory is read-only and prefers canonical repository rows
    for the requested workspace, with retained source_events/discovery data only
    as compatibility fallback.
    """

    inventory = await load_repository_source_inventory(
        session=session,
        workspace_id=workspace_id,
    )
    if inventory.get("network_calls") is not False or inventory.get("db_written") is not False:
        raise ValueError("repository_inventory_not_read_only")

    source_class = _safe_text(inventory.get("source_class")) or "unknown"
    warnings = _source_warnings(source_class)
    raw_items = _inventory_items(inventory=inventory, source_class=source_class)
    if source_class == INVENTORY_LEGACY_SEED:
        warnings.append(
            "no local GitHub repository evidence found; legacy seed catalog is not returned by this API"
        )

    snapshot_ref = _snapshot_evidence_ref(inventory.get("source_snapshot"), source_class)
    normalized = [
        _normalize_repository(
            item,
            source_class=source_class,
            snapshot_ref=snapshot_ref,
        )
        for item in raw_items
    ]
    filtered = _apply_filters(normalized, filters=filters)

    if raw_items and not any(repo["evidence_refs"] for repo in filtered):
        warnings.append(
            "repository evidence refs are not yet available from the selected inventory source"
        )
    if not filtered:
        warnings.append("no repositories matched the current local inventory and filters")

    result = GitHubRepositoryListResult(
        repositories=filtered[: filters.limit],
        count=len(filtered[: filters.limit]),
        source=GITHUB_REPOSITORY_READ_SOURCE,
        is_live=False,
        warnings=warnings,
    )
    return result


def _source_warnings(source_class: str) -> list[str]:
    if source_class == INVENTORY_CANONICAL_REPOSITORIES:
        return [
            "repository inventory is read from canonical repositories; no live provider call was made"
        ]
    if source_class == INVENTORY_SOURCE_EVENTS:
        return [
            "repository inventory is using retained source_events compatibility fallback"
        ]
    return [
        "repository inventory is currently from local/operator bridge and is not yet tied to IntegrationConnection"
    ]


def _inventory_items(
    *,
    inventory: Mapping[str, Any],
    source_class: str,
) -> list[Mapping[str, Any]]:
    if source_class == INVENTORY_LEGACY_SEED:
        return []
    items = inventory.get("repositories")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def _normalize_repository(
    item: Mapping[str, Any],
    *,
    source_class: str,
    snapshot_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    name = _safe_text(item.get("repo_key")) or _safe_name_from_full_name(item.get("full_name"))
    full_name = _safe_text(item.get("full_name")) or name
    visibility = _safe_visibility(item.get("visibility"))
    evidence_refs = _item_evidence_refs(item.get("evidence_refs"))
    if not evidence_refs and snapshot_ref is not None:
        evidence_refs = [snapshot_ref]
    return {
        "id": full_name or name or "unknown",
        "name": name or full_name or "unknown",
        "full_name": full_name or name or "unknown",
        "default_branch": _safe_text(item.get("default_branch")),
        "visibility": visibility,
        "archived": _safe_bool(item.get("archived")) or False,
        "source_url": _safe_github_url(item.get("source_url")),
        "last_activity_at": _safe_datetime_text(item.get("last_observed_at")),
        "source": GITHUB_REPOSITORY_READ_SOURCE,
        "evidence_refs": evidence_refs,
        "metadata": {
            "source_class": source_class,
            "provider_key": _safe_text(item.get("provider_key")) or "github",
            "repo_role": _safe_text(item.get("repo_role")),
            "repo_not_jira_project": bool(item.get("repo_not_jira_project")),
            "source_event_count": int(item.get("source_event_count") or 0),
        },
    }


def _apply_filters(
    repositories: list[dict[str, Any]],
    *,
    filters: GitHubRepositoryFilters,
) -> list[dict[str, Any]]:
    search = filters.search.strip().casefold() if filters.search else None
    visibility = filters.visibility
    archived = filters.archived

    def matches(repo: Mapping[str, Any]) -> bool:
        if search:
            haystack = " ".join(
                str(repo.get(key) or "") for key in ("name", "full_name")
            ).casefold()
            if search not in haystack:
                return False
        if visibility and repo.get("visibility") != visibility:
            return False
        if archived is not None and bool(repo.get("archived")) is not archived:
            return False
        return True

    return [repo for repo in repositories if matches(repo)]


def _snapshot_evidence_ref(
    value: Any,
    source_class: str,
) -> dict[str, Any] | None:
    if source_class != INVENTORY_DISCOVERY_SNAPSHOT or not isinstance(value, Mapping):
        return None
    ref = _safe_text(value.get("snapshot_key")) or _safe_text(value.get("path"))
    if not ref:
        return None
    return {
        "kind": "repository_inventory_snapshot",
        "source": INVENTORY_DISCOVERY_SNAPSHOT,
        "ref": ref,
        "url": None,
    }


def _item_evidence_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs: list[dict[str, Any]] = []
    for raw in value[:20]:
        if not isinstance(raw, Mapping):
            continue
        ref = {
            "kind": _safe_text(raw.get("kind")) or "source_event",
            "source": _safe_text(raw.get("source")) or INVENTORY_SOURCE_EVENTS,
            "ref": _safe_text(raw.get("ref")),
            "url": _safe_github_url(raw.get("url")),
        }
        if ref["ref"]:
            refs.append(ref)
    return refs


def _safe_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _safe_name_from_full_name(value: Any) -> str | None:
    text = _safe_text(value)
    if not text:
        return None
    return text.rsplit("/", 1)[-1]


def _safe_visibility(value: Any) -> str:
    text = _safe_text(value)
    return text if text in _VALID_VISIBILITIES else "unknown"


def _safe_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _safe_github_url(value: Any) -> str | None:
    text = _safe_text(value)
    if text and "github.com" in text and "@" not in text:
        return text
    return None


def _safe_datetime_text(value: Any) -> str | None:
    text = _safe_text(value)
    if text is None:
        return None
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return text
