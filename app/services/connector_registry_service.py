"""Connector framework registry (read-only, deterministic).

FounderOS MVP scope (founderOS_MASTER_PLAYBOOK.md 1.5) requires a connector
framework covering GitHub, Jira, Gmail, and Google Drive. This module is the
single source of truth for what connectors exist, their MVP status, and their
per-workspace connection state.

It is intentionally read-only and side-effect free: it reads existing
``integration_connections`` rows and static provider descriptors, performs no
provider calls, starts no sync, and returns no secret values (tokens are never
read or emitted). It gives the product a real connector surface that Jira /
Gmail / Drive connectors can plug into as they are implemented, without inventing
a parallel architecture.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import (
    CONNECTOR_DESCRIPTORS,
    CONNECTOR_STATUS_AVAILABLE,
    CONNECTOR_STATUS_PLANNED,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    IntegrationConnection,
)


async def _connection_counts_by_provider(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, dict[str, int]]:
    """Count integration connection rows per provider for a workspace.

    Reads only non-secret columns (provider/status); never touches encrypted
    token columns.
    """

    rows = (
        await session.execute(
            select(
                IntegrationConnection.provider,
                IntegrationConnection.status,
            ).where(IntegrationConnection.workspace_id == workspace_id)
        )
    ).all()

    counts: dict[str, dict[str, int]] = {}
    for provider, status in rows:
        bucket = counts.setdefault(provider, {"total": 0, "connected": 0})
        bucket["total"] += 1
        if status == INTEGRATION_CONNECTION_STATUS_CONNECTED:
            bucket["connected"] += 1
    return counts


async def build_workspace_connector_registry(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    """Return the deterministic connector registry for a workspace.

    Read-only: no provider calls, no sync, no external writes, no secret values.
    """

    counts = await _connection_counts_by_provider(session, workspace_id=workspace_id)

    connectors: list[dict[str, Any]] = []
    for descriptor in CONNECTOR_DESCRIPTORS:
        provider_counts = counts.get(descriptor.provider, {"total": 0, "connected": 0})
        connectors.append(
            {
                "provider": descriptor.provider,
                "name": descriptor.name,
                "status": descriptor.status,
                "read_only": descriptor.read_only,
                "manage_path": descriptor.manage_path,
                "summary": descriptor.summary,
                "connection_count": provider_counts["total"],
                "connected_count": provider_counts["connected"],
                "has_connection": provider_counts["total"] > 0,
            }
        )

    available = sum(
        1 for c in connectors if c["status"] == CONNECTOR_STATUS_AVAILABLE
    )
    planned = sum(1 for c in connectors if c["status"] == CONNECTOR_STATUS_PLANNED)

    return {
        "workspace_id": str(workspace_id),
        "connectors": connectors,
        "summary": {
            "total": len(connectors),
            "available": available,
            "planned": planned,
            "connected": sum(1 for c in connectors if c["connected_count"] > 0),
        },
        "boundary": {
            "provider_calls": False,
            "external_writes": False,
            "llm": False,
            "reads_secrets": False,
        },
    }
