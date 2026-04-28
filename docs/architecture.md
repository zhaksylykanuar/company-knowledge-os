# Architecture

## Status

- FastAPI backend: implemented
- Raw storage + Postgres source of truth: implemented
- Obsidian export-only model: implemented
- End-to-end Gmail-to-knowledge pipeline: partial
- GitHub/Jira/Telegram real connectors: planned

## System Shape

FounderOS is a Python/FastAPI backend for evidence-backed company knowledge and decisions.

Pipeline:

```text
Drive / Gmail / manual text / future connector payloads
-> raw storage
-> ingested_events
-> source_documents + document_chunks or source_events
-> extraction
-> extracted_tasks / extracted_risks / extracted_decisions
-> deterministic scoring
-> search / ask / attention dashboard
-> Obsidian export
```

## Source Of Truth

- Raw storage + Postgres are the source of truth.
- Obsidian is export-only.
- Generated vault files must not be treated as authoritative data.

## Safety Model

- Every extracted task/risk/decision must have `evidence_refs`.
- LLM outputs used in pipelines must be strict JSON.
- LLM output must be validated before persistence.
- If evidence is missing, return `null`, an empty array, or `insufficient evidence`.
- LLM must not directly mutate production data.
