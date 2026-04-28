# Extraction Agent

## Status

- Rule-based extraction: implemented
- Optional LLM extraction: partial
- SourceEvent extraction: planned

## Responsibilities

- Extract tasks, risks, and decisions only when evidence exists.
- Attach `evidence_refs` to every extracted task/risk/decision.
- Return empty arrays or `insufficient evidence` when evidence is missing.
- Validate output before persistence.

## Rules

- LLM outputs used in pipelines must be strict JSON.
- LLM must not directly mutate production data.
- Unsupported claims must be rejected.
- Do not repair missing evidence silently.
