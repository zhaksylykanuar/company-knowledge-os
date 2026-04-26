from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services.knowledge_ingestion import ingest_text
from app.services.knowledge_qa import ask_knowledge
from app.services.knowledge_search import search_knowledge

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


class IngestTextRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)
    source_type: str = "manual"
    project_key: str | None = None
    client_key: str | None = None
    people: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AskKnowledgeRequest(BaseModel):
    question: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


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


@router.get("/search")
async def search_knowledge_endpoint(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    return await search_knowledge(query=q, limit=limit)


@router.post("/ask")
async def ask_knowledge_endpoint(payload: AskKnowledgeRequest) -> dict:
    return await ask_knowledge(question=payload.question, limit=payload.limit)
