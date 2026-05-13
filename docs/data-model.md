# Data Model

## Status

- Audit logs: implemented
- Raw ingested events: implemented
- Source documents and chunks: implemented
- Extracted tasks/risks/decisions: implemented
- Knowledge scores: implemented
- Source events: partial
- Approval/action execution tables: planned

## Core Tables

- `ingested_events`: raw event envelope with idempotency and trace fields.
- `audit_logs`: append-style audit trail for accepted events and operations.
- `source_documents`: source document metadata and raw refs.
- `document_chunks`: searchable text chunks with offsets and raw refs.
- `extracted_tasks`: evidence-backed extracted task records.
- `extracted_risks`: evidence-backed extracted risk records.
- `extracted_decisions`: evidence-backed extracted decision records.
- `knowledge_scores`: deterministic score payloads for extracted entities.
- `source_events`: normalized connector event records linked to `ingested_events`.
- `email_thread_states`: deterministic Gmail conversation state built from
  stored Gmail rows for digest and source-intelligence workflows.

## Invariants

- Raw storage + Postgres are the source of truth.
- Obsidian is export-only.
- Extracted tasks/risks/decisions require `evidence_refs`.
- `source_event_id` is for actual SourceEvent linkage when present.
- Document-derived provenance belongs in `source_document_id`, `chunk_id`, and `evidence_refs`.
- Source-event projections must preserve `raw_object_ref` and evidence links.
- Missing evidence means no persisted fact.
