from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, SecretStr

from app.api.workspace_auth import (
    WorkspaceAccess,
    require_workspace_access,
    require_workspace_role,
)
from app.db.base import AsyncSessionLocal
from app.db.identity_models import MEMBERSHIP_ROLE_ADMIN
from app.services.connector_control_service import (
    ConnectorConfigurationInput,
    ConnectorControlError,
    apply_connector_configuration,
    build_connector_control_center,
    disconnect_connector_configuration,
    run_connector_read_check,
    run_connector_write_readiness_check,
)
from app.services.connector_registry_service import (
    build_workspace_connector_registry,
)
from app.services.real_connector_guard import RealConnectorsDisabledError
from app.services.secret_encryption import SecretEncryptionError

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


class ConnectorControlRead(BaseModel):
    provider: str
    name: str
    state: str
    connection_status: str | None = None
    configured: bool
    credential_present: bool
    removable_credential_present: bool
    auth_method: str | None = None
    display_name: str | None = None
    account_label: str | None = None
    base_url: str | None = None
    scopes: list[str] = Field(default_factory=list)
    last_checked_at: str | None = None
    read_check: dict[str, Any] | None = None
    write_check: dict[str, Any] | None = None
    read_test_supported: bool
    write_test_mode: str
    manage_path: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ConnectorControlSummary(BaseModel):
    total: int
    configured: int
    verified: int
    errors: int


class ConnectorControlBoundary(BaseModel):
    provider_calls: bool
    external_writes: bool
    stored_secrets_returned: bool
    write_checks_are_dry_run: bool


class ConnectorControlCenterResponse(BaseModel):
    contract: str
    workspace_id: str
    connectors: list[ConnectorControlRead] = Field(default_factory=list)
    summary: ConnectorControlSummary
    boundary: ConnectorControlBoundary


class ConnectorConfigurationApplyRequest(BaseModel):
    auth_method: str = Field(min_length=1, max_length=80)
    access_token: SecretStr = Field(min_length=1, max_length=8192)
    display_name: str | None = Field(default=None, max_length=255)
    base_url: str | None = Field(default=None, max_length=500)
    account_email: str | None = Field(default=None, max_length=320)
    scopes: list[str] = Field(default_factory=list, max_length=50)


class ConnectorCheckResponse(BaseModel):
    status: str
    code: str
    message: str
    checked_at: str
    provider_call_performed: bool
    external_write_performed: bool
    account_label: str | None = None
    scopes: list[str] | None = None
    records_visible: int | None = None
    checks: dict[str, bool] | None = None


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


@router.get("/control-center", response_model=ConnectorControlCenterResponse)
async def get_connector_control_center(
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> ConnectorControlCenterResponse:
    _set_private_no_store(response)
    async with AsyncSessionLocal() as session:
        result = await build_connector_control_center(
            session,
            workspace_id=access.workspace_membership.workspace.id,
        )
    return ConnectorControlCenterResponse.model_validate(result)


@router.post(
    "/{provider}/configuration",
    response_model=ConnectorControlRead,
)
async def save_connector_configuration(
    provider: str,
    payload: ConnectorConfigurationApplyRequest,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> ConnectorControlRead:
    _set_private_no_store(response)
    try:
        async with AsyncSessionLocal() as session:
            result = await apply_connector_configuration(
                session,
                workspace_id=access.workspace_membership.workspace.id,
                payload=ConnectorConfigurationInput(
                    provider=provider,
                    auth_method=payload.auth_method,
                    access_token=payload.access_token.get_secret_value(),
                    display_name=payload.display_name,
                    base_url=payload.base_url,
                    account_email=payload.account_email,
                    scopes=tuple(payload.scopes),
                ),
            )
            await session.commit()
    except ConnectorControlError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except SecretEncryptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="secure connector credential storage is unavailable",
        ) from exc
    return ConnectorControlRead.model_validate(result)


@router.delete(
    "/{provider}/configuration",
    response_model=ConnectorControlRead,
)
async def disconnect_connector_configuration_route(
    provider: str,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> ConnectorControlRead:
    _set_private_no_store(response)
    try:
        async with AsyncSessionLocal() as session:
            result = await disconnect_connector_configuration(
                session,
                workspace_id=access.workspace_membership.workspace.id,
                provider=provider,
            )
            await session.commit()
    except ConnectorControlError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return ConnectorControlRead.model_validate(result)


@router.post(
    "/{provider}/checks/read",
    response_model=ConnectorCheckResponse,
)
async def check_connector_read_access(
    provider: str,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> ConnectorCheckResponse:
    _set_private_no_store(response)
    try:
        async with AsyncSessionLocal() as session:
            result = await run_connector_read_check(
                session,
                workspace_id=access.workspace_membership.workspace.id,
                provider=provider,
                requested_by_operator=access.actor.is_operator,
            )
            await session.commit()
    except ConnectorControlError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RealConnectorsDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.detail,
        ) from exc
    return ConnectorCheckResponse.model_validate(result)


@router.post(
    "/{provider}/checks/write",
    response_model=ConnectorCheckResponse,
)
async def check_connector_write_readiness(
    provider: str,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> ConnectorCheckResponse:
    _set_private_no_store(response)
    try:
        async with AsyncSessionLocal() as session:
            result = await run_connector_write_readiness_check(
                session,
                workspace_id=access.workspace_membership.workspace.id,
                provider=provider,
            )
            await session.commit()
    except ConnectorControlError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ConnectorCheckResponse.model_validate(result)


def _set_private_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
