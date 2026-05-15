# Data Model

## Status

- Audit logs: implemented
- Raw ingested events: implemented
- Source documents and chunks: implemented
- Extracted tasks/risks/decisions: implemented
- Knowledge scores: implemented
- Source events: partial
- Attention triage feedback: implemented
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
- `attention_triage_feedback`: user feedback events for future attention
  triage context. Rows store `feedback_id`, optional `source`, required
  `source_object_id`, nullable `triage_result_id`, `user_action`, and
  `created_at`.

## Invariants

- Raw storage + Postgres are the source of truth.
- Obsidian is export-only.
- Extracted tasks/risks/decisions require `evidence_refs`.
- `source_event_id` is for actual SourceEvent linkage when present.
- Document-derived provenance belongs in `source_document_id`, `chunk_id`, and `evidence_refs`.
- Source-event projections must preserve `raw_object_ref` and evidence links.
- Missing evidence means no persisted fact.
- Attention feedback stores user intent only; it must not store raw source
  bodies or provider payloads.
- `source` on attention feedback is optional collision protection because
  `source_object_id` may not be globally unique across connectors.
- `triage_result_id` on attention feedback is nullable until
  `AttentionTriageResult` persistence exists.
