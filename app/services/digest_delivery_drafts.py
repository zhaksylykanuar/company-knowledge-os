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
DIGEST_DELIVERY_TELEGRAM_EXECUTION_PREFLIGHT_STATUS = "telegram_execution_preflight"
DIGEST_DELIVERY_TELEGRAM_EXECUTION_GATE_STATUS = "telegram_execution_gate"
DIGEST_DELIVERY_RESULT_STATUS = "delivery_result"
DIGEST_DELIVERY_DRAFT_TYPE = "persisted_attention"
DIGEST_DELIVERY_DRAFT_CHANNEL = "telegram"
DIGEST_DELIVERY_DRAFT_ID_PREFIX = "ddraft_"
DIGEST_DELIVERY_INTENTION_ID_PREFIX = "dint_"
DIGEST_DELIVERY_RESULT_ID_PREFIX = "dres_"
DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE = "digest.delivery_draft.created"
DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE = "digest.delivery_draft.approved"
DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE = "digest.delivery_draft.rejected"
DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE = "digest.delivery_intention.created"
DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE = "digest.delivery_result.recorded"
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
DIGEST_DELIVERY_RESULT_STATUSES = (
    "succeeded",
    "failed",
    "partial",
    "skipped",
)
DIGEST_DELIVERY_DRAFT_DECISION_REVIEWER_MAX_LENGTH = 120
DIGEST_DELIVERY_DRAFT_DECISION_NOTE_MAX_LENGTH = 500
DIGEST_DELIVERY_RESULT_EXECUTION_ATTEMPT_ID_MAX_LENGTH = 120
DIGEST_DELIVERY_RESULT_SAFE_ERROR_CODE_MAX_LENGTH = 80
DIGEST_DELIVERY_RESULT_SAFE_ERROR_SUMMARY_MAX_LENGTH = 240
DIGEST_DELIVERY_RESULT_SAFE_MESSAGE_REFS_LIMIT = 20
DIGEST_DELIVERY_RESULT_SAFE_MESSAGE_REF_VALUE_MAX_LENGTH = 120
DIGEST_DELIVERY_TELEGRAM_EXECUTION_GATE_MAX_CHUNKS = 10
DIGEST_PRESENTATION_VARIANT_CANONICAL_SUCCESS_BLOCKER = (
    "presentation_variant_canonical_hash_already_successfully_sent"
)

DIGEST_DELIVERY_TELEGRAM_EXECUTION_GATE_REQUIRED_OPERATOR_FIELDS = (
    "delivery_intention_id",
    "execution_attempt_id",
    "max_chunks",
    "confirm_send",
    "test_mode",
)

SAFE_DELIVERY_RESULT_MESSAGE_REF_KEYS = (
    "chunk_index",
    "message_id",
    "provider_message_id",
    "chunk_sha256",
    "status",
)
UNSAFE_DELIVERY_RESULT_TEXT_MARKERS = (
    "bot_token",
    "chat_id",
    "credential",
    "secret",
    "token",
    "webhook",
    "http://",
    "https://",
    "api.telegram.org",
)

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


class DeliveryTelegramExecutionPreflightConflictError(ValueError):
    """Raised when Telegram execution preflight cannot safely inspect an intention."""


class DeliveryTelegramExecutionGateConflictError(ValueError):
    """Raised when Telegram execution gate cannot safely inspect an intention."""


class DeliveryResultConflictError(ValueError):
    """Raised when a delivery result record conflicts with stored audit data."""


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


def build_delivery_result_id(
    *,
    delivery_intention_id: str,
    execution_attempt_id: str,
    channel: str,
    text_sha256: str,
    result_status: str,
) -> str:
    stable_input = {
        "channel": channel,
        "delivery_intention_id": delivery_intention_id,
        "execution_attempt_id": execution_attempt_id,
        "result_status": result_status,
        "text_sha256": text_sha256,
    }
    digest = sha256(_canonical_json(stable_input).encode("utf-8")).hexdigest()
    return f"{DIGEST_DELIVERY_RESULT_ID_PREFIX}{digest[:32]}"


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


def _clean_delivery_result_id(delivery_result_id: str) -> str:
    if not isinstance(delivery_result_id, str):
        raise ValueError("delivery_result_id must be a non-empty string")

    cleaned = delivery_result_id.strip()
    if not cleaned:
        raise ValueError("delivery_result_id must be a non-empty string")
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


def _clean_text_sha256(
    value: str | None,
    *,
    field_name: str,
    required: bool,
) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field_name} must be a SHA-256 hex digest")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")

    cleaned = value.strip().lower()
    if not cleaned:
        if required:
            raise ValueError(f"{field_name} must be a SHA-256 hex digest")
        return None
    if len(cleaned) != 64 or any(char not in "0123456789abcdef" for char in cleaned):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
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


def _clean_delivery_result_status(result_status: str) -> str:
    if not isinstance(result_status, str):
        raise ValueError("result_status must be one of succeeded, failed, partial, skipped")

    cleaned = result_status.strip().lower()
    if cleaned not in DIGEST_DELIVERY_RESULT_STATUSES:
        raise ValueError("result_status must be one of succeeded, failed, partial, skipped")
    return cleaned


