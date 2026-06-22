from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.event_models import SourceEvent
from app.services.operator_output_sanitizer import inspect_operator_output
from app.services.repository_portfolio import repository_portfolio_catalog

INVENTORY_SOURCE_EVENTS = "source_events"
INVENTORY_DISCOVERY_SNAPSHOT = "github_discovery_snapshot"
INVENTORY_LEGACY_SEED = "legacy_seed_catalog"
REPO_MAPPING_POLICY = "repo_is_component_or_evidence_not_jira_project"

_SAFE_REPO_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_GITHUB_URL_RE = re.compile(r"github\.com[:/]+([^/\s?#]+)/([^/\s?#]+)")
_FULL_NAME_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:[#@/]|$)")


async def load_repository_source_inventory(
    *,
    session: AsyncSession | None = None,
    workspace_path: str | Path | None = None,
    raw_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the current repository inventory read model.

    Precedence is SourceEvent/Postgres first, saved GitHub discovery snapshots
    second, and the static repository portfolio only as a legacy seed fallback.
    The function is read-only and never calls providers.
    """

    safe_now = now or datetime.now(timezone.utc)
    legacy_items = _legacy_seed_items()
    source_event_items: list[dict[str, Any]] = []
    if session is not None:
        source_event_items = await _source_event_items(session)
    if source_event_items:
        return _finalize(
            _inventory_payload(
                source_class=INVENTORY_SOURCE_EVENTS,
                items=source_event_items,
                legacy_items=legacy_items,
                now=safe_now,
                source_event_count=len(source_event_items),
                discovery_snapshot=_empty_snapshot(),
            )
        )

    discovery_items, discovery_snapshot = _discovery_items(
        workspace_path=workspace_path,
        raw_path=raw_path,
        now=safe_now,
    )
    if discovery_items:
        return _finalize(
            _inventory_payload(
                source_class=INVENTORY_DISCOVERY_SNAPSHOT,
                items=discovery_items,
                legacy_items=legacy_items,
                now=safe_now,
                source_event_count=0,
                discovery_snapshot=discovery_snapshot,
            )
        )

    return _finalize(
        _inventory_payload(
            source_class=INVENTORY_LEGACY_SEED,
            items=legacy_items,
            legacy_items=legacy_items,
            now=safe_now,
            source_event_count=0,
            discovery_snapshot=discovery_snapshot,
        )
    )


def load_repository_source_inventory_snapshot(
    *,
    workspace_path: str | Path | None = None,
    raw_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Synchronous discovery/legacy inventory for scripts and static summaries."""

    safe_now = now or datetime.now(timezone.utc)
    legacy_items = _legacy_seed_items()
    discovery_items, discovery_snapshot = _discovery_items(
        workspace_path=workspace_path,
        raw_path=raw_path,
        now=safe_now,
    )
    source_class = (
        INVENTORY_DISCOVERY_SNAPSHOT if discovery_items else INVENTORY_LEGACY_SEED
    )
    items = discovery_items or legacy_items
    return _finalize(
        _inventory_payload(
            source_class=source_class,
            items=items,
            legacy_items=legacy_items,
            now=safe_now,
            source_event_count=0,
            discovery_snapshot=discovery_snapshot,
        )
    )


async def _source_event_items(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SourceEvent)
            .where(SourceEvent.source_system == "github")
            .order_by(SourceEvent.updated_at.desc(), SourceEvent.id.desc())
            .limit(1000)
        )
    ).scalars()
    items: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = _identity_from_source_event(row)
        if identity is None:
            continue
        key = _match_key(identity["repo_key"])
        current = items.get(key)
        item = {
            "repo_key": identity["repo_key"],
            "full_name": identity.get("full_name") or identity["repo_key"],
            "provider_key": "github",
            "source_class": INVENTORY_SOURCE_EVENTS,
            "last_observed_at": _iso(row.source_event_ts or row.updated_at or row.created_at),
            "source_event_count": 1,
            "repo_role": "component_evidence",
            "repo_not_jira_project": True,
        }
        if current is None:
            items[key] = item
        else:
            current["source_event_count"] = int(current.get("source_event_count") or 0) + 1
            current["last_observed_at"] = _max_iso(
                current.get("last_observed_at"), item["last_observed_at"]
            )
    return sorted(items.values(), key=lambda item: str(item["repo_key"]).casefold())


