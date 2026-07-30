"""Workspace-scoped AI configuration, encrypted credential lifecycle and probe."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.integration_models import (
    AI_CHECK_STATUS_FAILED,
    AI_CHECK_STATUS_PASSED,
    AI_PROVIDER_OPENAI,
    WorkspaceAIConfiguration,
)
from app.services.assistant_llm_service import (
    AssistantEvidenceFact,
    AssistantLLMRejectedError,
    AssistantLLMUnavailableError,
    generate_assistant_reasoning,
)
from app.services.secret_encryption import decrypt_secret, encrypt_secret


AI_SETTINGS_CONTRACT = "ai-settings.v1"
AI_DATA_POLICY_VERSION = "openai-api-data-controls-2026-07-29"
AI_DEFAULT_MODEL = "gpt-5.6"
AI_SUPPORTED_MODELS = (
    "gpt-5.6",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
)
AI_REASONING_EFFORTS = ("low", "medium", "high")


class AISettingsError(ValueError):
    """Safe settings validation error suitable for a product response."""


@dataclass(frozen=True, repr=False)
class AISettingsInput:
    enabled: bool
    data_policy_acknowledged: bool
    model: str
    reasoning_effort: Literal["low", "medium", "high"]
    max_output_tokens: int
    api_key: str | None = None


@dataclass(frozen=True, repr=False)
class AssistantRuntimeConfiguration:
    api_key: str
    model: str
    reasoning_effort: Literal["low", "medium", "high"]
    max_output_tokens: int
    timeout_seconds: float


@dataclass(frozen=True)
class AssistantRuntimeResolution:
    configuration: AssistantRuntimeConfiguration | None
    warning: str | None = None


async def get_workspace_ai_settings(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    configuration = await _configuration(session, workspace_id=workspace_id)
    return _settings_payload(configuration, workspace_id=workspace_id)


async def save_workspace_ai_settings(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    requested_by_user_id: UUID,
    payload: AISettingsInput,
) -> dict[str, Any]:
    model = _model(payload.model)
    effort = _reasoning_effort(payload.reasoning_effort)
    output_budget = _output_budget(payload.max_output_tokens)
    api_key = payload.api_key.strip() if payload.api_key else None

    configuration = await _configuration(
        session,
        workspace_id=workspace_id,
        for_update=True,
    )
    if configuration is None:
        configuration = WorkspaceAIConfiguration(
            workspace_id=workspace_id,
            model=model,
            reasoning_effort=effort,
            max_output_tokens=output_budget,
        )
        session.add(configuration)
    prior_fingerprint = _verification_fingerprint(configuration)

    if api_key:
        configuration.encrypted_api_key = encrypt_secret(api_key)
    if payload.enabled and not configuration.encrypted_api_key:
        raise AISettingsError("API key is required before AI can be enabled")
    if payload.enabled and not payload.data_policy_acknowledged:
        raise AISettingsError(
            "Provider data policy acknowledgement is required before AI can be enabled"
        )

    now = _utcnow()
    configuration.enabled = payload.enabled
    configuration.model = model
    configuration.reasoning_effort = effort
    configuration.max_output_tokens = output_budget
    configuration.configuration_version = (
        configuration.configuration_version + 1
        if configuration.id is not None
        else 1
    )
    if payload.data_policy_acknowledged:
        if (
            configuration.data_policy_version != AI_DATA_POLICY_VERSION
            or configuration.data_policy_acknowledged_at is None
        ):
            configuration.data_policy_acknowledged_at = now
            configuration.data_policy_acknowledged_by_user_id = requested_by_user_id
        configuration.data_policy_version = AI_DATA_POLICY_VERSION
    else:
        configuration.data_policy_version = None
        configuration.data_policy_acknowledged_at = None
        configuration.data_policy_acknowledged_by_user_id = None
        configuration.enabled = False

    if prior_fingerprint != _verification_fingerprint(configuration):
        _clear_check(configuration)
    await session.flush()
    return _settings_payload(configuration, workspace_id=workspace_id)


async def remove_workspace_ai_credential(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    configuration = await _configuration(
        session,
        workspace_id=workspace_id,
        for_update=True,
    )
    if configuration is None:
        return _settings_payload(None, workspace_id=workspace_id)
    configuration.encrypted_api_key = None
    configuration.enabled = False
    configuration.data_policy_version = None
    configuration.data_policy_acknowledged_at = None
    configuration.data_policy_acknowledged_by_user_id = None
    configuration.configuration_version += 1
    _clear_check(configuration)
    await session.flush()
    return _settings_payload(configuration, workspace_id=workspace_id)


async def check_workspace_ai_connection(
    *,
    workspace_id: UUID,
    requested_by_user_id: UUID,
) -> dict[str, Any]:
    if not settings.enable_llm:
        return _check_receipt(
            status="failed",
            code="server_gate_disabled",
            message="AI provider calls are disabled by the server safety gate.",
            provider_call_performed=False,
            model=None,
        )

    async with AsyncSessionLocal() as session:
        configuration = await _configuration(session, workspace_id=workspace_id)
        if configuration is None or not configuration.encrypted_api_key:
            raise AISettingsError("Save an API key before checking the connection")
        if (
            configuration.data_policy_version != AI_DATA_POLICY_VERSION
            or configuration.data_policy_acknowledged_at is None
        ):
            raise AISettingsError(
                "Acknowledge the current provider data policy before checking"
            )
        try:
            api_key = decrypt_secret(configuration.encrypted_api_key)
        except Exception as exc:
            raise AISettingsError("Saved AI credential is unavailable") from exc
        version = configuration.configuration_version
        model = _model(configuration.model)
        effort = _reasoning_effort(configuration.reasoning_effort)
        output_budget = _output_budget(configuration.max_output_tokens)

    probe_fact = AssistantEvidenceFact(
        id="connection.check",
        text="FounderOS AI connection check uses no company facts.",
        citation_ids=("internal:ai-settings-check",),
    )
    try:
        await generate_assistant_reasoning(
            api_key=api_key,
            model=model,
            reasoning_effort=effort,
            max_output_tokens=max(400, min(output_budget, 600)),
            timeout_seconds=settings.assistant_llm_timeout_seconds,
            safety_identifier=_safety_identifier(workspace_id, requested_by_user_id),
            query="Return the provided fact as the fact section.",
            facts=[probe_fact],
        )
    except AssistantLLMRejectedError:
        receipt = _check_receipt(
            status="failed",
            code="response_rejected",
            message="The provider answered, but the strict response check failed.",
            provider_call_performed=True,
            model=model,
        )
    except AssistantLLMUnavailableError:
        receipt = _check_receipt(
            status="failed",
            code="provider_unavailable",
            message="The provider connection could not be verified.",
            provider_call_performed=True,
            model=model,
        )
    else:
        receipt = _check_receipt(
            status="passed",
            code="connection_verified",
            message="The provider returned a strict evidence-bound response.",
            provider_call_performed=True,
            model=model,
        )

    async with AsyncSessionLocal() as session:
        current = await _configuration(
            session,
            workspace_id=workspace_id,
            for_update=True,
        )
        if current is None or current.configuration_version != version:
            await session.rollback()
            return _check_receipt(
                status="failed",
                code="configuration_changed",
                message="AI settings changed during the check. Run it again.",
                provider_call_performed=receipt["provider_call_performed"],
                model=model,
            )
        current.last_checked_at = _utcnow()
        current.last_check_status = receipt["status"]
        current.last_check_code = receipt["code"]
        current.last_check_model = model
        await session.commit()
    return receipt


async def resolve_assistant_runtime_configuration(
    *,
    workspace_id: UUID,
) -> AssistantRuntimeResolution:
    if not settings.enable_llm:
        return AssistantRuntimeResolution(configuration=None)

    async with AsyncSessionLocal() as session:
        configuration = await _configuration(session, workspace_id=workspace_id)
        if configuration is not None:
            if not configuration.enabled:
                return AssistantRuntimeResolution(
                    configuration=None,
                    warning="ai_disabled_in_settings",
                )
            if (
                configuration.data_policy_version != AI_DATA_POLICY_VERSION
                or configuration.data_policy_acknowledged_at is None
            ):
                return AssistantRuntimeResolution(
                    configuration=None,
                    warning="ai_data_policy_not_acknowledged",
                )
            if not configuration.encrypted_api_key:
                return AssistantRuntimeResolution(
                    configuration=None,
                    warning="ai_not_configured",
                )
            if configuration.last_check_status != AI_CHECK_STATUS_PASSED:
                return AssistantRuntimeResolution(
                    configuration=None,
                    warning="ai_not_verified",
                )
            try:
                api_key = decrypt_secret(configuration.encrypted_api_key)
            except Exception:
                return AssistantRuntimeResolution(
                    configuration=None,
                    warning="ai_credential_unavailable",
                )
            return AssistantRuntimeResolution(
                configuration=AssistantRuntimeConfiguration(
                    api_key=api_key,
                    model=_model(configuration.model),
                    reasoning_effort=_reasoning_effort(
                        configuration.reasoning_effort
                    ),
                    max_output_tokens=_output_budget(
                        configuration.max_output_tokens
                    ),
                    timeout_seconds=settings.assistant_llm_timeout_seconds,
                )
            )

    return AssistantRuntimeResolution(
        configuration=None,
        warning="ai_not_configured",
    )


async def _configuration(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    for_update: bool = False,
) -> WorkspaceAIConfiguration | None:
    statement = select(WorkspaceAIConfiguration).where(
        WorkspaceAIConfiguration.workspace_id == workspace_id
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


def _settings_payload(
    configuration: WorkspaceAIConfiguration | None,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    acknowledged = bool(
        configuration is not None
        and configuration.data_policy_version == AI_DATA_POLICY_VERSION
        and configuration.data_policy_acknowledged_at is not None
    )
    last_check = (
        {
            "status": configuration.last_check_status,
            "code": configuration.last_check_code,
            "checked_at": configuration.last_checked_at.isoformat(),
            "model": configuration.last_check_model,
            "provider_call_performed": True,
        }
        if configuration is not None
        and configuration.last_check_status in {
            AI_CHECK_STATUS_PASSED,
            AI_CHECK_STATUS_FAILED,
        }
        and configuration.last_check_code
        and configuration.last_checked_at
        else None
    )
    return {
        "contract": AI_SETTINGS_CONTRACT,
        "workspace_id": str(workspace_id),
        "provider": AI_PROVIDER_OPENAI,
        "configured": bool(
            configuration is not None and configuration.encrypted_api_key
        ),
        "enabled": bool(configuration is not None and configuration.enabled),
        "server_permitted": bool(settings.enable_llm),
        "model": configuration.model if configuration else AI_DEFAULT_MODEL,
        "supported_models": list(AI_SUPPORTED_MODELS),
        "reasoning_effort": (
            configuration.reasoning_effort if configuration else "medium"
        ),
        "max_output_tokens": (
            configuration.max_output_tokens if configuration else 1_200
        ),
        "configuration_version": (
            configuration.configuration_version if configuration else 0
        ),
        "key_present": bool(
            configuration is not None and configuration.encrypted_api_key
        ),
        "data_policy": {
            "version": AI_DATA_POLICY_VERSION,
            "acknowledged": acknowledged,
            "acknowledged_at": (
                configuration.data_policy_acknowledged_at.isoformat()
                if acknowledged
                and configuration is not None
                and configuration.data_policy_acknowledged_at
                else None
            ),
            "notice_code": "provider_retention_may_apply",
        },
        "last_check": last_check,
        "boundary": {
            "provider_call_on_apply": False,
            "company_data_sent_during_check": False,
            "stored_secret_returned": False,
            "chat_persisted": False,
            "external_writes": False,
        },
    }


def _check_receipt(
    *,
    status: Literal["passed", "failed"],
    code: str,
    message: str,
    provider_call_performed: bool,
    model: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "code": code,
        "message": message,
        "checked_at": _utcnow().isoformat(),
        "model": model,
        "provider_call_performed": provider_call_performed,
        "company_data_sent": False,
        "external_write_performed": False,
    }


def _verification_fingerprint(configuration: WorkspaceAIConfiguration) -> tuple[Any, ...]:
    return (
        configuration.encrypted_api_key,
        configuration.model,
        configuration.reasoning_effort,
        configuration.max_output_tokens,
        configuration.data_policy_version,
    )


def _clear_check(configuration: WorkspaceAIConfiguration) -> None:
    configuration.last_checked_at = None
    configuration.last_check_status = None
    configuration.last_check_code = None
    configuration.last_check_model = None


def _model(value: str) -> str:
    normalized = value.strip()
    if normalized not in AI_SUPPORTED_MODELS:
        raise AISettingsError("Unsupported AI model")
    return normalized


def _reasoning_effort(value: str) -> Literal["low", "medium", "high"]:
    normalized = value.strip().casefold()
    if normalized not in AI_REASONING_EFFORTS:
        raise AISettingsError("Unsupported reasoning effort")
    return cast(Literal["low", "medium", "high"], normalized)


def _output_budget(value: int) -> int:
    if isinstance(value, bool) or not 400 <= value <= 4_000:
        raise AISettingsError("AI output budget must be between 400 and 4000")
    return value


def _safety_identifier(workspace_id: UUID, user_id: UUID) -> str:
    return hashlib.sha256(
        f"founderos:{workspace_id}:{user_id}".encode("utf-8")
    ).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
