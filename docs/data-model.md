# Data Model

## Status

- Audit logs: implemented
- Raw ingested events: implemented
- Source documents and chunks: implemented
- Extracted tasks/risks/decisions: implemented
- Knowledge scores: implemented
- Source events: partial
- Normalized activity items: persistence and source-event projection foundation implemented
- Attention triage results: persistence, single-activity triage bridge, and
  persisted digest read-model foundations implemented
- Attention triage feedback: implemented
- Meeting transcript artifacts: draft-only, not persisted
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
- `normalized_activity_items`: validated cross-source activity projections linked
  to source/source object identifiers and optionally to a stored
  `source_event_id`. Rows store `activity_item_id`, optional
  `source_event_id`, source metadata, activity type, title, actor, activity
  timestamp, project, safe summary, related people/Jira keys/PRs/files,
  evidence refs, and record `created_at`.
- `email_thread_states`: deterministic Gmail conversation state built from
  stored Gmail rows for digest and source-intelligence workflows.
- `attention_triage_results`: validated attention triage outputs linked to a
  source and source object. Rows store `triage_result_id`, `source`,
  `source_object_id`, optional `activity_item_id`, attention class,
  priority, digest visibility, confidence, reason, recommended action, owner,
  deadline, evidence refs, and `created_at`. Stored rows can now be read as
  provider-free digest input for explicit time windows.
- `attention_triage_feedback`: user feedback events for future attention
  triage context. Rows store `feedback_id`, optional `source`, required
  `source_object_id`, nullable `triage_result_id`, `user_action`, and
  `created_at`.
- Meeting transcript summaries, decisions, actions, risks, open questions,
  Jira draft tickets, and KB update drafts are not stored in FOS-048. They are
  strict in-memory draft schemas only.

## Invariants

- Raw storage + Postgres are the source of truth.
- Obsidian is export-only.
- Extracted tasks/risks/decisions require `evidence_refs`.
- `source_event_id` is for actual SourceEvent linkage when present.
- Document-derived provenance belongs in `source_document_id`, `chunk_id`, and `evidence_refs`.
- Source-event projections must preserve `raw_object_ref` and evidence links.
- Missing evidence means no persisted fact.
- Normalized activity item persistence stores only strict schema-validated
  `NormalizedActivityItem` metadata and evidence refs. It must not store raw
  source bodies, prompts, provider payloads, secrets, or unvalidated JSON blobs.
- Provider-free source-event projection can persist one supported stored
  `SourceEvent` as one validated `normalized_activity_items` row. Projection is
  idempotent by `source_event_id`; repeating the projection returns the existing
  activity row instead of creating duplicates.
- Durable activity linkage is now:
  `source_events` -> `normalized_activity_items` ->
  `attention_triage_results` -> `attention_triage_feedback`.
- `source_event_id` on normalized activity items remains nullable for provider-
  free tests and future activity sources that do not yet have a durable source
  event row.
- Attention feedback stores user intent only; it must not store raw source
  bodies or provider payloads.
- `source` on attention feedback is optional collision protection because
  `source_object_id` may not be globally unique across connectors.
- Feedback context loaders use `source` as a DB/service-level filter; the
  public `AttentionTriageFeedback` DTO remains playbook-compatible and does not
  expose `source`.
- Attention triage result persistence stores only strict schema-validated
  result metadata and evidence refs. It must not store raw source bodies,
  prompts, provider payloads, secrets, or unvalidated JSON blobs.
- Provider-free persisted activity triage can classify one stored
  `normalized_activity_items` row through the shared `AttentionTriageAgent`
  contract and persist one linked `attention_triage_results` row. The service
  loads bounded recent feedback into `AttentionContext.recent_feedback` as
  advisory context only.
- Persisted activity triage is service-level idempotent by `activity_item_id`;
  repeating triage for the same activity returns the existing linked attention
  result instead of creating a duplicate.
- Persisted attention digest reading is provider-free and read-only. It groups
  existing `attention_triage_results` rows for an explicit timezone-aware
  window into daily digest section keys, applies the existing low-confidence
  visibility policy for read-time safety, and keeps hidden/no-action
  low-priority rows as count-only summary data.
- Persisted attention digest items may enrich visible rows from linked
  `normalized_activity_items` via `activity_item_id`. Enrichment is optional:
  missing normalized activity rows do not fail digest building, and result
  evidence refs are not fabricated.
- `triage_result_id` on attention feedback remains nullable. Feedback can
  reference a stored attention triage result, but feedback remains advisory and
  does not force deterministic show/hide behavior.
- Automatic batch projection from all source events into normalized activity
  rows is still deferred. Batch persisted attention triage,
  retriage/versioning, digest replacement/rendering from persisted attention
  rows, scheduler behavior, delivery, and human approvals are also still
  deferred.
- Meeting artifacts must not mutate Jira, Obsidian, raw storage, or Postgres
  until a future persistence and human approval/action model exists.
