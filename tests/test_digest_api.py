import json
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.attention_models import AttentionTriageResultRecord
from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import AuditLog, IngestedEvent
from app.main import app
from app.services.attention_results import record_attention_triage_result
from app.services.attention_triage import AttentionTriageResult, NormalizedActivityItem
from app.services.digest_delivery_drafts import (
    DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
    DIGEST_DELIVERY_DRAFT_AUDIT_EVENT_TYPES,
    DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
    DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE,
)
from app.services.normalized_activity import record_normalized_activity_item
import app.services.telegram_delivery as telegram_delivery


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _set_auth(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool,
    key: SecretStr | str | None,
) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", key)
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


async def _cleanup_digest_fixture(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(SourceEvent).where(
                SourceEvent.source_event_id.like(f"sevt_digest_api_{unique}_%")
            )
        )
        await session.execute(
            delete(IngestedEvent).where(
                IngestedEvent.event_id.like(f"evt_digest_api_{unique}_%")
            )
        )
        await session.commit()


async def _ensure_persisted_attention_digest_api_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(AuditLog.__table__.create, checkfirst=True)
        await conn.run_sync(IngestedEvent.__table__.create, checkfirst=True)
        await conn.run_sync(SourceEvent.__table__.create, checkfirst=True)
        await conn.run_sync(NormalizedActivityItemRecord.__table__.create, checkfirst=True)
        await conn.run_sync(AttentionTriageResultRecord.__table__.create, checkfirst=True)


async def _cleanup_delivery_draft_api_record(delivery_draft_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AuditLog)
            .where(AuditLog.event_type.in_(DIGEST_DELIVERY_DRAFT_AUDIT_EVENT_TYPES))
            .where(AuditLog.after_ref == delivery_draft_id)
        )
        await session.commit()


async def _delivery_draft_api_record_count(delivery_draft_id: str) -> int:
    return await _delivery_draft_api_event_count(
        delivery_draft_id,
        DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
    )


async def _delivery_draft_api_event_count(
    delivery_draft_id: str,
    event_type: str,
) -> int:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type == event_type)
            .where(AuditLog.after_ref == delivery_draft_id)
        )
    return int(count or 0)


async def _delivery_draft_api_event_total(delivery_draft_id: str) -> int:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.event_type.in_(DIGEST_DELIVERY_DRAFT_AUDIT_EVENT_TYPES))
            .where(AuditLog.after_ref == delivery_draft_id)
        )
    return int(count or 0)


async def _delivery_draft_api_payload(
    delivery_draft_id: str,
    *,
    event_type: str = DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE,
) -> dict:
    async with AsyncSessionLocal() as session:
        payload = await session.scalar(
            select(AuditLog.payload)
            .where(AuditLog.event_type == event_type)
            .where(AuditLog.after_ref == delivery_draft_id)
            .order_by(AuditLog.id)
        )
    assert isinstance(payload, dict)
    return payload


async def _cleanup_persisted_attention_digest_api_fixture(unique: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.triage_result_id.like(
                    f"atri_digest_api_{unique}%"
                )
            )
        )
        await session.execute(
            delete(AttentionTriageResultRecord).where(
                AttentionTriageResultRecord.source_object_id.like(
                    f"digest:api:attention:{unique}%"
                )
            )
        )
        await session.execute(
            delete(NormalizedActivityItemRecord).where(
                NormalizedActivityItemRecord.activity_item_id.like(
                    f"nact_digest_api_{unique}%"
                )
            )
        )
        await session.commit()


def _attention_result(**overrides: object) -> AttentionTriageResult:
    defaults = {
        "attention_class": "requires_my_attention",
        "priority": "high",
        "show_in_digest": True,
        "confidence": 0.91,
        "reason": "validated persisted attention API fixture",
        "recommended_action": "review the persisted attention preview",
        "owner": "me",
        "deadline": "2131-01-02",
        "evidence": [
            {
                "kind": "source_event",
                "source_event_id": "sevt_digest_api_attention_fake",
                "source_system": "github",
                "source_object_type": "pull_request",
                "source_object_id": "digest:api:attention:fake",
                "raw_object_ref": "raw://digest-api-attention/fake.json",
                "raw_payload": "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE",
                "provider_payload": "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                "prompt": "PRIVATE_PROMPT_DO_NOT_EXPOSE",
                "source_payload": "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE",
            }
        ],
    }
    defaults.update(overrides)
    return AttentionTriageResult.model_validate(defaults)


def _normalized_activity(unique: str, suffix: str, **overrides: object) -> NormalizedActivityItem:
    defaults = {
        "source": "github",
        "source_object_id": f"digest:api:attention:{unique}:{suffix}",
        "activity_type": "pull_request.review_requested",
        "title": f"Persisted attention API title {suffix}",
        "actor": "github:fake-user",
        "created_at": _utc(2131, 1, 1, 9),
        "project": "company-knowledge-os",
        "safe_summary": f"Safe persisted attention API summary {suffix}.",
        "related_people": ["github:fake-user"],
        "related_jira_keys": ["FOS-57"],
        "related_prs": ["https://example.test/company-knowledge-os/pull/57"],
        "related_files": [],
        "evidence_refs": [
            {
                "kind": "source_event",
                "source_event_id": f"sevt_digest_api_attention_{unique}_{suffix}",
                "source_system": "github",
                "source_object_type": "pull_request",
                "source_object_id": f"digest:api:attention:{unique}:{suffix}",
                "raw_object_ref": f"raw://digest-api-attention/{unique}/{suffix}.json",
                "raw_payload": "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE",
                "provider_payload": "PRIVATE_ACTIVITY_PROVIDER_PAYLOAD_DO_NOT_EXPOSE",
                "prompt": "PRIVATE_ACTIVITY_PROMPT_DO_NOT_EXPOSE",
            }
        ],
    }
    defaults.update(overrides)
    return NormalizedActivityItem.model_validate(defaults)


async def _record_persisted_attention_api_item(
    *,
    unique: str,
    suffix: str,
    attention_class: str,
    priority: str,
    created_at: datetime,
    show_in_digest: bool = True,
    confidence: float = 0.91,
    activity: NormalizedActivityItem | None = None,
    evidence: list[dict] | None = None,
) -> str:
    async with AsyncSessionLocal() as session:
        activity_item_id = None
        source_object_id = f"digest:api:attention:{unique}:{suffix}"
        if activity is not None:
            stored_activity = await record_normalized_activity_item(
                session,
                activity_item_id=f"nact_digest_api_{unique}_{suffix}",
                activity=activity,
            )
            activity_item_id = stored_activity.activity_item_id
            source_object_id = stored_activity.source_object_id

        result = _attention_result(
            attention_class=attention_class,
            priority=priority,
            show_in_digest=show_in_digest,
            confidence=confidence,
            evidence=evidence if evidence is not None else _attention_result().evidence,
        )
        stored = await record_attention_triage_result(
            session,
            triage_result_id=f"atri_digest_api_{unique}_{suffix}",
            source="github",
            source_object_id=source_object_id,
            activity_item_id=activity_item_id,
            result=result,
            created_at=created_at,
        )
        await session.commit()
        return stored.triage_result_id