def _require_non_negative_int(value: Any, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    if value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _safe_message_ref_value(value: Any) -> int | str | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            return None
        if _contains_unsafe_delivery_result_marker(cleaned):
            return None
        return cleaned[:DIGEST_DELIVERY_RESULT_SAFE_MESSAGE_REF_VALUE_MAX_LENGTH]
    return None


def _contains_unsafe_delivery_result_marker(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in UNSAFE_DELIVERY_RESULT_TEXT_MARKERS)


def _clean_safe_delivery_result_text(
    value: str | None,
    *,
    field_name: str,
    max_length: int,
) -> str | None:
    cleaned = _clean_optional_text(
        value,
        field_name=field_name,
        max_length=max_length,
    )
    if cleaned is not None and _contains_unsafe_delivery_result_marker(cleaned):
        raise ValueError(f"{field_name} must not include credential-like values")
    return cleaned


def _safe_message_refs(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("safe_message_refs must be a list")

    refs: list[dict[str, Any]] = []
    for ref in value[:DIGEST_DELIVERY_RESULT_SAFE_MESSAGE_REFS_LIMIT]:
        if not isinstance(ref, Mapping):
            continue
        safe_ref = {}
        for key in SAFE_DELIVERY_RESULT_MESSAGE_REF_KEYS:
            if key not in ref:
                continue
            safe_value = _safe_message_ref_value(ref[key])
            if safe_value is not None:
                safe_ref[key] = safe_value
        if safe_ref:
            refs.append(safe_ref)
    return refs


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


def _safe_delivery_draft_lookup_metadata(
    draft: Mapping[str, Any],
) -> dict[str, Any]:
    audit_log = draft.get("audit_log")
    recorded_at = (
        audit_log.get("created_at")
        if isinstance(audit_log, Mapping)
        else None
    )
    return {
        "delivery_draft_id": draft.get("delivery_draft_id"),
        "digest_type": draft.get("digest_type"),
        "channel": draft.get("channel"),
        "status": draft.get("status"),
        "persisted": bool(draft.get("persisted")),
        "start_at": draft.get("start_at"),
        "end_at": draft.get("end_at"),
        "limit": draft.get("limit"),
        "debug_evidence": bool(draft.get("debug_evidence")),
        "text_sha256": draft.get("text_sha256"),
        "char_count": draft.get("char_count"),
        "chunk_count": draft.get("chunk_count"),
        "recorded_at": recorded_at,
    }


async def list_persisted_digest_delivery_drafts_for_window(
    session: AsyncSession,
    *,
    start_at: datetime,
    end_at: datetime,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
    debug_evidence: bool = False,
    channel: str = DIGEST_DELIVERY_DRAFT_CHANNEL,
) -> list[dict[str, Any]]:
    """Return safe delivery draft metadata for an exact persisted digest window.

    This reads existing ``digest.delivery_draft.created`` audit rows and filters
    them by the safe window/limit/debug metadata stored in the draft payload. It
    intentionally returns lookup metadata only and never exposes rendered text,
    digest item snapshots, chunk text, raw payloads, credentials, or evidence
    refs.
    """

    _require_aware_datetime(start_at, field_name="start_at")
    _require_aware_datetime(end_at, field_name="end_at")
    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")

    safe_limit = _validated_limit(limit)
    start_at_iso = start_at.isoformat()
    end_at_iso = end_at.isoformat()
    records = await session.scalars(
        select(AuditLog)
        .where(AuditLog.event_type == DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE)
        .order_by(AuditLog.id)
    )

    drafts: list[dict[str, Any]] = []
    for record in records:
        response = _audit_log_response(record)
        if response is None:
            continue
        if response.get("digest_type") != DIGEST_DELIVERY_DRAFT_TYPE:
            continue
        if response.get("channel") != channel:
            continue
        if response.get("start_at") != start_at_iso:
            continue
        if response.get("end_at") != end_at_iso:
            continue
        if response.get("limit") != safe_limit:
            continue
        if bool(response.get("debug_evidence")) != bool(debug_evidence):
            continue
        drafts.append(_safe_delivery_draft_lookup_metadata(response))
    return drafts


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


def _telegram_execution_preflight_safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "db_write_scope": "none",
        "credential_values_exposed": False,
        "credential_validation_invoked": False,
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
        "telegram_preflight_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _telegram_execution_gate_safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "db_write_scope": "none",
        "credential_values_exposed": False,
        "credential_validation_invoked": False,
        "raw_payloads_exposed": False,
        "telegram_raw_api_response_stored": False,
        "rendered_text_included": False,
        "chunk_text_included": False,
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
        "telegram_preflight_is_source_of_truth": False,
        "telegram_execution_gate_is_source_of_truth": False,
        "delivery_result_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _delivery_result_safety_metadata(
    *,
    delivery_invoked: bool,
    delivery_adapter_invoked: bool,
) -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": False,
        "db_write_scope": "audit_logs_only",
        "audit_log_backed": True,
        "credential_values_exposed": False,
        "credential_validation_invoked": False,
        "raw_payloads_exposed": False,
        "telegram_raw_api_response_stored": False,
        "rendered_text_included": False,
        "chunk_text_included": False,
        "delivery_invoked": delivery_invoked,
        "delivery_adapter_invoked": delivery_adapter_invoked,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "outbox_record_created": False,
        "connectors_invoked": False,
        "live_api_calls": False,
        "draft_is_source_of_truth": False,
        "intention_is_source_of_truth": False,
        "telegram_plan_is_source_of_truth": False,
        "telegram_preflight_is_source_of_truth": False,
        "delivery_result_is_source_of_truth": False,
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


def _safe_delivery_intention_lookup_metadata(
    intention: Mapping[str, Any],
) -> dict[str, Any]:
    audit_log = intention.get("audit_log")
    recorded_at = (
        audit_log.get("created_at")
        if isinstance(audit_log, Mapping)
        else None
    )
    return {
        "delivery_intention_id": intention.get("delivery_intention_id"),
        "delivery_draft_id": intention.get("delivery_draft_id"),
        "digest_type": intention.get("digest_type"),
        "channel": intention.get("channel"),
        "current_decision": intention.get("current_decision"),
        "eligible_for_delivery": intention.get("eligible_for_delivery"),
        "text_sha256": intention.get("text_sha256"),
        "char_count": intention.get("char_count"),
        "chunk_count": intention.get("chunk_count"),
        "sent": bool(intention.get("sent")),
        "scheduler_invoked": bool(intention.get("scheduler_invoked")),
        "recorded_at": recorded_at,
    }


async def list_delivery_intentions_for_delivery_draft(
    session: AsyncSession,
    *,
    delivery_draft_id: str,
) -> list[dict[str, Any]]:
    cleaned_delivery_draft_id = _clean_delivery_draft_id(delivery_draft_id)
    records = await session.scalars(
        select(AuditLog)
        .where(AuditLog.event_type == DIGEST_DELIVERY_INTENTION_CREATED_EVENT_TYPE)
        .where(AuditLog.before_ref == cleaned_delivery_draft_id)
        .order_by(AuditLog.id)
    )

    intentions: list[dict[str, Any]] = []
    for record in records:
        response = _delivery_intention_audit_log_response(record)
        if response is None:
            continue
        intentions.append(_safe_delivery_intention_lookup_metadata(response))
    return intentions


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


def _safe_delivery_result_intention_metadata(
    intention: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "status": intention.get("status"),
        "persisted": bool(intention.get("persisted")),
        "current_decision": intention.get("current_decision"),
        "eligible_for_delivery": bool(intention.get("eligible_for_delivery")),
        "audit_log": _safe_intention_audit_log_metadata(intention),
    }


def _delivery_result_source_of_truth_metadata(plan: Mapping[str, Any]) -> dict[str, Any]:
    source_of_truth = (
        dict(plan.get("source_of_truth"))
        if isinstance(plan.get("source_of_truth"), Mapping)
        else {}
    )
    source_of_truth["delivery_result_is_source_of_truth"] = False
    source_of_truth["delivery_result_scope"] = "delivery_execution_metadata"
    source_of_truth["telegram_is_source_of_truth"] = False
    return source_of_truth


def _validate_delivery_result_counts(
    *,
    result_status: str,
    planned_chunk_count: int,
    attempted_chunk_count: int,
    delivered_chunk_count: int,
    failed_chunk_count: int,
) -> None:
    if attempted_chunk_count > planned_chunk_count:
        raise ValueError("attempted_chunk_count must be at most planned_chunk_count")
    if delivered_chunk_count > attempted_chunk_count:
        raise ValueError("delivered_chunk_count must be at most attempted_chunk_count")
    if failed_chunk_count > attempted_chunk_count:
        raise ValueError("failed_chunk_count must be at most attempted_chunk_count")

    if result_status == "succeeded":
        if (
            attempted_chunk_count != planned_chunk_count
            or delivered_chunk_count != planned_chunk_count
            or failed_chunk_count != 0
        ):
            raise ValueError("succeeded delivery results must deliver all planned chunks")
    elif result_status == "failed":
        if attempted_chunk_count < 1 or delivered_chunk_count != 0 or failed_chunk_count < 1:
            raise ValueError("failed delivery results must attempt and fail at least one chunk")
    elif result_status == "partial":
        if delivered_chunk_count < 1 or delivered_chunk_count >= planned_chunk_count:
            raise ValueError("partial delivery results must deliver some but not all chunks")
    elif result_status == "skipped" and (
        attempted_chunk_count != 0
        or delivered_chunk_count != 0
        or failed_chunk_count != 0
    ):
        raise ValueError("skipped delivery results must not attempt chunks")


def _configured_value_present(value: Any) -> bool:
    if value is None:
        return False

    get_secret_value = getattr(value, "get_secret_value", None)
    if callable(get_secret_value):
        value = get_secret_value()

    if not isinstance(value, str):
        return False
    return bool(value.strip())


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


async def get_digest_delivery_intention_telegram_execution_preflight(
    session: AsyncSession,
    *,
    delivery_intention_id: str,
    telegram_bot_token: Any = None,
    telegram_chat_id: Any = None,
) -> dict[str, Any] | None:
    """Return a no-send Telegram execution preflight for a stored intention.

    The preflight validates stored delivery chain readiness through the existing
    Telegram plan path and checks configuration presence only. It never returns
    credential values, validates credentials with Telegram, sends, schedules,
    appends audit logs, or calls provider/delivery adapters.
    """

    cleaned_delivery_intention_id = _clean_delivery_intention_id(
        delivery_intention_id
    )
    try:
        plan = await get_digest_delivery_intention_telegram_plan(
            session,
            delivery_intention_id=cleaned_delivery_intention_id,
        )
    except DeliveryTelegramPlanConflictError as exc:
        raise DeliveryTelegramExecutionPreflightConflictError(str(exc)) from exc
    if plan is None:
        return None

    intention = await get_digest_delivery_intention(
        session,
        delivery_intention_id=cleaned_delivery_intention_id,
    )
    if intention is None:
        return None

    delivery_draft_id = _clean_delivery_draft_id(
        str(plan.get("delivery_draft_id", ""))
    )
    approval_status = await get_digest_delivery_draft_approval_status(
        session,
        delivery_draft_id=delivery_draft_id,
    )
    if approval_status is None:
        raise DeliveryTelegramExecutionPreflightConflictError(
            "approval status was not found"
        )

    readiness = await get_digest_delivery_draft_delivery_readiness(
        session,
        delivery_draft_id=delivery_draft_id,
    )
    if readiness is None:
        raise DeliveryTelegramExecutionPreflightConflictError(
            "delivery readiness was not found"
        )

    telegram_bot_token_present = _configured_value_present(telegram_bot_token)
    telegram_chat_id_present = _configured_value_present(telegram_chat_id)
    blockers: list[str] = []
    if not telegram_bot_token_present:
        blockers.append("telegram_bot_token_missing")
    if not telegram_chat_id_present:
        blockers.append("telegram_chat_id_missing")
    blockers.append("delivery_execution_not_implemented")

    return {
        "status": DIGEST_DELIVERY_TELEGRAM_EXECUTION_PREFLIGHT_STATUS,
        "delivery_intention_id": cleaned_delivery_intention_id,
        "delivery_draft_id": delivery_draft_id,
        "digest_type": plan.get("digest_type"),
        "channel": DIGEST_DELIVERY_DRAFT_CHANNEL,
        "text_sha256": plan.get("text_sha256"),
        "char_count": plan.get("char_count"),
        "chunk_count": plan.get("chunk_count"),
        "telegram_plan_ready": True,
        "telegram_bot_token_present": telegram_bot_token_present,
        "telegram_chat_id_present": telegram_chat_id_present,
        "credential_presence_ready": (
            telegram_bot_token_present and telegram_chat_id_present
        ),
        "execution_preflight_ready": False,
        "blockers": blockers,
        "delivery_execution_enabled": False,
        "delivery_enabled": False,
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "sent": False,
        "intention": {
            "status": intention.get("status"),
            "persisted": bool(intention.get("persisted")),
            "current_decision": intention.get("current_decision"),
            "eligible_for_delivery": bool(intention.get("eligible_for_delivery")),
            "audit_log": _safe_intention_audit_log_metadata(intention),
        },
        "approval": {
            "current_decision": approval_status.get("current_decision"),
            "approved": bool(approval_status.get("approved")),
            "rejected": bool(approval_status.get("rejected")),
        },
        "readiness": _readiness_summary(readiness),
        "telegram_plan": {
            "status": plan.get("status"),
            "chunk_count": plan.get("chunk_count"),
            "chunks_text_included": bool(plan.get("chunks_text_included")),
            "delivery_execution_enabled": False,
            "delivery_enabled": False,
            "delivery_invoked": False,
            "delivery_adapter_invoked": False,
            "scheduler_invoked": False,
            "sent": False,
        },
        "source_of_truth": (
            dict(plan.get("source_of_truth"))
            if isinstance(plan.get("source_of_truth"), Mapping)
            else {}
        ),
        "safety": _telegram_execution_preflight_safety_metadata(),
    }


def build_digest_delivery_result(
    *,
    intention: Mapping[str, Any],
    telegram_plan: Mapping[str, Any],
    execution_attempt_id: str,
    result_status: str,
    attempted_chunk_count: int,
    delivered_chunk_count: int,
    failed_chunk_count: int,
    safe_message_refs: list[Mapping[str, Any]] | None = None,
    safe_error_code: str | None = None,
    safe_error_summary: str | None = None,
    delivery_invoked: bool = False,
    delivery_adapter_invoked: bool = False,
) -> dict[str, Any]:
    cleaned_execution_attempt_id = _clean_required_text(
        execution_attempt_id,
        field_name="execution_attempt_id",
        max_length=DIGEST_DELIVERY_RESULT_EXECUTION_ATTEMPT_ID_MAX_LENGTH,
    )
    cleaned_result_status = _clean_delivery_result_status(result_status)
    delivery_intention_id = _clean_delivery_intention_id(
        str(intention.get("delivery_intention_id", ""))
    )
    channel = str(telegram_plan.get("channel", ""))
    if channel != DIGEST_DELIVERY_DRAFT_CHANNEL:
        raise DeliveryResultConflictError("delivery result channel is not telegram")

    text_hash = str(telegram_plan.get("text_sha256", ""))
    if not text_hash or text_hash != str(intention.get("text_sha256", "")):
        raise DeliveryResultConflictError(
            "delivery result text_sha256 does not match intention"
        )

    planned_chunk_count = _require_non_negative_int(
        telegram_plan.get("chunk_count"),
        field_name="planned_chunk_count",
    )
    safe_attempted_chunk_count = _require_non_negative_int(
        attempted_chunk_count,
        field_name="attempted_chunk_count",
    )
    safe_delivered_chunk_count = _require_non_negative_int(
        delivered_chunk_count,
        field_name="delivered_chunk_count",
    )
    safe_failed_chunk_count = _require_non_negative_int(
        failed_chunk_count,
        field_name="failed_chunk_count",
    )
    _validate_delivery_result_counts(
        result_status=cleaned_result_status,
        planned_chunk_count=planned_chunk_count,
        attempted_chunk_count=safe_attempted_chunk_count,
        delivered_chunk_count=safe_delivered_chunk_count,
        failed_chunk_count=safe_failed_chunk_count,
    )

    delivery_result_id = build_delivery_result_id(
        delivery_intention_id=delivery_intention_id,
        execution_attempt_id=cleaned_execution_attempt_id,
        channel=channel,
        text_sha256=text_hash,
        result_status=cleaned_result_status,
    )
    delivery_invoked_bool = bool(delivery_invoked)
    delivery_adapter_invoked_bool = bool(delivery_adapter_invoked)
    payload = {
        "persisted": True,
        "status": DIGEST_DELIVERY_RESULT_STATUS,
        "delivery_result_id": delivery_result_id,
        "delivery_intention_id": delivery_intention_id,
        "execution_attempt_id": cleaned_execution_attempt_id,
        "digest_type": telegram_plan.get("digest_type"),
        "channel": channel,
        "result_status": cleaned_result_status,
        "text_sha256": text_hash,
        "planned_chunk_count": planned_chunk_count,
        "attempted_chunk_count": safe_attempted_chunk_count,
        "delivered_chunk_count": safe_delivered_chunk_count,
        "failed_chunk_count": safe_failed_chunk_count,
        "safe_message_refs": _safe_message_refs(safe_message_refs),
        "delivery_invoked": delivery_invoked_bool,
        "delivery_adapter_invoked": delivery_adapter_invoked_bool,
        "scheduler_invoked": False,
        "approval_execution_invoked": False,
        "sent": safe_delivered_chunk_count > 0,
        "intention": _safe_delivery_result_intention_metadata(intention),
        "telegram_plan": {
            "status": telegram_plan.get("status"),
            "delivery_intention_id": telegram_plan.get("delivery_intention_id"),
            "delivery_draft_id": telegram_plan.get("delivery_draft_id"),
            "channel": telegram_plan.get("channel"),
            "text_sha256": telegram_plan.get("text_sha256"),
            "chunk_count": telegram_plan.get("chunk_count"),
            "chunks_text_included": bool(telegram_plan.get("chunks_text_included")),
            "delivery_execution_enabled": False,
            "delivery_enabled": False,
            "delivery_invoked": False,
            "delivery_adapter_invoked": False,
            "scheduler_invoked": False,
            "sent": False,
        },
        "source_of_truth": _delivery_result_source_of_truth_metadata(telegram_plan),
        "safety": _delivery_result_safety_metadata(
            delivery_invoked=delivery_invoked_bool,
            delivery_adapter_invoked=delivery_adapter_invoked_bool,
        ),
    }

    cleaned_error_code = _clean_safe_delivery_result_text(
        safe_error_code,
        field_name="safe_error_code",
        max_length=DIGEST_DELIVERY_RESULT_SAFE_ERROR_CODE_MAX_LENGTH,
    )
    if cleaned_error_code is not None:
        payload["safe_error_code"] = cleaned_error_code

    cleaned_error_summary = _clean_safe_delivery_result_text(
        safe_error_summary,
        field_name="safe_error_summary",
        max_length=DIGEST_DELIVERY_RESULT_SAFE_ERROR_SUMMARY_MAX_LENGTH,
    )
    if cleaned_error_summary is not None:
        payload["safe_error_summary"] = cleaned_error_summary

    return payload


def _delivery_result_audit_log_response(record: AuditLog) -> dict[str, Any] | None:
    if not isinstance(record.payload, Mapping):
        return None

    response = dict(record.payload)
    if response.get("delivery_result_id") != record.after_ref:
        return None
    if response.get("delivery_intention_id") != record.before_ref:
        return None

    response["persisted"] = True
    recorded_at = record.created_at.isoformat() if record.created_at is not None else None
    response["recorded_at"] = recorded_at
    response["audit_log"] = {
        "event_type": record.event_type,
        "before_ref": record.before_ref,
        "after_ref": record.after_ref,
        "created_at": recorded_at,
    }
    return response


def _safe_delivery_result_lookup_metadata(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "delivery_result_id": result.get("delivery_result_id"),
        "delivery_intention_id": result.get("delivery_intention_id"),
        "execution_attempt_id": result.get("execution_attempt_id"),
        "result_status": result.get("result_status"),
        "sent": bool(result.get("sent")),
        "attempted_chunk_count": result.get("attempted_chunk_count"),
        "delivered_chunk_count": result.get("delivered_chunk_count"),
        "failed_chunk_count": result.get("failed_chunk_count"),
        "recorded_at": result.get("recorded_at"),
    }


def _delivery_result_metadata_is_successful(result: Mapping[str, Any]) -> bool:
    delivered_chunk_count = result.get("delivered_chunk_count")
    return (
        result.get("result_status") == "succeeded"
        and result.get("sent") is True
        and isinstance(delivered_chunk_count, int)
        and not isinstance(delivered_chunk_count, bool)
        and delivered_chunk_count > 0
    )


async def get_digest_delivery_result(
    session: AsyncSession,
    *,
    delivery_result_id: str,
) -> dict[str, Any] | None:
    cleaned_delivery_result_id = _clean_delivery_result_id(delivery_result_id)
    record = await session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE)
        .where(AuditLog.after_ref == cleaned_delivery_result_id)
        .order_by(AuditLog.id)
    )
    if record is None:
        return None
    return _delivery_result_audit_log_response(record)


