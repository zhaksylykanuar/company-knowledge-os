import json

from openai import OpenAI

from app.agents.schemas import EvidenceRef, ExtractedTask, ExtractionResult
from app.core.config import settings

client = OpenAI(api_key=settings.openai_api_key)


class LLMAgentRunner:
    async def extract(
        self,
        *,
        source_document_id: str,
        chunk_id: str,
        raw_object_ref: str,
        text: str,
    ) -> ExtractionResult:
        if not settings.openai_api_key:
            return ExtractionResult(tasks=[])

        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {
                    "role": "system",
                    "content": (
                        "You extract actionable company knowledge from text. "
                        "Return only items that are explicitly supported by the text. "
                        "Do not invent owners, dates, or tasks. "
                        "If there are no clear tasks, return an empty tasks array."
                    ),
                },
                {
                    "role": "user",
                    "content": text,
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "company_knowledge_extraction",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "tasks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "title": {"type": "string"},
                                        "owner": {"type": ["string", "null"]},
                                        "due_date": {"type": ["string", "null"]},
                                        "task_type": {
                                            "type": "string",
                                            "enum": ["task", "decision", "risk", "commitment"],
                                        },
                                        "quote": {"type": "string"},
                                    },
                                    "required": [
                                        "title",
                                        "owner",
                                        "due_date",
                                        "task_type",
                                        "quote",
                                    ],
                                },
                            }
                        },
                        "required": ["tasks"],
                    },
                }
            },
        )

        parsed = json.loads(response.output_text)

        tasks = []
        for item in parsed.get("tasks", []):
            quote = item.get("quote") or text[:300]

            tasks.append(
                ExtractedTask(
                    title=item["title"],
                    owner=item.get("owner"),
                    due_date=item.get("due_date"),
                    task_type=item.get("task_type", "task"),
                    confidence=0.85,
                    evidence_refs=[
                        EvidenceRef(
                            source_document_id=source_document_id,
                            chunk_id=chunk_id,
                            raw_object_ref=raw_object_ref,
                            quote=quote[:800],
                        )
                    ],
                )
            )

        return ExtractionResult(tasks=tasks)
