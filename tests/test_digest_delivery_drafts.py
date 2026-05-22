from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

import pytest

import app.services.telegram_delivery as telegram_delivery
from app.services.digest_delivery_drafts import (
    build_persisted_attention_digest_delivery_draft,
    build_persisted_attention_digest_delivery_draft_from_db,
    sanitize_persisted_attention_digest_for_delivery_draft,
)
from app.services.digest_rendering import render_persisted_attention_digest_text


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _persisted_attention_digest() -> dict[str, Any]:
    return {
        "section_title": "Persisted attention digest",
        "available": True,
        "window": {
            "start_at": "2132-01-01T00:00:00+00:00",
            "end_at": "2132-01-02T00:00:00+00:00",
        },
        "section_labels": {
            "work_actions": "Work actions requiring my attention",
            "manual_actions": "Manual actions",
            "waiting_external_reply": "Waiting for external reply",
            "work_info": "Important project updates",
            "review_optional": "Review optional",
        },
        "counts": {
            "total": 2,
            "visible": 1,
            "hidden": 1,
            "shown": 1,
            "by_attention_class": {
                "no_action_required": 1,
                "requires_my_attention": 1,
            },
            "by_priority": {
                "high": 1,
                "low": 1,
            },
            "by_show_in_digest": {
                "false": 1,
                "true": 1,
            },
            "by_source": {
                "github": 2,
            },
        },
        "groups": {
            "work_actions": [
                {
                    "id": "atri_delivery_visible",
                    "triage_result_id": "atri_delivery_visible",
                    "activity_item_id": "nact_delivery_visible",
                    "source": "github",
                    "source_object_id": "delivery:visible",
                    "attention_class": "requires_my_attention",
                    "priority": "high",
                    "show_in_digest": True,
                    "confidence": 0.93,
                    "title": "Review delivery draft preview",
                    "safe_summary": "Safe delivery draft summary.",
                    "reason": "validated delivery draft fixture",
                    "recommended_action": "review the inert delivery draft",
                    "owner": "me",
                    "deadline": "2132-01-02",
                    "project": "company-knowledge-os",
                    "activity_created_at": "2132-01-01T09:00:00+00:00",
                    "triage_created_at": "2132-01-01T10:00:00+00:00",
                    "evidence": "1 triage evidence ref",
                    "evidence_refs": [
                        {
                            "kind": "source_event",
                            "source_event_id": "sevt_delivery_visible",
                            "source_system": "github",
                            "source_object_type": "pull_request",
                            "source_object_id": "delivery:visible",
                            "raw_object_ref": "raw://delivery/visible.json",
                            "raw_payload": "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
                            "provider_payload": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                            "prompt": "PRIVATE_PROMPT_DO_NOT_EXPOSE",
                            "source_payload": "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
                        }
                    ],
                    "activity_evidence_refs": [
                        {
                            "kind": "normalized_activity_item",
                            "source_event_id": "sevt_delivery_visible",
                            "raw_object_ref": "raw://delivery/visible.json",
                            "raw_payload": "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE",
                        }
                    ],
                    "activity_available": True,
                    "raw_text": "PRIVATE_RAW_TEXT_DO_NOT_EXPOSE",
                    "provider_payload": {"body": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE"},
                    "prompt": "PRIVATE_PROMPT_DO_NOT_EXPOSE",
                }
            ],
            "manual_actions": [],
            "waiting_external_reply": [],
            "work_info": [],
            "review_optional": [],
        },
        "hidden_low_priority_summary": {
            "total": 1,
            "counts": {"no-action low-priority items": 1},
            "items": [
                {
                    "id": "atri_delivery_hidden",
                    "title": "Hidden delivery draft title",
                    "evidence_refs": [
                        {
                            "source_event_id": "sevt_delivery_hidden",
                            "raw_object_ref": "raw://delivery/hidden.json",
                        }
                    ],
                }
            ],
        },
        "data_quality_notes": [],
        "metadata": {
            "source_model": "attention_triage_results",
            "enrichment_model": "normalized_activity_items",
            "group_limit": 20,
            "truncated": False,
            "llm_used": False,
            "read_model_only": True,
            "source_activity_digest_replaced": False,
        },
    }


def _rendered_digest(
    digest: dict[str, Any],
    *,
    debug_evidence: bool = False,
) -> str:
    safe_digest = sanitize_persisted_attention_digest_for_delivery_draft(
        digest,
        debug_evidence=debug_evidence,
    )
    return render_persisted_attention_digest_text(
        safe_digest,
        debug_evidence=debug_evidence,
    )


def test_delivery_draft_builder_returns_inert_review_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery draft builder must not send Telegram messages")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)

    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 1, 1),
        end_at=_utc(2132, 1, 2),
        limit=20,
    )

    assert draft["status"] == "draft"
    assert draft["digest_type"] == "persisted_attention"
    assert draft["channel"] == "telegram"
    assert draft["delivery_enabled"] is False
    assert draft["approval_required"] is True
    assert draft["approved"] is False
    assert draft["sent"] is False
    assert draft["rendered_text"] == rendered_text
    assert draft["text_sha256"] == sha256(rendered_text.encode("utf-8")).hexdigest()
    assert draft["char_count"] == len(rendered_text)
    assert draft["chunk_count"] == len(draft["chunk_metadata"]["chunk_lengths"])
    assert draft["chunk_count"] >= 1
    assert draft["chunk_metadata"]["chunks_preview_included"] is False
    assert draft["safety"] == {
        "provider_free": True,
        "read_only": True,
        "delivery_invoked": False,
        "approval_executed": False,
        "persisted": False,
        "scheduler_invoked": False,
        "triage_run": False,
        "connectors_invoked": False,
        "live_api_calls": False,
    }