async def _insert_source_event(
    *,
    unique: str,
    suffix: str,
    source_system: str,
    source_object_type: str,
    event_type: str,
    event_time: datetime,
    title: str,
    summary: str | None = None,
    payload: dict | None = None,
) -> str:
    event_id = f"evt_digest_api_{unique}_{suffix}"
    source_event_id = f"sevt_digest_api_{unique}_{suffix}"
    raw_object_ref = f"raw://digest-api-test/{unique}/{suffix}.json"

    async with AsyncSessionLocal() as session:
        session.add(
            IngestedEvent(
                event_id=event_id,
                event_type=event_type,
                source_system=source_system,
                source_object_id=f"object-{unique}-{suffix}",
                idempotency_key=f"idem_digest_api_{unique}_{suffix}",
                correlation_id=f"corr_digest_api_{unique}_{suffix}",
                trace_id=f"trace_digest_api_{unique}_{suffix}",
                raw_object_ref=raw_object_ref,
                payload=payload or {},
            )
        )
        await session.flush()
        session.add(
            SourceEvent(
                source_event_id=source_event_id,
                source_event_key=f"{source_system}:{source_object_type}:{unique}:{suffix}",
                ingested_event_id=event_id,
                event_type=event_type,
                source_system=source_system,
                source_object_type=source_object_type,
                source_object_id=f"object-{unique}-{suffix}",
                source_event_ts=event_time,
                actor_external_id=f"actor-{unique}",
                title=title,
                summary=summary,
                source_url=None,
                raw_object_ref=raw_object_ref,
                evidence_refs=[
                    {
                        "kind": "ingested_event",
                        "event_id": event_id,
                        "source_system": source_system,
                        "source_object_id": f"object-{unique}-{suffix}",
                        "raw_object_ref": raw_object_ref,
                    }
                ],
                metadata_json={
                    "trace_id": f"trace_digest_api_{unique}_{suffix}",
                    "correlation_id": f"corr_digest_api_{unique}_{suffix}",
                },
                schema_version="1.0",
            )
        )
        await session.commit()

    return source_event_id


async def test_source_activity_digest_endpoint_returns_empty_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/source-activity",
            params={
                "start_at": "2120-01-01T00:00:00+00:00",
                "end_at": "2120-01-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["digest_type"] == "source_activity"
    assert body["window"] == {
        "start_at": "2120-01-01T00:00:00+00:00",
        "end_at": "2120-01-02T00:00:00+00:00",
    }
    assert body["counts"] == {
        "total": 0,
        "by_source_system": {},
        "by_event_type": {},
        "by_source_object_type": {},
    }
    assert body["entries"] == []
    assert body["metadata"]["generated_at"]
    assert body["metadata"]["entry_limit"] == 20
    assert body["metadata"]["entry_count"] == 0
    assert body["metadata"]["truncated"] is False
    assert body["metadata"]["source_model"] == "source_events"
    assert body["metadata"]["debug_evidence"] is False
    assert body["metadata"]["debug_triage"] is False
    assert body["metadata"]["llm_used"] is False
    assert body["source_event_data_quality"] == {
        "hidden_mock_example_event_count": 0,
        "notes": [],
    }


async def test_source_activity_digest_text_endpoint_returns_empty_plain_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/source-activity/text",
            params={
                "start_at": "2124-01-01T00:00:00+00:00",
                "end_at": "2124-01-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "Source activity digest" in response.text
    assert "Generated at:" in response.text
    assert (
        "Window: 2124-01-01T00:00:00+00:00 to 2124-01-02T00:00:00+00:00"
        in response.text
    )
    assert "Total events: 0" in response.text
    assert "Entries: none" in response.text
    assert "No source activity found for this window." in response.text
    assert "does not infer decisions, tasks, or risks" in response.text


async def test_source_activity_digest_endpoint_filters_events_and_preserves_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)
    unique = uuid4().hex
    raw_body = (
        "Full raw source body should not appear in the digest API response. "
        "This is fixture-only content."
    )
    await _cleanup_digest_fixture(unique)

    try:
        inside_id = await _insert_source_event(
            unique=unique,
            suffix="inside",
            source_system="gmail",
            source_object_type="message",
            event_type="gmail.message.ingested",
            event_time=_utc(2121, 1, 1, 12),
            title="Digest API Gmail subject",
            summary=raw_body,
            payload={"text": raw_body},
        )
        outside_id = await _insert_source_event(
            unique=unique,
            suffix="outside",
            source_system="drive",
            source_object_type="file",
            event_type="drive.file.ingested",
            event_time=_utc(2121, 1, 3, 12),
            title="Outside digest API window",
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/digest/source-activity",
                params={
                    "start_at": "2121-01-01T00:00:00+00:00",
                    "end_at": "2121-01-02T00:00:00+00:00",
                    "limit": "10",
                },
            )

        assert response.status_code == 200
        body = response.json()
        serialized = json.dumps(body, sort_keys=True)

        matching_entries = [
            entry
            for entry in body["entries"]
            if entry["source_event_id"].startswith(f"sevt_digest_api_{unique}_")
        ]

        assert body["counts"]["by_source_system"]["gmail"] >= 1
        assert [entry["source_event_id"] for entry in matching_entries] == [inside_id]
        assert outside_id not in {entry["source_event_id"] for entry in body["entries"]}
        assert matching_entries[0]["evidence"] == "1 event"
        assert "evidence_refs" not in matching_entries[0]
        assert raw_body not in serialized
        assert body["metadata"]["llm_used"] is False

    finally:
        await _cleanup_digest_fixture(unique)


async def test_source_activity_digest_text_endpoint_filters_events_and_preserves_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)
    unique = uuid4().hex
    raw_body = (
        "Full raw source body should not appear in the digest text API response. "
        "This is fixture-only content."
    )
    await _cleanup_digest_fixture(unique)

    try:
        inside_id = await _insert_source_event(
            unique=unique,
            suffix="inside_text",
            source_system="gmail",
            source_object_type="message",
            event_type="gmail.message.ingested",
            event_time=_utc(2124, 2, 1, 12),
            title="Digest text API Gmail subject",
            summary=raw_body,
            payload={"text": raw_body},
        )
        outside_id = await _insert_source_event(
            unique=unique,
            suffix="outside_text",
            source_system="drive",
            source_object_type="file",
            event_type="drive.file.ingested",
            event_time=_utc(2124, 2, 3, 12),
            title="Outside digest text API window",
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/digest/source-activity/text",
                params={
                    "start_at": "2124-02-01T00:00:00+00:00",
                    "end_at": "2124-02-02T00:00:00+00:00",
                    "limit": "10",
                },
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert (
            "Window: 2124-02-01T00:00:00+00:00 to 2124-02-02T00:00:00+00:00"
            in response.text
        )
        assert "Source systems:" in response.text
        assert "- gmail:" in response.text
        assert "Event types:" in response.text
        assert "- gmail.message.ingested:" in response.text
        assert "Source object types:" in response.text
        assert "- message:" in response.text
        assert inside_id not in response.text
        assert outside_id not in response.text
        assert "Digest text API Gmail subject" in response.text
        assert "Outside digest text API window" not in response.text
        assert "Evidence: 1 event" in response.text
        assert "kind=source_event" not in response.text
        assert f"source_event_id={inside_id}" not in response.text
        assert raw_body not in response.text
        assert "does not infer decisions, tasks, or risks" in response.text

    finally:
        await _cleanup_digest_fixture(unique)


async def test_source_activity_digest_text_endpoint_debug_evidence_includes_raw_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)
    unique = uuid4().hex
    await _cleanup_digest_fixture(unique)

    try:
        inside_id = await _insert_source_event(
            unique=unique,
            suffix="debug_text",
            source_system="drive",
            source_object_type="file",
            event_type="drive.file.ingested",
            event_time=_utc(2124, 5, 1, 12),
            title="Digest text API debug file",
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/digest/source-activity/text",
                params={
                    "start_at": "2124-05-01T00:00:00+00:00",
                    "end_at": "2124-05-02T00:00:00+00:00",
                    "limit": "10",
                    "debug_evidence": "true",
                },
            )

        assert response.status_code == 200
        assert "Debug evidence refs:" in response.text
        assert "kind=source_event" in response.text
        assert f"source_event_id={inside_id}" in response.text

    finally:
        await _cleanup_digest_fixture(unique)


