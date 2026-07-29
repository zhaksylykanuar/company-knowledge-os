from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.action_models import (
    ACTION_CREATED_BY_AI,
    ACTION_CREATED_BY_SYSTEM,
    ACTION_CREATED_BY_USER,
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_PROPOSAL_STATUS_PROPOSED,
    ACTION_PROPOSAL_STATUS_REJECTED,
    ACTION_TARGET_PROVIDER_GITHUB,
    ACTION_TARGET_PROVIDER_INTERNAL,
    ACTION_TYPE_CREATE_GITHUB_ISSUE,
    ACTION_TYPE_INTERNAL_TODO,
    ActionProposal,
)
from app.services.company_memory_event_service import (
    append_action_proposal_created_memory_event,
    append_action_proposal_decision_memory_event,
)

ACTION_PROPOSAL_APPROVAL_WARNING = (
    "Action approved locally. Execution is deferred to a later step."
)
ACTION_PROPOSAL_NO_EXECUTION_WARNING = (
    "Action proposal API is local-only and does not execute provider actions."
)
ACTION_PROPOSAL_NOT_FOUND = "action proposal not found"
ACTION_PROPOSAL_INVALID_TRANSITION = "action proposal is not in proposed status"
ACTION_PROPOSAL_PAYLOAD_MAX_BYTES = 64 * 1024
ACTION_PROPOSAL_EVIDENCE_REFS_MAX_BYTES = 64 * 1024
ACTION_PROPOSAL_EVIDENCE_REFS_MAX_ITEMS = 50
ACTION_EVIDENCE_ALLOWED_KEYS = frozenset(
    {
        "evidence_ref_id",
        "id",
        "kind",
        "record_id",
        "ref",
        "source",
        "source_record_id",
        "url",
    }
)
ACTION_EVIDENCE_KIND_MAX_LENGTH = 80
ACTION_EVIDENCE_SELECTOR_MAX_LENGTH = 500
ACTION_EVIDENCE_SOURCE_MAX_LENGTH = 80

VALID_TARGET_PROVIDERS = {
    ACTION_TARGET_PROVIDER_GITHUB,
    ACTION_TARGET_PROVIDER_INTERNAL,
}
VALID_ACTION_TYPES = {
    ACTION_TYPE_CREATE_GITHUB_ISSUE,
    ACTION_TYPE_INTERNAL_TODO,
}
VALID_PROVIDER_ACTION_PAIRS = {
    (ACTION_TARGET_PROVIDER_GITHUB, ACTION_TYPE_CREATE_GITHUB_ISSUE),
    (ACTION_TARGET_PROVIDER_INTERNAL, ACTION_TYPE_INTERNAL_TODO),
}
VALID_CREATED_BY = {
    ACTION_CREATED_BY_USER,
    ACTION_CREATED_BY_SYSTEM,
    ACTION_CREATED_BY_AI,
}
SECRET_LIKE_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "api_key",
    "private_key",
}


class ActionProposalError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ActionProposalNotFoundError(ActionProposalError):
    pass


class ActionProposalTransitionError(ActionProposalError):
    pass


@dataclass(frozen=True)
class ActionProposalCreateInput:
    target_provider: str
    action_type: str
    title: str
    description: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    briefing_item_id: UUID | None = None
    created_by: str = ACTION_CREATED_BY_USER


@dataclass(frozen=True)
class ActionProposalFilters:
    status: str | None = None
    target_provider: str | None = None
    action_type: str | None = None
    limit: int = 50


def validate_action_proposal_input(payload: ActionProposalCreateInput) -> None:
    target_provider = _normalize_value(payload.target_provider)
    action_type = _normalize_value(payload.action_type)
    created_by = _normalize_value(payload.created_by)
    title = payload.title.strip()

    if target_provider not in VALID_TARGET_PROVIDERS:
        raise ActionProposalError("unknown target_provider")
    if action_type not in VALID_ACTION_TYPES:
        raise ActionProposalError("unknown action_type")
    if (target_provider, action_type) not in VALID_PROVIDER_ACTION_PAIRS:
        raise ActionProposalError("invalid provider/action pair")
    if not title:
        raise ActionProposalError("title is required")
    if not isinstance(payload.payload, dict):
        raise ActionProposalError("payload must be an object")
    if not isinstance(payload.evidence_refs, list):
        raise ActionProposalError("evidence_refs must be a list")
    if len(payload.evidence_refs) > ACTION_PROPOSAL_EVIDENCE_REFS_MAX_ITEMS:
        raise ActionProposalError(
            f"evidence_refs exceeds {ACTION_PROPOSAL_EVIDENCE_REFS_MAX_ITEMS} items"
        )
    if any(not isinstance(ref, Mapping) for ref in payload.evidence_refs):
        raise ActionProposalError("evidence_refs items must be objects")
    _validate_json_byte_size(
        payload.payload,
        field_name="payload",
        max_bytes=ACTION_PROPOSAL_PAYLOAD_MAX_BYTES,
    )
    _validate_json_byte_size(
        payload.evidence_refs,
        field_name="evidence_refs",
        max_bytes=ACTION_PROPOSAL_EVIDENCE_REFS_MAX_BYTES,
    )
    if any(not action_evidence_ref_matches_schema(ref) for ref in payload.evidence_refs):
        raise ActionProposalError(
            "evidence_refs items must match the evidence_ref.v1 schema"
        )
    if created_by not in VALID_CREATED_BY:
        raise ActionProposalError("unknown created_by")
    secret_key = _first_secret_like_key(payload.payload)
    if secret_key is not None:
        raise ActionProposalError(f"payload contains secret-like key: {secret_key}")


