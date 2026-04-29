# Feature: Ingestion

## Status

- Manual text ingestion: implemented
- Drive read-only backfill: partial
- Gmail raw read-only backfill: partial
- Connector payload ingestion boundary: implemented
- External write actions: planned

## Current Behavior

- Manual text is written to raw storage and persisted as `source_documents` and `document_chunks`.
- Manual text documents and chunks use SHA-256 content hashes.
- Drive backfill saves raw metadata/content, creates source documents and chunks.
- Gmail backfill saves raw messages, threads, messages, and attachment metadata.
- Gmail backfill creates source documents and chunks when a raw message contains readable body text.
- Drive/Gmail emitted ingestion events use registry-compatible event names and payload fields.
- Drive/Gmail persist flows normalize valid new `IngestedEvent` rows into `SourceEvent` rows.
- Connector payloads can map into `IngestedEvent` and then `SourceEvent`.
- Persisted external events require future API auth and webhook signature boundaries before production exposure.

## Invariants

- Raw input must be stored before downstream processing.
- Raw storage + Postgres are the source of truth.
- Obsidian is export-only.
- Ingestion should preserve `raw_object_ref`, idempotency, correlation, and trace IDs.

## Known Gaps

- Gmail attachment content is not yet ingested into `SourceDocument` and chunks.