async def test_source_activity_digest_endpoint_debug_triage_sets_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/source-activity",
            params={
                "start_at": "2124-06-01T00:00:00+00:00",
                "end_at": "2124-06-02T00:00:00+00:00",
                "debug_triage": "true",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["debug_triage"] is True
    assert body["metadata"]["debug_evidence"] is False


async def test_source_activity_digest_endpoint_rejects_naive_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/source-activity",
            params={
                "start_at": "2122-01-01T00:00:00",
                "end_at": "2122-01-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "start_at must be timezone-aware"}


async def test_source_activity_digest_text_endpoint_rejects_naive_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/source-activity/text",
            params={
                "start_at": "2124-03-01T00:00:00",
                "end_at": "2124-03-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "start_at must be timezone-aware"}


async def test_source_activity_digest_endpoint_rejects_invalid_window_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/source-activity",
            params={
                "start_at": "2122-01-02T00:00:00+00:00",
                "end_at": "2122-01-01T00:00:00+00:00",
            },
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "end_at must be after start_at"}


async def test_source_activity_digest_text_endpoint_rejects_invalid_window_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/source-activity/text",
            params={
                "start_at": "2124-03-02T00:00:00+00:00",
                "end_at": "2124-03-01T00:00:00+00:00",
            },
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "end_at must be after start_at"}


async def test_source_activity_digest_endpoint_requires_api_key_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/source-activity",
            params={
                "start_at": "2123-01-01T00:00:00+00:00",
                "end_at": "2123-01-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text


async def test_source_activity_digest_text_endpoint_requires_api_key_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/source-activity/text",
            params={
                "start_at": "2124-04-01T00:00:00+00:00",
                "end_at": "2124-04-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text


async def test_persisted_attention_digest_endpoint_returns_empty_read_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/persisted-attention",
            params={
                "start_at": "2199-01-01T00:00:00+00:00",
                "end_at": "2199-01-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["section_title"] == "Persisted attention digest"
    assert body["window"] == {
        "start_at": "2199-01-01T00:00:00+00:00",
        "end_at": "2199-01-02T00:00:00+00:00",
    }
    assert body["counts"]["total"] == 0
    assert body["counts"]["visible"] == 0
    assert body["hidden_low_priority_summary"] == {"total": 0, "counts": {}}
    assert body["metadata"]["source_model"] == "attention_triage_results"
    assert body["metadata"]["llm_used"] is False
    assert body["metadata"]["debug_evidence"] is False


async def test_persisted_attention_digest_text_endpoint_returns_empty_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/persisted-attention/text",
            params={
                "start_at": "2199-02-01T00:00:00+00:00",
                "end_at": "2199-02-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "Persisted attention digest" in response.text
    assert (
        "Window: 2199-02-01T00:00:00+00:00 to 2199-02-02T00:00:00+00:00"
        in response.text
    )
    assert "Total attention items: 0" in response.text
    assert "No persisted attention items found for this window." in response.text
    assert "Hidden low-priority summary: 0 hidden" in response.text


async def test_persisted_attention_digest_text_endpoint_renders_visible_sections_and_hidden_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)
    unique = uuid4().hex
    await _cleanup_persisted_attention_digest_api_fixture(unique)

    try:
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="work",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2131, 1, 1, 9),
            activity=_normalized_activity(unique, "work"),
        )
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="hidden",
            attention_class="no_action_required",
            priority="low",
            show_in_digest=False,
            created_at=_utc(2131, 1, 1, 10),
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/digest/persisted-attention/text",
                params={
                    "start_at": "2131-01-01T00:00:00+00:00",
                    "end_at": "2131-01-02T00:00:00+00:00",
                    "limit": "10",
                },
            )

        assert response.status_code == 200
        assert "Work actions requiring my attention:" in response.text
        assert "1. Persisted attention API title work" in response.text
        assert "Source: github" in response.text
        assert "Priority: high" in response.text
        assert "Summary: Safe persisted attention API summary work." in response.text
        assert "Hidden low-priority summary:" in response.text
        assert "- 1 no-action low-priority items" in response.text
        assert f"digest:api:attention:{unique}:hidden" not in response.text
        assert f"atri_digest_api_{unique}_hidden" not in response.text

    finally:
        await _cleanup_persisted_attention_digest_api_fixture(unique)


async def test_persisted_attention_digest_endpoint_omits_evidence_refs_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)
    unique = uuid4().hex
    await _cleanup_persisted_attention_digest_api_fixture(unique)
    raw_marker = "PRIVATE_RAW_PAYLOAD_DO_NOT_EXPOSE"

    try:
        activity = _normalized_activity(unique, "json")
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="json",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2131, 2, 1, 9),
            activity=activity,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/digest/persisted-attention",
                params={
                    "start_at": "2131-02-01T00:00:00+00:00",
                    "end_at": "2131-02-02T00:00:00+00:00",
                    "limit": "10",
                },
            )

        assert response.status_code == 200
        body = response.json()
        item = body["groups"]["work_actions"][0]
        serialized = json.dumps(body, sort_keys=True)

        assert item["title"] == "Persisted attention API title json"
        assert "evidence_refs" not in item
        assert "activity_evidence_refs" not in item
        assert raw_marker not in serialized
        assert "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_PROMPT_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_SOURCE_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "raw_payload" not in serialized
        assert "provider_payload" not in serialized
        assert "prompt" not in serialized
        assert "source_payload" not in serialized

    finally:
        await _cleanup_persisted_attention_digest_api_fixture(unique)


