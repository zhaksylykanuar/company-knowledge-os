from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.services.knowledge_ingestion import ingest_text


router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


class IngestTextRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)
    source_type: str = "manual"
    project_key: str | None = None
    client_key: str | None = None
    people: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


@router.post("/ingest-text", status_code=202)
async def ingest_text_endpoint(payload: IngestTextRequest) -> dict:
    result = await ingest_text(
        title=payload.title,
        text=payload.text,
        source_type=payload.source_type,
        project_key=payload.project_key,
        client_key=payload.client_key,
        people=payload.people,
        tags=payload.tags,
    )

    return {
        "accepted": True,
        **result,
    }