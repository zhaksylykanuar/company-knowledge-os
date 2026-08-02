from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import Field, StringConstraints, field_validator, model_validator

from app.api.headquarters import (
    HeadquartersActionRead,
    HeadquartersEvidenceRefRead,
    StrictReadModel,
)
from app.api.workspace_auth import WorkspaceAccess, require_workspace_access
from app.services.assistant_query_service import (
    ASSISTANT_INTENTS,
    ASSISTANT_QUERY_MAX_CHARS,
    ASSISTANT_RESPONSE_TEXT_MAX_CHARS,
    AssistantRateLimitedError,
    AssistantResponseTooLargeError,
    AssistantSnapshotChangedError,
    query_workspace_assistant,
)
from app.services.headquarters_read_service import HeadquartersAccessChangedError


router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/assistant",
    tags=["assistant"],
)

AssistantIntent = Literal[
    "action_request",
    "briefing",
    "company_person",
    "current_priority",
    "decision_status",
    "evidence",
    "owners",
    "second_opinion",
    "sources",
    "unsupported",
    "waiting_decisions",
    "why_now",
]
BoundedWarning = Annotated[str, StringConstraints(min_length=1, max_length=160)]


class AssistantQueryRequest(StrictReadModel):
    query: str = Field(min_length=1, max_length=ASSISTANT_QUERY_MAX_CHARS)
    expected_snapshot_id: str = Field(pattern=r"^hqs1_[0-9a-f]{64}$")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        if any(ord(character) < 32 and character not in "\t\n\r" for character in stripped):
            raise ValueError("query contains control characters")
        return stripped


class AssistantSuggestionRead(StrictReadModel):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=ASSISTANT_QUERY_MAX_CHARS)


class AssistantPerspectiveRead(StrictReadModel):
    text: str | None = Field(
        default=None,
        min_length=1,
        max_length=ASSISTANT_RESPONSE_TEXT_MAX_CHARS,
    )
    citation_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("citation_ids")
    @classmethod
    def validate_unique_citation_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("perspective citation ids must be unique")
        if any(not citation_id or len(citation_id) > 180 for citation_id in value):
            raise ValueError("perspective citation id is invalid")
        return value

    @model_validator(mode="after")
    def validate_support_shape(self) -> AssistantPerspectiveRead:
        if self.text is None and self.citation_ids:
            raise ValueError("empty perspective cannot cite evidence")
        if self.text is not None and not self.citation_ids:
            raise ValueError("non-empty perspective requires evidence")
        return self


class AssistantPerspectivesRead(StrictReadModel):
    fact: AssistantPerspectiveRead
    interpretation: AssistantPerspectiveRead
    objection: AssistantPerspectiveRead
    recommendation: AssistantPerspectiveRead


class AssistantQueryResponse(StrictReadModel):
    contract_version: Literal["assistant.v2"]
    intent: AssistantIntent
    text: str = Field(min_length=1, max_length=ASSISTANT_RESPONSE_TEXT_MAX_CHARS)
    perspectives: AssistantPerspectivesRead
    citations: list[HeadquartersEvidenceRefRead] = Field(default_factory=list, max_length=8)
    suggestions: list[AssistantSuggestionRead] = Field(default_factory=list, max_length=4)
    action: HeadquartersActionRead | None = None
    snapshot_id: str = Field(pattern=r"^hqs1_[0-9a-f]{64}$")
    as_of: datetime
    partial: bool
    warnings: list[BoundedWarning] = Field(default_factory=list, max_length=8)
    is_live: Literal[True]
    llm_used: bool
    validation_status: Literal["deterministic", "evidence_validated"]

    @field_validator("intent")
    @classmethod
    def validate_allowlisted_intent(cls, value: str) -> str:
        if value not in ASSISTANT_INTENTS:
            raise ValueError("assistant intent is not allowlisted")
        return value

    @model_validator(mode="after")
    def validate_evidence_resolution(self) -> AssistantQueryResponse:
        available_ids = {citation.id for citation in self.citations}
        for perspective in (
            self.perspectives.fact,
            self.perspectives.interpretation,
            self.perspectives.objection,
            self.perspectives.recommendation,
        ):
            if not set(perspective.citation_ids).issubset(available_ids):
                raise ValueError("perspective references unavailable evidence")
        if self.llm_used != (self.validation_status == "evidence_validated"):
            raise ValueError("LLM status does not match validation status")
        if self.llm_used and self.perspectives.fact.text is None:
            raise ValueError("validated LLM answer requires a fact")
        return self


@router.post("/query", response_model=AssistantQueryResponse)
async def query_assistant(
    workspace_id: UUID,
    payload: AssistantQueryRequest,
    response: Response,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> AssistantQueryResponse:
    try:
        result = await query_workspace_assistant(
            workspace_id=workspace_id,
            user_id=access.workspace_membership.user.id,
            query=payload.query,
            expected_snapshot_id=payload.expected_snapshot_id,
        )
    except HeadquartersAccessChangedError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace not found",
        ) from exc
    except AssistantSnapshotChangedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="snapshot_changed",
        ) from exc
    except AssistantRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="assistant query rate limit exceeded",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="assistant query timed out",
        ) from exc
    except AssistantResponseTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="assistant response unavailable",
        ) from exc

    response.headers["Cache-Control"] = "private, no-store"
    return AssistantQueryResponse.model_validate(result)