async def test_persisted_attention_digest_endpoint_debug_evidence_filters_safe_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)
    unique = uuid4().hex
    await _cleanup_persisted_attention_digest_api_fixture(unique)

    try:
        activity = _normalized_activity(unique, "debug")
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="debug",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2131, 3, 1, 9),
            activity=activity,
            evidence=activity.evidence_refs,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/digest/persisted-attention",
                params={
                    "start_at": "2131-03-01T00:00:00+00:00",
                    "end_at": "2131-03-02T00:00:00+00:00",
                    "limit": "10",
                    "debug_evidence": "true",
                },
            )

        assert response.status_code == 200
        body = response.json()
        item = body["groups"]["work_actions"][0]
        evidence_ref = item["evidence_refs"][0]
        activity_ref = item["activity_evidence_refs"][0]
        serialized = json.dumps(body, sort_keys=True)

        assert evidence_ref == {
            "kind": "source_event",
            "source_event_id": f"sevt_digest_api_attention_{unique}_debug",
            "source_system": "github",
            "source_object_type": "pull_request",
            "source_object_id": f"digest:api:attention:{unique}:debug",
            "raw_object_ref": f"raw://digest-api-attention/{unique}/debug.json",
        }
        assert activity_ref == evidence_ref
        assert "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_ACTIVITY_PROVIDER_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_ACTIVITY_PROMPT_DO_NOT_EXPOSE" not in serialized
        assert "raw_payload" not in serialized
        assert "provider_payload" not in serialized
        assert "prompt" not in serialized

    finally:
        await _cleanup_persisted_attention_digest_api_fixture(unique)


async def test_persisted_attention_digest_text_endpoint_debug_evidence_is_safe_formatted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)
    unique = uuid4().hex
    await _cleanup_persisted_attention_digest_api_fixture(unique)

    try:
        activity = _normalized_activity(unique, "debug-text")
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="debug-text",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2131, 4, 1, 9),
            activity=activity,
            evidence=activity.evidence_refs,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/digest/persisted-attention/text",
                params={
                    "start_at": "2131-04-01T00:00:00+00:00",
                    "end_at": "2131-04-02T00:00:00+00:00",
                    "limit": "10",
                    "debug_evidence": "true",
                },
            )

        assert response.status_code == 200
        assert "Debug evidence refs:" in response.text
        assert "kind=source_event" in response.text
        assert f"source_event_id=sevt_digest_api_attention_{unique}_debug-text" in response.text
        assert "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE" not in response.text
        assert "raw_payload=" not in response.text
        assert "provider_payload=" not in response.text
        assert "prompt=" not in response.text

    finally:
        await _cleanup_persisted_attention_digest_api_fixture(unique)


async def test_persisted_attention_digest_delivery_draft_endpoint_returns_empty_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery draft endpoint must not send Telegram messages")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/persisted-attention/delivery-draft",
            params={
                "start_at": "2131-04-10T00:00:00+00:00",
                "end_at": "2131-04-11T00:00:00+00:00",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["digest_type"] == "persisted_attention"
    assert body["channel"] == "telegram"
    assert body["delivery_enabled"] is False
    assert body["approval_required"] is True
    assert body["approved"] is False
    assert body["sent"] is False
    assert body["start_at"] == "2131-04-10T00:00:00+00:00"
    assert body["end_at"] == "2131-04-11T00:00:00+00:00"
    assert body["limit"] == 20
    assert body["debug_evidence"] is False
    assert "No persisted attention items found for this window." in body["rendered_text"]
    assert body["text_sha256"] == sha256(body["rendered_text"].encode("utf-8")).hexdigest()
    assert body["char_count"] == len(body["rendered_text"])
    assert body["chunk_count"] == len(body["chunk_metadata"]["chunk_lengths"])
    assert body["digest"]["counts"]["total"] == 0
    assert body["safety"]["provider_free"] is True
    assert body["safety"]["read_only"] is True
    assert body["safety"]["delivery_invoked"] is False
    assert body["safety"]["approval_executed"] is False
    assert body["safety"]["persisted"] is False
    assert body["source_of_truth"]["digest_source_model"] == "attention_triage_results"
    assert body["source_of_truth"]["draft_is_source_of_truth"] is False
    assert body["source_of_truth"]["telegram_is_source_of_truth"] is False


async def test_persisted_attention_digest_delivery_draft_endpoint_renders_visible_sections_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)
    unique = uuid4().hex
    await _cleanup_persisted_attention_digest_api_fixture(unique)
    hidden_title = "Hidden delivery draft API title"

    try:
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="work",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2131, 4, 12, 9),
            activity=_normalized_activity(unique, "work"),
        )
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="hidden",
            attention_class="no_action_required",
            priority="low",
            show_in_digest=False,
            created_at=_utc(2131, 4, 12, 10),
            activity=_normalized_activity(
                unique,
                "hidden",
                title=hidden_title,
            ),
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-04-12T00:00:00+00:00",
                    "end_at": "2131-04-13T00:00:00+00:00",
                    "limit": "10",
                },
            )

        assert response.status_code == 200
        body = response.json()
        serialized = json.dumps(body, sort_keys=True)
        item = body["digest"]["groups"]["work_actions"][0]

        assert body["status"] == "draft"
        assert body["rendered_text"].startswith("Persisted attention digest")
        assert "Work actions requiring my attention:" in body["rendered_text"]
        assert "Persisted attention API title work" in body["rendered_text"]
        assert "Hidden low-priority summary:" in body["rendered_text"]
        assert "- 1 no-action low-priority items" in body["rendered_text"]
        assert item["title"] == "Persisted attention API title work"
        assert "evidence_refs" not in item
        assert "activity_evidence_refs" not in item
        assert body["digest"]["hidden_low_priority_summary"] == {
            "total": 1,
            "counts": {"no-action low-priority items": 1},
        }
        assert hidden_title not in serialized
        assert f"atri_digest_api_{unique}_hidden" not in serialized
        assert f"digest:api:attention:{unique}:hidden" not in serialized
        assert "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_ACTIVITY_PROVIDER_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_ACTIVITY_PROMPT_DO_NOT_EXPOSE" not in serialized
        assert "raw_payload" not in serialized
        assert "provider_payload" not in serialized
        assert "prompt" not in serialized

    finally:
        await _cleanup_persisted_attention_digest_api_fixture(unique)


