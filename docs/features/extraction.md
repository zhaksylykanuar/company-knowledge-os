# Feature: Extraction

## Status

- Rule-based extraction: implemented
- Optional LLM extraction: partial
- Evidence validation: implemented
- SourceEvent-driven extraction: planned

## Current Behavior

- Document chunks are processed into tasks, risks, and decisions.
- Rule-based extraction is deterministic and default.
- Optional LLM extraction exists behind configuration.
- Evidence validation rejects extracted items without evidence refs.

## Invariants

- Every extracted task/risk/decision must have `evidence_refs`.
- LLM outputs used in pipelines must be strict JSON.
- LLM output must be validated before persistence.
- If evidence is missing, return `null`, an empty array, or `insufficient evidence`.
- LLM must not directly mutate production data.

## Known Gaps

- Document extraction currently has confusing `source_event_id` semantics.
- LLM extraction needs strict operational review before production use.
