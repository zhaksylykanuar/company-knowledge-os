from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog
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
DIGEST_DELIVERY_DRAFT_READINESS_STATUS = "delivery_readiness"
DIGEST_DELIVERY_INTENTION_STATUS = "delivery_intention"
DIGEST_DELIVERY_TELEGRAM_PLAN_STATUS = "telegram_delivery_plan"
DIGEST_DELIVERY_DRAFT_TYPE = "persisted_attention"
DIGEST_DELIVERY_DRAFT_CHANNEL = "telegram"
DIGEST_DELIVERY_DRAFT_ID_PREFIX = "ddraft_"
DIGEST_DELIVERY_INTENTION_ID_PREFIX = "dint_"
DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE = "digest.delivery_draft.created"
DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE = "digest.delivery_draft.approved"
DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE = "digest.delivery_draft.rejected"
DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE = "digest.delivery_intention.created"
DIGEST_DELIVERY_DRAFT_DECISION_EVENT_TYPES = (
    DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
    DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE,
)
DIGEST_DELIVERY_DRAFT_AUDIT_EVENT_TYPES = (
    DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
    *DIGEST_DELIVERY_DRAFT_DECISION_EVENT_TYPES,
)
DIGEST_DELIVERY_DRAFT_APPROVED_DECISION = "approved"
DIGEST_DELIVERY_DRAFT_REJECTED_DECISION = "rejected"
DIGEST_DELIVERY_DRAFT_DECISIONS = (
    DIGEST_DELIVERY_DRAFT_APPROVED_DECISION,
    DIGEST_DELIVERY_DRAFT_REJECTED_DECISION,
)
DIGEST_DELIVERY_DRAFT_DECISION_REVIEWER_MAX_LENGTH = 120
DIGEST_DELIVERY_DRAFT_DECISION_NOTE_MAX_LENGTH = 500

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


class DeliveryDraftNotFoundError(ValueError):
    """Raised when a requested persisted delivery draft does not exist."""


class DeliveryDraftDecisionConflictError(ValueError):
    """Raised when a terminal delivery draft decision already exists."""


class DeliveryIntentionNotReadyError(ValueError):
    """Raised when a delivery intention is requested for a non-ready draft."""


class DeliveryIntentionConflictError(ValueError):
    """Raised when a stored delivery intention does not match expected data."""


class DeliveryTelegramPlanConflictError(ValueError):
    """Raised when a Telegram delivery plan cannot be safely built."""


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


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
    )


def build_delivery_draft_id(
    *,
    digest_type: str,
    channel: str,
    start_at: str,
    end_at: str,
    limit: int,
    debug_evidence: bool,
    text_sha256: str,
) -> str:
    stable_input = {
        "channel": channel,
        "debug_evidence": bool(debug_evidence),
        "digest_type": digest_type,
        "end_at": end_at,
        "limit": int(limit),
        "start_at": start_at,
        "text_sha256": text_sha256,
    }
    digest = sha256(_canonical_json(stable_input).encode("utf-8")).hexdigest()
    return f"{DIGEST_DELIVERY_DRAFT_ID_PREFIX}{digest[:32]}"


def build_delivery_intention_id(
    *,
    delivery_draft_id: str,
    digest_type: str,
    channel: str,
    text_sha256: str,
    chunk_count: int,
    chunk_metadata: Mapping[str, Any],
) -> str:
    stable_input = {
        "channel": channel,
        "chunk_count": int(chunk_count),
        "chunk_metadata": dict(chunk_metadata),
        "delivery_draft_id": delivery_draft_id,
        "digest_type": digest_type,
        "readiness_status": DIGEST_DELIVERY_DRAFT_READINESS_STATUS,
        "text_sha256": text_sha256,
    }
    digest = sha256(_canonical_json(stable_input).encode("utf-8")).hexdigest()
    return f"{DIGEST_DELIVERY_INTENTION_ID_PREFIX}{digest[:32]}"


def _clean_delivery_draft_id(delivery_draft_id: str) -> str:
    if not isinstance(delivery_draft_id, str):
        raise ValueError("delivery_draft_id must be a non-empty string")

    cleaned = delivery_draft_id.strip()
    if not cleaned:
        raise ValueError("delivery_draft_id must be a non-empty string")
    return cleaned