def _identity_from_source_event(row: SourceEvent) -> dict[str, str] | None:
    candidates: list[Any] = [
        row.source_object_id,
        row.source_url,
        row.title,
    ]
    metadata = row.metadata_json if isinstance(row.metadata_json, Mapping) else {}
    candidates.extend(
        metadata.get(key)
        for key in ("repo", "repository", "repository_full_name", "full_name")
    )
    for candidate in candidates:
        identity = _parse_repo_identity(candidate)
        if identity is not None:
            return identity
    if row.source_object_type == "repository":
        repo_key = _safe_repo_part(row.source_object_id)
        if repo_key:
            return {"repo_key": repo_key, "full_name": repo_key}
    return None


def _discovery_items(
    *,
    workspace_path: str | Path | None,
    raw_path: str | Path | None,
    now: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    workspace = Path(workspace_path or settings.founderos_local_workspace_path)
    selected = Path(raw_path) if raw_path is not None else _latest_raw_repos_path(workspace)
    if selected is None or not selected.exists():
        return [], _empty_snapshot()
    snapshot = _snapshot_meta(path=selected, workspace=workspace, now=now)
    try:
        raw = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], {**snapshot, "available": False, "status": "invalid_json"}
    if not isinstance(raw, list):
        return [], {**snapshot, "available": False, "status": "invalid_shape"}

    items: list[dict[str, Any]] = []
    for repo in raw:
        if not isinstance(repo, Mapping):
            continue
        name = _safe_repo_part(repo.get("name"))
        full_name = _safe_full_name(repo.get("full_name"))
        if name is None and full_name is not None:
            name = full_name.split("/")[-1]
        if name is None:
            continue
        items.append(
            {
                "repo_key": name,
                "full_name": full_name or name,
                "provider_key": "github",
                "source_class": INVENTORY_DISCOVERY_SNAPSHOT,
                "last_observed_at": _safe_text(repo.get("updated_at"))
                or _safe_text(repo.get("pushed_at")),
                "repo_role": "component_evidence",
                "repo_not_jira_project": True,
            }
        )
    return _dedupe_items(items), {**snapshot, "repo_count": len(items)}


def _legacy_seed_items() -> list[dict[str, Any]]:
    items = []
    for entry in repository_portfolio_catalog():
        if not isinstance(entry, Mapping):
            continue
        repo_key = _safe_repo_part(entry.get("repo_key"))
        if repo_key is None:
            continue
        items.append(
            {
                "repo_key": repo_key,
                "full_name": repo_key,
                "provider_key": "github",
                "source_class": INVENTORY_LEGACY_SEED,
                "product_area": _safe_text(entry.get("product_area")),
                "lifecycle_status": _safe_text(entry.get("lifecycle_status")),
                "repo_role": "legacy_seed",
                "repo_not_jira_project": True,
            }
        )
    return _dedupe_items(items)


