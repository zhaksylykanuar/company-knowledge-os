# Feature: Ingestion

## Status

- Manual text ingestion: implemented
- One-step manual text processing: implemented
- Drive read-only backfill request wrapper: implemented through Source Control
- Gmail raw read-only backfill request wrapper: implemented through Source Control
- Google Gmail/Drive backfill activation guardrails: implemented
- Connector payload ingestion boundary: implemented
- External write actions: planned

## Current Behavior

- Manual text is written to raw storage and persisted as `source_documents` and `document_chunks`.
- Manual text documents and chunks use SHA-256 content hashes.
- `POST /v1/knowledge/ingest-text-process` ingests manual text, runs deterministic extraction, refreshes scores for the new document, and returns a compact evidence-backed processing summary.
- The one-step response includes `extracted_items_preview`, a small list of persisted tasks, risks, and decisions with `evidence_refs`, source document/chunk IDs, short evidence snippets from stored evidence quotes, and score metadata when available.
- Existing `POST /v1/knowledge/ingest-text` behavior is unchanged and still performs ingestion only.
- Preferred operator flow for Gmail/Drive is Source Control:
  `POST /v1/founder/sources/{gmail|drive}/{preview_sync|backfill}` followed by
  `scripts/run_source_requests.py`. In the current default registry these
  queued Google requests are request-wrapper/local/noop lifecycle runs; real
  Gmail/Drive clients are not yet wired into the orchestrator.
- Compatibility direct Gmail/Drive backfill routes only record redacted Source
  Control requests. They do not call Google connectors, write raw storage, or
  persist provider data.
- Existing direct Google connector helpers can save raw metadata/content and
  create source documents/chunks when explicitly approved and configured, but
  the Source Control default registry does not yet execute those helpers as
  live Gmail/Drive clients.
- Gmail backfill creates source documents and chunks when a raw message contains readable body text.
- Drive/Gmail emitted ingestion events use registry-compatible event names and payload fields.
- Drive/Gmail persist flows normalize valid new `IngestedEvent` rows into
  `SourceEvent` rows when an approved connector path creates those rows.
- Gmail and Drive direct backfill routes are compatibility-only Source Control
  wrappers. Gmail rejects blank or historically broad explicit queries, and
  Drive records only whether a folder boundary is configured.
- Gmail manual backfill is additionally bounded to a safe per-request result
  limit; it is not a production pagination or incremental sync flow.
- Drive manual backfill is additionally bounded to a safe per-request result
  limit; it is not a production pagination or incremental sync flow.
- Gmail and Drive manual backfill wrapper responses are redacted to safe
  request/status fields; use stored `SourceEvent` and digest checks to verify
  detailed source activity after orchestrator execution.
- Local manual Gmail and Drive backfill checks should follow
  `../runbooks/google-local-backfill.md`.
- Connector payloads can map into `IngestedEvent` and then `SourceEvent`.
- Persisted external events require future API auth and webhook signature boundaries before production exposure.
- Future real source connectivity must follow the credentials, source identity, activation, and allowlist contract in `source-integrations.md`.

## Invariants

- Raw input must be stored before downstream processing.
- Raw storage + Postgres are the source of truth.
- Obsidian is export-only.
- Ingestion should preserve `raw_object_ref`, idempotency, correlation, and trace IDs.
- Extracted tasks, risks, and decisions produced after ingestion must retain `evidence_refs`.
- One-step previews must not fabricate facts or evidence.

## Known Gaps

- Gmail attachment content is not yet ingested into `SourceDocument` and chunks.
- Production Gmail/Drive sync, OAuth hardening, pagination, incremental sync, webhooks, and scheduler jobs are not implemented.