def _clean_delivery_intention_id(delivery_intention_id: str) -> str:
    if not isinstance(delivery_intention_id, str):
        raise ValueError("delivery_intention_id must be a non-empty string")

    cleaned = delivery_intention_id.strip()
    if not cleaned:
        raise ValueError("delivery_intention_id must be a non-empty string")
    return cleaned


def _clean_required_text(value: str | None, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    if len(cleaned) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return cleaned


def _clean_optional_text(
    value: str | None,
    *,
    field_name: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return cleaned


def _clean_decision(decision: str) -> str:
    if not isinstance(decision, str):
        raise ValueError("decision must be approved or rejected")

    cleaned = decision.strip().lower()
    if cleaned not in DIGEST_DELIVERY_DRAFT_DECISIONS:
        raise ValueError("decision must be approved or rejected")
    return cleaned


def _decision_event_type(decision: str) -> str:
    cleaned = _clean_decision(decision)
    if cleaned == DIGEST_DELIVERY_DRAFT_APPROVED_DECISION:
        return DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE
    return DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE


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
    text_hash = sha256(rendered_text.encode("utf-8")).hexdigest()
    start_at_iso = start_at.isoformat()
    end_at_iso = end_at.isoformat()
    delivery_draft_id = build_delivery_draft_id(
        digest_type=DIGEST_DELIVERY_DRAFT_TYPE,
        channel=channel,
        start_at=start_at_iso,
        end_at=end_at_iso,
        limit=safe_limit,
        debug_evidence=bool(debug_evidence),
        text_sha256=text_hash,
    )

    return {
        "delivery_draft_id": delivery_draft_id,
        "status": DIGEST_DELIVERY_DRAFT_STATUS,
        "digest_type": DIGEST_DELIVERY_DRAFT_TYPE,
        "channel": channel,
        "persisted": False,
        "delivery_enabled": False,
        "approval_required": True,
        "approved": False,
        "sent": False,
        "start_at": start_at_iso,
        "end_at": end_at_iso,
        "limit": safe_limit,
        "debug_evidence": bool(debug_evidence),
        "rendered_text": rendered_text,
        "text_sha256": text_hash,
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


def _persisted_payload(draft: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(draft)
    payload["persisted"] = True
    payload["persistence"] = {
        "storage": "audit_logs",
        "event_type": DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
        "after_ref": payload["delivery_draft_id"],
        "approval_state": "not_requested",
    }

    safety = (
        dict(payload.get("safety", {}))
        if isinstance(payload.get("safety"), Mapping)
        else {}
    )
    safety["read_only"] = False
    safety["db_write_scope"] = "audit_logs_only"
    safety["audit_log_backed"] = True
    payload["safety"] = safety
    return payload


def _audit_log_response(record: AuditLog) -> dict[str, Any] | None:
    if not isinstance(record.payload, Mapping):
        return None

    response = dict(record.payload)
    if response.get("delivery_draft_id") != record.after_ref:
        return None

    response["persisted"] = True
    response["audit_log"] = {
        "event_type": record.event_type,
        "after_ref": record.after_ref,
        "created_at": (
            record.created_at.isoformat() if record.created_at is not None else None
        ),
    }
    return response


async def get_persisted_digest_delivery_draft(
    session: AsyncSession,
    *,
    delivery_draft_id: str,
) -> dict[str, Any] | None:
    cleaned_delivery_draft_id = _clean_delivery_draft_id(delivery_draft_id)
    record = await session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE)
        .where(AuditLog.after_ref == cleaned_delivery_draft_id)
        .order_by(AuditLog.id)
    )
    if record is None:
        return None
    return _audit_log_response(record)


async def persist_digest_delivery_draft(
    session: AsyncSession,
    *,
    draft: Mapping[str, Any],
    actor: str = "system",
) -> dict[str, Any]:
    delivery_draft_id = _clean_delivery_draft_id(str(draft.get("delivery_draft_id", "")))
    existing = await get_persisted_digest_delivery_draft(
        session,
        delivery_draft_id=delivery_draft_id,
    )
    if existing is not None:
        return existing

    payload = _persisted_payload(draft)
    record = AuditLog(
        event_type=DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
        actor=actor,
        correlation_id=delivery_draft_id,
        trace_id=delivery_draft_id,
        after_ref=delivery_draft_id,
        payload=payload,
    )
    session.add(record)
    await session.flush()

    response = _audit_log_response(record)
    if response is None:
        raise ValueError("persisted delivery draft audit payload is invalid")
    return response


async def create_persisted_attention_digest_delivery_draft(
    session: AsyncSession,
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
    debug_evidence: bool = False,
    channel: str = DIGEST_DELIVERY_DRAFT_CHANNEL,
    actor: str = "system",
) -> dict[str, Any]:
    draft = await build_persisted_attention_digest_delivery_draft_from_db(
        session,
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        debug_evidence=debug_evidence,
        channel=channel,
    )
    return await persist_digest_delivery_draft(
        session,
        draft=draft,
        actor=actor,
    )


def _draft_approval_status_metadata(draft: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "digest_type": draft.get("digest_type"),
        "channel": draft.get("channel"),
        "status": draft.get("status"),
        "start_at": draft.get("start_at"),
        "end_at": draft.get("end_at"),
        "limit": draft.get("limit"),
        "debug_evidence": bool(draft.get("debug_evidence")),
        "text_sha256": draft.get("text_sha256"),
        "char_count": draft.get("char_count"),
        "chunk_count": draft.get("chunk_count"),
        "source_of_truth": (
            dict(draft.get("source_of_truth"))
            if isinstance(draft.get("source_of_truth"), Mapping)
            else {}
        ),
    }


def _decision_safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "delivery_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "connectors_invoked": False,
        "live_api_calls": False,
        "db_write_scope": "audit_logs_only",
        "draft_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _delivery_readiness_safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "delivery_execution_enabled": False,
        "delivery_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "connectors_invoked": False,
        "live_api_calls": False,
        "db_write_scope": "none",
        "draft_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _delivery_intention_safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": False,
        "db_write_scope": "audit_logs_only",
        "audit_log_backed": True,
        "delivery_execution_enabled": False,
        "delivery_enabled": False,
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "connectors_invoked": False,
        "live_api_calls": False,
        "draft_is_source_of_truth": False,
        "intention_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _telegram_delivery_plan_safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "db_write_scope": "none",
        "delivery_execution_enabled": False,
        "delivery_enabled": False,
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "delivery_result_audit_event_created": False,
        "outbox_record_created": False,
        "connectors_invoked": False,
        "live_api_calls": False,
        "draft_is_source_of_truth": False,
        "intention_is_source_of_truth": False,
        "telegram_plan_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _safe_chunk_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}

    metadata: dict[str, Any] = {}
    chunk_size = value.get("chunk_size")
    if isinstance(chunk_size, int):
        metadata["chunk_size"] = chunk_size

    chunk_lengths = value.get("chunk_lengths")
    if isinstance(chunk_lengths, list):
        metadata["chunk_lengths"] = [
            length for length in chunk_lengths if isinstance(length, int)
        ]

    chunks_preview_included = value.get("chunks_preview_included")
    if isinstance(chunks_preview_included, bool):
        metadata["chunks_preview_included"] = chunks_preview_included

    return metadata


def _readiness_summary(readiness: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": readiness.get("status"),
        "current_decision": readiness.get("current_decision"),
        "approved": bool(readiness.get("approved")),
        "rejected": bool(readiness.get("rejected")),
        "eligible_for_delivery": bool(readiness.get("eligible_for_delivery")),
        "ineligible_reasons": (
            list(readiness.get("ineligible_reasons", []))
            if isinstance(readiness.get("ineligible_reasons"), list)
            else []
        ),
    }


def _decision_payload(
    *,
    draft: Mapping[str, Any],
    decision: str,
    reviewer: str,
    note: str | None,
) -> dict[str, Any]:
    delivery_draft_id = _clean_delivery_draft_id(str(draft.get("delivery_draft_id", "")))
    payload = {
        "delivery_draft_id": delivery_draft_id,
        "decision": _clean_decision(decision),
        "reviewer": reviewer,
        "draft_text_sha256": draft.get("text_sha256"),
        "draft": _draft_approval_status_metadata(draft),
        "safety": _decision_safety_metadata(),
    }
    if note is not None:
        payload["note"] = note
    return payload


def _decision_history_entry(record: AuditLog) -> dict[str, Any] | None:
    if not isinstance(record.payload, Mapping):
        return None
    if record.payload.get("delivery_draft_id") != record.after_ref:
        return None

    decision = record.payload.get("decision")
    if decision not in DIGEST_DELIVERY_DRAFT_DECISIONS:
        return None

    entry = {
        "event_type": record.event_type,
        "decision": decision,
        "reviewer": record.payload.get("reviewer"),
        "draft_text_sha256": record.payload.get("draft_text_sha256"),
        "created_at": (
            record.created_at.isoformat() if record.created_at is not None else None
        ),
        "audit_log": {
            "event_type": record.event_type,
            "after_ref": record.after_ref,
        },
        "safety": _decision_safety_metadata(),
    }
    note = record.payload.get("note")
    if isinstance(note, str) and note:
        entry["note"] = note
    return entry


async def get_digest_delivery_draft_decision_records(
    session: AsyncSession,
    *,
    delivery_draft_id: str,
) -> list[AuditLog]:
    cleaned_delivery_draft_id = _clean_delivery_draft_id(delivery_draft_id)
    result = await session.scalars(
        select(AuditLog)
        .where(AuditLog.event_type.in_(DIGEST_DELIVERY_DRAFT_DECISION_EVENT_TYPES))
        .where(AuditLog.after_ref == cleaned_delivery_draft_id)
        .order_by(AuditLog.id)
    )
    return list(result.all())


async def get_digest_delivery_draft_approval_status(
    session: AsyncSession,
    *,
    delivery_draft_id: str,
) -> dict[str, Any] | None:
    cleaned_delivery_draft_id = _clean_delivery_draft_id(delivery_draft_id)
    draft = await get_persisted_digest_delivery_draft(
        session,
        delivery_draft_id=cleaned_delivery_draft_id,
    )
    if draft is None:
        return None

    decision_records = await get_digest_delivery_draft_decision_records(
        session,
        delivery_draft_id=cleaned_delivery_draft_id,
    )
    decision_history = [
        entry
        for record in decision_records
        if (entry := _decision_history_entry(record)) is not None
    ]
    current_decision = (
        decision_history[-1]["decision"] if decision_history else None
    )

    return {
        "delivery_draft_id": cleaned_delivery_draft_id,
        "draft_exists": True,
        "current_decision": current_decision,
        "approved": current_decision == DIGEST_DELIVERY_DRAFT_APPROVED_DECISION,
        "rejected": current_decision == DIGEST_DELIVERY_DRAFT_REJECTED_DECISION,
        "delivery_enabled": False,
        "sent": False,
        "delivery_invoked": False,
        "approval_execution_invoked": False,
        "decision_history": decision_history,
        "draft": _draft_approval_status_metadata(draft),
        "safety": _decision_safety_metadata(),
    }


async def get_digest_delivery_draft_delivery_readiness(
    session: AsyncSession,
    *,
    delivery_draft_id: str,
) -> dict[str, Any] | None:
    """Return a read-only delivery readiness preview for a persisted draft.

    This reads the stored delivery draft and decision audit events only. It does
    not recompute digest contents, mutate approval state, create outbox records,
    send, schedule, or write audit rows.
    """

    cleaned_delivery_draft_id = _clean_delivery_draft_id(delivery_draft_id)
    draft = await get_persisted_digest_delivery_draft(
        session,
        delivery_draft_id=cleaned_delivery_draft_id,
    )
    if draft is None:
        return None

    approval_status = await get_digest_delivery_draft_approval_status(
        session,
        delivery_draft_id=cleaned_delivery_draft_id,
    )
    if approval_status is None:
        return None

    current_decision = approval_status["current_decision"]
    approved = current_decision == DIGEST_DELIVERY_DRAFT_APPROVED_DECISION
    rejected = current_decision == DIGEST_DELIVERY_DRAFT_REJECTED_DECISION
    ineligible_reasons: list[str] = []
    if rejected:
        ineligible_reasons.append("rejected")
    elif not approved:
        ineligible_reasons.append("not_approved")

    return {
        "delivery_draft_id": cleaned_delivery_draft_id,
        "draft_exists": True,
        "status": DIGEST_DELIVERY_DRAFT_READINESS_STATUS,
        "digest_type": draft.get("digest_type"),
        "channel": draft.get("channel"),
        "current_decision": current_decision,
        "approved": approved,
        "rejected": rejected,
        "eligible_for_delivery": approved,
        "ineligible_reasons": ineligible_reasons,
        "delivery_execution_enabled": False,
        "delivery_enabled": False,
        "delivery_invoked": False,
        "approval_execution_invoked": False,
        "sent": False,
        "text_sha256": draft.get("text_sha256"),
        "char_count": draft.get("char_count"),
        "chunk_count": draft.get("chunk_count"),
        "chunk_metadata": _safe_chunk_metadata(draft.get("chunk_metadata")),
        "start_at": draft.get("start_at"),
        "end_at": draft.get("end_at"),
        "limit": draft.get("limit"),
        "debug_evidence": bool(draft.get("debug_evidence")),
        "decision_history": approval_status["decision_history"],
        "source_of_truth": (
            dict(draft.get("source_of_truth"))
            if isinstance(draft.get("source_of_truth"), Mapping)
            else {}
        ),
        "safety": _delivery_readiness_safety_metadata(),
    }


def _delivery_intention_payload(readiness: Mapping[str, Any]) -> dict[str, Any]:
    delivery_draft_id = _clean_delivery_draft_id(
        str(readiness.get("delivery_draft_id", ""))
    )
    digest_type = str(readiness.get("digest_type", ""))
    channel = str(readiness.get("channel", ""))
    text_hash = str(readiness.get("text_sha256", ""))
    chunk_count = int(readiness.get("chunk_count", 0))
    chunk_metadata = _safe_chunk_metadata(readiness.get("chunk_metadata"))
    delivery_intention_id = build_delivery_intention_id(
        delivery_draft_id=delivery_draft_id,
        digest_type=digest_type,
        channel=channel,
        text_sha256=text_hash,
        chunk_count=chunk_count,
        chunk_metadata=chunk_metadata,
    )

    return {
        "persisted": True,
        "status": DIGEST_DELIVERY_INTENTION_STATUS,
        "delivery_intention_id": delivery_intention_id,
        "delivery_draft_id": delivery_draft_id,
        "digest_type": digest_type,
        "channel": channel,
        "current_decision": readiness.get("current_decision"),
        "eligible_for_delivery": True,
        "delivery_execution_enabled": False,
        "delivery_enabled": False,
        "delivery_invoked": False,
        "approval_execution_invoked": False,
        "sent": False,
        "scheduler_invoked": False,
        "text_sha256": text_hash,
        "char_count": readiness.get("char_count"),
        "chunk_count": chunk_count,
        "chunk_metadata": chunk_metadata,
        "start_at": readiness.get("start_at"),
        "end_at": readiness.get("end_at"),
        "limit": readiness.get("limit"),
        "debug_evidence": bool(readiness.get("debug_evidence")),
        "readiness": _readiness_summary(readiness),
        "source_of_truth": (
            dict(readiness.get("source_of_truth"))
            if isinstance(readiness.get("source_of_truth"), Mapping)
            else {}
        ),
        "safety": _delivery_intention_safety_metadata(),
    }


def _delivery_intention_audit_log_response(record: AuditLog) -> dict[str, Any] | None:
    if not isinstance(record.payload, Mapping):
        return None

    response = dict(record.payload)
    if response.get("delivery_intention_id") != record.after_ref:
        return None
    if response.get("delivery_draft_id") != record.before_ref:
        return None

    response["persisted"] = True
    response["audit_log"] = {
        "event_type": record.event_type,
        "before_ref": record.before_ref,
        "after_ref": record.after_ref,
        "created_at": (
            record.created_at.isoformat() if record.created_at is not None else None
        ),
    }
    return response


async def get_digest_delivery_intention(
    session: AsyncSession,
    *,
    delivery_intention_id: str,
) -> dict[str, Any] | None:
    cleaned_delivery_intention_id = _clean_delivery_intention_id(
        delivery_intention_id
    )
    record = await session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE)
        .where(AuditLog.after_ref == cleaned_delivery_intention_id)
        .order_by(AuditLog.id)
    )
    if record is None:
        return None
    return _delivery_intention_audit_log_response(record)


