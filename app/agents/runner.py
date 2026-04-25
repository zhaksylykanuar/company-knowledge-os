import re

from app.agents.schemas import EvidenceRef, ExtractedTask, ExtractionResult


class RuleBasedAgentRunner:
    async def extract(
        self,
        *,
        source_document_id: str,
        chunk_id: str,
        raw_object_ref: str,
        text: str,
    ) -> ExtractionResult:
        lowered = text.lower()
        tasks = []

        has_task_signal = any(word in lowered for word in ["todo", "нужно", "deadline", "задача"])
        if not has_task_signal:
            return ExtractionResult(tasks=[])

        owner = None
        owner_match = re.search(r"(owner|ответственный)\s*:\s*([A-Za-zА-Яа-яЁё0-9 _.-]+)", text)
        if owner_match:
            owner = owner_match.group(2).strip()

        due_date = None
        due_match = re.search(r"(by|до|deadline)\s+([A-Za-zА-Яа-яЁё0-9 ._-]+)", text, re.IGNORECASE)
        if due_match:
            due_date = due_match.group(2).strip()

        tasks.append(
            ExtractedTask(
                title=text[:120].strip(),
                owner=owner,
                due_date=due_date,
                task_type="task",
                confidence=0.6,
                evidence_refs=[
                    EvidenceRef(
                        source_document_id=source_document_id,
                        chunk_id=chunk_id,
                        raw_object_ref=raw_object_ref,
                        quote=text[:300].strip(),
                    )
                ],
            )
        )

        return ExtractionResult(tasks=tasks)


def get_agent_runner() -> RuleBasedAgentRunner:
    return RuleBasedAgentRunner()