async def list_delivery_results_for_delivery_intention(
    session: AsyncSession,
    *,
    delivery_intention_id: str,
) -> list[dict[str, Any]]:
    cleaned_delivery_intention_id = _clean_delivery_intention_id(
        delivery_intention_id
    )
    records = await session.scalars(
        select(AuditLog)
        .where(AuditLog.event_type == DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE)
        .where(AuditLog.before_ref == cleaned_delivery_intention_id)
        .order_by(AuditLog.id)
    )

    results: list[dict[str, Any]] = []
    for record in records:
        response = _delivery_result_audit_log_response(record)
        if response is None:
            continue
        results.append(_safe_delivery_result_lookup_metadata(response))
    return results


async def get_successful_delivery_result_for_delivery_intention(
    session: AsyncSession,
    *,
    delivery_intention_id: str,
) -> dict[str, Any] | None:
    results = await list_delivery_results_for_delivery_intention(
        session,
        delivery_intention_id=delivery_intention_id,
    )
    for result in results:
        if _delivery_result_metadata_is_successful(result):
            return result
    return None


async def get_delivery_draft_send_status(
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

    intentions = await list_delivery_intentions_for_delivery_draft(
        session,
        delivery_draft_id=cleaned_delivery_draft_id,
    )
    associated_intentions: list[dict[str, Any]] = []
    delivery_result_count = 0
    successful_result_count = 0
    failed_result_count = 0
    partial_result_count = 0
    skipped_result_count = 0
    prior_successful: dict[str, Any] | None = None

    for intention in intentions:
        delivery_intention_id = str(intention.get("delivery_intention_id") or "")
        if not delivery_intention_id:
            continue
        results = await list_delivery_results_for_delivery_intention(
            session,
            delivery_intention_id=delivery_intention_id,
        )
        successful_results = [
            result
            for result in results
            if _delivery_result_metadata_is_successful(result)
        ]
        statuses = [result.get("result_status") for result in results]
        delivery_result_count += len(results)
        successful_result_count += len(successful_results)
        failed_result_count += statuses.count("failed")
        partial_result_count += statuses.count("partial")
        skipped_result_count += statuses.count("skipped")
        if prior_successful is None and successful_results:
            prior_successful = successful_results[0]

        associated_intentions.append(
            {
                **intention,
                "delivery_results": {
                    "count": len(results),
                    "successful_count": len(successful_results),
                    "failed_count": statuses.count("failed"),
                    "partial_count": statuses.count("partial"),
                    "skipped_count": statuses.count("skipped"),
                    "results": results,
                },
            }
        )

    already_sent = prior_successful is not None
    return {
        "status": "delivery_draft_send_status",
        "delivery_draft_id": cleaned_delivery_draft_id,
        "associated_delivery_intention_count": len(associated_intentions),
        "associated_delivery_intentions": associated_intentions,
        "delivery_results_summary": {
            "count": delivery_result_count,
            "successful_count": successful_result_count,
            "failed_count": failed_result_count,
            "partial_count": partial_result_count,
            "skipped_count": skipped_result_count,
        },
        "stale_or_already_sent_warning": already_sent,
        "blocker": (
            "delivery_draft_already_successfully_sent" if already_sent else None
        ),
        "prior_successful_delivery_intention_id": (
            prior_successful.get("delivery_intention_id")
            if prior_successful is not None
            else None
        ),
        "prior_successful_delivery_result_id": (
            prior_successful.get("delivery_result_id")
            if prior_successful is not None
            else None
        ),
        "prior_successful_execution_attempt_id": (
            prior_successful.get("execution_attempt_id")
            if prior_successful is not None
            else None
        ),
        "prior_successful_delivered_chunk_count": (
            prior_successful.get("delivered_chunk_count")
            if prior_successful is not None
            else None
        ),
        "recommended_next_action": (
            "create_new_digest_window_or_synthetic_sample_before_another_send"
            if already_sent
            else "continue_manual_pilot_flow"
        ),
        "safety": {
            "provider_free": True,
            "read_only": True,
            "db_write_scope": "none",
            "delivery_invoked": False,
            "delivery_adapter_invoked": False,
            "approval_execution_invoked": False,
            "scheduler_invoked": False,
            "outbox_record_created": False,
            "delivery_worker_invoked": False,
            "credential_values_exposed": False,
            "stored_digest_text_included": False,
            "chunk_text_included": False,
            "raw_content_exposed": False,
            "draft_status_is_source_of_truth": False,
        },
    }


def _presentation_variant_duplicate_guard_safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "db_write_scope": "none",
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "outbox_record_created": False,
        "delivery_worker_invoked": False,
        "delivery_result_record_created": False,
        "rendered_text_included": False,
        "grouped_preview_text_included": False,
        "chunk_text_included": False,
        "raw_payloads_exposed": False,
        "credential_values_exposed": False,
        "urls_exposed": False,
        "source_ids_exposed": False,
        "author_identity_exposed": False,
        "evidence_refs_exposed": False,
        "semantic_duplicate_claimed": False,
        "enforced_in_send_path": False,
        "draft_is_source_of_truth": False,
        "delivery_result_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


def _empty_hash_lifecycle(text_sha256: str | None) -> dict[str, Any]:
    return {
        "text_sha256": text_sha256,
        "matching_delivery_draft_count": 0,
        "matches_existing_draft": False,
        "has_successful_delivery_result": False,
        "matching_delivery_draft_id": None,
        "prior_successful_delivery_intention_id": None,
        "prior_successful_delivery_result_id": None,
        "prior_successful_execution_attempt_id": None,
        "prior_successful_delivered_chunk_count": None,
        "blocker": None,
        "recommended_next_action": "continue_manual_pilot_flow",
    }


async def _delivery_hash_lifecycle_for_window(
    session: AsyncSession,
    *,
    text_sha256: str,
    delivery_drafts: list[Mapping[str, Any]],
) -> dict[str, Any]:
    matching_drafts = [
        draft for draft in delivery_drafts if draft.get("text_sha256") == text_sha256
    ]
    lifecycle = _empty_hash_lifecycle(text_sha256)
    lifecycle["matching_delivery_draft_count"] = len(matching_drafts)
    lifecycle["matches_existing_draft"] = bool(matching_drafts)

    first_status: Mapping[str, Any] | None = None
    successful_status: Mapping[str, Any] | None = None
    successful_delivery_draft_id: str | None = None
    first_delivery_draft_id: str | None = None

    for draft in matching_drafts:
        delivery_draft_id = str(draft.get("delivery_draft_id") or "").strip()
        if not delivery_draft_id:
            continue
        if first_delivery_draft_id is None:
            first_delivery_draft_id = delivery_draft_id

        status = await get_delivery_draft_send_status(
            session,
            delivery_draft_id=delivery_draft_id,
        )
        if status is None:
            continue
        if first_status is None:
            first_status = status
        if status.get("blocker") == "delivery_draft_already_successfully_sent":
            successful_status = status
            successful_delivery_draft_id = delivery_draft_id
            break

    if successful_status is None:
        lifecycle["matching_delivery_draft_id"] = first_delivery_draft_id
        if first_status is not None:
            lifecycle["recommended_next_action"] = first_status.get(
                "recommended_next_action"
            )
        return lifecycle

    lifecycle["has_successful_delivery_result"] = True
    lifecycle["matching_delivery_draft_id"] = successful_delivery_draft_id
    lifecycle["prior_successful_delivery_intention_id"] = successful_status.get(
        "prior_successful_delivery_intention_id"
    )
    lifecycle["prior_successful_delivery_result_id"] = successful_status.get(
        "prior_successful_delivery_result_id"
    )
    lifecycle["prior_successful_execution_attempt_id"] = successful_status.get(
        "prior_successful_execution_attempt_id"
    )
    lifecycle["prior_successful_delivered_chunk_count"] = successful_status.get(
        "prior_successful_delivered_chunk_count"
    )
    lifecycle["blocker"] = successful_status.get("blocker")
    lifecycle["recommended_next_action"] = successful_status.get(
        "recommended_next_action"
    )
    return lifecycle


async def evaluate_digest_delivery_presentation_variant_duplicate_guard(
    session: AsyncSession,
    *,
    presentation_text_sha256: str,
    canonical_text_sha256: str | None = None,
    start_at: datetime,
    end_at: datetime,
    limit: int = DEFAULT_DIGEST_ENTRY_LIMIT,
    debug_evidence: bool = False,
    channel: str = DIGEST_DELIVERY_DRAFT_CHANNEL,
) -> dict[str, Any]:
    """Read-only duplicate-success evaluator for linked presentation variants.

    The evaluator reports what a future canonical-hash guard could do when a
    current presentation hash is explicitly linked to a canonical digest hash.
    It does not enforce blocking, send messages, or create audit rows.
    """

    presentation_hash = _clean_text_sha256(
        presentation_text_sha256,
        field_name="presentation_text_sha256",
        required=True,
    )
    assert presentation_hash is not None
    canonical_hash = _clean_text_sha256(
        canonical_text_sha256,
        field_name="canonical_text_sha256",
        required=False,
    )
    safe_channel = _clean_required_text(
        channel,
        field_name="channel",
        max_length=40,
    )

    delivery_drafts = await list_persisted_digest_delivery_drafts_for_window(
        session,
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        debug_evidence=debug_evidence,
        channel=safe_channel,
    )
    presentation_lifecycle = await _delivery_hash_lifecycle_for_window(
        session,
        text_sha256=presentation_hash,
        delivery_drafts=delivery_drafts,
    )

    canonical_hash_provided = canonical_hash is not None
    canonical_hash_distinct = canonical_hash_provided and canonical_hash != presentation_hash
    if canonical_hash_distinct:
        canonical_lifecycle = await _delivery_hash_lifecycle_for_window(
            session,
            text_sha256=canonical_hash,
            delivery_drafts=delivery_drafts,
        )
    else:
        canonical_lifecycle = _empty_hash_lifecycle(canonical_hash)

    presentation_success = (
        presentation_lifecycle.get("has_successful_delivery_result") is True
    )
    canonical_success = (
        canonical_hash_distinct
        and canonical_lifecycle.get("has_successful_delivery_result") is True
    )
    presentation_variant_blocked = bool(canonical_success and not presentation_success)

    if presentation_success:
        blocker = "delivery_draft_already_successfully_sent"
        recommended_next_action = (
            presentation_lifecycle.get("recommended_next_action")
            or "create_new_digest_window_or_synthetic_sample_before_another_send"
        )
    elif presentation_variant_blocked:
        blocker = DIGEST_PRESENTATION_VARIANT_CANONICAL_SUCCESS_BLOCKER
        recommended_next_action = (
            "do_not_send_presentation_variant_of_successful_canonical_digest"
        )
    else:
        blocker = None
        recommended_next_action = "continue_manual_pilot_flow"

    return {
        "status": "presentation_variant_duplicate_guard_evaluation",
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "limit": _validated_limit(limit),
        "debug_evidence": bool(debug_evidence),
        "channel": safe_channel,
        "presentation_text_sha256": presentation_hash,
        "canonical_text_sha256": canonical_hash,
        "canonical_hash_provided": canonical_hash_provided,
        "canonical_hash_distinct_from_presentation": bool(canonical_hash_distinct),
        "presentation_hash_matches_existing_draft": (
            presentation_lifecycle.get("matches_existing_draft") is True
        ),
        "presentation_hash_has_successful_delivery_result": presentation_success,
        "canonical_hash_matches_existing_draft": (
            canonical_hash_distinct
            and canonical_lifecycle.get("matches_existing_draft") is True
        ),
        "canonical_hash_has_successful_delivery_result": bool(canonical_success),
        "presentation_variant_blocked_by_canonical_success": (
            presentation_variant_blocked
        ),
        "current_duplicate_success_guard_would_block": presentation_success,
        "canonical_hash_guard_extension_would_block": presentation_variant_blocked,
        "blocker": blocker,
        "recommended_next_action": recommended_next_action,
        "enforced": False,
        "semantic_duplicate_claimed": False,
        "presentation_hash_lifecycle": presentation_lifecycle,
        "canonical_hash_lifecycle": canonical_lifecycle,
        "safety": _presentation_variant_duplicate_guard_safety_metadata(),
    }


async def record_digest_delivery_result(
    session: AsyncSession,
    *,
    delivery_intention_id: str,
    execution_attempt_id: str,
    result_status: str,
    attempted_chunk_count: int,
    delivered_chunk_count: int,
    failed_chunk_count: int,
    safe_message_refs: list[Mapping[str, Any]] | None = None,
    safe_error_code: str | None = None,
    safe_error_summary: str | None = None,
    delivery_invoked: bool = False,
    delivery_adapter_invoked: bool = False,
    actor: str = "system",
) -> dict[str, Any]:
    cleaned_delivery_intention_id = _clean_delivery_intention_id(delivery_intention_id)
    intention = await get_digest_delivery_intention(
        session,
        delivery_intention_id=cleaned_delivery_intention_id,
    )
    if intention is None:
        raise DeliveryResultConflictError("delivery intention was not found")

    try:
        telegram_plan = await get_digest_delivery_intention_telegram_plan(
            session,
            delivery_intention_id=cleaned_delivery_intention_id,
        )
    except DeliveryTelegramPlanConflictError as exc:
        raise DeliveryResultConflictError(str(exc)) from exc
    if telegram_plan is None:
        raise DeliveryResultConflictError("delivery intention was not found")

    payload = build_digest_delivery_result(
        intention=intention,
        telegram_plan=telegram_plan,
        execution_attempt_id=execution_attempt_id,
        result_status=result_status,
        attempted_chunk_count=attempted_chunk_count,
        delivered_chunk_count=delivered_chunk_count,
        failed_chunk_count=failed_chunk_count,
        safe_message_refs=safe_message_refs,
        safe_error_code=safe_error_code,
        safe_error_summary=safe_error_summary,
        delivery_invoked=delivery_invoked,
        delivery_adapter_invoked=delivery_adapter_invoked,
    )
    delivery_result_id = _clean_delivery_result_id(
        str(payload.get("delivery_result_id", ""))
    )
    existing = await get_digest_delivery_result(
        session,
        delivery_result_id=delivery_result_id,
    )
    if existing is not None:
        stored_payload = {
            key: value
            for key, value in existing.items()
            if key not in {"audit_log", "recorded_at"}
        }
        if stored_payload != payload:
            raise DeliveryResultConflictError(
                "existing delivery result payload does not match expected payload"
            )
        return existing

    record = AuditLog(
        event_type=DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
        actor=actor,
        correlation_id=cleaned_delivery_intention_id,
        trace_id=delivery_result_id,
        before_ref=cleaned_delivery_intention_id,
        after_ref=delivery_result_id,
        approval_id=f"{cleaned_delivery_intention_id}:delivery_result",
        payload=payload,
    )
    session.add(record)
    await session.flush()

    response = _delivery_result_audit_log_response(record)
    if response is None:
        raise ValueError("persisted delivery result audit payload is invalid")
    return response


def _append_unique_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def _telegram_execution_gate_result_contract_summary(
    *,
    intention: Mapping[str, Any],
    telegram_plan: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        build_digest_delivery_result(
            intention=intention,
            telegram_plan=telegram_plan,
            execution_attempt_id="execution-gate-preview",
            result_status="skipped",
            attempted_chunk_count=0,
            delivered_chunk_count=0,
            failed_chunk_count=0,
            delivery_invoked=False,
            delivery_adapter_invoked=False,
        )
    except (DeliveryResultConflictError, ValueError) as exc:
        raise DeliveryTelegramExecutionGateConflictError(
            f"delivery result contract is not ready: {exc}"
        ) from exc

    return {
        "status": DIGEST_DELIVERY_RESULT_STATUS,
        "event_type": DIGEST_DELIVERY_RESULT_RECORDED_EVENT_TYPE,
        "delivery_result_id_prefix": DIGEST_DELIVERY_RESULT_ID_PREFIX,
        "allowed_result_statuses": list(DIGEST_DELIVERY_RESULT_STATUSES),
        "result_audit_contract_ready": True,
        "delivery_result_record_created": False,
        "result_creation_endpoint_available": False,
        "db_write_scope": "none",
    }


async def get_digest_delivery_intention_telegram_execution_gate(
    session: AsyncSession,
    *,
    delivery_intention_id: str,
    telegram_bot_token: Any = None,
    telegram_chat_id: Any = None,
    max_chunks_allowed: int = DIGEST_DELIVERY_TELEGRAM_EXECUTION_GATE_MAX_CHUNKS,
) -> dict[str, Any] | None:
    """Return a no-send bounded Telegram execution gate for a stored intention.

    The gate composes existing stored approval/readiness, Telegram plan,
    credential-presence preflight, and result-contract metadata. It never sends,
    validates credentials with Telegram, creates delivery results, schedules,
    appends audit logs, or calls provider/delivery adapters.
    """

    cleaned_delivery_intention_id = _clean_delivery_intention_id(
        delivery_intention_id
    )
    safe_max_chunks_allowed = _require_int(
        max_chunks_allowed,
        field_name="max_chunks_allowed",
    )
    if safe_max_chunks_allowed < 1:
        raise ValueError("max_chunks_allowed must be at least 1")

    try:
        preflight = await get_digest_delivery_intention_telegram_execution_preflight(
            session,
            delivery_intention_id=cleaned_delivery_intention_id,
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id,
        )
    except DeliveryTelegramExecutionPreflightConflictError as exc:
        raise DeliveryTelegramExecutionGateConflictError(str(exc)) from exc
    if preflight is None:
        return None

    intention = await get_digest_delivery_intention(
        session,
        delivery_intention_id=cleaned_delivery_intention_id,
    )
    if intention is None:
        return None

    delivery_draft_id = _clean_delivery_draft_id(
        str(preflight.get("delivery_draft_id", ""))
    )
    approval_status = await get_digest_delivery_draft_approval_status(
        session,
        delivery_draft_id=delivery_draft_id,
    )
    if approval_status is None:
        raise DeliveryTelegramExecutionGateConflictError(
            "approval status was not found"
        )

    readiness = await get_digest_delivery_draft_delivery_readiness(
        session,
        delivery_draft_id=delivery_draft_id,
    )
    if readiness is None:
        raise DeliveryTelegramExecutionGateConflictError(
            "delivery readiness was not found"
        )

    try:
        telegram_plan = await get_digest_delivery_intention_telegram_plan(
            session,
            delivery_intention_id=cleaned_delivery_intention_id,
        )
    except DeliveryTelegramPlanConflictError as exc:
        raise DeliveryTelegramExecutionGateConflictError(str(exc)) from exc
    if telegram_plan is None:
        return None

    planned_chunk_count = _require_non_negative_int(
        telegram_plan.get("chunk_count"),
        field_name="planned_chunk_count",
    )
    within_chunk_bounds = planned_chunk_count <= safe_max_chunks_allowed
    result_contract = _telegram_execution_gate_result_contract_summary(
        intention=intention,
        telegram_plan=telegram_plan,
    )

    approval_ready = (
        approval_status.get("current_decision")
        == DIGEST_DELIVERY_DRAFT_APPROVED_DECISION
    )
    readiness_ready = bool(readiness.get("eligible_for_delivery"))
    telegram_plan_ready = (
        telegram_plan.get("status") == DIGEST_DELIVERY_TELEGRAM_PLAN_STATUS
        and bool(preflight.get("telegram_plan_ready"))
    )
    credential_presence_ready = bool(preflight.get("credential_presence_ready"))
    result_audit_contract_ready = bool(
        result_contract.get("result_audit_contract_ready")
    )

    blockers: list[str] = []
    for blocker in preflight.get("blockers", []):
        if isinstance(blocker, str) and blocker:
            _append_unique_blocker(blockers, blocker)
    if not approval_ready:
        _append_unique_blocker(blockers, "not_approved")
    if not readiness_ready:
        _append_unique_blocker(blockers, "not_ready")
    if not telegram_plan_ready:
        _append_unique_blocker(blockers, "telegram_plan_not_ready")
    if not result_audit_contract_ready:
        _append_unique_blocker(blockers, "delivery_result_contract_not_ready")
    if not within_chunk_bounds:
        _append_unique_blocker(blockers, "planned_chunk_count_exceeds_max_chunks")
    _append_unique_blocker(blockers, "delivery_execution_not_implemented")
    _append_unique_blocker(blockers, "bounded_operator_request_required")

    return {
        "status": DIGEST_DELIVERY_TELEGRAM_EXECUTION_GATE_STATUS,
        "delivery_intention_id": cleaned_delivery_intention_id,
        "delivery_draft_id": delivery_draft_id,
        "digest_type": telegram_plan.get("digest_type"),
        "channel": DIGEST_DELIVERY_DRAFT_CHANNEL,
        "text_sha256": telegram_plan.get("text_sha256"),
        "char_count": telegram_plan.get("char_count"),
        "chunk_count": telegram_plan.get("chunk_count"),
        "approval_ready": approval_ready,
        "readiness_ready": readiness_ready,
        "telegram_plan_ready": telegram_plan_ready,
        "credential_presence_ready": credential_presence_ready,
        "result_audit_contract_ready": result_audit_contract_ready,
        "bounded_operator_request_required": True,
        "required_operator_fields": list(
            DIGEST_DELIVERY_TELEGRAM_EXECUTION_GATE_REQUIRED_OPERATOR_FIELDS
        ),
        "max_chunks_allowed": safe_max_chunks_allowed,
        "planned_chunk_count": planned_chunk_count,
        "within_chunk_bounds": within_chunk_bounds,
        "execution_gate_ready": False,
        "blockers": blockers,
        "warnings": [
            "future_bounded_operator_path_required",
            "approval_does_not_trigger_delivery",
        ],
        "delivery_execution_enabled": False,
        "delivery_enabled": False,
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "sent": False,
        "intention": {
            "status": intention.get("status"),
            "persisted": bool(intention.get("persisted")),
            "current_decision": intention.get("current_decision"),
            "eligible_for_delivery": bool(intention.get("eligible_for_delivery")),
            "audit_log": _safe_intention_audit_log_metadata(intention),
        },
        "approval": {
            "current_decision": approval_status.get("current_decision"),
            "approved": bool(approval_status.get("approved")),
            "rejected": bool(approval_status.get("rejected")),
        },
        "readiness": _readiness_summary(readiness),
        "telegram_plan": {
            "status": telegram_plan.get("status"),
            "chunk_count": telegram_plan.get("chunk_count"),
            "chunks_text_included": bool(telegram_plan.get("chunks_text_included")),
            "delivery_execution_enabled": False,
            "delivery_enabled": False,
            "delivery_invoked": False,
            "delivery_adapter_invoked": False,
            "scheduler_invoked": False,
            "sent": False,
        },
        "preflight": {
            "status": preflight.get("status"),
            "telegram_plan_ready": bool(preflight.get("telegram_plan_ready")),
            "telegram_bot_token_present": bool(
                preflight.get("telegram_bot_token_present")
            ),
            "telegram_chat_id_present": bool(
                preflight.get("telegram_chat_id_present")
            ),
            "credential_presence_ready": credential_presence_ready,
            "execution_preflight_ready": bool(
                preflight.get("execution_preflight_ready")
            ),
            "blockers": [
                blocker
                for blocker in preflight.get("blockers", [])
                if isinstance(blocker, str)
            ],
            "delivery_execution_enabled": False,
            "delivery_enabled": False,
            "delivery_invoked": False,
            "delivery_adapter_invoked": False,
            "scheduler_invoked": False,
            "sent": False,
        },
        "result_contract": result_contract,
        "source_of_truth": (
            dict(telegram_plan.get("source_of_truth"))
            if isinstance(telegram_plan.get("source_of_truth"), Mapping)
            else {}
        ),
        "safety": _telegram_execution_gate_safety_metadata(),
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
