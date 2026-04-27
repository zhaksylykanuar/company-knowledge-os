import pytest

from app.integrations.payload_mapper import (
    ConnectorPayloadValidationError,
    map_connector_payload_to_ingested_event,
)
from tests.integration_fixture_loader import (
    list_integration_fixtures,
    load_integration_fixture,
)


def _all_fixture_refs() -> list[tuple[str, str]]:
    fixture_refs: list[tuple[str, str]] = []

    for source_system in ("github", "jira", "telegram"):
        fixture_refs.extend(
            (source_system, fixture_path.name)
            for fixture_path in list_integration_fixtures(source_system)
        )

    return fixture_refs


FIXTURE_REFS = _all_fixture_refs()


@pytest.mark.parametrize(("source_system", "fixture_name"), FIXTURE_REFS)
def test_connector_payload_mapper_maps_all_fixtures_to_ingested_event_ready_payload(
    source_system: str,
    fixture_name: str,
) -> None:
    fixture = load_integration_fixture(source_system, fixture_name)

    mapped = map_connector_payload_to_ingested_event(fixture)

    assert mapped.event_id.startswith("evt_")
    assert len(mapped.event_id) == 36
    assert mapped.event_type == fixture["event_type"]
    assert mapped.source_system == fixture["source_system"]
    assert mapped.source_object_id == fixture["source_object_id"]
    assert mapped.idempotency_key == fixture["idempotency_key"]
    assert mapped.raw_object_ref == fixture["raw_object_ref"]
    assert mapped.payload == fixture["payload"]

    assert mapped.to_ingested_event_kwargs() == {
        "event_id": mapped.event_id,
        "event_type": fixture["event_type"],
        "source_system": fixture["source_system"],
        "source_object_id": fixture["source_object_id"],
        "idempotency_key": fixture["idempotency_key"],
        "correlation_id": None,
        "trace_id": None,
        "raw_object_ref": fixture["raw_object_ref"],
        "payload": fixture["payload"],
    }


def test_connector_payload_mapper_is_deterministic() -> None:
    fixture = load_integration_fixture("github", "pull_request_opened.json")

    first = map_connector_payload_to_ingested_event(fixture)
    second = map_connector_payload_to_ingested_event(fixture)

    assert first.event_id == second.event_id
    assert first.to_ingested_event_kwargs() == second.to_ingested_event_kwargs()


def test_connector_payload_mapper_rejects_missing_top_level_field() -> None:
    fixture = load_integration_fixture("github", "pull_request_opened.json")
    fixture.pop("raw_object_ref")

    with pytest.raises(ConnectorPayloadValidationError) as exc_info:
        map_connector_payload_to_ingested_event(fixture)

    assert "missing connector payload fields: raw_object_ref" in str(exc_info.value)


def test_connector_payload_mapper_rejects_contract_invalid_payload() -> None:
    fixture = load_integration_fixture("github", "pull_request_opened.json")
    fixture["payload"] = {
        "source_object_type": "pull_request",
        "title": "Missing source URL",
    }

    with pytest.raises(ConnectorPayloadValidationError) as exc_info:
        map_connector_payload_to_ingested_event(fixture)

    assert "missing required payload field: source_url" in str(exc_info.value)


def test_connector_payload_mapper_accepts_optional_trace_fields() -> None:
    fixture = load_integration_fixture("telegram", "command_received.json")
    fixture["correlation_id"] = "corr-test"
    fixture["trace_id"] = "trace-test"

    mapped = map_connector_payload_to_ingested_event(fixture)

    assert mapped.correlation_id == "corr-test"
    assert mapped.trace_id == "trace-test"