def _inventory_payload(
    *,
    source_class: str,
    items: Sequence[Mapping[str, Any]],
    legacy_items: Sequence[Mapping[str, Any]],
    now: datetime,
    source_event_count: int,
    discovery_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    operational_items = _dedupe_items(items)
    legacy_seed_items = _dedupe_items(legacy_items)
    reconciliation = _reconcile(operational_items, legacy_seed_items)
    payload = {
        "report_kind": "repository_source_inventory",
        "generated_at": now.isoformat(),
        "read_only": True,
        "network_calls": False,
        "db_written": False,
        "source_priority": [
            INVENTORY_SOURCE_EVENTS,
            INVENTORY_DISCOVERY_SNAPSHOT,
            INVENTORY_LEGACY_SEED,
        ],
        "source_class": source_class,
        "operational_repo_source": source_class,
        "operational_repo_count": len(operational_items),
        "operational_repo_count_class": _zero_nonzero(len(operational_items)),
        "source_event_repo_count": source_event_count,
        "discovery_repo_count": int(discovery_snapshot.get("repo_count") or 0),
        "legacy_seed_repo_count": len(legacy_seed_items),
        "repo_as_component": True,
        "repo_mapping_policy": REPO_MAPPING_POLICY,
        "source_snapshot": dict(discovery_snapshot),
        "catalog_drift": reconciliation,
        "repositories": [dict(item) for item in operational_items],
        "legacy_seed_source_class": INVENTORY_LEGACY_SEED,
        "legacy_seed_status": "present" if legacy_seed_items else "missing",
        "fallback_used": source_class == INVENTORY_LEGACY_SEED,
    }
    return payload


def _reconcile(
    operational_items: Sequence[Mapping[str, Any]],
    legacy_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    operational = {
        _match_key(str(item.get("repo_key") or "")): str(item.get("repo_key") or "")
        for item in operational_items
        if item.get("repo_key")
    }
    legacy = {
        _match_key(str(item.get("repo_key") or "")): str(item.get("repo_key") or "")
        for item in legacy_items
        if item.get("repo_key")
    }
    operational_keys = set(operational)
    legacy_keys = set(legacy)
    matched = operational_keys & legacy_keys
    return {
        "status": "computed",
        "operational_count": len(operational_keys),
        "legacy_seed_count": len(legacy_keys),
        "matched_count": len(matched),
        "operational_repos": [operational[key] for key in sorted(operational_keys)],
        "legacy_seed_repos": [legacy[key] for key in sorted(legacy_keys)],
        "in_operational_not_in_legacy_seed": [
            operational[key] for key in sorted(operational_keys - legacy_keys)
        ],
        "in_legacy_seed_not_in_operational": [
            legacy[key] for key in sorted(legacy_keys - operational_keys)
        ],
        "matched": [operational[key] for key in sorted(matched)],
        "repo_mapping_policy": REPO_MAPPING_POLICY,
    }


def _latest_raw_repos_path(workspace: Path) -> Path | None:
    candidates = sorted((workspace / "discovery" / "github").glob("*/raw/repos.json"))
    return candidates[-1] if candidates else None


def _snapshot_meta(*, path: Path, workspace: Path, now: datetime) -> dict[str, Any]:
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return _empty_snapshot()
    relative = _safe_relative(path, workspace)
    snapshot_id = None
    try:
        snapshot_id = path.parents[1].name
    except IndexError:
        snapshot_id = None
    return {
        "available": True,
        "status": "available",
        "path": relative,
        "snapshot_id": snapshot_id,
        "snapshot_key": snapshot_id or relative,
        "modified_at": modified.isoformat(),
        "snapshot_age_seconds": max(0, int((now - modified).total_seconds())),
    }


def _empty_snapshot() -> dict[str, Any]:
    return {
        "available": False,
        "status": "missing",
        "path": None,
        "snapshot_id": None,
        "snapshot_key": None,
        "modified_at": None,
        "snapshot_age_seconds": None,
        "repo_count": 0,
    }


def _parse_repo_identity(value: Any) -> dict[str, str] | None:
    text = _safe_text(value, limit=1000)
    if not text:
        return None
    github_match = _GITHUB_URL_RE.search(text)
    if github_match:
        owner = _safe_repo_part(github_match.group(1))
        repo = _safe_repo_part(github_match.group(2).removesuffix(".git"))
        if owner and repo:
            return {"repo_key": repo, "full_name": f"{owner}/{repo}"}
    full_match = _FULL_NAME_RE.match(text)
    if full_match:
        owner = _safe_repo_part(full_match.group(1))
        repo = _safe_repo_part(full_match.group(2))
        if owner and repo:
            return {"repo_key": repo, "full_name": f"{owner}/{repo}"}
    repo_key = _safe_repo_part(text)
    if repo_key:
        return {"repo_key": repo_key, "full_name": repo_key}
    return None


def _dedupe_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        repo_key = _safe_repo_part(item.get("repo_key"))
        if repo_key is None:
            continue
        key = _match_key(repo_key)
        current = deduped.get(key, {})
        merged = {**current, **dict(item), "repo_key": repo_key}
        deduped[key] = merged
    return sorted(deduped.values(), key=lambda item: str(item["repo_key"]).casefold())


def _safe_repo_part(value: Any) -> str | None:
    text = _safe_text(value, limit=200)
    if not text or "/" in text:
        return None
    text = text.removesuffix(".git")
    if not _SAFE_REPO_PART_RE.match(text):
        return None
    return text


def _safe_full_name(value: Any) -> str | None:
    text = _safe_text(value, limit=300)
    if not text:
        return None
    parts = text.removesuffix(".git").split("/")
    if len(parts) != 2:
        return None
    owner = _safe_repo_part(parts[0])
    repo = _safe_repo_part(parts[1])
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"


def _safe_text(value: Any, *, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:limit]


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _match_key(value: str) -> str:
    return value.strip().casefold().replace("_", "-")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _max_iso(left: Any, right: Any) -> str | None:
    values = [value for value in (left, right) if isinstance(value, str) and value]
    return max(values) if values else None


def _zero_nonzero(value: int) -> str:
    return "nonzero_count" if value else "zero_count"


def _finalize(payload: dict[str, Any]) -> dict[str, Any]:
    diagnostics = inspect_operator_output(payload)
    if not diagnostics.safe:
        raise ValueError("repository_source_inventory_unsafe")
    return payload
