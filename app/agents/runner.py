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
        tasks = []

        lowered = text.lower()

        if "todo" in lowered or "нужно" in lowered or "deadline" in lowered:
            tasks.append(
                ExtractedTask(
                    title=text[:120].strip(),
                    confidence=0.55,
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