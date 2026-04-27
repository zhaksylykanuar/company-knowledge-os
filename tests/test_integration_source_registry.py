import pytest

from app.integrations.source_registry import (
    INTEGRATION_SOURCE_REGISTRY,
    SourceSystem,
    get_integration_source,
    get_source_object_contract,
    validate_source_event_contract,
)


def test_registry_includes_future_first_class_sources() -> None:
    assert get_integration_source("github") is not None
    assert get_integration_source("jira") is not None
    assert get_integration_source("telegram") is not None


def test_registry_keeps_sources_safe_by_default() -> None:
    for source_system in (SourceSystem.GITHUB.value, SourceSystem.JIRA.value, SourceSystem.TELEGRAM.value):
        spec = get_integration_source(source_system)

        assert spec is not None
        assert spec.read_only_first is True
        assert spec.write_requires_approval is True
        assert spec.connector_layer_only is True
        assert spec.llm_direct_access_allowed is False


def test_github_pull_request_contract_accepts_valid_payload() -> None:
    errors = validate_source_event_contract(
        source_system="github",
        source_object_type="pull_request",
        event_type="github.pull_request.opened",
        payload={
            "title": "Add source events foundation",
            "source_url": "https://example.invalid/repo/pull/1",
        },
    )

    assert errors == []


def test_jira_issue_contract_rejects_missing_required_fields() -> None:
    errors = validate_source_event_contract(
        source_system="jira",
        source_object_type="issue",
        event_type="jira.issue.created",
        payload={"title": "Create GitHub connector contract"},
    )

    assert errors == ["missing required payload field: source_url"]


def test_telegram_command_contract_rejects_wrong_event_type() -> None:
    errors = validate_source_event_contract(
        source_system="telegram",
        source_object_type="command",
        event_type="telegram.command.executed",
        payload={"text": "/briefing"},
    )

    assert errors == [
        "unsupported event_type for telegram.command: telegram.command.executed"
    ]


def test_registry_is_immutable() -> None:
    with pytest.raises(TypeError):
        INTEGRATION_SOURCE_REGISTRY["unknown"] = get_integration_source("github")


def test_can_lookup_object_contract() -> None:
    contract = get_source_object_contract("github", "pull_request")

    assert contract is not None
    assert "github.pull_request.opened" in contract.event_types
