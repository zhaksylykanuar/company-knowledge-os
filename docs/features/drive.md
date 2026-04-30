# Feature: Drive

## Status

- Google Drive read-only API wrapper: implemented
- AI_INBOX backfill: partial
- Drive backfill activation/folder guardrail: implemented
- Drive manual backfill limit guardrail: implemented
- Drive manual backfill response redaction: implemented
- Google manual backfill preflight: implemented for safe guardrail inspection
- Drive file to SourceDocument/chunks: implemented
- Drive write actions: planned and approval-gated

## Current Behavior

- Drive files can be listed from a configured AI_INBOX folder.
- Drive backfill is disabled by default and must be explicitly enabled before
  the route calls connector code.
- Enabled Drive backfill still requires the configured AI_INBOX folder boundary.
- Manual Drive backfill uses a safe default of 10 files per request and a hard
  API maximum of 50 files per request.
- Manual Drive backfill responses are redacted by default and return safe
  counts/status fields instead of file names, titles, Drive links, provider
  file IDs, raw event payloads, or document content.
- The protected Google preflight endpoint can validate Drive backfill readiness
  and safe local Google credential file presence without calling Drive APIs,
  reading credential contents, or returning the configured folder ID,
  credential paths, token paths, or credential values.
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
- Production Drive sync, pagination, incremental sync, token refresh,
  production token storage, and OAuth hardening are not implemented.
