# Retrieval Agent

## Status

- Deterministic search: implemented
- Deterministic Q&A: implemented
- Semantic retrieval: planned

## Responsibilities

- Retrieve chunks, tasks, risks, and decisions with evidence refs.
- Prefer scored, evidence-backed items when available.
- Return empty results or `insufficient evidence` instead of unsupported answers.

## Rules

- Do not invent answers.
- Do not hide source refs.
- Keep retrieval changes scoped and documented.
