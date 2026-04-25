from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.evidence_validator import validate_evidence
from app.agents.runner import get_agent_runner

router = APIRouter(prefix="/v1/extraction", tags=["extraction"])


class ExtractionDemoRequest(BaseModel):
    text: str = Field(min_length=1)
    source_document_id: str = "doc_demo"
    chunk_id: str = "chunk_demo"
    raw_object_ref: str = "raw://demo"
    source_url: str | None = None


@router.post("/demo")
async def extract_demo(payload: ExtractionDemoRequest) -> dict:
    runner = get_agent_runner()
    result = await runner.extract(
        source_document_id=payload.source_document_id,
        chunk_id=payload.chunk_id,
        raw_object_ref=payload.raw_object_ref,
        source_url=payload.source_url,
        text=payload.text,
    )
    validate_evidence(result)
    return result.model_dump()
