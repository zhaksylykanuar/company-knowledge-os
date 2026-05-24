#!/usr/bin/env python
"""Seed one local synthetic persisted attention digest item."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONFIRM_LOCAL_SEED_PHRASE = "SEED LOCAL SYNTHETIC DIGEST"
SAMPLE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
PRODUCTION_ENV_NAMES = (
    "APP_ENV",
    "ENV",
    "ENVIRONMENT",
    "FOUNDEROS_ENV",
    "RAILS_ENV",
    "NODE_ENV",
)
PRODUCTION_ENV_PREFIXES = ("prod", "production", "stag", "staging")


class SeedInputError(ValueError):
    pass


class SeedBlockedError(RuntimeError):
    pass


class SeedConflictError(RuntimeError):
    pass


class SeedRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SeedQuery:
    sample_id: str
    created_at: datetime
    confirm_local_seed: str
    output_format: str = "json"


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SeedInputError(f"{field_name} must be a timezone-aware ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise SeedInputError(
            f"{field_name} must be a timezone-aware ISO datetime"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SeedInputError(f"{field_name} must be timezone-aware")
    return parsed


def _clean_sample_id(value: str) -> str:
    if not isinstance(value, str):
        raise SeedInputError("sample_id must be a non-empty string")
    cleaned = value.strip()
    if not cleaned:
        raise SeedInputError("sample_id must not be empty")
    if len(cleaned) > 80:
        raise SeedInputError("sample_id must be at most 80 characters")
    if SAMPLE_ID_RE.fullmatch(cleaned) is None:
        raise SeedInputError(
            "sample_id may contain only letters, numbers, dot, underscore, and dash"
        )
    return cleaned


def _clean_confirm(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SeedInputError("confirm_local_seed must not be empty")
    cleaned = value.strip()
    if cleaned != CONFIRM_LOCAL_SEED_PHRASE:
        raise SeedInputError("confirm_local_seed phrase did not match")
    return cleaned


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-id",
        required=True,
        help="Deterministic local synthetic sample id.",
    )
    parser.add_argument(
        "--created-at",
        required=True,
        help="Timezone-aware ISO datetime for the synthetic attention item.",
    )
    parser.add_argument(
        "--confirm-local-seed",
        required=True,
        help=f'Must be exactly "{CONFIRM_LOCAL_SEED_PHRASE}".',
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args(argv)


def _query_from_args(args: argparse.Namespace) -> SeedQuery:
    return SeedQuery(
        sample_id=_clean_sample_id(args.sample_id),
        created_at=_parse_datetime(args.created_at, field_name="created_at"),
        confirm_local_seed=_clean_confirm(args.confirm_local_seed),
        output_format=args.format,
    )


def _seed_key(*, sample_id: str, created_at: datetime) -> str:
    stable = json.dumps(
        {
            "sample_id": sample_id,
            "created_at": created_at.isoformat(),
            "scope": "fos_071_local_persisted_attention_seed",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(stable.encode("utf-8")).hexdigest()[:32]


def _window_for(created_at: datetime) -> tuple[datetime, datetime]:
    start_at = created_at.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_at, start_at + timedelta(days=1)


def _env_value_is_production_like(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().casefold()
    if not normalized:
        return False
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}-")
        for prefix in PRODUCTION_ENV_PREFIXES
    )


def _assert_local_environment(*, settings: Any, environ: Mapping[str, str]) -> None:
    if _env_value_is_production_like(getattr(settings, "app_env", None)):
        raise SeedBlockedError("refusing to seed in production-like environment")
    for name in PRODUCTION_ENV_NAMES:
        if _env_value_is_production_like(environ.get(name)):
            raise SeedBlockedError("refusing to seed in production-like environment")


def _expected_payloads(query: SeedQuery) -> dict[str, Any]:
    seed_key = _seed_key(sample_id=query.sample_id, created_at=query.created_at)
    short_key = seed_key[:16]
    source_object_id = f"local.synthetic.persisted_attention_seed:{query.sample_id}:{short_key}"
    event_id = f"evt_seed_{seed_key[:32]}"
    activity_item_id = f"nact_seed_{seed_key[:32]}"
    triage_result_id = f"atri_seed_{seed_key[:32]}"
    raw_object_ref = (
        f"local_synthetic_persisted_attention:{query.sample_id}:{short_key}"
    )

    source_payload = {
        "source_object_type": "system_event",
        "title": f"Local synthetic persisted attention seed {query.sample_id}",
        "summary": (
            "Synthetic local dev-only persisted attention digest seed; "
            "not a company fact."
        ),
        "actor_external_id": "local.synthetic.operator",
    }
    activity_payload = {
        "source": "internal",
        "source_object_id": source_object_id,
        "activity_type": "synthetic.persisted_attention_digest.seed",
        "title": f"Local synthetic digest seed {query.sample_id}",
        "actor": "local.synthetic.operator",
        "created_at": query.created_at,
        "project": "Synthetic Local Digest Seed",
        "safe_summary": (
            "Synthetic local dev-only activity created to exercise the persisted "
            "attention digest and Telegram delivery test path."
        ),
        "related_people": ["local.synthetic.operator"],
        "related_jira_keys": [],
        "related_prs": [],
        "related_files": [],
        "evidence_refs": [
            {
                "kind": "source_event",
                "source_event_id": None,
                "source_system": "internal",
                "source_object_type": "system_event",
                "source_object_id": source_object_id,
                "event_type": "internal.system_event.recorded",
            }
        ],
    }
    attention_payload = {
        "attention_class": "requires_my_attention",
        "priority": "high",
        "show_in_digest": True,
        "confidence": 0.99,
        "reason": (
            "synthetic local dev-only digest seed for first bounded Telegram test"
        ),
        "recommended_action": (
            "Review this synthetic local digest seed through the normal "
            "delivery draft and approval flow."
        ),
        "owner": "local.synthetic.operator",
        "deadline": None,
        "evidence": [],
    }

    return {
        "seed_key": seed_key,
        "event_id": event_id,
        "idempotency_key": f"fos-071-local-seed:{query.sample_id}:{seed_key}",
        "source_object_id": source_object_id,
        "raw_object_ref": raw_object_ref,
        "activity_item_id": activity_item_id,
        "triage_result_id": triage_result_id,
        "source_payload": source_payload,
        "activity_payload": activity_payload,
        "attention_payload": attention_payload,
    }


def _model_json(value: Any) -> dict[str, Any]:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _stored_activity_json(value: Any) -> dict[str, Any]:
    activity = value.to_normalized_activity_item()
    return activity.model_dump(mode="json")


def _stored_attention_json(value: Any) -> dict[str, Any]:
    result = value.to_attention_triage_result()
    return result.model_dump(mode="json")


def _without_none_evidence_source_event(
    value: dict[str, Any],
    source_event_id: str,
) -> dict[str, Any]:
    copied = dict(value)
    refs = []
    for ref in copied.get("evidence_refs", []):
        safe_ref = dict(ref)
        if safe_ref.get("source_event_id") is None:
            safe_ref["source_event_id"] = source_event_id
        refs.append(safe_ref)
    copied["evidence_refs"] = refs
    return copied


def _assert_mapping_matches(
    *,
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    conflict_name: str,
) -> None:
    if dict(actual) != dict(expected):
        raise SeedConflictError(
            f"existing {conflict_name} metadata does not match expected synthetic seed"
        )


async def execute_seed(
    query: SeedQuery,
    *,
    session_factory: Callable[[], Any] | None = None,
    settings_override: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    from app.core.config import settings
    from app.db.attention_models import AttentionTriageResultRecord
    from app.db.base import AsyncSessionLocal
    from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
    from app.db.models import IngestedEvent
    from app.services.attention_results import (
        get_attention_triage_result,
        record_attention_triage_result,
    )
    from app.services.attention_triage import AttentionTriageResult, NormalizedActivityItem
    from app.services.digest import build_persisted_attention_digest_read_model
    from app.services.normalized_activity import (
        get_normalized_activity_item,
        record_normalized_activity_item,
    )
    from app.services.source_events import normalize_ingested_event_to_source_event

    _clean_sample_id(query.sample_id)
    _parse_datetime(query.created_at.isoformat(), field_name="created_at")
    _clean_confirm(query.confirm_local_seed)
    _assert_local_environment(
        settings=settings_override or settings,
        environ=environ if environ is not None else os.environ,
    )

    session_factory = session_factory or AsyncSessionLocal
    expected = _expected_payloads(query)
    window_start, window_end = _window_for(query.created_at)
    created = {
        "ingested_event": False,
        "source_event": False,
        "normalized_activity_item": False,
        "attention_triage_result": False,
    }

    try:
        async with session_factory() as session:
            existing_ingested = await session.scalar(
                select(IngestedEvent).where(
                    IngestedEvent.event_id == expected["event_id"]
                )
            )
            if existing_ingested is None:
                ingested_event = IngestedEvent(
                    event_id=expected["event_id"],
                    event_type="internal.system_event.recorded",
                    source_system="internal",
                    source_object_id=expected["source_object_id"],
                    idempotency_key=expected["idempotency_key"],
                    correlation_id=f"corr_{expected['event_id']}",
                    trace_id=f"trace_{expected['event_id']}",
                    raw_object_ref=expected["raw_object_ref"],
                    payload=dict(expected["source_payload"]),
                    status="received",
                )
                session.add(ingested_event)
                await session.flush()
                created["ingested_event"] = True
            else:
                ingested_event = existing_ingested
                _assert_mapping_matches(
                    actual={
                        "event_type": ingested_event.event_type,
                        "source_system": ingested_event.source_system,
                        "source_object_id": ingested_event.source_object_id,
                        "idempotency_key": ingested_event.idempotency_key,
                        "raw_object_ref": ingested_event.raw_object_ref,
                        "payload": ingested_event.payload,
                        "status": ingested_event.status,
                    },
                    expected={
                        "event_type": "internal.system_event.recorded",
                        "source_system": "internal",
                        "source_object_id": expected["source_object_id"],
                        "idempotency_key": expected["idempotency_key"],
                        "raw_object_ref": expected["raw_object_ref"],
                        "payload": expected["source_payload"],
                        "status": "received",
                    },
                    conflict_name="ingested event",
                )

            source_event_before = await session.scalar(
                select(SourceEvent).where(
                    SourceEvent.ingested_event_id == ingested_event.event_id
                )
            )
            source_event = await normalize_ingested_event_to_source_event(
                session,
                ingested_event,
            )
            created["source_event"] = source_event_before is None
            if (
                source_event.source_system != "internal"
                or source_event.source_object_type != "system_event"
                or source_event.source_object_id != expected["source_object_id"]
                or source_event.event_type != "internal.system_event.recorded"
                or source_event.title != expected["source_payload"]["title"]
                or source_event.summary != expected["source_payload"]["summary"]
                or source_event.raw_object_ref != expected["raw_object_ref"]
            ):
                raise SeedConflictError(
                    "existing source event metadata does not match expected synthetic seed"
                )

            activity_payload = _without_none_evidence_source_event(
                expected["activity_payload"],
                source_event.source_event_id,
            )
            existing_activity = await get_normalized_activity_item(
                session,
                activity_item_id=expected["activity_item_id"],
            )
            if existing_activity is None:
                activity = await record_normalized_activity_item(
                    session,
                    activity_item_id=expected["activity_item_id"],
                    source_event_id=source_event.source_event_id,
                    activity=NormalizedActivityItem.model_validate(activity_payload),
                )
                created["normalized_activity_item"] = True
            else:
                activity = existing_activity
                if activity.source_event_id != source_event.source_event_id:
                    raise SeedConflictError(
                        "existing normalized activity source_event_id does not match expected synthetic seed"
                    )
                _assert_mapping_matches(
                    actual=_stored_activity_json(activity),
                    expected=_model_json(
                        NormalizedActivityItem.model_validate(activity_payload)
                    ),
                    conflict_name="normalized activity item",
                )

            attention_payload = dict(expected["attention_payload"])
            attention_payload["evidence"] = list(activity.evidence_refs)
            existing_attention = await get_attention_triage_result(
                session,
                triage_result_id=expected["triage_result_id"],
            )
            if existing_attention is None:
                attention = await record_attention_triage_result(
                    session,
                    triage_result_id=expected["triage_result_id"],
                    source="internal",
                    source_object_id=expected["source_object_id"],
                    activity_item_id=activity.activity_item_id,
                    result=AttentionTriageResult.model_validate(attention_payload),
                    created_at=query.created_at,
                )
                created["attention_triage_result"] = True
            else:
                attention = existing_attention
                if (
                    attention.source != "internal"
                    or attention.source_object_id != expected["source_object_id"]
                    or attention.activity_item_id != activity.activity_item_id
                    or attention.created_at != query.created_at
                ):
                    raise SeedConflictError(
                        "existing attention result metadata does not match expected synthetic seed"
                    )
                _assert_mapping_matches(
                    actual=_stored_attention_json(attention),
                    expected=_model_json(
                        AttentionTriageResult.model_validate(attention_payload)
                    ),
                    conflict_name="attention triage result",
                )

            digest = await build_persisted_attention_digest_read_model(
                session,
                start_at=window_start,
                end_at=window_end,
                limit_per_section=20,
            )
            await session.commit()

            row_counts = {
                "ingested_events": 1
                if await session.scalar(
                    select(IngestedEvent).where(
                        IngestedEvent.event_id == ingested_event.event_id
                    )
                )
                is not None
                else 0,
                "source_events": 1
                if await session.scalar(
                    select(SourceEvent).where(
                        SourceEvent.source_event_id == source_event.source_event_id
                    )
                )
                is not None
                else 0,
                "normalized_activity_items": 1
                if await session.scalar(
                    select(NormalizedActivityItemRecord).where(
                        NormalizedActivityItemRecord.activity_item_id
                        == activity.activity_item_id
                    )
                )
                is not None
                else 0,
                "attention_triage_results": 1
                if await session.scalar(
                    select(AttentionTriageResultRecord).where(
                        AttentionTriageResultRecord.triage_result_id
                        == attention.triage_result_id
                    )
                )
                is not None
                else 0,
            }
    except (SeedBlockedError, SeedConflictError, SeedInputError):
        raise
    except Exception as exc:
        raise SeedRuntimeError(
            "local synthetic persisted attention seed blocked; database, schema, or configuration is unavailable"
        ) from exc

    any_created = any(created.values())
    return {
        "status": "local_persisted_attention_seed",
        "seeded": any_created,
        "idempotent": not any_created,
        "sample_id": query.sample_id,
        "created_at": query.created_at.isoformat(),
        "window": {
            "start_at": window_start.isoformat(),
            "end_at": window_end.isoformat(),
        },
        "ids": {
            "ingested_event_id": ingested_event.event_id,
            "source_event_id": source_event.source_event_id,
            "normalized_activity_item_id": activity.activity_item_id,
            "attention_triage_result_id": attention.triage_result_id,
        },
        "created": created,
        "row_counts": row_counts,
        "digest_preview": {
            "counts": digest.get("counts", {}),
            "hidden_low_priority_summary": digest.get(
                "hidden_low_priority_summary",
                {},
            ),
            "metadata": digest.get("metadata", {}),
        },
        "next_steps": {
            "persisted_attention_preview_path": "/v1/digest/persisted-attention",
            "delivery_draft_create_path": "/v1/digest/persisted-attention/delivery-draft",
            "delivery_flow": (
                "preview digest, create delivery draft, approve, check readiness, "
                "create delivery intention, review, check gate, then run bounded test send"
            ),
        },
        "safety": {
            "synthetic": True,
            "local_dev_only": True,
            "provider_free": True,
            "live_api_calls": False,
            "connectors_invoked": False,
            "openai_invoked": False,
            "telegram_invoked": False,
            "slack_invoked": False,
            "delivery_draft_created": False,
            "delivery_intention_created": False,
            "delivery_result_created": False,
            "delivery_invoked": False,
            "scheduler_invoked": False,
            "raw_storage_touched": False,
            "obsidian_touched": False,
            "credential_values_exposed": False,
        },
    }


def _blocked_result(*, error_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "error_code": error_code,
        "message": message,
        "safety": {
            "synthetic": True,
            "provider_free": True,
            "live_api_calls": False,
            "telegram_invoked": False,
            "delivery_invoked": False,
            "scheduler_invoked": False,
            "credential_values_exposed": False,
        },
    }


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def format_text_seed(result: Mapping[str, Any]) -> str:
    if result.get("status") == "blocked":
        return f"Local synthetic persisted attention seed blocked: {result.get('message')}\n"
    ids = result.get("ids") if isinstance(result.get("ids"), Mapping) else {}
    window = result.get("window") if isinstance(result.get("window"), Mapping) else {}
    counts = {}
    digest_preview = result.get("digest_preview")
    if isinstance(digest_preview, Mapping) and isinstance(
        digest_preview.get("counts"),
        Mapping,
    ):
        counts = digest_preview["counts"]
    lines = [
        "Local synthetic persisted attention seed",
        f"Sample ID: {result.get('sample_id')}",
        f"Created at: {result.get('created_at')}",
        f"Seeded new rows: {result.get('seeded')}",
        f"Idempotent existing rows: {result.get('idempotent')}",
        f"Preview start: {window.get('start_at')}",
        f"Preview end: {window.get('end_at')}",
        f"Ingested event ID: {ids.get('ingested_event_id')}",
        f"Source event ID: {ids.get('source_event_id')}",
        f"Normalized activity item ID: {ids.get('normalized_activity_item_id')}",
        f"Attention triage result ID: {ids.get('attention_triage_result_id')}",
        f"Digest total: {counts.get('total')}",
        f"Digest visible: {counts.get('visible')}",
        f"Digest shown: {counts.get('shown')}",
        "Synthetic only: True",
        "Delivery invoked: False",
        "Telegram invoked: False",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        query = _query_from_args(args)
        result = asyncio.run(execute_seed(query))
    except SeedInputError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="input_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except SeedBlockedError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="seed_blocked", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SeedConflictError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="seed_conflict", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SeedRuntimeError as exc:
        output_format = getattr(locals().get("args", None), "format", "json")
        if output_format == "json":
            _print_json(_blocked_result(error_code="runtime_error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    if query.output_format == "json":
        _print_json(result)
    else:
        print(format_text_seed(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
