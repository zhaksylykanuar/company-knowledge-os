# Feature: Retrieval

## Status

- Deterministic search endpoint: implemented
- Deterministic ask endpoint: implemented
- Score-aware ordering: partial
- Full-text or semantic search: planned

## Current Behavior

- Search queries chunks, tasks, risks, and decisions.
- Q&A composes deterministic answers from search and recent fallback logic.
- Search results include evidence refs and score payloads when available.
- Manual text processed through `POST /v1/knowledge/ingest-text-process` is immediately ready for search, ask, score-aware ordering, and attention once the endpoint completes.
- The one-step processing response includes a small evidence-backed preview so users can inspect extracted tasks, risks, decisions, and supporting evidence without reading database tables.
- Search, ask, and attention endpoints are sensitive and should require auth outside local/dev.

## Invariants

- Answers must be evidence-backed.
- If evidence is missing, return `insufficient evidence` or empty result sets.
- Retrieval must not invent facts absent from source data.
- Previewed extracted entities must include `evidence_refs`.

## Known Gaps

- Search uses simple `ILIKE` matching.
- Scaling path is planned, not implemented.
- No embedding index is visible in the repo.
