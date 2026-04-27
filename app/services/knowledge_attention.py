from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal
from app.db.score_models import KnowledgeScore
from app.db.source_models import SourceDocument
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask

DEFAULT_ATTENTION_LIMIT = 10
MAX_ATTENTION_LIMIT = 50

_CLOSED_TASK_STATUSES = {
    "done",
    "closed",
    "completed",
    "cancelled",
    "canceled",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_ATTENTION_LIMIT

    if parsed < 1:
        return DEFAULT_ATTENTION_LIMIT

    return min(parsed, MAX_ATTENTION_LIMIT)


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _non_empty_str(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    return text


def _first_evidence_value(evidence_refs: list[Any], key: str) -> str | None:
    for evidence_ref in evidence_refs:
        if not isinstance(evidence_ref, dict):
            continue

        value = evidence_ref.get(key)
        if isinstance(value, str) and value:
            return value

    return None


def _first_evidence_dict(evidence_refs: list[Any]) -> dict[str, Any]:
    for evidence_ref in evidence_refs:
        if isinstance(evidence_ref, dict):
            return evidence_ref

    return {}


def _normalize_attention_item(raw_item: dict[str, Any]) -> dict[str, Any] | None:
    evidence_refs = _as_list(raw_item.get("evidence_refs"))
    if not evidence_refs:
        return None

    source_document_id = _non_empty_str(
        raw_item.get("source_document_id")
    ) or _first_evidence_value(evidence_refs, "source_document_id")
    chunk_id = _non_empty_str(raw_item.get("chunk_id")) or _first_evidence_value(
        evidence_refs,
        "chunk_id",
    )

    if not source_document_id or not chunk_id:
        return None

    item_type = _non_empty_str(raw_item.get("item_type")) or _non_empty_str(
        raw_item.get("entity_type")
    )
    entity_id = _non_empty_str(raw_item.get("entity_id")) or _non_empty_str(
        raw_item.get("id")
    )
    title = _non_empty_str(raw_item.get("title"))

    if not item_type or not entity_id or not title:
        return None

    return {
        "item_type": item_type,
        "entity_id": entity_id,
        "title": title,
        "source_document_id": source_document_id,
        "chunk_id": chunk_id,
        "source_title": raw_item.get("source_title"),
        "attention_score": _as_float(raw_item.get("attention_score")),
        "importance_score": _as_float(raw_item.get("importance_score")),
        "urgency_score": _as_float(raw_item.get("urgency_score")),
        "risk_score": _as_float(raw_item.get("risk_score")),
        "confidence_score": _as_float(raw_item.get("confidence_score")),
        "reasons": _as_list(raw_item.get("reasons")),
        "evidence_refs": evidence_refs,
        "metadata": _as_dict(raw_item.get("metadata")),
        "created_at": raw_item.get("created_at"),
    }


def _attention_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["attention_score"],
        item["importance_score"],
        item["risk_score"],
        item["urgency_score"],
        item["confidence_score"],
        item["created_at"] or "",
        item["entity_id"],
    )


def _recent_decision_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["created_at"] or "",
        item["attention_score"],
        item["entity_id"],
    )


def _is_open_task(item: dict[str, Any]) -> bool:
    if item["item_type"] != "task":
        return False

    status = str(item["metadata"].get("status") or "open").lower()
    return status not in _CLOSED_TASK_STATUSES


def _source_from_item(item: dict[str, Any]) -> dict[str, Any]:
    first_evidence_ref = _first_evidence_dict(item["evidence_refs"])

    return {
        "source_document_id": item["source_document_id"],
        "chunk_id": item["chunk_id"],
        "source_title": item.get("source_title"),
        "source_url": first_evidence_ref.get("source_url"),
        "raw_object_ref": first_evidence_ref.get("raw_object_ref"),
        "quote": first_evidence_ref.get("quote"),
        "item_types": [item["item_type"]],
    }


