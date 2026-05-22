from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.digest import (
    DEFAULT_DIGEST_ENTRY_LIMIT,
    MAX_DIGEST_ENTRY_LIMIT,
    build_persisted_attention_digest_read_model,
)
from app.services.digest_rendering import (
    SAFE_EVIDENCE_REF_KEYS,
    render_persisted_attention_digest_text,
)
from app.services.telegram_delivery import (
    DEFAULT_TELEGRAM_CHUNK_SIZE,
    split_telegram_plain_text,
)

DIGEST_DELIVERY_DRAFT_STATUS = "draft"
DIGEST_DELIVERY_DRAFT_TYPE = "persisted_attention"
DIGEST_DELIVERY_DRAFT_CHANNEL = "telegram"

SAFE_PERSISTED_ATTENTION_ITEM_KEYS = (
    "id",
    "triage_result_id",
    "activity_item_id",
    "source",
    "source_object_id",
    "attention_class",
    "priority",
    "show_in_digest",
    "confidence",
    "title",
    "safe_summary",
    "reason",
    "recommended_action",
    "owner",
    "deadline",
    "project",
    "activity_created_at",
    "triage_created_at",
    "evidence",
    "activity_available",
)


def _require_aware_datetime(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _validated_limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc

    if parsed < 1 or parsed > MAX_DIGEST_ENTRY_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_DIGEST_ENTRY_LIMIT}")
    return parsed


def _safe_evidence_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    refs: list[dict[str, Any]] = []
    for ref in value:
        if not isinstance(ref, Mapping):
            continue
        safe_ref = {
            key: ref[key]
            for key in SAFE_EVIDENCE_REF_KEYS
            if ref.get(key) is not None
        }
        if safe_ref:
            refs.append(safe_ref)
    return refs


def _safe_item(value: Any, *, debug_evidence: bool) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None

    item = {
        key: value[key]
        for key in SAFE_PERSISTED_ATTENTION_ITEM_KEYS
        if key in value
    }
    if debug_evidence:
        item["evidence_refs"] = _safe_evidence_refs(value.get("evidence_refs"))
        item["activity_evidence_refs"] = _safe_evidence_refs(
            value.get("activity_evidence_refs")
        )
    return item


def sanitize_persisted_attention_digest_for_delivery_draft(
    digest: Mapping[str, Any],
    *,
    debug_evidence: bool,
) -> dict[str, Any]:
    """Return the safe persisted digest shape allowed in delivery draft previews."""

    groups: dict[str, list[dict[str, Any]]] = {}
    raw_groups = digest.get("groups")
    if isinstance(raw_groups, Mapping):
        for group_key, raw_items in raw_groups.items():
            items: list[dict[str, Any]] = []
            if isinstance(raw_items, list):
                for raw_item in raw_items:
                    item = _safe_item(raw_item, debug_evidence=debug_evidence)
                    if item is not None:
                        items.append(item)
            groups[str(group_key)] = items

    hidden_summary = digest.get("hidden_low_priority_summary")
    safe_hidden_summary: dict[str, Any] = {"total": 0, "counts": {}}
    if isinstance(hidden_summary, Mapping):
        counts = hidden_summary.get("counts")
        safe_hidden_summary = {
            "total": hidden_summary.get("total", 0),
            "counts": dict(counts) if isinstance(counts, Mapping) else {},
        }

    metadata = (
        dict(digest.get("metadata", {}))
        if isinstance(digest.get("metadata"), Mapping)
        else {}
    )
    metadata["debug_evidence"] = bool(debug_evidence)

    return {
        "section_title": digest.get("section_title", "Persisted attention digest"),
        "available": digest.get("available", True),
        "window": (
            dict(digest.get("window", {}))
            if isinstance(digest.get("window"), Mapping)
            else {}
        ),
        "section_labels": (
            dict(digest.get("section_labels", {}))
            if isinstance(digest.get("section_labels"), Mapping)
            else {}
        ),
        "counts": (
            dict(digest.get("counts", {}))
            if isinstance(digest.get("counts"), Mapping)
            else {}
        ),
        "groups": groups,
        "hidden_low_priority_summary": safe_hidden_summary,
        "data_quality_notes": (
            list(digest.get("data_quality_notes", []))
            if isinstance(digest.get("data_quality_notes"), list)
            else []
        ),
        "metadata": metadata,
    }


