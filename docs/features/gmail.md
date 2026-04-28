# Feature: Gmail

## Status

- Gmail read-only API wrapper: implemented
- Gmail raw backfill: partial
- Gmail message to SourceDocument/chunks: planned
- Gmail write actions: planned and approval-gated

## Current Behavior

- Gmail messages can be listed and fetched with read-only scope.
- Raw Gmail messages are stored under raw storage.
- Threads, messages, and attachment metadata are persisted.

## Invariants

- Gmail access is read-only first.
- Tokens must stay backend-only.
- Raw messages must be stored before downstream processing.
- Write actions require future explicit approval flow.

## Known Gaps

- Gmail bodies are not yet converted into source documents and chunks.
- Gmail event names need alignment with source registry contracts.
- Webhook/PubSub handling is not visible as implemented.