def test_delivery_draft_keeps_hidden_details_count_only_and_omits_raw_payloads() -> None:
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)

    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 1, 1),
        end_at=_utc(2132, 1, 2),
    )
    dumped = json.dumps(draft, sort_keys=True)

    assert draft["digest"]["hidden_low_priority_summary"] == {
        "total": 1,
        "counts": {"no-action low-priority items": 1},
    }
    assert "Hidden delivery draft title" not in dumped
    assert "atri_delivery_hidden" not in dumped
    assert "sevt_delivery_hidden" not in dumped
    assert "evidence_refs" not in dumped
    assert "activity_evidence_refs" not in dumped
    for marker in (
        "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_PROMPT_DO_NOT_EXPOSE",
        "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE",
        "PRIVATE_RAW_TEXT_DO_NOT_EXPOSE",
        "raw_payload",
        "provider_payload",
        "prompt",
        "source_payload",
        "raw_text",
    ):
        assert marker not in dumped
        assert marker not in draft["rendered_text"]


def test_delivery_draft_debug_evidence_includes_only_safe_evidence_keys() -> None:
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest, debug_evidence=True)

    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 1, 1),
        end_at=_utc(2132, 1, 2),
        debug_evidence=True,
    )
    item = draft["digest"]["groups"]["work_actions"][0]
    dumped = json.dumps(draft, sort_keys=True)

    assert item["evidence_refs"] == [
        {
            "kind": "source_event",
            "source_event_id": "sevt_delivery_visible",
            "source_system": "github",
            "source_object_type": "pull_request",
            "source_object_id": "delivery:visible",
            "raw_object_ref": "raw://delivery/visible.json",
        }
    ]
    assert item["activity_evidence_refs"] == [
        {
            "kind": "normalized_activity_item",
            "source_event_id": "sevt_delivery_visible",
            "raw_object_ref": "raw://delivery/visible.json",
        }
    ]
    assert "Debug evidence refs:" in draft["rendered_text"]
    assert "raw_payload" not in dumped
    assert "provider_payload" not in dumped
    assert "prompt" not in dumped
    assert "source_payload" not in dumped


def test_delivery_draft_records_source_of_truth_metadata_without_becoming_truth() -> None:
    digest = _persisted_attention_digest()
    rendered_text = _rendered_digest(digest)

    draft = build_persisted_attention_digest_delivery_draft(
        digest=digest,
        rendered_text=rendered_text,
        start_at=_utc(2132, 1, 1),
        end_at=_utc(2132, 1, 2),
    )

    assert draft["source_of_truth"] == {
        "source": "postgres",
        "raw_storage_authoritative": True,
        "postgres_authoritative": True,
        "draft_is_source_of_truth": False,
        "telegram_is_source_of_truth": False,
        "derived_from": [
            "attention_triage_results",
            "normalized_activity_items",
        ],
        "digest_source_model": "attention_triage_results",
        "digest_enrichment_model": "normalized_activity_items",
        "rendered_text_source": "render_persisted_attention_digest_text",
    }


class _FakeScalars:
    def all(self) -> list[Any]:
        return []


class _ReadOnlySession:
    async def scalars(self, *_args: object, **_kwargs: object) -> _FakeScalars:
        return _FakeScalars()

    def add(self, _value: object) -> None:
        raise AssertionError("delivery draft builder must not add rows")

    async def flush(self) -> None:
        raise AssertionError("delivery draft builder must not flush rows")

    async def commit(self) -> None:
        raise AssertionError("delivery draft builder must not commit")

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery draft builder must not execute write paths")


async def test_db_read_delivery_draft_builder_does_not_call_write_methods() -> None:
    draft = await build_persisted_attention_digest_delivery_draft_from_db(
        _ReadOnlySession(),  # type: ignore[arg-type]
        start_at=_utc(2132, 2, 1),
        end_at=_utc(2132, 2, 2),
        limit=20,
    )

    assert draft["status"] == "draft"
    assert draft["delivery_enabled"] is False
    assert draft["approved"] is False
    assert draft["sent"] is False
    assert "No persisted attention items found for this window." in draft["rendered_text"]


async def test_db_read_delivery_draft_builder_rejects_invalid_windows_before_query() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await build_persisted_attention_digest_delivery_draft_from_db(
            _ReadOnlySession(),  # type: ignore[arg-type]
            start_at=datetime(2132, 3, 1),
            end_at=_utc(2132, 3, 2),
        )

    with pytest.raises(ValueError, match="after start_at"):
        await build_persisted_attention_digest_delivery_draft_from_db(
            _ReadOnlySession(),  # type: ignore[arg-type]
            start_at=_utc(2132, 3, 2),
            end_at=_utc(2132, 3, 1),
        )
