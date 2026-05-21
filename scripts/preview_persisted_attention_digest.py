#!/usr/bin/env python
"""Preview stored persisted attention digest text for an explicit window."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_LIMIT = 20
MAX_LIMIT = 50

SAFE_ITEM_KEYS = (
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

SAFE_EVIDENCE_KEYS = (
    "kind",
    "source_event_id",
    "event_id",
    "source_system",
    "source_object_type",
    "source_object_id",
    "event_type",
    "raw_object_ref",
    "source_document_id",
    "chunk_id",
    "message_id",
)


class PreviewInputError(ValueError):
    pass


class PreviewRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreviewQuery:
    start_at: datetime
    end_at: datetime
    limit: int
    output_format: str
    debug_evidence: bool


Builder = Callable[..., Awaitable[dict[str, Any]]]


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PreviewInputError(f"{field_name} must be an ISO datetime") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PreviewInputError(f"{field_name} must be timezone-aware")
    return parsed


def _validated_limit(value: int) -> int:
    if value < 1 or value > MAX_LIMIT:
        raise PreviewInputError(f"limit must be between 1 and {MAX_LIMIT}")
    return value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-at", required=True, help="Timezone-aware ISO start.")
    parser.add_argument("--end-at", required=True, help="Timezone-aware ISO end.")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Maximum visible items per section, 1-{MAX_LIMIT}.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--debug-evidence",
        action="store_true",
        help="Include safe-formatted debug evidence refs.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> PreviewQuery:
    start_at = _parse_datetime(args.start_at, field_name="start_at")
    end_at = _parse_datetime(args.end_at, field_name="end_at")
    if end_at <= start_at:
        raise PreviewInputError("end_at must be after start_at")

    return PreviewQuery(
        start_at=start_at,
        end_at=end_at,
        limit=_validated_limit(args.limit),
        output_format=args.format,
        debug_evidence=bool(args.debug_evidence),
    )


def _safe_evidence_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    safe_refs: list[dict[str, Any]] = []
    for ref in value:
        if not isinstance(ref, Mapping):
            continue
        safe_ref = {key: ref[key] for key in SAFE_EVIDENCE_KEYS if ref.get(key) is not None}
        if safe_ref:
            safe_refs.append(safe_ref)
    return safe_refs


def _safe_item(value: Any, *, debug_evidence: bool) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None

    item = {key: value[key] for key in SAFE_ITEM_KEYS if key in value}
    if debug_evidence:
        item["evidence_refs"] = _safe_evidence_refs(value.get("evidence_refs"))
        item["activity_evidence_refs"] = _safe_evidence_refs(
            value.get("activity_evidence_refs")
        )
    return item


def sanitize_persisted_attention_digest(
    digest: Mapping[str, Any],
    *,
    debug_evidence: bool,
) -> dict[str, Any]:
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

    metadata = dict(digest.get("metadata", {})) if isinstance(digest.get("metadata"), Mapping) else {}
    metadata["debug_evidence"] = debug_evidence

    return {
        "section_title": digest.get("section_title", "Persisted attention digest"),
        "available": digest.get("available", True),
        "window": dict(digest.get("window", {})) if isinstance(digest.get("window"), Mapping) else {},
        "section_labels": dict(digest.get("section_labels", {}))
        if isinstance(digest.get("section_labels"), Mapping)
        else {},
        "counts": dict(digest.get("counts", {})) if isinstance(digest.get("counts"), Mapping) else {},
        "groups": groups,
        "hidden_low_priority_summary": safe_hidden_summary,
        "data_quality_notes": list(digest.get("data_quality_notes", []))
        if isinstance(digest.get("data_quality_notes"), list)
        else [],
        "metadata": metadata,
    }


async def build_preview(
    query: PreviewQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    builder: Builder | None = None,
) -> dict[str, Any]:
    from app.db.base import AsyncSessionLocal
    from app.services.digest import build_persisted_attention_digest_read_model
    from app.services.digest_rendering import render_persisted_attention_digest_text

    session_factory = session_factory or AsyncSessionLocal
    builder = builder or build_persisted_attention_digest_read_model

    try:
        async with session_factory() as session:
            digest = await builder(
                session,
                start_at=query.start_at,
                end_at=query.end_at,
                limit_per_section=query.limit,
            )
    except ValueError:
        raise
    except Exception as exc:
        raise PreviewRuntimeError(
            "persisted attention digest preview blocked; database, schema, or configuration is unavailable"
        ) from exc

    safe_digest = sanitize_persisted_attention_digest(
        digest,
        debug_evidence=query.debug_evidence,
    )
    rendered_text = render_persisted_attention_digest_text(
        safe_digest,
        debug_evidence=query.debug_evidence,
    )

    return {
        "status": "completed",
        "query": {
            "start_at": query.start_at.isoformat(),
            "end_at": query.end_at.isoformat(),
            "limit": query.limit,
            "debug_evidence": query.debug_evidence,
        },
        "digest": safe_digest,
        "rendered_text": rendered_text,
        "safety": {
            "provider_free": True,
            "read_only": True,
            "delivery": False,
        },
    }


def _blocked_result(error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        query = _query_from_args(args)
    except PreviewInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        preview = asyncio.run(build_preview(query))
    except ValueError as exc:
        message = str(exc) or "invalid persisted attention digest preview window"
        if query.output_format == "json":
            _print_json(_blocked_result("invalid_window", message))
        else:
            print(f"error: {message}", file=sys.stderr)
        return 2
    except PreviewRuntimeError as exc:
        message = str(exc)
        if query.output_format == "json":
            _print_json(_blocked_result("preview_blocked", message))
        else:
            print(f"error: {message}", file=sys.stderr)
        return 1

    if query.output_format == "json":
        _print_json(preview)
    else:
        print(preview["rendered_text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
