import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete

from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.models import IngestedEvent
from app.main import app


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
