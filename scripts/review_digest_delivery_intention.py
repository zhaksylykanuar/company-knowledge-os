#!/usr/bin/env python
"""Review a stored digest delivery intention chain without sending."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class ReviewInputError(ValueError):
    pass


class ReviewNotFoundError(RuntimeError):
    pass


class ReviewRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReviewQuery:
    delivery_intention_id: str
    output_format: str = "text"
    include_rendered_text: bool = False


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delivery-intention-id",
        required=True,
        help="Stored delivery intention id to review.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--include-rendered-text",
        action="store_true",
        help="Include stored sanitized draft text in the review output.",
    )
    return parser.parse_args(argv)


def _clean_delivery_intention_id(value: str) -> str:
    if not isinstance(value, str):
        raise ReviewInputError("delivery_intention_id must be a non-empty string")

    cleaned = value.strip()
    if not cleaned:
        raise ReviewInputError("delivery_intention_id must not be empty")
    return cleaned


def _query_from_args(args: argparse.Namespace) -> ReviewQuery:
    return ReviewQuery(
        delivery_intention_id=_clean_delivery_intention_id(
            args.delivery_intention_id
        ),
        output_format=args.format,
        include_rendered_text=bool(args.include_rendered_text),
    )


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_keys(value: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value[key] for key in keys if value.get(key) is not None}


def _safe_chunk_metadata(value: Any) -> dict[str, Any]:
    metadata = _safe_mapping(value)
    safe: dict[str, Any] = {}
    if isinstance(metadata.get("chunk_size"), int):
        safe["chunk_size"] = metadata["chunk_size"]
    if isinstance(metadata.get("chunk_lengths"), list):
        safe["chunk_lengths"] = [
            length for length in metadata["chunk_lengths"] if isinstance(length, int)
        ]
    if isinstance(metadata.get("chunks_preview_included"), bool):
        safe["chunks_preview_included"] = metadata["chunks_preview_included"]
    return safe


def _safe_source_of_truth(value: Any) -> dict[str, Any]:
    source_of_truth = _safe_mapping(value)
    safe = _safe_keys(
        source_of_truth,
        (
            "source",
            "raw_storage_authoritative",
            "postgres_authoritative",
            "draft_is_source_of_truth",
            "intention_is_source_of_truth",
            "telegram_plan_is_source_of_truth",
            "review_bundle_is_source_of_truth",
            "telegram_is_source_of_truth",
            "digest_source_model",
            "digest_enrichment_model",
        ),
    )
    derived_from = source_of_truth.get("derived_from")
    if isinstance(derived_from, list):
        safe["derived_from"] = [str(item) for item in derived_from]
    return safe


def _safe_decision_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    history: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            continue
        safe_entry = _safe_keys(
            entry,
            (
                "event_type",
                "decision",
                "reviewer",
                "draft_text_sha256",
                "created_at",
                "note",
            ),
        )
        audit_log = entry.get("audit_log")
        if isinstance(audit_log, Mapping):
            safe_entry["audit_log"] = _safe_keys(
                audit_log,
                ("event_type", "after_ref"),
            )
        safety = entry.get("safety")
        if isinstance(safety, Mapping):
            safe_entry["safety"] = _safe_keys(
                safety,
                (
                    "provider_free",
                    "delivery_invoked",
                    "approval_execution_invoked",
                    "scheduler_invoked",
                    "connectors_invoked",
                    "live_api_calls",
                    "db_write_scope",
                    "draft_is_source_of_truth",
                    "telegram_is_source_of_truth",
                ),
            )
        history.append(safe_entry)
    return history


def _safe_approval_status(value: Mapping[str, Any]) -> dict[str, Any]:
    safe = _safe_keys(
        value,
        (
            "delivery_draft_id",
            "draft_exists",
            "current_decision",
            "approved",
            "rejected",
            "delivery_enabled",
            "sent",
            "delivery_invoked",
            "approval_execution_invoked",
        ),
    )
    safe["decision_history"] = _safe_decision_history(value.get("decision_history"))
    draft = value.get("draft")
    if isinstance(draft, Mapping):
        safe["draft"] = _safe_keys(
            draft,
            (
                "digest_type",
                "channel",
                "status",
                "start_at",
                "end_at",
                "limit",
                "debug_evidence",
                "text_sha256",
                "char_count",
                "chunk_count",
            ),
        )
        safe["draft"]["source_of_truth"] = _safe_source_of_truth(
            draft.get("source_of_truth")
        )
    safe["safety"] = _safe_mapping(value.get("safety"))
    return safe


def _safe_readiness(value: Mapping[str, Any]) -> dict[str, Any]:
    safe = _safe_keys(
        value,
        (
            "delivery_draft_id",
            "draft_exists",
            "status",
            "digest_type",
            "channel",
            "current_decision",
            "approved",
            "rejected",
            "eligible_for_delivery",
            "delivery_execution_enabled",
            "delivery_enabled",
            "delivery_invoked",
            "approval_execution_invoked",
            "sent",
            "text_sha256",
            "char_count",
            "chunk_count",
            "start_at",
            "end_at",
            "limit",
            "debug_evidence",
        ),
    )
    reasons = value.get("ineligible_reasons")
    safe["ineligible_reasons"] = list(reasons) if isinstance(reasons, list) else []
    safe["chunk_metadata"] = _safe_chunk_metadata(value.get("chunk_metadata"))
    safe["decision_history"] = _safe_decision_history(value.get("decision_history"))
    safe["source_of_truth"] = _safe_source_of_truth(value.get("source_of_truth"))
    safe["safety"] = _safe_mapping(value.get("safety"))
    return safe


def _safe_intention(value: Mapping[str, Any]) -> dict[str, Any]:
    safe = _safe_keys(
        value,
        (
            "persisted",
            "status",
            "delivery_intention_id",
            "delivery_draft_id",
            "digest_type",
            "channel",
            "current_decision",
            "eligible_for_delivery",
            "delivery_execution_enabled",
            "delivery_enabled",
            "delivery_invoked",
            "approval_execution_invoked",
            "sent",
            "scheduler_invoked",
            "text_sha256",
            "char_count",
            "chunk_count",
            "start_at",
            "end_at",
            "limit",
            "debug_evidence",
        ),
    )
    safe["chunk_metadata"] = _safe_chunk_metadata(value.get("chunk_metadata"))
    safe["readiness"] = _safe_mapping(value.get("readiness"))
    safe["source_of_truth"] = _safe_source_of_truth(value.get("source_of_truth"))
    safe["safety"] = _safe_mapping(value.get("safety"))
    audit_log = value.get("audit_log")
    if isinstance(audit_log, Mapping):
        safe["audit_log"] = _safe_keys(
            audit_log,
            ("event_type", "before_ref", "after_ref", "created_at"),
        )
    return safe


def _safe_telegram_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    safe = _safe_keys(
        value,
        (
            "status",
            "delivery_intention_id",
            "delivery_draft_id",
            "digest_type",
            "channel",
            "text_sha256",
            "char_count",
            "chunk_count",
            "chunks_text_included",
            "delivery_execution_enabled",
            "delivery_enabled",
            "delivery_invoked",
            "delivery_adapter_invoked",
            "approval_execution_invoked",
            "scheduler_invoked",
            "sent",
            "start_at",
            "end_at",
            "limit",
            "debug_evidence",
        ),
    )
    safe_chunks: list[dict[str, Any]] = []
    chunks = value.get("chunks")
    if isinstance(chunks, list):
        for chunk in chunks:
            if isinstance(chunk, Mapping):
                safe_chunks.append(
                    _safe_keys(chunk, ("index", "char_count", "sha256"))
                )
    safe["chunks"] = safe_chunks
    safe["chunk_metadata"] = _safe_chunk_metadata(value.get("chunk_metadata"))
    intention = value.get("intention")
    if isinstance(intention, Mapping):
        safe["intention"] = _safe_keys(intention, ("status", "persisted"))
        audit_log = intention.get("audit_log")
        if isinstance(audit_log, Mapping):
            safe["intention"]["audit_log"] = _safe_keys(
                audit_log,
                ("event_type", "before_ref", "after_ref", "created_at"),
            )
    safe["source_of_truth"] = _safe_source_of_truth(value.get("source_of_truth"))
    safe["safety"] = _safe_mapping(value.get("safety"))
    return safe


def _review_safety_metadata() -> dict[str, Any]:
    return {
        "provider_free": True,
        "read_only": True,
        "db_write_scope": "none",
        "delivery_invoked": False,
        "delivery_adapter_invoked": False,
        "approval_execution_invoked": False,
        "scheduler_invoked": False,
        "delivery_result_audit_event_created": False,
        "outbox_record_created": False,
        "connectors_invoked": False,
        "live_api_calls": False,
        "api_clients_invoked": False,
        "sent": False,
        "draft_is_source_of_truth": False,
        "intention_is_source_of_truth": False,
        "telegram_plan_is_source_of_truth": False,
        "review_bundle_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
    }


async def build_review(
    query: ReviewQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    from app.db.base import AsyncSessionLocal
    from app.services.digest_delivery_drafts import (
        DeliveryTelegramPlanConflictError,
        get_digest_delivery_draft_approval_status,
        get_digest_delivery_draft_delivery_readiness,
        get_digest_delivery_intention,
        get_digest_delivery_intention_telegram_plan,
        get_persisted_digest_delivery_draft,
    )

    delivery_intention_id = _clean_delivery_intention_id(
        query.delivery_intention_id
    )
    session_factory = session_factory or AsyncSessionLocal

    try:
        async with session_factory() as session:
            intention = await get_digest_delivery_intention(
                session,
                delivery_intention_id=delivery_intention_id,
            )
            if intention is None:
                raise ReviewNotFoundError("delivery intention was not found")

            delivery_draft_id = str(intention.get("delivery_draft_id", "")).strip()
            if not delivery_draft_id:
                raise ReviewRuntimeError(
                    "stored delivery intention is missing a delivery_draft_id"
                )

            draft = await get_persisted_digest_delivery_draft(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if draft is None:
                raise ReviewRuntimeError("referenced delivery draft was not found")

            approval_status = await get_digest_delivery_draft_approval_status(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if approval_status is None:
                raise ReviewRuntimeError("approval status was not found")

            readiness = await get_digest_delivery_draft_delivery_readiness(
                session,
                delivery_draft_id=delivery_draft_id,
            )
            if readiness is None:
                raise ReviewRuntimeError("delivery readiness was not found")

            telegram_plan = await get_digest_delivery_intention_telegram_plan(
                session,
                delivery_intention_id=delivery_intention_id,
            )
            if telegram_plan is None:
                raise ReviewNotFoundError("delivery intention was not found")
    except (ReviewInputError, ReviewNotFoundError, ReviewRuntimeError):
        raise
    except DeliveryTelegramPlanConflictError as exc:
        raise ReviewRuntimeError(str(exc)) from exc
    except ValueError as exc:
        raise ReviewRuntimeError(str(exc)) from exc
    except Exception as exc:
        raise ReviewRuntimeError(
            "delivery intention review blocked; database, schema, or configuration is unavailable"
        ) from exc

    rendered_text = draft.get("rendered_text")
    if query.include_rendered_text and not isinstance(rendered_text, str):
        raise ReviewRuntimeError("stored rendered draft text is unavailable")

    review = {
        "status": "delivery_intention_review",
        "delivery_intention_id": delivery_intention_id,
        "delivery_draft_id": delivery_draft_id,
        "digest_type": intention.get("digest_type"),
        "channel": intention.get("channel"),
        "text_sha256": intention.get("text_sha256"),
        "char_count": intention.get("char_count"),
        "chunk_count": intention.get("chunk_count"),
        "stored_digest_text_included": bool(query.include_rendered_text),
        "delivery_intention": _safe_intention(intention),
        "approval_status": _safe_approval_status(approval_status),
        "readiness": _safe_readiness(readiness),
        "telegram_plan": _safe_telegram_plan(telegram_plan),
        "source_of_truth": _safe_source_of_truth(intention.get("source_of_truth")),
        "safety": _review_safety_metadata(),
    }
    if query.include_rendered_text:
        review["rendered_text"] = rendered_text
    return review


def format_text_review(review: Mapping[str, Any]) -> str:
    approval_status = _safe_mapping(review.get("approval_status"))
    readiness = _safe_mapping(review.get("readiness"))
    telegram_plan = _safe_mapping(review.get("telegram_plan"))
    safety = _safe_mapping(review.get("safety"))

    lines = [
        "Delivery intention review (review-only; no send)",
        f"Delivery intention ID: {review.get('delivery_intention_id')}",
        f"Delivery draft ID: {review.get('delivery_draft_id')}",
        f"Digest type: {review.get('digest_type')}",
        f"Channel: {review.get('channel')}",
        f"Text SHA-256: {review.get('text_sha256')}",
        f"Characters: {review.get('char_count')}",
        f"Telegram chunks: {review.get('chunk_count')}",
        f"Current decision: {approval_status.get('current_decision')}",
        f"Eligible for delivery: {readiness.get('eligible_for_delivery')}",
        f"Ineligible reasons: {readiness.get('ineligible_reasons', [])}",
        f"Delivery execution enabled: {readiness.get('delivery_execution_enabled')}",
        f"Delivery invoked: {safety.get('delivery_invoked')}",
        f"Delivery adapter invoked: {safety.get('delivery_adapter_invoked')}",
        f"Scheduler invoked: {safety.get('scheduler_invoked')}",
        f"Sent: {safety.get('sent')}",
        f"Chunk text included: {telegram_plan.get('chunks_text_included')}",
        f"Stored rendered digest text included: {review.get('stored_digest_text_included')}",
    ]
    if isinstance(review.get("rendered_text"), str):
        lines.extend(["", "Stored rendered digest text:", review["rendered_text"]])
    return "\n".join(lines) + "\n"


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": _review_safety_metadata(),
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        review = asyncio.run(build_review(query))
    except ReviewInputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ReviewNotFoundError as exc:
        output_format = getattr(locals().get("args", None), "format", "text")
        if output_format == "json":
            _print_json(_blocked_result(error_code="not_found", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ReviewRuntimeError as exc:
        output_format = getattr(locals().get("args", None), "format", "text")
        if output_format == "json":
            _print_json(_blocked_result(error_code="review_blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    if query.output_format == "json":
        _print_json(review)
    else:
        print(format_text_review(review), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
