from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class SourceSystem(str, Enum):
    DRIVE = "drive"
    GMAIL = "gmail"
    GITHUB = "github"
    JIRA = "jira"
    TELEGRAM = "telegram"
    INTERNAL = "internal"


@dataclass(frozen=True)
class SourceObjectContract:
    source_object_type: str
    event_types: frozenset[str]
    required_payload_fields: frozenset[str]


@dataclass(frozen=True)
class IntegrationSourceSpec:
    source_system: SourceSystem
    display_name: str
    source_kind: str
    read_only_first: bool
    write_requires_approval: bool
    connector_layer_only: bool
    llm_direct_access_allowed: bool
    object_contracts: Mapping[str, SourceObjectContract]


def _contracts(*contracts: SourceObjectContract) -> Mapping[str, SourceObjectContract]:
    return MappingProxyType({contract.source_object_type: contract for contract in contracts})


INTEGRATION_SOURCE_REGISTRY: Mapping[str, IntegrationSourceSpec] = MappingProxyType(
    {
        SourceSystem.DRIVE.value: IntegrationSourceSpec(
            source_system=SourceSystem.DRIVE,
            display_name="Google Drive",
            source_kind="document_store",
            read_only_first=True,
            write_requires_approval=True,
            connector_layer_only=True,
            llm_direct_access_allowed=False,
            object_contracts=_contracts(
                SourceObjectContract(
                    source_object_type="file",
                    event_types=frozenset(
                        {
                            "drive.file.created",
                            "drive.file.updated",
                            "drive.file.ingested",
                        }
                    ),
                    required_payload_fields=frozenset({"title"}),
                ),
            ),
        ),
        SourceSystem.GMAIL.value: IntegrationSourceSpec(
            source_system=SourceSystem.GMAIL,
            display_name="Gmail",
            source_kind="email",
            read_only_first=True,
            write_requires_approval=True,
            connector_layer_only=True,
            llm_direct_access_allowed=False,
            object_contracts=_contracts(
                SourceObjectContract(
                    source_object_type="message",
                    event_types=frozenset(
                        {
                            "gmail.message.received",
                            "gmail.message.sent",
                            "gmail.message.ingested",
                        }
                    ),
                    required_payload_fields=frozenset({"subject"}),
                ),
            ),
        ),
        SourceSystem.GITHUB.value: IntegrationSourceSpec(
            source_system=SourceSystem.GITHUB,
            display_name="GitHub",
            source_kind="development",
            read_only_first=True,
            write_requires_approval=True,
            connector_layer_only=True,
            llm_direct_access_allowed=False,
            object_contracts=_contracts(
                SourceObjectContract(
                    source_object_type="pull_request",
                    event_types=frozenset(
                        {
                            "github.pull_request.opened",
                            "github.pull_request.closed",
                            "github.pull_request.merged",
                            "github.pull_request.reopened",
                            "github.pull_request.synchronized",
                        }
                    ),
                    required_payload_fields=frozenset({"title", "source_url"}),
                ),
                SourceObjectContract(
                    source_object_type="issue",
                    event_types=frozenset(
                        {
                            "github.issue.opened",
                            "github.issue.closed",
                            "github.issue.reopened",
                            "github.issue.commented",
                        }
                    ),
                    required_payload_fields=frozenset({"title", "source_url"}),
                ),
                SourceObjectContract(
                    source_object_type="commit",
                    event_types=frozenset({"github.commit.pushed"}),
                    required_payload_fields=frozenset({"title", "source_url"}),
                ),
                SourceObjectContract(
                    source_object_type="check_run",
                    event_types=frozenset({"github.check_run.completed"}),
                    required_payload_fields=frozenset({"title", "source_url"}),
                ),
            ),
        ),
        SourceSystem.JIRA.value: IntegrationSourceSpec(
            source_system=SourceSystem.JIRA,
            display_name="Jira",
            source_kind="project_management",
            read_only_first=True,
            write_requires_approval=True,
            connector_layer_only=True,
            llm_direct_access_allowed=False,
            object_contracts=_contracts(
                SourceObjectContract(
                    source_object_type="issue",
                    event_types=frozenset(
                        {
                            "jira.issue.created",
                            "jira.issue.updated",
                            "jira.issue.status_changed",
                            "jira.issue.commented",
                        }
                    ),
                    required_payload_fields=frozenset({"title", "source_url"}),
                ),
                SourceObjectContract(
                    source_object_type="sprint",
                    event_types=frozenset(
                        {
                            "jira.sprint.started",
                            "jira.sprint.closed",
                            "jira.sprint.updated",
                        }
                    ),
                    required_payload_fields=frozenset({"title", "source_url"}),
                ),
            ),
        ),
        SourceSystem.TELEGRAM.value: IntegrationSourceSpec(
            source_system=SourceSystem.TELEGRAM,
            display_name="Telegram",
            source_kind="command_interface",
            read_only_first=True,
            write_requires_approval=True,
            connector_layer_only=True,
            llm_direct_access_allowed=False,
            object_contracts=_contracts(
                SourceObjectContract(
                    source_object_type="command",
                    event_types=frozenset({"telegram.command.received"}),
                    required_payload_fields=frozenset({"text"}),
                ),
                SourceObjectContract(
                    source_object_type="message",
                    event_types=frozenset({"telegram.message.received"}),
                    required_payload_fields=frozenset({"text"}),
                ),
                SourceObjectContract(
                    source_object_type="approval_response",
                    event_types=frozenset({"telegram.approval.received"}),
                    required_payload_fields=frozenset({"text"}),
                ),
            ),
        ),
        SourceSystem.INTERNAL.value: IntegrationSourceSpec(
            source_system=SourceSystem.INTERNAL,
            display_name="Internal",
            source_kind="system",
            read_only_first=True,
            write_requires_approval=True,
            connector_layer_only=True,
            llm_direct_access_allowed=False,
            object_contracts=_contracts(
                SourceObjectContract(
                    source_object_type="system_event",
                    event_types=frozenset({"internal.system_event.recorded"}),
                    required_payload_fields=frozenset({"title"}),
                ),
            ),
        ),
    }
)


def get_integration_source(source_system: str) -> IntegrationSourceSpec | None:
    return INTEGRATION_SOURCE_REGISTRY.get(source_system)


def get_source_object_contract(
    source_system: str,
    source_object_type: str,
) -> SourceObjectContract | None:
    source_spec = get_integration_source(source_system)
    if source_spec is None:
        return None

    return source_spec.object_contracts.get(source_object_type)


def validate_source_event_contract(
    *,
    source_system: str,
    source_object_type: str,
    event_type: str,
    payload: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    source_spec = get_integration_source(source_system)
    if source_spec is None:
        return [f"unsupported source_system: {source_system}"]

    object_contract = source_spec.object_contracts.get(source_object_type)
    if object_contract is None:
        return [
            f"unsupported source_object_type for {source_system}: {source_object_type}"
        ]

    if event_type not in object_contract.event_types:
        errors.append(
            f"unsupported event_type for {source_system}.{source_object_type}: {event_type}"
        )

    for field in sorted(object_contract.required_payload_fields):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"missing required payload field: {field}")

    return errors