def _collect_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for item in items:
        source = _source_from_item(item)
        key = (source["source_document_id"], source["chunk_id"])

        if key not in sources_by_key:
            sources_by_key[key] = source
            continue

        item_types = sources_by_key[key]["item_types"]
        if item["item_type"] not in item_types:
            item_types.append(item["item_type"])

    return list(sources_by_key.values())


def _summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return (
            "No evidence-backed scored items found. "
            "Run POST /v1/knowledge/score before using the attention dashboard."
        )

    top_item = items[0]
    score = top_item["attention_score"]

    return (
        f"{len(items)} evidence-backed scored items found. "
        f"Top attention item: {top_item['title']} "
        f"({top_item['item_type']}, attention_score={score:.2f})."
    )


def compute_attention_dashboard(
    items: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_ATTENTION_LIMIT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    safe_limit = _safe_limit(limit)

    normalized_items = [
        normalized_item
        for item in items
        if (normalized_item := _normalize_attention_item(item)) is not None
    ]

    sorted_items = sorted(
        normalized_items,
        key=_attention_sort_key,
        reverse=True,
    )

    top_tasks = [
        item
        for item in sorted_items
        if _is_open_task(item)
    ][:safe_limit]
    top_risks = [
        item
        for item in sorted_items
        if item["item_type"] == "risk"
    ][:safe_limit]
    recent_decisions = sorted(
        [
            item
            for item in sorted_items
            if item["item_type"] == "decision"
        ],
        key=_recent_decision_sort_key,
        reverse=True,
    )[:safe_limit]

    return {
        "answer_type": "attention_dashboard",
        "generated_at": generated_at or _utc_now_iso(),
        "summary": _summary(sorted_items),
        "top_items": sorted_items[:safe_limit],
        "top_tasks": top_tasks,
        "top_risks": top_risks,
        "recent_decisions": recent_decisions,
        "sources": _collect_sources(sorted_items),
        "metadata": {
            "limit": safe_limit,
            "scoring_required": not bool(sorted_items),
            "scored_item_count": len(sorted_items),
            "dropped_item_count": len(items) - len(sorted_items),
        },
    }



_ENTITY_MODELS: dict[str, type[Any]] = {
    "task": ExtractedTask,
    "risk": ExtractedRisk,
    "decision": ExtractedDecision,
}

_SUPPORTED_ENTITY_TYPES = tuple(_ENTITY_MODELS)


def _serialize_metadata_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _entity_id_for_lookup(entity_id: Any) -> int | None:
    try:
        return int(str(entity_id))
    except (TypeError, ValueError):
        return None


def _entity_metadata(entity_type: str, entity: Any) -> dict[str, Any]:
    field_names_by_type = {
        "task": ["status", "item_type", "owner", "due_date"],
        "risk": ["severity"],
        "decision": ["decision", "owner"],
    }

    metadata: dict[str, Any] = {}

    for field_name in field_names_by_type.get(entity_type, []):
        value = getattr(entity, field_name, None)
        if value is not None:
            metadata[field_name] = _serialize_metadata_value(value)

    return metadata


def _iso_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _as_entity_title(entity: Any) -> str | None:
    title = getattr(entity, "title", None)
    if title is None:
        return None

    title_text = str(title).strip()
    if not title_text:
        return None

    return title_text


def _enrich_evidence_refs(
    *,
    evidence_refs: list[Any],
    source_document_id: str | None,
    chunk_id: str | None,
    document: SourceDocument | None,
) -> list[Any]:
    if not evidence_refs:
        return []

    enriched_refs: list[Any] = []

    for evidence_ref in evidence_refs:
        if not isinstance(evidence_ref, dict):
            enriched_refs.append(evidence_ref)
            continue

        enriched_ref = dict(evidence_ref)

        if source_document_id and not enriched_ref.get("source_document_id"):
            enriched_ref["source_document_id"] = source_document_id
        if chunk_id and not enriched_ref.get("chunk_id"):
            enriched_ref["chunk_id"] = chunk_id
        if document and not enriched_ref.get("source_url"):
            enriched_ref["source_url"] = document.source_url
        if document and not enriched_ref.get("raw_object_ref"):
            enriched_ref["raw_object_ref"] = document.raw_object_ref

        enriched_refs.append(enriched_ref)

    return enriched_refs


async def _load_attention_entity(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
) -> Any | None:
    model = _ENTITY_MODELS.get(entity_type)
    lookup_id = _entity_id_for_lookup(entity_id)

    if model is None or lookup_id is None:
        return None

    result = await session.execute(select(model).where(model.id == lookup_id))
    return result.scalar_one_or_none()


async def _load_source_document(
    session: AsyncSession,
    source_document_id: str | None,
) -> SourceDocument | None:
    if not source_document_id:
        return None

    result = await session.execute(
        select(SourceDocument).where(
            SourceDocument.source_document_id == source_document_id
        )
    )
    return result.scalar_one_or_none()


async def _attention_item_from_score(
    session: AsyncSession,
    score: KnowledgeScore,
) -> dict[str, Any] | None:
    entity_type = score.entity_type

    if entity_type not in _ENTITY_MODELS:
        return None

    entity = await _load_attention_entity(
        session,
        entity_type=entity_type,
        entity_id=score.entity_id,
    )

    if entity is None:
        return None

    source_document_id = (
        getattr(entity, "source_document_id", None)
        or score.source_document_id
    )
    chunk_id = getattr(entity, "chunk_id", None) or score.chunk_id
    document = await _load_source_document(session, source_document_id)

    evidence_refs = _enrich_evidence_refs(
        evidence_refs=(
            getattr(entity, "evidence_refs", None)
            or score.evidence_refs
            or []
        ),
        source_document_id=source_document_id,
        chunk_id=chunk_id,
        document=document,
    )

    metadata = _entity_metadata(entity_type, entity)
    metadata["score_id"] = score.id

    return {
        "item_type": entity_type,
        "entity_id": score.entity_id,
        "title": _as_entity_title(entity),
        "source_document_id": source_document_id,
        "chunk_id": chunk_id,
        "source_title": document.title if document else None,
        "attention_score": score.attention_score,
        "importance_score": score.importance_score,
        "urgency_score": score.urgency_score,
        "risk_score": score.risk_score,
        "confidence_score": score.confidence_score,
        "reasons": score.reasons or [],
        "evidence_refs": evidence_refs,
        "metadata": metadata,
        "created_at": _iso_datetime(getattr(entity, "created_at", None)),
    }


async def collect_attention_items_from_session(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_ATTENTION_LIMIT,
    source_document_id: str | None = None,
) -> list[dict[str, Any]]:
    safe_limit = _safe_limit(limit)
    score_limit = min(MAX_ATTENTION_LIMIT, safe_limit * 5)

    statement = (
        select(KnowledgeScore)
        .where(KnowledgeScore.entity_type.in_(_SUPPORTED_ENTITY_TYPES))
        .order_by(
            desc(KnowledgeScore.attention_score),
            desc(KnowledgeScore.updated_at),
            desc(KnowledgeScore.id),
        )
        .limit(score_limit)
    )

    if source_document_id:
        statement = statement.where(
            KnowledgeScore.source_document_id == source_document_id
        )

    result = await session.execute(statement)
    scores = list(result.scalars().all())

    items: list[dict[str, Any]] = []

    for score in scores:
        item = await _attention_item_from_score(session, score)
        if item is not None:
            items.append(item)

    return items


async def collect_attention_items(
    *,
    limit: int = DEFAULT_ATTENTION_LIMIT,
    source_document_id: str | None = None,
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        return await collect_attention_items_from_session(
            session,
            limit=limit,
            source_document_id=source_document_id,
        )


async def get_attention_dashboard(
    *,
    limit: int = DEFAULT_ATTENTION_LIMIT,
    source_document_id: str | None = None,
) -> dict[str, Any]:
    items = await collect_attention_items(
        limit=limit,
        source_document_id=source_document_id,
    )

    return compute_attention_dashboard(items, limit=limit)
