# Feature: Drive

## Status

- Google Drive read-only API wrapper: implemented
- AI_INBOX backfill: partial
- Drive file to SourceDocument/chunks: implemented
- Drive write actions: planned and approval-gated

## Current Behavior

- Drive files can be listed from a configured AI_INBOX folder.
- File content is downloaded/exported as text when supported.
- Raw metadata/content are saved before creating source documents and chunks.
- Drive emits registry-compatible `drive.file.ingested` events with `source_object_type` and `title`.

## Invariants

- Drive access is read-only first.
- Tokens must stay backend-only.
- Raw storage + Postgres are the source of truth.
- Write actions require future explicit approval flow.

## Known Gaps

- Webhook/PubSub handling is not visible as implemented.
- Binary/non-text extraction behavior is unknown.
