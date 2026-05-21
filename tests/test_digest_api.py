import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete

from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.attention_models import AttentionTriageResultRecord
from app.db.base import AsyncSessionLocal, engine
from app.db.event_models import NormalizedActivityItemRecord, SourceEvent
from app.db.models import IngestedEvent
from app.main import app
from app.services.attention_results import record_attention_triage_result
from app.services.attention_triage import AttentionTriageResult, NormalizedActivityItem
from app.services.normalized_activity import record_normalized_activity_item


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
        await conn.run_sync(IngestedEvent.__table__.create, checkfirst=True)
        await conn.run_sync(SourceEvent.__table__.create, checkfirst=True)
        await conn.run_sync(NormalizedActivityItemRecord.__table__.create, checkfirst=True)
        await conn.run_sync(AttentionTriageResultRecord.__table__.create, checkfirst=True)


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
