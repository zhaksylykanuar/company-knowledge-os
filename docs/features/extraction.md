# Feature: Extraction

## Status

- Rule-based extraction: implemented
- Optional LLM extraction: partial
- Evidence validation: implemented
- SourceEvent-driven extraction: planned

## Current Behavior

- Document chunks are processed into tasks, risks, and decisions.
- Gmail messages with readable body text enter extraction through the same document chunk path.
- Rule-based extraction is deterministic and default.
- Optional LLM extraction exists behind configuration.
- Evidence validation rejects extracted items without evidence refs.
- Document-derived extractions leave `source_event_id` empty and use `source_document_id`, `chunk_id`, and `evidence_refs` for provenance.
- Extraction endpoints are sensitive and should require auth outside local/dev.

## Invariants

- Every extracted task/risk/decision must have `evidence_refs`.
- LLM outputs used in pipelines must be strict JSON.
- LLM output must be validated before persistence.
- If evidence is missing, return `null`, an empty array, or `insufficient evidence`.
- LLM must not directly mutate production data.

## Known Gaps

- LLM extraction needs strict operational review before production use.
