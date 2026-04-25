from app.agents.schemas import ExtractionResult


def validate_evidence(result: ExtractionResult) -> None:
    for group_name in ("tasks", "decisions", "risks"):
        for item in getattr(result, group_name):
            if not item.evidence_refs:
                raise ValueError(f"{group_name} item has no evidence_refs")

            for ref in item.evidence_refs:
                if not ref.source_document_id:
                    raise ValueError("evidence_ref.source_document_id is empty")
                if not ref.chunk_id:
                    raise ValueError("evidence_ref.chunk_id is empty")
                if not ref.raw_object_ref:
                    raise ValueError("evidence_ref.raw_object_ref is empty")
                if not ref.quote.strip():
                    raise ValueError("evidence_ref.quote is empty")
