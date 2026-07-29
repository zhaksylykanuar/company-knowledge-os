from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.api.workspace_auth import (
    WorkspaceAccess,
    require_workspace_access,
    require_workspace_role,
)
from app.db.base import AsyncSessionLocal
from app.db.identity_models import MEMBERSHIP_ROLE_ADMIN
from app.services.ai_settings_service import (
    AISettingsError,
    AISettingsInput,
    check_workspace_ai_connection,
    get_workspace_ai_settings,
    remove_workspace_ai_credential,
    save_workspace_ai_settings,
)
from app.services.secret_encryption import SecretEncryptionError


router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/ai-settings",
    tags=["ai-settings"],
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AIDataPolicyRead(_StrictModel):
    version: str = Field(min_length=1, max_length=80)
    acknowledged: bool
    acknowledged_at: str | None
    notice_code: Literal["provider_retention_may_apply"]


class AICheckReceiptRead(_StrictModel):
    status: Literal["passed", "failed"]
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=240)
    checked_at: str
    model: str | None = Field(default=None, max_length=80)
    provider_call_performed: bool
    company_data_sent: Literal[False]
    external_write_performed: Literal[False]


class AIStoredCheckRead(_StrictModel):
    status: Literal["passed", "failed"]
    code: str = Field(min_length=1, max_length=80)
    checked_at: str
    model: str | None = Field(default=None, max_length=80)
    provider_call_performed: Literal[True]


class AIBoundaryRead(_StrictModel):
    provider_call_on_apply: Literal[False]
    company_data_sent_during_check: Literal[False]
    stored_secret_returned: Literal[False]
    chat_persisted: Literal[False]
    external_writes: Literal[False]


class AISettingsRead(_StrictModel):
    contract: Literal["ai-settings.v1"]
    workspace_id: str
    provider: Literal["openai"]
    configured: bool
    enabled: bool
    server_permitted: bool
    model: Literal["gpt-5.6", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]
    supported_models: list[
        Literal["gpt-5.6", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]
    ] = Field(min_length=4, max_length=4)
    reasoning_effort: Literal["low", "medium", "high"]
    max_output_tokens: int = Field(ge=400, le=4_000)
    configuration_version: int = Field(ge=0)
    key_present: bool
    data_policy: AIDataPolicyRead
    last_check: AIStoredCheckRead | None
    boundary: AIBoundaryRead


class AISettingsApplyRequest(_StrictModel):
    enabled: bool
    data_policy_acknowledged: bool
    model: Literal["gpt-5.6", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]
    reasoning_effort: Literal["low", "medium", "high"]
    max_output_tokens: int = Field(ge=400, le=4_000)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=512)


@router.get("", response_model=AISettingsRead)
async def read_ai_settings(
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> AISettingsRead:
    _set_private_no_store(response)
    async with AsyncSessionLocal() as session:
        result = await get_workspace_ai_settings(
            session,
            workspace_id=access.workspace_membership.workspace.id,
        )
    return AISettingsRead.model_validate(result)


@router.post("/configuration", response_model=AISettingsRead)
async def apply_ai_settings(
    payload: AISettingsApplyRequest,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> AISettingsRead:
    _set_private_no_store(response)
    try:
        async with AsyncSessionLocal() as session:
            result = await save_workspace_ai_settings(
                session,
                workspace_id=access.workspace_membership.workspace.id,
                requested_by_user_id=access.workspace_membership.user.id,
                payload=AISettingsInput(
                    enabled=payload.enabled,
                    data_policy_acknowledged=payload.data_policy_acknowledged,
                    model=payload.model,
                    reasoning_effort=payload.reasoning_effort,
                    max_output_tokens=payload.max_output_tokens,
                    api_key=(
                        payload.api_key.get_secret_value()
                        if payload.api_key is not None
                        else None
                    ),
                ),
            )
            await session.commit()
    except AISettingsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except SecretEncryptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="secure AI credential storage is unavailable",
        ) from exc
    return AISettingsRead.model_validate(result)


@router.delete("/configuration", response_model=AISettingsRead)
async def delete_ai_credential(
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> AISettingsRead:
    _set_private_no_store(response)
    async with AsyncSessionLocal() as session:
        result = await remove_workspace_ai_credential(
            session,
            workspace_id=access.workspace_membership.workspace.id,
        )
        await session.commit()
    return AISettingsRead.model_validate(result)


@router.post("/check", response_model=AICheckReceiptRead)
async def check_ai_connection(
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> AICheckReceiptRead:
    _set_private_no_store(response)
    try:
        result = await check_workspace_ai_connection(
            workspace_id=access.workspace_membership.workspace.id,
            requested_by_user_id=access.workspace_membership.user.id,
        )
    except AISettingsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return AICheckReceiptRead.model_validate(result)


def _set_private_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