async def create_action_proposal(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    created_by_user_id: UUID | None,
    payload: ActionProposalCreateInput,
) -> ActionProposal:
    validate_action_proposal_input(payload)
    created_by = _normalize_value(payload.created_by)
    proposal = ActionProposal(
        workspace_id=workspace_id,
        briefing_item_id=payload.briefing_item_id,
        target_provider=_normalize_value(payload.target_provider),
        action_type=_normalize_value(payload.action_type),
        title=payload.title.strip(),
        description=_optional_text(payload.description),
        payload=dict(payload.payload),
        evidence_refs=list(payload.evidence_refs),
        created_by=created_by,
        created_by_user_id=(
            created_by_user_id if created_by == ACTION_CREATED_BY_USER else None
        ),
    )
    session.add(proposal)
    await session.flush()
    await session.refresh(proposal)
    await append_action_proposal_created_memory_event(
        session,
        proposal=proposal,
    )
    return proposal


async def list_action_proposals(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    filters: ActionProposalFilters,
) -> list[ActionProposal]:
    statement = (
        select(ActionProposal)
        .where(ActionProposal.workspace_id == workspace_id)
        .order_by(ActionProposal.created_at.desc(), ActionProposal.id.desc())
        .limit(filters.limit)
    )
    if filters.status:
        statement = statement.where(ActionProposal.status == filters.status)
    if filters.target_provider:
        statement = statement.where(
            ActionProposal.target_provider == filters.target_provider
        )
    if filters.action_type:
        statement = statement.where(ActionProposal.action_type == filters.action_type)
    return list((await session.execute(statement)).scalars())


async def get_action_proposal(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal_id: UUID,
) -> ActionProposal | None:
    return await session.scalar(
        select(ActionProposal)
        .where(ActionProposal.workspace_id == workspace_id)
        .where(ActionProposal.id == proposal_id)
    )


async def approve_action_proposal(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal_id: UUID,
    approved_by_user_id: UUID,
) -> ActionProposal:
    proposal = await _get_action_proposal_or_raise(
        session,
        workspace_id=workspace_id,
        proposal_id=proposal_id,
    )
    _ensure_proposed(proposal)
    proposal.status = ACTION_PROPOSAL_STATUS_APPROVED
    proposal.approved_by_user_id = approved_by_user_id
    proposal.approved_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(proposal)
    await append_action_proposal_decision_memory_event(
        session,
        proposal=proposal,
        actor_user_id=approved_by_user_id,
    )
    return proposal


async def reject_action_proposal(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal_id: UUID,
    rejected_by_user_id: UUID,
    reason: str | None,
) -> ActionProposal:
    proposal = await _get_action_proposal_or_raise(
        session,
        workspace_id=workspace_id,
        proposal_id=proposal_id,
    )
    _ensure_proposed(proposal)
    proposal.status = ACTION_PROPOSAL_STATUS_REJECTED
    proposal.rejected_by_user_id = rejected_by_user_id
    proposal.rejected_at = datetime.now(timezone.utc)
    proposal.rejection_reason = _optional_text(reason)
    await session.flush()
    await session.refresh(proposal)
    await append_action_proposal_decision_memory_event(
        session,
        proposal=proposal,
        actor_user_id=rejected_by_user_id,
    )
    return proposal


def serialize_action_proposal(proposal: ActionProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "workspace_id": proposal.workspace_id,
        "briefing_item_id": proposal.briefing_item_id,
        "target_provider": proposal.target_provider,
        "action_type": proposal.action_type,
        "title": proposal.title,
        "description": proposal.description,
        "payload": proposal.payload or {},
        "status": proposal.status,
        "evidence_refs": proposal.evidence_refs or [],
        "created_by": proposal.created_by,
        "created_by_user_id": proposal.created_by_user_id,
        "approved_by_user_id": proposal.approved_by_user_id,
        "approved_at": proposal.approved_at,
        "rejected_by_user_id": proposal.rejected_by_user_id,
        "rejected_at": proposal.rejected_at,
        "rejection_reason": proposal.rejection_reason,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
        "proposal_version": action_proposal_version(proposal),
        "is_live": False,
        "execution_started": False,
        "warnings": [ACTION_PROPOSAL_NO_EXECUTION_WARNING],
    }


