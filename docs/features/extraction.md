# Feature: Extraction

## Status

- Rule-based extraction: implemented
- Optional LLM extraction: partial
- Evidence validation: implemented
- Meeting transcript draft pipeline: implemented as provider-free schemas and
  deterministic draft generation
- SourceEvent-driven extraction: planned

## Current Behavior

- Document chunks are processed into tasks, risks, and decisions.
- Gmail messages with readable body text enter extraction through the same document chunk path.
- Rule-based extraction is deterministic and default.
- Optional LLM extraction exists behind configuration.
- Evidence validation rejects extracted items without evidence refs.
- Document-derived extractions leave `source_event_id` empty and use `source_document_id`, `chunk_id`, and `evidence_refs` for provenance.
- Extraction endpoints are sensitive and should require auth outside local/dev.
- FOS-048 adds a pure meeting transcript draft pipeline. It accepts transcript
  text and source refs, recognizes explicit markers such as `Summary:`,
  `Decision:`, `Action:`, `TODO:`, `Risk:`, `Question:`, `Jira:`, and `KB:`,
  and returns validated draft-only meeting artifacts.
- Meeting decisions, action items, risks, open questions, Jira draft tickets,
  and KB update drafts all require bounded `evidence_refs`. The pipeline does
  not call providers and does not write Jira issues, Obsidian files, raw
  storage, or database rows.
- Any future LLM meeting path must produce the same strict schemas and validate
  output before persistence or user-visible action.

## Invariants

- Every extracted task/risk/decision must have `evidence_refs`.
- LLM outputs used in pipelines must be strict JSON.
- LLM output must be validated before persistence.
- If evidence is missing, return `null`, an empty array, or `insufficient evidence`.
- LLM must not directly mutate production data.
- Meeting artifacts are drafts only until a future human approval/action layer
  exists.

## Known Gaps

- LLM extraction needs strict operational review before production use.
- Meeting draft persistence, Jira creation, KB/Obsidian writes, transcript
  ingestion, and approval execution are not implemented.
