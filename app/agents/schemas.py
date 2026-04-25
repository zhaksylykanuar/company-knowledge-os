from typing import Literal

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    source_document_id: str
    chunk_id: str
    raw_object_ref: str
    source_url: str | None = None
    quote: str = Field(min_length=1, max_length=800)


class ExtractedTask(BaseModel):
    title: str
    owner: str | None = None
    due_date: str | None = None
    task_type: Literal["task", "follow_up", "commitment"] = "task"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[EvidenceRef] = Field(min_length=1)


class ExtractedDecision(BaseModel):
    title: str
    decision: str
    owner: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[EvidenceRef] = Field(min_length=1)


class ExtractedRisk(BaseModel):
    title: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[EvidenceRef] = Field(min_length=1)


class ExtractionResult(BaseModel):
    tasks: list[ExtractedTask] = Field(default_factory=list)
    decisions: list[ExtractedDecision] = Field(default_factory=list)
    risks: list[ExtractedRisk] = Field(default_factory=list)
    unsupported_claims_rejected: int = 0