async def create_digest_delivery_intention(
    session: AsyncSession,
    *,
    delivery_draft_id: str,
    actor: str = "system",
) -> dict[str, Any]:
    cleaned_delivery_draft_id = _clean_delivery_draft_id(delivery_draft_id)
    readiness = await get_digest_delivery_draft_delivery_readiness(
        session,
        delivery_draft_id=cleaned_delivery_draft_id,
    )
    if readiness is None:
        raise DeliveryDraftNotFoundError("delivery draft was not found")
    if readiness.get("eligible_for_delivery") is not True:
        reasons = readiness.get("ineligible_reasons")
        reason_text = ", ".join(reasons) if isinstance(reasons, list) else "not_ready"
        raise DeliveryIntentionNotReadyError(
            f"delivery draft is not ready for delivery: {reason_text}"
        )

    payload = _delivery_intention_payload(readiness)
    delivery_intention_id = _clean_delivery_intention_id(
        str(payload.get("delivery_intention_id", ""))
    )
    existing = await get_digest_delivery_intention(
        session,
        delivery_intention_id=delivery_intention_id,
    )
    if existing is not None:
        stored_payload = {
            key: value for key, value in existing.items() if key != "audit_log"
        }
        if stored_payload != payload:
            raise DeliveryIntentionConflictError(
                "existing delivery intention payload does not match expected payload"
            )
        return existing

    record = AuditLog(
        event_type=DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE,
        actor=actor,
        correlation_id=cleaned_delivery_draft_id,
        trace_id=delivery_intention_id,
        before_ref=cleaned_delivery_draft_id,
        after_ref=delivery_intention_id,
        approval_id=f"{cleaned_delivery_draft_id}:delivery_intention",
        payload=payload,
    )
    session.add(record)
    await session.flush()

    response = _delivery_intention_audit_log_response(record)
    if response is None:
        raise ValueError("persisted delivery intention audit payload is invalid")
    return response