def action_proposal_version(proposal: ActionProposal) -> str:
    """Return one opaque version over the exact persisted proposal row.

    Canonical evidence rows may affect whether Headquarters ranks a proposal,
    but they do not silently change the proposal command version. A local
    decision therefore binds to the row the actor reviewed while Headquarters
    continues to validate evidence independently.
    """

    material = {
        "id": proposal.id,
        "workspace_id": proposal.workspace_id,
        "briefing_item_id": proposal.briefing_item_id,
        "target_provider": proposal.target_provider,
        "action_type": proposal.action_type,
        "title": proposal.title,
        "description": proposal.description,
        "payload": proposal.payload,
        "status": proposal.status,
        "evidence_refs": proposal.evidence_refs,
        "created_by": proposal.created_by,
        "created_by_user_id": proposal.created_by_user_id,
        "approved_by_user_id": proposal.approved_by_user_id,
        "approved_at": proposal.approved_at,
        "rejected_by_user_id": proposal.rejected_by_user_id,
        "rejected_at": proposal.rejected_at,
        "rejection_reason": proposal.rejection_reason,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
    }
    serialized = json.dumps(
        material,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=_proposal_version_json_default,
    )
    return f"ap1_{sha256(serialized.encode('utf-8')).hexdigest()}"


def action_evidence_ref_matches_schema(ref: Mapping[str, Any]) -> bool:
    """Validate the durable evidence_ref.v1 JSON shape without database reads."""

    if any(not isinstance(key, str) for key in ref):
        return False
    if not set(ref).issubset(ACTION_EVIDENCE_ALLOWED_KEYS):
        return False
    kind = _strict_text(ref.get("kind"))
    source = _strict_text(ref.get("source"))
    if (
        kind is None
        or len(kind) > ACTION_EVIDENCE_KIND_MAX_LENGTH
        or source is None
        or len(source) > ACTION_EVIDENCE_SOURCE_MAX_LENGTH
    ):
        return False
    selector_keys = (
        "evidence_ref_id",
        "source_record_id",
        "record_id",
        "ref",
        "id",
    )
    selectors = {
        key: _strict_text(ref.get(key))
        for key in selector_keys
        if ref.get(key) is not None
    }
    if not selectors or any(value is None for value in selectors.values()):
        return False
    if any(
        len(value) > ACTION_EVIDENCE_SELECTOR_MAX_LENGTH
        for value in selectors.values()
        if value is not None
    ):
        return False
    for key in ("evidence_ref_id", "source_record_id", "record_id"):
        value = selectors.get(key)
        if value is not None:
            try:
                UUID(value)
            except ValueError:
                return False
    url = ref.get("url")
    return url is None or _action_evidence_url_is_safe(url)


def _strict_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if any(character.isspace() and character != " " for character in value):
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    return value


def _action_evidence_url_is_safe(value: Any) -> bool:
    text = _strict_text(value)
    if text is None or len(text) > 1000 or "\\" in text or any(
        character.isspace() for character in text
    ):
        return False
    try:
        parsed = urlsplit(text)
        parsed.port
    except ValueError:
        return False
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)


def _proposal_version_json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"unsupported proposal version value: {type(value).__name__}")


async def _get_action_proposal_or_raise(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal_id: UUID,
) -> ActionProposal:
    proposal = await get_action_proposal(
        session,
        workspace_id=workspace_id,
        proposal_id=proposal_id,
    )
    if proposal is None:
        raise ActionProposalNotFoundError(ACTION_PROPOSAL_NOT_FOUND)
    return proposal


def _ensure_proposed(proposal: ActionProposal) -> None:
    if proposal.status != ACTION_PROPOSAL_STATUS_PROPOSED:
        raise ActionProposalTransitionError(ACTION_PROPOSAL_INVALID_TRANSITION)


def _normalize_value(value: str) -> str:
    return value.strip().casefold()


def _optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _first_secret_like_key(payload: Mapping[str, Any]) -> str | None:
    for key, value in payload.items():
        key_text = str(key).strip().casefold()
        if key_text in SECRET_LIKE_KEYS:
            return key_text
        if isinstance(value, Mapping):
            nested = _first_secret_like_key(value)
            if nested is not None:
                return nested
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping):
                    nested = _first_secret_like_key(item)
                    if nested is not None:
                        return nested
    return None


def _validate_json_byte_size(
    value: object,
    *,
    field_name: str,
    max_bytes: int,
) -> None:
    try:
        # Match SQLAlchemy's default JSON serializer so PostgreSQL
        # octet_length(...::text) enforces the same boundary for HQ reads.
        serialized = json.dumps(
            value,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ActionProposalError(f"{field_name} must be JSON serializable") from exc
    if len(serialized) > max_bytes:
        raise ActionProposalError(f"{field_name} exceeds {max_bytes} UTF-8 serialized bytes")