async def test_persisted_attention_digest_delivery_draft_endpoint_debug_evidence_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)
    unique = uuid4().hex
    await _cleanup_persisted_attention_digest_api_fixture(unique)

    try:
        activity = _normalized_activity(unique, "draft-debug")
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="draft-debug",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2131, 4, 14, 9),
            activity=activity,
            evidence=activity.evidence_refs,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-04-14T00:00:00+00:00",
                    "end_at": "2131-04-15T00:00:00+00:00",
                    "debug_evidence": "true",
                },
            )

        assert response.status_code == 200
        body = response.json()
        item = body["digest"]["groups"]["work_actions"][0]
        serialized = json.dumps(body, sort_keys=True)

        assert body["debug_evidence"] is True
        assert item["evidence_refs"] == [
            {
                "kind": "source_event",
                "source_event_id": f"sevt_digest_api_attention_{unique}_draft-debug",
                "source_system": "github",
                "source_object_type": "pull_request",
                "source_object_id": f"digest:api:attention:{unique}:draft-debug",
                "raw_object_ref": (
                    f"raw://digest-api-attention/{unique}/draft-debug.json"
                ),
            }
        ]
        assert item["activity_evidence_refs"] == item["evidence_refs"]
        assert "Debug evidence refs:" in body["rendered_text"]
        assert "raw_payload" not in serialized
        assert "provider_payload" not in serialized
        assert "prompt" not in serialized

    finally:
        await _cleanup_persisted_attention_digest_api_fixture(unique)


async def test_persisted_attention_digest_delivery_draft_endpoint_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/persisted-attention/delivery-draft",
            params={
                "start_at": "2131-04-16T00:00:00+00:00",
                "end_at": "2131-04-17T00:00:00+00:00",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text


async def test_persisted_attention_digest_delivery_draft_endpoint_rejects_invalid_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        naive = await client.get(
            "/v1/digest/persisted-attention/delivery-draft",
            params={
                "start_at": "2131-04-18T00:00:00",
                "end_at": "2131-04-19T00:00:00+00:00",
            },
        )
        reversed_window = await client.get(
            "/v1/digest/persisted-attention/delivery-draft",
            params={
                "start_at": "2131-04-20T00:00:00+00:00",
                "end_at": "2131-04-19T00:00:00+00:00",
            },
        )

    assert naive.status_code == 400
    assert naive.json() == {"detail": "start_at must be timezone-aware"}
    assert reversed_window.status_code == 400
    assert reversed_window.json() == {"detail": "end_at must be after start_at"}


async def test_persisted_attention_digest_delivery_draft_preview_remains_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery draft preview must not send Telegram messages")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    params = {
        "start_at": "2131-08-01T00:00:00+00:00",
        "end_at": "2131-08-02T00:00:00+00:00",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        preview = await client.get(
            "/v1/digest/persisted-attention/delivery-draft",
            params=params,
        )

    assert preview.status_code == 200
    delivery_draft_id = preview.json()["delivery_draft_id"]
    await _cleanup_delivery_draft_api_record(delivery_draft_id)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/digest/persisted-attention/delivery-draft",
                params=params,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["delivery_draft_id"] == delivery_draft_id
        assert body["persisted"] is False
        assert body["safety"]["read_only"] is True
        assert await _delivery_draft_api_record_count(delivery_draft_id) == 0
    finally:
        await _cleanup_delivery_draft_api_record(delivery_draft_id)


async def test_persisted_attention_digest_delivery_draft_post_persists_empty_draft_idempotently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery draft persistence must not send Telegram messages")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    params = {
        "start_at": "2131-08-03T00:00:00+00:00",
        "end_at": "2131-08-04T00:00:00+00:00",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        preview = await client.get(
            "/v1/digest/persisted-attention/delivery-draft",
            params=params,
        )

    assert preview.status_code == 200
    delivery_draft_id = preview.json()["delivery_draft_id"]
    await _cleanup_delivery_draft_api_record(delivery_draft_id)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created_response = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params=params,
            )
            repeated_response = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params=params,
            )
            retrieved_response = await client.get(
                f"/v1/digest/delivery-drafts/{delivery_draft_id}",
            )

        assert created_response.status_code == 200
        assert repeated_response.status_code == 200
        assert retrieved_response.status_code == 200
        created = created_response.json()
        repeated = repeated_response.json()
        retrieved = retrieved_response.json()

        assert created["delivery_draft_id"] == delivery_draft_id
        assert repeated["delivery_draft_id"] == delivery_draft_id
        assert retrieved["delivery_draft_id"] == delivery_draft_id
        assert created["persisted"] is True
        assert created["status"] == "draft"
        assert created["digest_type"] == "persisted_attention"
        assert created["channel"] == "telegram"
        assert created["delivery_enabled"] is False
        assert created["approval_required"] is True
        assert created["approved"] is False
        assert created["sent"] is False
        assert created["persistence"]["storage"] == "audit_logs"
        assert created["persistence"]["event_type"] == (
            DIGEST_DELIVERY_DRAFT_CREATED_EVENT_TYPE
        )
        assert created["persistence"]["after_ref"] == delivery_draft_id
        assert created["audit_log"]["after_ref"] == delivery_draft_id
        assert created["safety"]["read_only"] is False
        assert created["safety"]["db_write_scope"] == "audit_logs_only"
        assert created["safety"]["delivery_invoked"] is False
        assert created["safety"]["approval_executed"] is False
        assert "No persisted attention items found for this window." in created[
            "rendered_text"
        ]
        assert retrieved["rendered_text"] == created["rendered_text"]
        assert repeated["text_sha256"] == created["text_sha256"]
        assert await _delivery_draft_api_record_count(delivery_draft_id) == 1
    finally:
        await _cleanup_delivery_draft_api_record(delivery_draft_id)


async def test_persisted_attention_digest_delivery_draft_post_persists_sections_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery draft persistence must not send Telegram messages")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    unique = uuid4().hex
    hidden_title = "Hidden persisted delivery draft API title"
    delivery_draft_id: str | None = None
    await _cleanup_persisted_attention_digest_api_fixture(unique)

    try:
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="post-work",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2131, 8, 5, 9),
            activity=_normalized_activity(unique, "post-work"),
        )
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="post-hidden",
            attention_class="no_action_required",
            priority="low",
            show_in_digest=False,
            created_at=_utc(2131, 8, 5, 10),
            activity=_normalized_activity(
                unique,
                "post-hidden",
                title=hidden_title,
            ),
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-08-05T00:00:00+00:00",
                    "end_at": "2131-08-06T00:00:00+00:00",
                    "limit": "10",
                },
            )

        assert response.status_code == 200
        body = response.json()
        delivery_draft_id = body["delivery_draft_id"]
        stored_payload = await _delivery_draft_api_payload(delivery_draft_id)
        serialized = json.dumps(
            {"response": body, "stored": stored_payload},
            sort_keys=True,
        )
        item = body["digest"]["groups"]["work_actions"][0]

        assert body["persisted"] is True
        assert body["rendered_text"].startswith("Persisted attention digest")
        assert "Work actions requiring my attention:" in body["rendered_text"]
        assert "Persisted attention API title post-work" in body["rendered_text"]
        assert "Hidden low-priority summary:" in body["rendered_text"]
        assert item["title"] == "Persisted attention API title post-work"
        assert "evidence_refs" not in item
        assert "activity_evidence_refs" not in item
        assert body["digest"]["hidden_low_priority_summary"] == {
            "total": 1,
            "counts": {"no-action low-priority items": 1},
        }
        assert stored_payload["digest"]["hidden_low_priority_summary"] == {
            "total": 1,
            "counts": {"no-action low-priority items": 1},
        }
        assert hidden_title not in serialized
        assert f"atri_digest_api_{unique}_post-hidden" not in serialized
        assert f"digest:api:attention:{unique}:post-hidden" not in serialized
        assert "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_ACTIVITY_PROVIDER_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_ACTIVITY_PROMPT_DO_NOT_EXPOSE" not in serialized
        assert "raw_payload" not in serialized
        assert "provider_payload" not in serialized
        assert "prompt" not in serialized
        assert await _delivery_draft_api_record_count(delivery_draft_id) == 1
    finally:
        if delivery_draft_id is not None:
            await _cleanup_delivery_draft_api_record(delivery_draft_id)
        await _cleanup_persisted_attention_digest_api_fixture(unique)