def _source_of_truth_metadata(digest: Mapping[str, Any]) -> dict[str, Any]:
    metadata = digest.get("metadata") if isinstance(digest.get("metadata"), Mapping) else {}
    return {
        "source": "postgres",
        "raw_storage_authoritative": True,
        "postgres_authoritative": True,
        "draft_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
        "derived_from": [
            "attention_triage_results",
            "normalized_activity_items",
        ],
        "digest_source_model": metadata.get("source_model", "attention_triage_results"),
        "digest_enrichment_model": metadata.get(
            "enrichment_model",
            "normalized_activity_items",
        ),
        "rendered_text_source": "render_persisted_attention_digest_text",
    }


def _chunk_metadata(rendered_text: str, *, chunk_size: int) -> dict[str, Any]:
    chunks = split_telegram_plain_text(rendered_text, max_chars=chunk_size)
    return {
        "chunk_size": chunk_size,
        "chunk_lengths": [len(chunk) for chunk in chunks],
        "chunks_preview_included": False,
    }


def build_persisted_attention_digest_delivery_draft(
    *,
    digest: Mapping[str, Any],
    rendered_text: str,
    start_at: datetime,
    end_at: datetime,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
    debug_evidence: bool = False,
    channel: str = DIGEST_DELIVERY_DRAFT_CHANNEL,
    chunk_size: int = DEFAULT_TELEGRAM_CHUNK_SIZE,
) -> dict[str, Any]:
    """Build an inert human-review delivery draft without side effects."""

    _require_aware_datetime(start_at, field_name="start_at")
    _require_aware_datetime(end_at, field_name="end_at")
    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")
    safe_limit = _validated_limit(limit)
    if not isinstance(rendered_text, str) or not rendered_text.strip():
        raise ValueError("rendered_text must not be empty")

    safe_digest = sanitize_persisted_attention_digest_for_delivery_draft(
        digest,
        debug_evidence=debug_evidence,
    )
    chunks = _chunk_metadata(rendered_text, chunk_size=chunk_size)

    return {
        "status": DIGEST_DELIVERY_DRAFT_STATUS,
        "digest_type": DIGEST_DELIVERY_DRAFT_TYPE,
        "channel": channel,
        "delivery_enabled": False,
        "approval_required": True,
        "approved": False,
        "sent": False,
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "limit": safe_limit,
        "debug_evidence": bool(debug_evidence),
        "rendered_text": rendered_text,
        "text_sha256": sha256(rendered_text.encode("utf-8")).hexdigest(),
        "char_count": len(rendered_text),
        "chunk_count": len(chunks["chunk_lengths"]),
        "chunk_metadata": chunks,
        "digest": safe_digest,
        "source_of_truth": _source_of_truth_metadata(safe_digest),
        "safety": {
            "provider_free": True,
            "read_only": True,
            "delivery_invoked": False,
            "approval_executed": False,
            "persisted": False,
            "scheduler_invoked": False,
            "triage_run": False,
            "connectors_invoked": False,
            "live_api_calls": False,
        },
    }


async def build_persisted_attention_digest_delivery_draft_from_db(
    session: AsyncSession,
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
    debug_evidence: bool = False,
    channel: str = DIGEST_DELIVERY_DRAFT_CHANNEL,
) -> dict[str, Any]:
    """Read stored persisted attention digest data and return an inert draft.

    The caller owns the session lifecycle. This function reads through the
    existing persisted attention digest service only; it does not commit, flush,
    insert, update, delete, approve, send, schedule, or call providers.
    """

    safe_limit = _validated_limit(limit)
    digest = await build_persisted_attention_digest_read_model(
        session,
        start_at=start_at,
        end_at=end_at,
        limit_per_section=safe_limit,
    )
    safe_digest = sanitize_persisted_attention_digest_for_delivery_draft(
        digest,
        debug_evidence=debug_evidence,
    )
    rendered_text = render_persisted_attention_digest_text(
        safe_digest,
        debug_evidence=debug_evidence,
    )
    return build_persisted_attention_digest_delivery_draft(
        digest=safe_digest,
        rendered_text=rendered_text,
        start_at=start_at,
        end_at=end_at,
        limit=safe_limit,
        debug_evidence=debug_evidence,
        channel=channel,
    )
