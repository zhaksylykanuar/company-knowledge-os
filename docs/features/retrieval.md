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

## Invariants

- Answers must be evidence-backed.
- If evidence is missing, return `insufficient evidence` or empty result sets.
- Retrieval must not invent facts absent from source data.

## Known Gaps

- Search uses simple `ILIKE` matching.
- Scaling path is planned, not implemented.
- No embedding index is visible in the repo.
