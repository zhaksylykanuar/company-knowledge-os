"""Static MVP connector catalog.

The per-workspace registry service combines these descriptors with local
``integration_connections`` rows. Provider-specific connector implementations
should extend this package and keep the catalog as the product-visible source of
truth for connector availability.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db.integration_models import (
    INTEGRATION_PROVIDER_DRIVE,
    INTEGRATION_PROVIDER_GITHUB,
    INTEGRATION_PROVIDER_GMAIL,
    INTEGRATION_PROVIDER_JIRA,
)

CONNECTOR_STATUS_AVAILABLE = "available"
CONNECTOR_STATUS_PLANNED = "planned"


@dataclass(frozen=True)
class ConnectorDescriptor:
    provider: str
    name: str
    status: str
    read_only: bool
    manage_path: str | None
    summary: str


CONNECTOR_DESCRIPTORS: tuple[ConnectorDescriptor, ...] = (
    ConnectorDescriptor(
        provider=INTEGRATION_PROVIDER_GITHUB,
        name="GitHub",
        status=CONNECTOR_STATUS_AVAILABLE,
        read_only=True,
        manage_path="/github",
        summary=(
            "Read-only repository/issue/PR normalization into canonical Company "
            "Brain state. Real provider reads require a human-approved GitHub App "
            "run."
        ),
    ),
    ConnectorDescriptor(
        provider=INTEGRATION_PROVIDER_JIRA,
        name="Jira",
        status=CONNECTOR_STATUS_AVAILABLE,
        read_only=True,
        manage_path="/jira",
        summary=(
            "Local read-only issue import into canonical SourceRecord/Task state. "
            "The MVP path accepts pasted/exported Jira issue JSON only; no provider "
            "calls or writes are performed."
        ),
    ),
    ConnectorDescriptor(
        provider=INTEGRATION_PROVIDER_GMAIL,
        name="Gmail",
        status=CONNECTOR_STATUS_AVAILABLE,
        read_only=True,
        manage_path="/gmail",
        summary=(
            "Local read-only message import into canonical SourceRecord state. "
            "The MVP path accepts pasted/exported Gmail message JSON only (no raw "
            "body); no provider calls or writes are performed."
        ),
    ),
    ConnectorDescriptor(
        provider=INTEGRATION_PROVIDER_DRIVE,
        name="Google Drive",
        status=CONNECTOR_STATUS_AVAILABLE,
        read_only=True,
        manage_path="/drive",
        summary=(
            "Local read-only file metadata import into canonical SourceRecord "
            "state. The MVP path accepts pasted/exported Drive file JSON only "
            "(no raw document body); no provider calls or writes are performed."
        ),
    ),
)
