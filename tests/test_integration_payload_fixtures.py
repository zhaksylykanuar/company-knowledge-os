from app.integrations.source_registry import validate_source_event_contract
from tests.integration_fixture_loader import (
    list_integration_fixtures,
    load_integration_fixture,
)


def test_fixture_loader_lists_safe_connector_fixtures() -> None:
    assert [path.name for path in list_integration_fixtures("github")] == [
        "pull_request_opened.json"
    ]
    assert [path.name for path in list_integration_fixtures("jira")] == [
        "issue_status_changed.json"
    ]
    assert [path.name for path in list_integration_fixtures("telegram")] == [
        "command_received.json"
    ]


def test_connector_payload_fixtures_pass_registry_contracts() -> None:
    fixture_refs = [
        ("github", "pull_request_opened.json"),
        ("jira", "issue_status_changed.json"),
        ("telegram", "command_received.json"),
    ]

    for source_system, fixture_name in fixture_refs:
        fixture = load_integration_fixture(source_system, fixture_name)

        errors = validate_source_event_contract(
            source_system=fixture["source_system"],
            source_object_type=fixture["source_object_type"],
            event_type=fixture["event_type"],
            payload=fixture["payload"],
        )

        assert errors == []


def test_connector_payload_fixtures_are_raw_event_ready() -> None:
    fixture_refs = [
        ("github", "pull_request_opened.json"),
        ("jira", "issue_status_changed.json"),
        ("telegram", "command_received.json"),
    ]

    required_top_level_fields = {
        "source_system",
        "source_object_type",
        "source_object_id",
        "event_type",
        "idempotency_key",
        "raw_object_ref",
        "payload",
    }

    for source_system, fixture_name in fixture_refs:
        fixture = load_integration_fixture(source_system, fixture_name)

        assert required_top_level_fields.issubset(fixture)
        assert fixture["source_system"] == source_system
        assert fixture["raw_object_ref"].startswith(f"raw://{source_system}/events/")
        assert isinstance(fixture["payload"], dict)