async def test_persisted_attention_digest_delivery_draft_post_debug_evidence_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)
    unique = uuid4().hex
    delivery_draft_id: str | None = None
    await _cleanup_persisted_attention_digest_api_fixture(unique)

    try:
        activity = _normalized_activity(unique, "post-debug")
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="post-debug",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2131, 8, 7, 9),
            activity=activity,
            evidence=activity.evidence_refs,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-08-07T00:00:00+00:00",
                    "end_at": "2131-08-08T00:00:00+00:00",
                    "debug_evidence": "true",
                },
            )

        assert response.status_code == 200
        body = response.json()
        delivery_draft_id = body["delivery_draft_id"]
        stored_payload = await _delivery_draft_api_payload(delivery_draft_id)
        item = body["digest"]["groups"]["work_actions"][0]
        serialized = json.dumps(
            {"response": body, "stored": stored_payload},
            sort_keys=True,
        )

        assert body["debug_evidence"] is True
        assert item["evidence_refs"] == [
            {
                "kind": "source_event",
                "source_event_id": f"sevt_digest_api_attention_{unique}_post-debug",
                "source_system": "github",
                "source_object_type": "pull_request",
                "source_object_id": f"digest:api:attention:{unique}:post-debug",
                "raw_object_ref": (
                    f"raw://digest-api-attention/{unique}/post-debug.json"
                ),
            }
        ]
        assert item["activity_evidence_refs"] == item["evidence_refs"]
        assert "Debug evidence refs:" in body["rendered_text"]
        assert "raw_payload" not in serialized
        assert "provider_payload" not in serialized
        assert "prompt" not in serialized
    finally:
        if delivery_draft_id is not None:
            await _cleanup_delivery_draft_api_record(delivery_draft_id)
        await _cleanup_persisted_attention_digest_api_fixture(unique)


async def test_persisted_attention_digest_delivery_draft_persisted_endpoints_require_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        post_response = await client.post(
            "/v1/digest/persisted-attention/delivery-draft",
            params={
                "start_at": "2131-08-09T00:00:00+00:00",
                "end_at": "2131-08-10T00:00:00+00:00",
            },
        )
        get_response = await client.get(
            "/v1/digest/delivery-drafts/ddraft_missing",
        )
        approve_response = await client.post(
            "/v1/digest/delivery-drafts/ddraft_missing/approve",
            json={"reviewer": "founder"},
        )
        reject_response = await client.post(
            "/v1/digest/delivery-drafts/ddraft_missing/reject",
            json={"reviewer": "founder"},
        )
        status_response = await client.get(
            "/v1/digest/delivery-drafts/ddraft_missing/approval-status",
        )
        readiness_response = await client.get(
            "/v1/digest/delivery-drafts/ddraft_missing/delivery-readiness",
        )

    assert post_response.status_code == 401
    assert get_response.status_code == 401
    assert approve_response.status_code == 401
    assert reject_response.status_code == 401
    assert status_response.status_code == 401
    assert readiness_response.status_code == 401
    assert post_response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert get_response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert approve_response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert reject_response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert status_response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert readiness_response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in post_response.text
    assert "test-api-key" not in get_response.text
    assert "test-api-key" not in approve_response.text
    assert "test-api-key" not in reject_response.text
    assert "test-api-key" not in status_response.text
    assert "test-api-key" not in readiness_response.text


async def test_persisted_attention_digest_delivery_draft_retrieval_returns_404_for_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/delivery-drafts/ddraft_unknown_fos_061",
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "delivery draft was not found"}


async def test_persisted_attention_digest_delivery_draft_post_rejects_invalid_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        naive = await client.post(
            "/v1/digest/persisted-attention/delivery-draft",
            params={
                "start_at": "2131-08-11T00:00:00",
                "end_at": "2131-08-12T00:00:00+00:00",
            },
        )
        reversed_window = await client.post(
            "/v1/digest/persisted-attention/delivery-draft",
            params={
                "start_at": "2131-08-13T00:00:00+00:00",
                "end_at": "2131-08-12T00:00:00+00:00",
            },
        )

    assert naive.status_code == 400
    assert naive.json() == {"detail": "start_at must be timezone-aware"}
    assert reversed_window.status_code == 400
    assert reversed_window.json() == {"detail": "end_at must be after start_at"}


async def test_delivery_draft_approval_endpoints_return_404_for_unknown_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)
    delivery_draft_id = "ddraft_unknown_fos_062_api"
    await _cleanup_delivery_draft_api_record(delivery_draft_id)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        approve_response = await client.post(
            f"/v1/digest/delivery-drafts/{delivery_draft_id}/approve",
            json={"reviewer": "founder"},
        )
        reject_response = await client.post(
            f"/v1/digest/delivery-drafts/{delivery_draft_id}/reject",
            json={"reviewer": "founder"},
        )
        status_response = await client.get(
            f"/v1/digest/delivery-drafts/{delivery_draft_id}/approval-status",
        )
        readiness_response = await client.get(
            f"/v1/digest/delivery-drafts/{delivery_draft_id}/delivery-readiness",
        )

    assert approve_response.status_code == 404
    assert reject_response.status_code == 404
    assert status_response.status_code == 404
    assert readiness_response.status_code == 404
    assert approve_response.json() == {"detail": "delivery draft was not found"}
    assert reject_response.json() == {"detail": "delivery draft was not found"}
    assert status_response.json() == {"detail": "delivery draft was not found"}
    assert readiness_response.json() == {"detail": "delivery draft was not found"}


