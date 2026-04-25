from fastapi import APIRouter

from app.agents.runner import get_agent_runner

router = APIRouter(prefix="/v1/extraction", tags=["extraction"])


@router.post("/demo")
async def extract_demo(payload: dict) -> dict:
    runner = get_agent_runner()

    result = await runner.extract(
        source_document_id=payload.get("source_document_id", "doc_demo"),
        chunk_id=payload.get("chunk_id", "chunk_demo"),
        raw_object_ref=payload.get("raw_object_ref", "raw://demo"),
        text=payload["text"],
    )

    return result.model_dump()