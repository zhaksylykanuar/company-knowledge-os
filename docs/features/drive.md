# Feature: Drive

## Status

- Google Drive read-only API wrapper: implemented
- AI_INBOX backfill: partial
- Drive backfill activation/folder guardrail: implemented
- Drive manual backfill limit guardrail: implemented
- Drive file to SourceDocument/chunks: implemented
- Drive write actions: planned and approval-gated

## Current Behavior

- Drive files can be listed from a configured AI_INBOX folder.
- Drive backfill is disabled by default and must be explicitly enabled before
  the route calls connector code.
- Enabled Drive backfill still requires the configured AI_INBOX folder boundary.
- Manual Drive backfill uses a safe default of 10 files per request and a hard
  API maximum of 50 files per request.
- Local manual Drive backfill testing should follow
  `../runbooks/google-local-backfill.md`.
- File content is downloaded/exported as text when supported.
- Raw metadata/content are saved before creating source documents and chunks.
- Drive emits registry-compatible `drive.file.ingested` events with `source_object_type` and `title`.
- Drive `persist=true` backfill creates SourceEvent rows for new ingested file events.

## Invariants

- Drive access is read-only first.
- Tokens must stay backend-only.
- Raw storage + Postgres are the source of truth.
- Write actions require future explicit approval flow.

## Known Gaps

- Webhook/PubSub handling is not visible as implemented.
- Binary/non-text extraction behavior is unknown.
- Production Drive sync, pagination, incremental sync, and OAuth hardening are
  not implemented.