async def test_delivery_draft_approve_endpoint_records_safe_idempotent_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("approval decision must not send Telegram messages")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    unique = uuid4().hex
    hidden_title = "Hidden approval API title"
    delivery_draft_id: str | None = None
    await _cleanup_persisted_attention_digest_api_fixture(unique)

    try:
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="approve-work",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2131, 9, 1, 9),
            activity=_normalized_activity(unique, "approve-work"),
        )
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="approve-hidden",
            attention_class="no_action_required",
            priority="low",
            show_in_digest=False,
            created_at=_utc(2131, 9, 1, 10),
            activity=_normalized_activity(
                unique,
                "approve-hidden",
                title=hidden_title,
            ),
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created_response = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-09-01T00:00:00+00:00",
                    "end_at": "2131-09-02T00:00:00+00:00",
                    "limit": "10",
                },
            )
            assert created_response.status_code == 200
            created = created_response.json()
            delivery_draft_id = created["delivery_draft_id"]
            approve_response = await client.post(
                f"/v1/digest/delivery-drafts/{delivery_draft_id}/approve",
                json={
                    "reviewer": "founder",
                    "note": "Approved for human-reviewed delivery.",
                },
            )
            repeated_response = await client.post(
                f"/v1/digest/delivery-drafts/{delivery_draft_id}/approve",
                json={"reviewer": "duplicate reviewer"},
            )
            status_response = await client.get(
                f"/v1/digest/delivery-drafts/{delivery_draft_id}/approval-status",
            )

        assert approve_response.status_code == 200
        assert repeated_response.status_code == 200
        assert status_response.status_code == 200
        approved = approve_response.json()
        repeated = repeated_response.json()
        approval_status = status_response.json()
        decision_payload = await _delivery_draft_api_payload(
            delivery_draft_id,
            event_type=DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
        )
        serialized = json.dumps(
            {
                "approved": approved,
                "status": approval_status,
                "decision_payload": decision_payload,
            },
            sort_keys=True,
        )

        assert approved == repeated == approval_status
        assert approved["delivery_draft_id"] == delivery_draft_id
        assert approved["current_decision"] == "approved"
        assert approved["approved"] is True
        assert approved["rejected"] is False
        assert approved["delivery_enabled"] is False
        assert approved["sent"] is False
        assert approved["delivery_invoked"] is False
        assert approved["approval_execution_invoked"] is False
        assert approved["draft"]["text_sha256"] == created["text_sha256"]
        assert len(approved["decision_history"]) == 1
        assert approved["decision_history"][0]["event_type"] == (
            DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE
        )
        assert approved["decision_history"][0]["reviewer"] == "founder"
        assert approved["decision_history"][0]["note"] == (
            "Approved for human-reviewed delivery."
        )
        assert decision_payload["decision"] == "approved"
        assert decision_payload["reviewer"] == "founder"
        assert decision_payload["draft_text_sha256"] == created["text_sha256"]
        assert await _delivery_draft_api_event_count(
            delivery_draft_id,
            DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
        ) == 1
        assert '"rendered_text":' not in serialized
        assert hidden_title not in serialized
        assert f"atri_digest_api_{unique}_approve-hidden" not in serialized
        assert f"digest:api:attention:{unique}:approve-hidden" not in serialized
        assert "evidence_refs" not in serialized
        assert "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_ACTIVITY_PROVIDER_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_ACTIVITY_PROMPT_DO_NOT_EXPOSE" not in serialized
        assert "raw_payload" not in serialized
        assert "provider_payload" not in serialized
        assert "prompt" not in serialized
    finally:
        if delivery_draft_id is not None:
            await _cleanup_delivery_draft_api_record(delivery_draft_id)
        await _cleanup_persisted_attention_digest_api_fixture(unique)


async def test_delivery_draft_reject_endpoint_records_safe_idempotent_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)
    delivery_draft_id: str | None = None

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created_response = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-09-03T00:00:00+00:00",
                    "end_at": "2131-09-04T00:00:00+00:00",
                },
            )
            assert created_response.status_code == 200
            created = created_response.json()
            delivery_draft_id = created["delivery_draft_id"]
            reject_response = await client.post(
                f"/v1/digest/delivery-drafts/{delivery_draft_id}/reject",
                json={
                    "reviewer": "founder",
                    "note": "Needs edits before delivery.",
                },
            )
            repeated_response = await client.post(
                f"/v1/digest/delivery-drafts/{delivery_draft_id}/reject",
                json={"reviewer": "duplicate reviewer"},
            )

        assert reject_response.status_code == 200
        assert repeated_response.status_code == 200
        rejected = reject_response.json()
        repeated = repeated_response.json()
        assert rejected == repeated
        assert rejected["current_decision"] == "rejected"
        assert rejected["approved"] is False
        assert rejected["rejected"] is True
        assert rejected["delivery_enabled"] is False
        assert rejected["sent"] is False
        assert rejected["decision_history"][0]["event_type"] == (
            DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE
        )
        assert rejected["decision_history"][0]["reviewer"] == "founder"
        assert rejected["decision_history"][0]["note"] == "Needs edits before delivery."
        assert await _delivery_draft_api_event_count(
            delivery_draft_id,
            DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE,
        ) == 1
    finally:
        if delivery_draft_id is not None:
            await _cleanup_delivery_draft_api_record(delivery_draft_id)


