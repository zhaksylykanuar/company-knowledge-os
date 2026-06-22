# Feature: Drive

## Status

- Current default: request-only/local/noop. The default Source Control registry
  does not wire a real Drive client.
- Google Drive read-only API wrapper library: implemented
- AI_INBOX backfill request wrapper: implemented through Source Control
- Drive backfill activation/folder guardrail: implemented
- Drive manual backfill limit guardrail: implemented
- Drive manual backfill response redaction: implemented
- Google manual backfill preflight: implemented for safe guardrail inspection
- Drive file to SourceDocument/chunks: implemented
- Drive write actions: planned and approval-gated

## Current Behavior

- Low-level Drive read-only wrapper code exists, but the current default Source
  Control registry does not wire a real Drive client. Operator-facing Source
  Control runs use noop/local behavior until a first-class real Google client
  is implemented and explicitly enabled.
- Preferred operator path is Source Control:
  `POST /v1/founder/sources/drive/{preview_sync|backfill}` records a request,
  and `scripts/run_source_requests.py` advances that queued request through the
  orchestrator.
- The compatibility `POST /v1/drive/backfill` route is request-only. It does
  not call Drive connector code, write raw storage, or persist provider data.
  It records a redacted Source Control request instead.
- On the compatibility route, `persist=false` maps to a `preview_sync` request
  and `persist=true` maps to a `backfill` request for the orchestrator; the
  wrapper itself never performs the live Drive read.
- The compatibility route records only whether a Drive folder boundary is
  configured; it does not store or return the folder ID.
- Drive request wrappers use a safe default of 10 files per request and a hard
  API maximum of 50 files per request.
- Drive request wrapper responses are redacted by default and return request
  IDs, status, action type, source type, safe limits, and sanitized input flags
  instead of file names, titles, Drive links, provider file IDs, raw event
  payloads, or document content.
- The protected Google preflight endpoint can validate Drive backfill readiness
  and safe local Google credential file presence without calling Drive APIs,
  reading credential contents, or returning the configured folder ID,
  credential paths, token paths, or credential values.
- Local manual Drive backfill testing should follow
  `../runbooks/google-local-backfill.md`.
- File content is downloaded/exported as text when supported only inside
  approved connector/orchestrator execution paths.
- Raw metadata/content are saved before creating source documents and chunks in
  those execution paths, not by the compatibility HTTP wrapper itself.
- Drive emits registry-compatible `drive.file.ingested` events with `source_object_type` and `title`.
- Drive connector/orchestrator backfill can create SourceEvent rows for new
  ingested file events.

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
