# Ingestion Agent

## Status

- Manual/Drive ingestion support: implemented
- Gmail-to-document ingestion: planned
- External write ingestion: planned as approval-gated

## Responsibilities

- Preserve raw input before processing.
- Maintain idempotency keys, raw refs, correlation IDs, and trace IDs.
- Create source documents/chunks only from stored raw inputs.
- Update feature docs when ingestion behavior changes.

## Rules

- Do not edit secrets or `.env` values.
- Do not invent source metadata.
- Do not mutate production data through LLM output.
- Use targeted files; do not rescan the whole repo unless needed.