def _require_int(value: Any, *, field_name: str) -> int:
    if not isinstance(value, int):
        raise DeliveryTelegramPlanConflictError(f"{field_name} must be an integer")
    return value


def _telegram_plan_chunks(rendered_text: str, *, chunk_size: int) -> list[dict[str, Any]]:
    chunks = split_telegram_plain_text(rendered_text, max_chars=chunk_size)
    return [
        {
            "index": index,
            "char_count": len(chunk),
            "sha256": sha256(chunk.encode("utf-8")).hexdigest(),
        }
        for index, chunk in enumerate(chunks, start=1)
    ]


def _safe_intention_audit_log_metadata(intention: Mapping[str, Any]) -> dict[str, Any]:
    audit_log = intention.get("audit_log")
    if not isinstance(audit_log, Mapping):
        return {}
    return {
        key: audit_log[key]
        for key in ("event_type", "before_ref", "after_ref", "created_at")
        if audit_log.get(key) is not None
    }


def _validate_telegram_plan_intention(intention: Mapping[str, Any]) -> None:
    if intention.get("channel") != DIGEST_DELIVERY_DRAFT_CHANNEL:
        raise DeliveryTelegramPlanConflictError(
            "delivery intention channel is not telegram"
        )
    if intention.get("current_decision") != DIGEST_DELIVERY_DRAFT_APPROVED_DECISION:
        raise DeliveryTelegramPlanConflictError(
            "delivery intention is not approved"
        )
    if intention.get("eligible_for_delivery") is not True:
        raise DeliveryTelegramPlanConflictError(
            "delivery intention is not eligible for delivery"
        )
    if intention.get("delivery_execution_enabled") is not False:
        raise DeliveryTelegramPlanConflictError(
            "delivery intention execution state is unsafe"
        )


