# Feature: Gmail

## Status

- Gmail read-only API wrapper: implemented
- Gmail raw backfill: partial
- Gmail backfill activation/query guardrail: implemented
- Gmail manual backfill limit guardrail: implemented
- Google manual backfill preflight: implemented for safe guardrail inspection
- Gmail message to SourceDocument/chunks: implemented for readable message bodies
- Gmail write actions: planned and approval-gated

## Current Behavior

- Gmail messages can be listed and fetched with read-only scope.
- Gmail backfill is disabled by default and must be explicitly enabled before
  the route calls connector code.
- Enabled Gmail backfill requires a narrower explicit query or configured safe
  query. The historical broad `in:inbox OR in:sent` query is rejected.
- Manual Gmail backfill uses a safe default of 10 messages per request and a
  hard API maximum of 50 messages per request.
- The protected Google preflight endpoint can validate Gmail backfill readiness
  without calling Gmail APIs and without returning the query value.
- Local manual Gmail backfill testing should follow
  `../runbooks/google-local-backfill.md`.
- Raw Gmail messages are stored under raw storage.
- Threads, messages, and attachment metadata are persisted.
- Gmail emits registry-compatible `gmail.message.ingested` events with `source_object_type` and `subject` when a Subject header is present.
- Gmail messages with readable `text/plain` body content, or `text/html` body content when no plain text exists, are converted into `source_documents` and `document_chunks`.
- Gmail messages without readable body text are skipped for document/chunk creation.
- Gmail `persist=true` backfill creates SourceEvent rows for new ingested message events when registry-required fields are present.
- Gmail messages without a real Subject header do not get SourceEvent rows in this ticket; no subject is invented.

## Invariants

- Gmail access is read-only first.
- Tokens must stay backend-only.
- Raw messages must be stored before downstream processing.
- Write actions require future explicit approval flow.

## Known Gaps

- Gmail attachment content ingestion is not implemented; attachments remain metadata-only.
- Webhook/PubSub handling is not visible as implemented.
- Production Gmail sync, pagination, incremental history sync, and OAuth
  hardening are not implemented.
