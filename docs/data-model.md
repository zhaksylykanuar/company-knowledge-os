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
- Persisted attention digest delivery draft review records:
  audit-log-backed, implemented
- Persisted attention digest delivery draft approval decisions:
  audit-log-backed, implemented
- Persisted attention digest delivery readiness preview:
  read-only, implemented
- Persisted attention digest delivery intention records:
  audit-log-backed, implemented
- Meeting transcript artifacts: draft-only, not persisted
- Approval/action execution tables: planned

## Core Tables

- `ingested_events`: raw event envelope with idempotency and trace fields.
- `audit_logs`: append-style audit trail for accepted events and operations.
  FOS-061 also stores sanitized persisted attention digest delivery draft review
  records here as `digest.delivery_draft.created` events, with `after_ref`
  set to the deterministic `delivery_draft_id`.
  FOS-062 stores sanitized delivery draft decision records here as
  `digest.delivery_draft.approved` and `digest.delivery_draft.rejected` events,
  also keyed by `after_ref=delivery_draft_id`.
  FOS-063 reads those draft and decision events to build a delivery readiness
  preview, but it does not append audit rows or introduce new storage.
  FOS-064 stores sanitized delivery intention handoff records here as
  `digest.delivery_intention.created` events, with `before_ref` set to the
  `delivery_draft_id` and `after_ref` set to the deterministic
  `delivery_intention_id`.
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
- Persisted attention digest delivery drafts are audit-log-backed review
  records only. They are derived from persisted attention digest read-model data
  and deterministic rendered text, are not source-of-truth company facts, are
  not approvals, and are not delivery execution.
- Persisted delivery draft audit payloads must store only sanitized draft data:
  `delivery_draft_id`, inert draft status, explicit window metadata, rendered
  text and hash, chunk metadata, sanitized digest snapshot, safe
  source-of-truth metadata, and safe debug evidence refs only when explicitly
  requested. Hidden low-priority items remain count-only.
- Persisted delivery draft audit payloads must not store raw source bodies,
  provider payloads, prompts, source payloads, secrets, tokens, hidden item
  details, or untrusted raw content.
- Delivery draft idempotency is service-level and keyed by deterministic
  `delivery_draft_id` in `audit_logs.after_ref`; no new table or migration is
  introduced by FOS-061.
- Delivery draft approval/rejection decisions are audit events only. They store
  safe reviewer/note metadata, the decision, the referenced
  `delivery_draft_id`, and the draft text hash; they must not store rendered
  digest text, raw source bodies, prompts, provider payloads, secrets, tokens,
  hidden item details, or untrusted raw content.
- Approval/rejection decision idempotency is service-level and keyed by
  `delivery_draft_id` plus terminal decision. Repeating the same decision
  returns the existing decision status, while conflicting terminal decisions are
  rejected. FOS-062 introduces no new table or migration.
- Approval decisions are not delivery execution. They do not mutate the draft
  event, do not mutate source-of-truth company facts, do not send
  Telegram/Slack messages, and do not invoke scheduler or delivery adapters.
- Delivery readiness for persisted delivery drafts is read-only and derived
  from existing `digest.delivery_draft.created`,
  `digest.delivery_draft.approved`, and `digest.delivery_draft.rejected` audit
  events. It reports whether a draft is approved and eligible for a future
  separately gated delivery path, but it must not store rendered digest text in
  the readiness response, create outbox/intention records, mutate source-of-
  truth data, mutate draft or decision events, send Telegram/Slack messages, or
  invoke scheduler, providers, live APIs, approval execution, or delivery
  adapters. FOS-063 introduces no new table or migration.
- Delivery intention records are audit-log-backed execution metadata for
  approved and ready persisted delivery drafts. They are durable handoff
  artifacts for a future separately gated execution path, not delivery
  execution, not outbox workers, not scheduler jobs, and not source-of-truth
  company facts. They store only safe draft/readiness metadata such as
  `delivery_intention_id`, `delivery_draft_id`, digest type, channel, rendered
  text hash, window, chunk metadata, readiness summary, source-of-truth
  metadata, and inert delivery flags.
- Delivery intention payloads must not store rendered digest text, full digest
  snapshots, raw source bodies, prompts, provider payloads, source payloads,
  secrets, tokens, hidden item details, or newly exposed evidence refs. They
  must not send Telegram/Slack messages, invoke delivery adapters, create
  scheduler jobs, mutate draft or decision events, or mutate source-of-truth
  company facts. FOS-064 introduces no new table or migration.
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
