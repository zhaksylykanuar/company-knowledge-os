# Chunking Agent

## Status

- Fixed-size overlapping text chunking: implemented
- Semantic chunking: planned
- Non-text chunking: unknown

## Responsibilities

- Produce stable, traceable chunks from source documents.
- Preserve source document ID, chunk ID, offsets, raw refs, and content hash.
- Keep chunking deterministic unless explicitly changed.

## Rules

- Do not drop source provenance.
- Do not create chunks from unstored raw inputs.
- Update docs when chunking behavior or chunk IDs change.