async def test_delivery_draft_delivery_readiness_endpoint_reports_safe_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async def forbidden_send(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("delivery readiness must not send Telegram messages")

    monkeypatch.setattr(telegram_delivery, "send_telegram_plain_text", forbidden_send)
    unique = uuid4().hex
    hidden_title = "Hidden delivery readiness API title"
    delivery_draft_ids: list[str] = []
    await _cleanup_persisted_attention_digest_api_fixture(unique)

    try:
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="readiness-work",
            attention_class="requires_my_attention",
            priority="high",
            created_at=_utc(2131, 9, 11, 9),
            activity=_normalized_activity(unique, "readiness-work"),
        )
        await _record_persisted_attention_api_item(
            unique=unique,
            suffix="readiness-hidden",
            attention_class="no_action_required",
            priority="low",
            show_in_digest=False,
            created_at=_utc(2131, 9, 11, 10),
            activity=_normalized_activity(
                unique,
                "readiness-hidden",
                title=hidden_title,
            ),
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            unapproved_created = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-09-09T00:00:00+00:00",
                    "end_at": "2131-09-10T00:00:00+00:00",
                },
            )
            rejected_created = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-09-10T00:00:00+00:00",
                    "end_at": "2131-09-11T00:00:00+00:00",
                },
            )
            approved_created = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-09-11T00:00:00+00:00",
                    "end_at": "2131-09-12T00:00:00+00:00",
                    "limit": "10",
                },
            )
            assert unapproved_created.status_code == 200
            assert rejected_created.status_code == 200
            assert approved_created.status_code == 200

            unapproved_id = unapproved_created.json()["delivery_draft_id"]
            rejected_id = rejected_created.json()["delivery_draft_id"]
            approved_id = approved_created.json()["delivery_draft_id"]
            delivery_draft_ids.extend([unapproved_id, rejected_id, approved_id])

            reject_response = await client.post(
                f"/v1/digest/delivery-drafts/{rejected_id}/reject",
                json={"reviewer": "founder", "note": "Not ready."},
            )
            approve_response = await client.post(
                f"/v1/digest/delivery-drafts/{approved_id}/approve",
                json={"reviewer": "founder", "note": "Ready for future gate."},
            )
            assert reject_response.status_code == 200
            assert approve_response.status_code == 200

            before_counts = {
                delivery_draft_id: await _delivery_draft_api_event_total(
                    delivery_draft_id
                )
                for delivery_draft_id in delivery_draft_ids
            }
            unapproved_response = await client.get(
                f"/v1/digest/delivery-drafts/{unapproved_id}/delivery-readiness",
            )
            rejected_response = await client.get(
                f"/v1/digest/delivery-drafts/{rejected_id}/delivery-readiness",
            )
            approved_response = await client.get(
                f"/v1/digest/delivery-drafts/{approved_id}/delivery-readiness",
            )
            after_counts = {
                delivery_draft_id: await _delivery_draft_api_event_total(
                    delivery_draft_id
                )
                for delivery_draft_id in delivery_draft_ids
            }

        assert before_counts == after_counts
        assert unapproved_response.status_code == 200
        assert rejected_response.status_code == 200
        assert approved_response.status_code == 200

        unapproved = unapproved_response.json()
        rejected = rejected_response.json()
        approved = approved_response.json()

        assert unapproved["status"] == "delivery_readiness"
        assert unapproved["current_decision"] is None
        assert unapproved["approved"] is False
        assert unapproved["rejected"] is False
        assert unapproved["eligible_for_delivery"] is False
        assert unapproved["ineligible_reasons"] == ["not_approved"]

        assert rejected["current_decision"] == "rejected"
        assert rejected["approved"] is False
        assert rejected["rejected"] is True
        assert rejected["eligible_for_delivery"] is False
        assert rejected["ineligible_reasons"] == ["rejected"]

        assert approved["current_decision"] == "approved"
        assert approved["approved"] is True
        assert approved["rejected"] is False
        assert approved["eligible_for_delivery"] is True
        assert approved["ineligible_reasons"] == []

        for readiness, created in (
            (unapproved, unapproved_created.json()),
            (rejected, rejected_created.json()),
            (approved, approved_created.json()),
        ):
            assert readiness["draft_exists"] is True
            assert readiness["digest_type"] == "persisted_attention"
            assert readiness["channel"] == "telegram"
            assert readiness["delivery_execution_enabled"] is False
            assert readiness["delivery_enabled"] is False
            assert readiness["delivery_invoked"] is False
            assert readiness["approval_execution_invoked"] is False
            assert readiness["sent"] is False
            assert readiness["text_sha256"] == created["text_sha256"]
            assert readiness["char_count"] == created["char_count"]
            assert readiness["chunk_count"] == created["chunk_count"]
            assert readiness["chunk_metadata"] == created["chunk_metadata"]
            assert readiness["source_of_truth"] == created["source_of_truth"]
            assert readiness["safety"]["provider_free"] is True
            assert readiness["safety"]["read_only"] is True
            assert readiness["safety"]["db_write_scope"] == "none"
            assert "rendered_text" not in readiness
            assert "digest" not in readiness

        serialized = json.dumps(
            {
                "unapproved": unapproved,
                "rejected": rejected,
                "approved": approved,
            },
            sort_keys=True,
        )
        assert hidden_title not in serialized
        assert f"atri_digest_api_{unique}_readiness-hidden" not in serialized
        assert f"digest:api:attention:{unique}:readiness-hidden" not in serialized
        assert "evidence_refs" not in serialized
        assert "PRIVATE_ACTIVITY_RAW_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_ACTIVITY_PROVIDER_PAYLOAD_DO_NOT_EXPOSE" not in serialized
        assert "PRIVATE_ACTIVITY_PROMPT_DO_NOT_EXPOSE" not in serialized
        assert "raw_payload" not in serialized
        assert "provider_payload" not in serialized
        assert "prompt" not in serialized
    finally:
        for delivery_draft_id in delivery_draft_ids:
            await _cleanup_delivery_draft_api_record(delivery_draft_id)
        await _cleanup_persisted_attention_digest_api_fixture(unique)


async def test_delivery_draft_decision_endpoints_reject_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)
    approved_id: str | None = None
    rejected_id: str | None = None

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            approved_created = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-09-05T00:00:00+00:00",
                    "end_at": "2131-09-06T00:00:00+00:00",
                },
            )
            rejected_created = await client.post(
                "/v1/digest/persisted-attention/delivery-draft",
                params={
                    "start_at": "2131-09-07T00:00:00+00:00",
                    "end_at": "2131-09-08T00:00:00+00:00",
                },
            )
            assert approved_created.status_code == 200
            assert rejected_created.status_code == 200
            approved_id = approved_created.json()["delivery_draft_id"]
            rejected_id = rejected_created.json()["delivery_draft_id"]

            approve_response = await client.post(
                f"/v1/digest/delivery-drafts/{approved_id}/approve",
                json={"reviewer": "founder"},
            )
            reject_after_approve = await client.post(
                f"/v1/digest/delivery-drafts/{approved_id}/reject",
                json={"reviewer": "founder"},
            )
            reject_response = await client.post(
                f"/v1/digest/delivery-drafts/{rejected_id}/reject",
                json={"reviewer": "founder"},
            )
            approve_after_reject = await client.post(
                f"/v1/digest/delivery-drafts/{rejected_id}/approve",
                json={"reviewer": "founder"},
            )

        assert approve_response.status_code == 200
        assert reject_response.status_code == 200
        assert reject_after_approve.status_code == 409
        assert approve_after_reject.status_code == 409
        assert "already has terminal decision approved" in reject_after_approve.text
        assert "already has terminal decision rejected" in approve_after_reject.text
        assert await _delivery_draft_api_event_count(
            approved_id,
            DIGEST_DELIVERY_DRAFT_REJECTED_EVENT_TYPE,
        ) == 0
        assert await _delivery_draft_api_event_count(
            rejected_id,
            DIGEST_DELIVERY_DRAFT_APPROVED_EVENT_TYPE,
        ) == 0
    finally:
        if approved_id is not None:
            await _cleanup_delivery_draft_api_record(approved_id)
        if rejected_id is not None:
            await _cleanup_delivery_draft_api_record(rejected_id)


async def test_persisted_attention_digest_endpoint_requires_api_key_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=True, key=SecretStr("test-api-key"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/persisted-attention",
            params={
                "start_at": "2131-05-01T00:00:00+00:00",
                "end_at": "2131-05-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
    assert "test-api-key" not in response.text


async def test_persisted_attention_digest_endpoint_rejects_naive_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/persisted-attention",
            params={
                "start_at": "2131-06-01T00:00:00",
                "end_at": "2131-06-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "start_at must be timezone-aware"}


async def test_persisted_attention_digest_text_endpoint_rejects_invalid_window_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _ensure_persisted_attention_digest_api_tables()
    _set_auth(monkeypatch, enabled=False, key=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/digest/persisted-attention/text",
            params={
                "start_at": "2131-07-02T00:00:00+00:00",
                "end_at": "2131-07-01T00:00:00+00:00",
            },
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "end_at must be after start_at"}