async def get_digest_delivery_intention_telegram_plan(
    session: AsyncSession,
    *,
    delivery_intention_id: str,
    chunk_size: int = DEFAULT_TELEGRAM_CHUNK_SIZE,
) -> dict[str, Any] | None:
    """Return a safe read-only Telegram delivery plan for a stored intention.

    This reads the delivery intention and referenced draft audit payloads only.
    It uses stored rendered draft text internally for deterministic Telegram
    chunk metadata, but never returns message text, sends, schedules, appends
    audit logs, or calls provider/delivery adapters.
    """

    cleaned_delivery_intention_id = _clean_delivery_intention_id(
        delivery_intention_id
    )
    intention = await get_digest_delivery_intention(
        session,
        delivery_intention_id=cleaned_delivery_intention_id,
    )
    if intention is None:
        return None

    _validate_telegram_plan_intention(intention)
    delivery_draft_id = _clean_delivery_draft_id(
        str(intention.get("delivery_draft_id", ""))
    )
    draft = await get_persisted_digest_delivery_draft(
        session,
        delivery_draft_id=delivery_draft_id,
    )
    if draft is None:
        raise DeliveryTelegramPlanConflictError(
            "referenced delivery draft was not found"
        )
    if draft.get("channel") != DIGEST_DELIVERY_DRAFT_CHANNEL:
        raise DeliveryTelegramPlanConflictError(
            "referenced delivery draft channel is not telegram"
        )

    rendered_text = draft.get("rendered_text")
    if not isinstance(rendered_text, str) or not rendered_text.strip():
        raise DeliveryTelegramPlanConflictError(
            "referenced delivery draft rendered text is unavailable"
        )

    text_hash = sha256(rendered_text.encode("utf-8")).hexdigest()
    draft_text_hash = str(draft.get("text_sha256", ""))
    intention_text_hash = str(intention.get("text_sha256", ""))
    if text_hash != draft_text_hash:
        raise DeliveryTelegramPlanConflictError(
            "delivery draft rendered text hash does not match stored text_sha256"
        )
    if intention_text_hash != draft_text_hash:
        raise DeliveryTelegramPlanConflictError(
            "delivery intention text_sha256 does not match referenced draft"
        )

    chunks = _telegram_plan_chunks(rendered_text, chunk_size=chunk_size)
    chunk_lengths = [chunk["char_count"] for chunk in chunks]
    chunk_metadata = {
        "chunk_size": chunk_size,
        "chunk_lengths": chunk_lengths,
        "chunks_preview_included": False,
    }
    for source_name, source in (("draft", draft), ("intention", intention)):
        source_chunk_count = _require_int(
            source.get("chunk_count"),
            field_name=f"{source_name} chunk_count",
        )
        if source_chunk_count != len(chunks):
            raise DeliveryTelegramPlanConflictError(
                f"{source_name} chunk_count does not match Telegram plan chunks"
            )

        source_char_count = _require_int(
            source.get("char_count"),
            field_name=f"{source_name} char_count",
        )
        if source_char_count != len(rendered_text):
            raise DeliveryTelegramPlanConflictError(
                f"{source_name} char_count does not match rendered text"
            )

        source_chunk_metadata = _safe_chunk_metadata(source.get("chunk_metadata"))
        if source_chunk_metadata.get("chunk_lengths") != chunk_lengths:
            raise DeliveryTelegramPlanConflictError(
                f"{source_name} chunk metadata does not match Telegram plan chunks"
            )

    return {
        "status": DIGEST_DELIVERY_TELEGRAM_PLAN_STATUS,
        "delivery_intention_id": cleaned_delivery_intention_id,
        "delivery_draft_id": delivery_draft_id,
        "digest_type": intention.get("digest_type"),
        "channel": DIGEST_DELIVERY_DRAFT_CHANNEL,
        "text_sha256": text_hash,
        "char_count": len(rendered_text),
        "chunk_count": len(chunks),
        "chunks_text_included": False,
        "chunks": chunks,
        "chunk_metadata": chunk_metadata,
        "delivery_execution_enabled": False,
        "delivery_enabled": False,
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "sent": False,
        "start_at": intention.get("start_at"),
        "end_at": intention.get("end_at"),
        "limit": intention.get("limit"),
        "debug_evidence": bool(intention.get("debug_evidence")),
        "intention": {
            "status": intention.get("status"),
            "persisted": bool(intention.get("persisted")),
            "audit_log": _safe_intention_audit_log_metadata(intention),
        },
        "source_of_truth": (
            dict(intention.get("source_of_truth"))
            if isinstance(intention.get("source_of_truth"), Mapping)
            else {}
        ),
        "safety": _telegram_delivery_plan_safety_metadata(),
    }


