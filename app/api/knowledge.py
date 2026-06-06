from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.knowledge_ingestion import ingest_text
from app.services.knowledge_pipeline import ingest_text_and_process
from app.services.knowledge_qa import ask_knowledge
from app.services.knowledge_search import search_knowledge
from app.services.knowledge_score_processor import process_knowledge_scores
from app.services.knowledge_attention import get_attention_dashboard
from app.services.production_operation_guard import ProductionOperationBlockedError

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


class IngestTextRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)
    source_type: str = "manual"
    project_key: str | None = None
    client_key: str | None = None
    people: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    allow_production_operation: bool = False
    confirm_production_operation: str | None = None


class AskKnowledgeRequest(BaseModel):
    question: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)

class ScoreKnowledgeRequest(BaseModel):
    source_document_id: str | None = None


@router.post("/ingest-text", status_code=202)
async def ingest_text_endpoint(payload: IngestTextRequest) -> dict:
    try:
        result = await ingest_text(
            title=payload.title,
            text=payload.text,
            source_type=payload.source_type,
            project_key=payload.project_key,
            client_key=payload.client_key,
            people=payload.people,
            tags=payload.tags,
            allow_production_operation=payload.allow_production_operation,
            production_operation_ack=payload.confirm_production_operation,
        )
    except ProductionOperationBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.reason_code,
        ) from exc

    return {
        "accepted": True,
        **result,
    }


@router.post("/ingest-text-process", status_code=202)
async def ingest_text_process_endpoint(payload: IngestTextRequest) -> dict:
    try:
        return await ingest_text_and_process(
            title=payload.title,
            text=payload.text,
            source_type=payload.source_type,
            project_key=payload.project_key,
            client_key=payload.client_key,
            people=payload.people,
            tags=payload.tags,
            allow_production_operation=payload.allow_production_operation,
            production_operation_ack=payload.confirm_production_operation,
        )
    except ProductionOperationBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.reason_code,
        ) from exc


@router.get("/search")
async def search_knowledge_endpoint(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    return await search_knowledge(query=q, limit=limit)


@router.post("/ask")
async def ask_knowledge_endpoint(payload: AskKnowledgeRequest) -> dict:
    return await ask_knowledge(question=payload.question, limit=payload.limit)

@router.post("/score", status_code=202)
async def score_knowledge_endpoint(payload: ScoreKnowledgeRequest) -> dict:
    result = await process_knowledge_scores(
        source_document_id=payload.source_document_id,
    )
    return {
        "processed": True,
        **result,
    }


@router.get("/attention")
async def get_knowledge_attention(
    limit: int = 10,
    source_document_id: str | None = None,
) -> dict:
    return await get_attention_dashboard(
        limit=limit,
        source_document_id=source_document_id,
    )
