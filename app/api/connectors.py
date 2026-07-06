from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.workspace_auth import WorkspaceAccess, require_workspace_access
from app.db.base import AsyncSessionLocal
from app.services.connector_registry_service import (
    build_workspace_connector_registry,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/connectors",
    tags=["connectors"],
)


class ConnectorRead(BaseModel):
    provider: str
    name: str
    status: str
    read_only: bool
    manage_path: str | None = None
    summary: str
    connection_count: int
    connected_count: int
    has_connection: bool


class ConnectorRegistrySummary(BaseModel):
    total: int
    available: int
    planned: int
    connected: int


class ConnectorRegistryBoundary(BaseModel):
    provider_calls: bool
    external_writes: bool
    llm: bool
    reads_secrets: bool


class ConnectorRegistryResponse(BaseModel):
    workspace_id: str
    connectors: list[ConnectorRead] = Field(default_factory=list)
    summary: ConnectorRegistrySummary
    boundary: ConnectorRegistryBoundary


@router.get("", response_model=ConnectorRegistryResponse)
async def list_workspace_connectors(
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> ConnectorRegistryResponse:
    async with AsyncSessionLocal() as session:
        registry = await build_workspace_connector_registry(
            session,
            workspace_id=access.workspace_membership.workspace.id,
        )
    return ConnectorRegistryResponse.model_validate(registry)
