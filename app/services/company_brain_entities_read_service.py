"""Deterministic read-only NormalizedEntity projection (§6.9 / MVP §1.5).

The master playbook lists "normalized entities" as a required MVP surface, and
DEC-028 deferred the physical ``NormalizedEntity`` table until "the canonical
``/api/v1/.../brain/entities`` API is actually built". This module builds that
API's read model **without** committing to a premature table or to the open
``Person`` design question (ASK-1): it projects the already-canonical Company
Brain rows (repositories, issues/tasks, pull requests, Gmail messages, Drive
files, and internal documents) into a single normalized-entity list with stable
keys and evidence refs.

It is deterministic and local-only: it performs no provider calls, no sync, no
external writes, no secret reads, and no LLM work. It reuses
``build_workspace_company_brain`` so the entity view always mirrors the same
canonical projection, scope, and evidence the Company Brain already exposes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.company_brain_github_read_service import (
    build_workspace_company_brain,
)

COMPANY_BRAIN_ENTITIES_MODE = "github_first_canonical"
COMPANY_BRAIN_ENTITIES_SOURCE = "canonical_company_brain_entities"

ENTITY_TYPE_REPOSITORY = "repository"
ENTITY_TYPE_ISSUE = "issue"
ENTITY_TYPE_PULL_REQUEST = "pull_request"
ENTITY_TYPE_EMAIL_MESSAGE = "email_message"
ENTITY_TYPE_DRIVE_FILE = "drive_file"
ENTITY_TYPE_DOCUMENT = "document"

SOURCE_PROVIDER_GITHUB = "github"
SOURCE_PROVIDER_GMAIL = "gmail"
SOURCE_PROVIDER_DRIVE = "drive"
SOURCE_PROVIDER_INTERNAL = "internal"


async def build_workspace_normalized_entities(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    limit: int = 10,
) -> dict[str, Any]:
    """Project canonical Company Brain rows into a normalized-entity read model.

    The returned payload contains a flat ``entities`` list (repositories,
    issues, pull requests, email messages, drive files, internal documents),
    a ``summary`` with counts by entity type and source provider, and a
    de-duplicated aggregate ``evidence`` list. The ``Person`` entity type from
    §6.9 is intentionally not produced (post-MVP, ASK-1).
    """

    brain = await build_workspace_company_brain(
        session=session,
        workspace_id=workspace_id,
        limit=limit,
    )

    entities: list[dict[str, Any]] = []
    entities.extend(_repository_entities(brain))
    entities.extend(_work_entities(brain))
    entities.extend(_communication_entities(brain))
    entities.extend(_document_entities(brain))

    evidence = _unique_source_refs(entity["source_refs"] for entity in entities)
    summary = _summary(entities)

    warnings: list[str] = []
    if not entities:
        warnings.append(
            "No canonical entities are available for this workspace yet."
        )

    return {
        "workspace_id": workspace_id,
        "mode": COMPANY_BRAIN_ENTITIES_MODE,
        "source": COMPANY_BRAIN_ENTITIES_SOURCE,
        "summary": summary,
        "entities": entities,
        "evidence": evidence,
        "capabilities": {
            "live_github_oauth": False,
            "live_provider_sync": False,
            "local_sync": True,
            "llm_briefing": False,
        },
        "is_live": False,
        "llm_used": False,
        "warnings": warnings,
    }


def _repository_entities(brain: Mapping[str, Any]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for row in _rows(brain.get("repositories")):
        provider = _text(row.get("provider")) or SOURCE_PROVIDER_GITHUB
        external_id = _text(row.get("external_id")) or _text(row.get("id"))
        entities.append(
            _entity(
                entity_type=ENTITY_TYPE_REPOSITORY,
                source_provider=provider,
                external_id=external_id,
                title=_text(row.get("full_name")) or _text(row.get("name")),
                status="archived" if row.get("archived") else "active",
                source_url=_text(row.get("source_url")),
                updated_at=row.get("last_activity_at"),
                reference_id=row.get("id"),
                source_refs=_rows(row.get("source_refs")),
            )
        )
    return entities


def _work_entities(brain: Mapping[str, Any]) -> list[dict[str, Any]]:
    work = brain.get("work") if isinstance(brain.get("work"), Mapping) else {}
    entities: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for section in ("issues", "pull_requests", "recent"):
        for row in _rows(work.get(section)):
            row_type = _text(row.get("type"))
            entity_type = (
                ENTITY_TYPE_PULL_REQUEST
                if row_type == "pull_request"
                else ENTITY_TYPE_ISSUE
            )
            provider = _text(row.get("source_provider")) or SOURCE_PROVIDER_GITHUB
            external_id = _text(row.get("external_id")) or _text(row.get("id"))
            entity = _entity(
                entity_type=entity_type,
                source_provider=provider,
                external_id=external_id,
                title=_text(row.get("title")),
                status=_text(row.get("state")),
                source_url=_text(row.get("source_url")),
                updated_at=row.get("updated_at"),
                reference_id=row.get("id"),
                source_refs=_rows(row.get("source_refs")),
            )
            # ``recent`` overlaps ``issues``/``pull_requests``; de-dupe by key so
            # a single work item is only projected as one entity.
            if entity["key"] in seen_keys:
                continue
            seen_keys.add(entity["key"])
            entities.append(entity)
    return entities


def _communication_entities(brain: Mapping[str, Any]) -> list[dict[str, Any]]:
    communications = (
        brain.get("communications")
        if isinstance(brain.get("communications"), Mapping)
        else {}
    )
    entities: list[dict[str, Any]] = []
    for row in _rows(communications.get("messages")):
        external_id = _text(row.get("message_id")) or _text(
            row.get("source_record_id")
        )
        entities.append(
            _entity(
                entity_type=ENTITY_TYPE_EMAIL_MESSAGE,
                source_provider=SOURCE_PROVIDER_GMAIL,
                external_id=external_id,
                title=_text(row.get("subject")),
                status="unread" if row.get("unread") else "read",
                source_url=_text(row.get("source_url")),
                updated_at=row.get("received_at"),
                reference_id=row.get("source_record_id"),
                source_refs=_rows(row.get("source_refs")),
            )
        )
    return entities


def _document_entities(brain: Mapping[str, Any]) -> list[dict[str, Any]]:
    documents = (
        brain.get("documents") if isinstance(brain.get("documents"), Mapping) else {}
    )
    entities: list[dict[str, Any]] = []
    for row in _rows(documents.get("files")):
        external_id = _text(row.get("file_id")) or _text(row.get("source_record_id"))
        entities.append(
            _entity(
                entity_type=ENTITY_TYPE_DRIVE_FILE,
                source_provider=SOURCE_PROVIDER_DRIVE,
                external_id=external_id,
                title=_text(row.get("name")),
                status="shared" if row.get("shared") else None,
                source_url=_text(row.get("source_url")),
                updated_at=row.get("modified_at"),
                reference_id=row.get("source_record_id"),
                source_refs=_rows(row.get("source_refs")),
            )
        )
    for row in _rows(documents.get("notes")):
        external_id = _text(row.get("document_id"))
        entities.append(
            _entity(
                entity_type=ENTITY_TYPE_DOCUMENT,
                source_provider=SOURCE_PROVIDER_INTERNAL,
                external_id=external_id,
                title=_text(row.get("title")),
                status=_text(row.get("status")),
                source_url=None,
                updated_at=row.get("updated_at"),
                reference_id=row.get("document_id"),
                source_refs=_rows(row.get("source_refs")),
            )
        )
    return entities


def _entity(
    *,
    entity_type: str,
    source_provider: str,
    external_id: str | None,
    title: str | None,
    status: str | None,
    source_url: str | None,
    updated_at: Any,
    reference_id: Any,
    source_refs: Sequence[Any],
) -> dict[str, Any]:
    resolved_external_id = external_id or (
        str(reference_id) if reference_id else "unknown"
    )
    return {
        "entity_type": entity_type,
        "key": f"{source_provider}:{entity_type}:{resolved_external_id}",
        "external_id": resolved_external_id,
        "title": title or f"{entity_type} {resolved_external_id}",
        "source_provider": source_provider,
        "status": status,
        "source_url": source_url,
        "updated_at": updated_at,
        "reference_id": reference_id,
        "source_refs": [ref for ref in source_refs if isinstance(ref, Mapping)],
    }


def _summary(entities: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_entity_type: dict[str, int] = {}
    by_source_provider: dict[str, int] = {}
    for entity in entities:
        entity_type = str(entity.get("entity_type"))
        provider = str(entity.get("source_provider"))
        by_entity_type[entity_type] = by_entity_type.get(entity_type, 0) + 1
        by_source_provider[provider] = by_source_provider.get(provider, 0) + 1
    return {
        "total": len(entities),
        "by_entity_type": [
            {"entity_type": entity_type, "count": count}
            for entity_type, count in sorted(by_entity_type.items())
        ],
        "by_source_provider": [
            {"source_provider": provider, "count": count}
            for provider, count in sorted(by_source_provider.items())
        ],
    }


def _unique_source_refs(source_ref_groups: Any) -> list[dict[str, Any]]:
    seen: set[str] = set()
    refs: list[dict[str, Any]] = []
    for group in source_ref_groups:
        for ref in group:
            if not isinstance(ref, Mapping):
                continue
            key = str(ref.get("id") or ref.get("label"))
            if key in seen:
                continue
            seen.add(key)
            refs.append(dict(ref))
    return refs


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, UUID):
        return str(value)
    return None
