from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    source_document_id: str
    chunk_id: str
    raw_object_ref: str
    source_url: str | None = None
    quote: str = Field(min_length=1, max_length=800)


class ExtractedTask(BaseModel):
    title: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[EvidenceRef]


class ExtractionResult(BaseModel):
    tasks: list[ExtractedTask] = []