async def record_digest_delivery_draft_decision(
    session: AsyncSession,
    *,
    delivery_draft_id: str,
    decision: str,
    reviewer: str = "system",
    note: str | None = None,
) -> dict[str, Any]:
    cleaned_delivery_draft_id = _clean_delivery_draft_id(delivery_draft_id)
    cleaned_decision = _clean_decision(decision)
    cleaned_reviewer = _clean_required_text(
        reviewer,
        field_name="reviewer",
        max_length=DIGEST_DELIVERY_DRAFT_DECISION_REVIEWER_MAX_LENGTH,
    )
    cleaned_note = _clean_optional_text(
        note,
        field_name="note",
        max_length=DIGEST_DELIVERY_DRAFT_DECISION_NOTE_MAX_LENGTH,
    )

    draft = await get_persisted_digest_delivery_draft(
        session,
        delivery_draft_id=cleaned_delivery_draft_id,
    )
    if draft is None:
        raise DeliveryDraftNotFoundError("delivery draft was not found")

    status = await get_digest_delivery_draft_approval_status(
        session,
        delivery_draft_id=cleaned_delivery_draft_id,
    )
    if status is None:
        raise DeliveryDraftNotFoundError("delivery draft was not found")

    current_decision = status["current_decision"]
    if current_decision == cleaned_decision:
        return status
    if current_decision is not None:
        raise DeliveryDraftDecisionConflictError(
            f"delivery draft already has terminal decision {current_decision}"
        )

    event_type = _decision_event_type(cleaned_decision)
    record = AuditLog(
        event_type=event_type,
        actor=cleaned_reviewer,
        correlation_id=cleaned_delivery_draft_id,
        trace_id=cleaned_delivery_draft_id,
        after_ref=cleaned_delivery_draft_id,
        approval_id=f"{cleaned_delivery_draft_id}:{cleaned_decision}",
        payload=_decision_payload(
            draft=draft,
            decision=cleaned_decision,
            reviewer=cleaned_reviewer,
            note=cleaned_note,
        ),
    )
    session.add(record)
    await session.flush()

    updated_status = await get_digest_delivery_draft_approval_status(
        session,
        delivery_draft_id=cleaned_delivery_draft_id,
    )
    if updated_status is None:
        raise DeliveryDraftNotFoundError("delivery draft was not found")
    return updated_status


async def approve_digest_delivery_draft(
    session: AsyncSession,
    *,
    delivery_draft_id: str,
    reviewer: str = "system",
    note: str | None = None,
) -> dict[str, Any]:
    return await record_digest_delivery_draft_decision(
        session,
        delivery_draft_id=delivery_draft_id,
        decision=DIGEST_DELIVERY_DRAFT_APPROVED_DECISION,
        reviewer=reviewer,
        note=note,
    )


async def reject_digest_delivery_draft(
    session: AsyncSession,
    *,
    delivery_draft_id: str,
    reviewer: str = "system",
    note: str | None = None,
) -> dict[str, Any]:
    return await record_digest_delivery_draft_decision(
        session,
        delivery_draft_id=delivery_draft_id,
        decision=DIGEST_DELIVERY_DRAFT_REJECTED_DECISION,
        reviewer=reviewer,
        note=note,
    )
