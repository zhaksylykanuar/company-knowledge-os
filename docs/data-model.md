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
- Persisted attention digest Telegram delivery plan preview:
  read-only, implemented
- Persisted attention digest delivery intention operator review:
  read-only, implemented
- Persisted attention digest Telegram execution preflight:
  read-only, implemented
- Persisted attention digest delivery result audit contract:
  audit-log-backed, implemented
- Persisted attention digest bounded Telegram execution gate:
  read-only, implemented
- Persisted attention digest test-only Telegram send command:
  audit-log-backed result recording, implemented
- Local/dev-only synthetic persisted attention digest seed command:
  implemented
- Duplicate-success protection for test-only Telegram sends:
  implemented
- Local approved-draft manual pilot handoff command:
  implemented
- Read-only manual pilot status report by sample/window:
  implemented
- Read-only persisted attention window discovery for manual pilots:
  implemented
- Read-only real stored local data readiness discovery:
  implemented
- Read-only stored source event normalization preview:
  implemented
- Local/dev-only stored source event normalization command:
  implemented
- Read-only normalized activity triage readiness preview:
  implemented
- Local/dev-only provider-free normalized activity triage command:
  implemented
- Read-only persisted attention window reconciliation report:
  implemented
- Read-only no-marker persisted attention candidate report:
  implemented
- Local/dev-only no-marker persisted attention delivery draft preparation:
  audit-log-backed, implemented
- Read-only no-marker persisted attention digest quality report:
  implemented
- Read-only no-marker duplicate root-cause linkage report:
  implemented
- Read-only presentation-variant canonical hash duplicate guard evaluator:
  implemented
- Read-only grouped lifecycle canonical hash guard review:
  implemented
- Read-only grouped lifecycle operator decision summary:
  implemented
- Sanitized grouped lifecycle report contract tests:
  implemented
- Decision-only grouped lifecycle review JSON output:
  implemented
- Grouped lifecycle CLI help and synthetic review smoke mode:
  implemented
- Grouped lifecycle review exit codes and sanitized artifacts:
  implemented
- Provider-free grouped lifecycle review operator doctor:
  implemented
- Gated manual local grouped lifecycle review runner:
  implemented
- Safe grouped lifecycle manual runner window presets and preflight:
  implemented
- Sanitized grouped lifecycle manual-review diagnostics:
  implemented
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
  FOS-065 reads delivery intention and referenced delivery draft events to build
  a pure Telegram delivery plan preview, but it does not append audit rows or
  introduce new storage.
  FOS-066 reads those stored delivery intention, draft, decision, and readiness
  artifacts for local operator review, but it does not append audit rows or
  introduce new storage.
  FOS-067 reads stored delivery intention and Telegram plan readiness plus
  Telegram credential presence metadata for execution preflight, but it does
  not append audit rows or introduce new storage.
  FOS-068 stores sanitized future delivery outcome metadata here as
  `digest.delivery_result.recorded` events, with `before_ref` set to the
  `delivery_intention_id` and `after_ref` set to the deterministic
  `delivery_result_id`; no new table or migration is introduced.
  FOS-069 reads stored delivery intention, preflight, plan, readiness, and
  result-contract metadata to build an execution gate preview, but it does not
  append audit rows or introduce new storage.
  FOS-070 records sanitized delivery result audit events after explicit
  test-only bounded operator Telegram send attempts; it reuses
  `digest.delivery_result.recorded`, writes no other rows, and introduces no new
  storage.
  FOS-072 reads existing `digest.delivery_result.recorded` rows by
  `before_ref=delivery_intention_id` to block duplicate successful test sends
  before any Telegram transport call; it appends no rows during the duplicate
  guard and introduces no new storage.
  FOS-078 reads existing delivery draft, decision, intention, and delivery
  result audit rows for an explicit digest window to build a manual pilot status
  report; it appends no rows and introduces no new storage.
  FOS-079 reads the same audit metadata across bounded explicit persisted
  attention windows for manual pilot candidate discovery; it appends no rows and
  introduces no new storage.
- FOS-080 reads existing `source_events`, `normalized_activity_items`, and
  `attention_triage_results` rows over explicit bounded windows for count-only
  real stored local data readiness discovery; it appends no rows and introduces
  no new storage.
- FOS-081 reads existing `source_events` and linked
  `normalized_activity_items` over an explicit bounded window for count-only
  normalization preview; it appends no rows and introduces no new storage.
- FOS-082 projects supported stored `source_events` into existing
  `normalized_activity_items` through the provider-free projection service from
  a local/dev-only operator command. It writes no source events, attention
  results, audit logs, delivery artifacts, new tables, or migrations.
- FOS-083 reads existing `normalized_activity_items` and linked
  `attention_triage_results` over an explicit bounded window for count-only
  triage readiness preview; it appends no rows and introduces no new storage.
- FOS-084 writes existing `normalized_activity_items` into existing
  `attention_triage_results` through the provider-free strict triage service
  from a local/dev-only operator command. It writes no source events,
  normalized activity rows, audit logs, delivery artifacts, new tables, or
  migrations.
- FOS-085 reads existing `attention_triage_results`, linked
  `normalized_activity_items`/`source_events`, and delivery draft audit logs for
  count-only window reconciliation. It appends no rows and introduces no new
  storage.
- `ingested_events`, `source_events`, `normalized_activity_items`, and
  `attention_triage_results` may contain explicitly labeled local/dev-only
  synthetic rows created by the FOS-071 operator seed command. Those rows exist
  only to make an empty local persisted attention digest visible for delivery
  workflow testing; they are not live provider data or source-of-truth company
  facts.
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
- Telegram delivery plan previews for delivery intentions are read-only derived
  metadata, not stored records. They may use the stored delivery draft rendered
  text internally for deterministic Telegram chunk hashes and lengths, but plan
  responses must not include rendered text, chunk text, Telegram bot tokens,
  chat IDs, URLs, full digest snapshots, raw source bodies, prompts, provider
  payloads, source payloads, secrets, hidden item details, or newly exposed
  evidence refs. FOS-065 introduces no new table or migration.
- Local delivery intention operator reviews are read-only derived bundles, not
  stored records and not source-of-truth company facts. They read the stored
  delivery intention, referenced delivery draft, approval status, readiness,
  and Telegram delivery plan by `delivery_intention_id`. Default output must
  omit rendered digest text and chunk text; optional rendered text output may
  include only the stored sanitized draft text. Review output must not include
  Telegram bot tokens, chat IDs, URLs, full digest snapshots, raw source
  bodies, prompts, provider payloads, source payloads, secrets, hidden item
  details, or newly exposed evidence refs. FOS-066 introduces no audit event,
  new table, or migration.
- Telegram execution preflight for delivery intentions is read-only derived
  metadata, not a stored record and not delivery execution. It reads the stored
  delivery intention and Telegram plan, checks Telegram bot token and chat ID
  presence only, and returns safe booleans and blockers. It must not return,
  print, store, log, or validate credential values; send Telegram/Slack
  messages; call delivery adapters; create scheduler jobs, delivery result
  events, outbox records, audit rows, new tables, or migrations; or expose
  rendered text, chunk text, raw source bodies, prompts, provider payloads,
  hidden item details, or newly exposed evidence refs.
- Delivery result records for delivery intentions are audit-log-backed execution
  outcome metadata, not source-of-truth company facts and not delivery
  execution. They are keyed by deterministic `delivery_result_id` values and may
  store only sanitized result fields: delivery intention ID, execution attempt
  ID, channel, rendered text hash, planned/attempted/delivered/failed chunk
  counts, bounded safe message refs, safe error code/summary, inert scheduler
  and approval-execution flags, and source-of-truth/safety metadata. They must
  not store rendered text, chunk text, Telegram bot tokens, chat IDs, URLs,
  webhook secrets, raw Telegram API responses, full digest snapshots, raw source
  bodies, prompts, provider payloads, source payloads, hidden item details, or
  newly exposed evidence refs. FOS-068 adds no public result creation API, send
  path, outbox table, scheduler job, new table, or migration.
- Bounded Telegram execution gates for delivery intentions are read-only derived
  metadata, not stored records and not delivery execution. They read stored
  approval/readiness, delivery intention, Telegram plan, credential-presence
  preflight, and result-contract metadata to report safe readiness booleans,
  blockers, required future operator fields, and chunk bounds. They must not
  return or store rendered text, chunk text, Telegram bot tokens, chat IDs,
  URLs, webhook secrets, raw Telegram API responses, raw source bodies, prompts,
  provider payloads, source payloads, hidden item details, or newly exposed
  evidence refs. FOS-069 adds no send path, delivery result record creation,
  execution API mutation, outbox table, scheduler job, new table, or migration.
- Test-only bounded Telegram send attempts for delivery intentions are local
  operator actions that reuse stored delivery drafts, intentions, plans,
  preflight, and execution gate metadata. The command writes only sanitized
  `digest.delivery_result.recorded` audit metadata after an attempt, keyed by
  deterministic `delivery_result_id` and operator-provided
  `execution_attempt_id`. It must not store rendered text, chunk text, bot
  tokens, chat IDs, URLs, webhook secrets, raw Telegram API responses, full
  digest snapshots, hidden item details, or newly exposed evidence refs. FOS-070
  adds no API send endpoint, production mode, scheduler job, delivery worker,
  outbox table, automatic retry, approval-triggered execution, new table, or
  migration.
- Local/dev-only synthetic persisted attention digest seed rows are explicit
  test fixtures in the local database, not company facts. The seed command uses
  deterministic IDs and fails closed on conflicts while writing only enough
  synthetic metadata to populate the persisted attention digest read model:
  `ingested_events`, `source_events`, `normalized_activity_items`, and
  `attention_triage_results`. Seed payloads must be clearly labeled synthetic
  and must not contain raw provider payloads, source bodies, prompts, secrets,
  credential values, chat IDs, webhook values, rendered digest text, chunk text,
  hidden low-priority details, or untrusted raw content. FOS-071 adds no
  delivery draft, approval, intention, plan, preflight, gate, delivery result,
  send path, scheduler job, delivery worker, outbox table, raw-storage edit,
  Obsidian export, new table, or migration.
- Duplicate-success checks for test-only Telegram sends are read-only checks
  over existing delivery result audit metadata. A prior result blocks a new
  `execution_attempt_id` only when the sanitized payload clearly has
  `result_status=succeeded`, `sent=true`, and a positive
  `delivered_chunk_count`. Failed, partial, skipped, malformed, or incomplete
  prior results do not silently count as successful duplicates. The lookup
  returns only safe metadata: delivery result ID, delivery intention ID,
  execution attempt ID, result status, sent flag, chunk counts, and recorded
  time. It must not expose rendered text, chunk text, credentials, raw Telegram
  responses, full digest snapshots, hidden item details, or newly exposed
  evidence refs. FOS-072 adds no override flag, API send endpoint, production
  mode, scheduler job, delivery worker, outbox table, automatic retry,
  approval-triggered execution, new table, or migration.
- FOS-073 adds a read-only operator report over the same delivery result audit
  metadata. It lists safe result metadata for a `delivery_intention_id`, derives
  whether the duplicate-success guard would block a new execution attempt, and
  surfaces only safe prior-success identifiers/counts. It does not append audit
  rows, send messages, read bot credentials, expose rendered text or chunks,
  expose raw Telegram/provider payloads, create a send API, add scheduler or
  worker behavior, introduce an outbox table, add a migration, or create a new
  table.
- FOS-074 adds a local manual pilot preparation path that can create only the
  existing `digest.delivery_draft.created` audit-log-backed review artifact for
  an explicit persisted attention digest window. It uses deterministic
  `delivery_draft_id` behavior, remains idempotent for the same window and
  rendered digest, and does not create approval/rejection rows, readiness
  records, delivery intentions, Telegram plans, preflight/gate records, delivery
  results, scheduler jobs, outbox rows, migrations, or new tables.
- FOS-075 extends that preparation path with read-only stale draft status. It
  reads existing `digest.delivery_intention.created` rows by
  `before_ref=delivery_draft_id` and existing `digest.delivery_result.recorded`
  rows by `before_ref=delivery_intention_id`, then reports only safe IDs,
  counts, statuses, and prior-success metadata. A draft is considered already
  sent only when an associated result has `result_status=succeeded`, `sent=true`,
  and `delivered_chunk_count > 0`; failed, partial, skipped, malformed, or
  incomplete results do not silently count as successful sends.
- FOS-075 appends no rows for the status lookup and does not approve, create
  intentions, create results, send, schedule, create outbox rows, add
  migrations, or add tables. Delivery drafts, intentions, and results remain
  audit/review/execution metadata, not source-of-truth company facts.
- FOS-076 adds a local/dev-only combined seed-and-draft operator path. It
  reuses the existing synthetic persisted attention seed rows
  (`ingested_events`, `source_events`, `normalized_activity_items`, and
  `attention_triage_results`) plus the existing
  `digest.delivery_draft.created` audit-log-backed review artifact. Re-running
  the same sample/window/draft inputs remains idempotent and appends no
  duplicate seed rows or draft audit rows.
- FOS-076 does not create approval/rejection rows, readiness records, delivery
  intentions, Telegram plans, preflight/gate records, delivery results,
  scheduler jobs, outbox rows, migrations, or new tables. It may surface the
  FOS-075 already-sent draft warning from existing audit rows, but the warning
  is status metadata only. Synthetic sample rows are local/dev test fixtures,
  not source-of-truth company facts.
- FOS-077 adds a local approved-draft handoff operator path. It reads an
  explicit stored `delivery_draft_id`, verifies existing approval and readiness,
  refuses stale/already-sent drafts using the FOS-075 status lookup, and creates
  or returns the deterministic `digest.delivery_intention.created` audit event
  through the existing FOS-064 service path.
- FOS-077 appends no approval/rejection rows, delivery result rows, Telegram
  plans, preflight/gate records, scheduler jobs, outbox rows, migrations, or new
  tables. Its derived review/status/gate summaries expose only safe IDs, counts,
  hashes, statuses, blockers, and safety flags; delivery drafts, intentions,
  and results remain audit/review/execution metadata, not source-of-truth
  company facts.
- FOS-078 adds a read-only manual pilot status report over an explicit persisted
  attention digest window and optional synthetic `sample_id`. It reads
  `attention_triage_results` for safe digest counts and existing
  `audit_logs` rows for matching drafts, approval decisions, delivery
  intentions, and delivery results. The report exposes only safe counts, IDs,
  hashes, statuses, duplicate/stale metadata, recommended next action, and
  placeholder command shapes.
- FOS-078 appends no seed rows, draft rows, decision rows, intention rows,
  result rows, Telegram plan/preflight/gate rows, scheduler jobs, outbox rows,
  migrations, or new tables. It does not expose rendered text, stored digest
  text, chunk text, raw payloads, credential values, hidden low-priority item
  details, or newly exposed evidence refs. Manual pilot status is operational
  metadata only and is not source-of-truth company data.
- FOS-079 adds a read-only persisted attention window discovery operator
  command. It reads `attention_triage_results` over explicit bounded windows
  for safe count summaries and reads existing `audit_logs` rows for matching
  delivery draft, decision, intention, and result lifecycle metadata. It can
  label synthetic/local/dev windows when safe FOS-071 seed markers are present,
  but absence of that marker is not proof of production truth.
- FOS-079 appends no seed rows, draft rows, decision rows, intention rows,
  result rows, Telegram plan/preflight/gate rows, scheduler jobs, outbox rows,
  migrations, or new tables. It does not expose rendered text, stored digest
  text, chunk text, digest item details, raw payloads, credential values, hidden
  low-priority item details, or newly exposed evidence refs. Window discovery is
  operational metadata only and is not source-of-truth company data.
- FOS-080 adds a read-only real stored local data readiness operator command
  over existing `source_events`, `normalized_activity_items`, and
  `attention_triage_results`. It returns only aggregate counts, synthetic/no-
  marker labels, pipeline coverage booleans, and recommended next actions for
  explicit bounded windows. It does not treat no-marker rows as production
  truth and does not expose row-level titles, summaries, actions, people, URLs,
  source identifiers, raw refs, raw payloads, provider payloads, prompts,
  evidence refs, rendered digest text, chunk text, secrets, credential values,
  or hidden low-priority details.
- FOS-080 appends no source events, normalized activity rows, attention result
  rows, seed rows, draft rows, decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations,
  or new tables. Readiness discovery is operational metadata only and is not
  source-of-truth company data.
- FOS-081 adds a read-only stored source event normalization preview over
  existing `source_events` and linked `normalized_activity_items`. It returns
  only aggregate source event counts, synthetic/no-marker counts, already-
  normalized counts, eligible/unsupported/invalid preview counts, safe projected
  normalized source/activity-type counts, and recommended next actions. It does
  not treat no-marker rows as production truth and does not expose row-level
  titles, summaries, actions, people, URLs, source object identifiers, raw refs,
  raw payloads, provider payloads, prompts, evidence refs, rendered digest text,
  chunk text, secrets, credential values, or hidden low-priority details.
- FOS-081 appends no source events, normalized activity rows, attention result
  rows, seed rows, draft rows, decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations,
  or new tables. Normalization preview is operational metadata only and is not
  source-of-truth company data; any future projection write command must be
  separate and explicit.
- FOS-082 adds a local/dev-only stored source event normalization operator
  command. It requires an explicit timezone-aware window, bounded `--max-events`,
  and the exact `NORMALIZE STORED SOURCE EVENTS` confirmation phrase before
  calling the existing provider-free
  `project_source_event_to_normalized_activity_item` service. It refuses
  production-like environments, excludes clearly synthetic local/dev rows by
  default, skips already-normalized rows, counts unsupported or invalid rows
  safely, and is idempotent by `source_event_id`.
- FOS-082 writes only `normalized_activity_items` rows and only through the
  existing normalized activity service. It appends no source events, attention
  result rows, audit logs, seed rows, draft rows, decision rows, intention rows,
  result rows, Telegram plan/preflight/gate rows, scheduler jobs, outbox rows,
  migrations, or new tables. Its output is count-only operational metadata and
  must not expose row-level titles, summaries, actions, people, URLs, source
  object identifiers, raw refs, raw payloads, provider payloads, prompts,
  evidence refs, rendered digest text, chunk text, secrets, credential values,
  or hidden low-priority details. No-marker rows are not production truth, and
  attention triage remains a separate explicit step.
- FOS-083 adds a read-only normalized activity triage readiness preview over
  existing `normalized_activity_items` and linked `attention_triage_results`.
  It reports only aggregate normalized activity counts, synthetic/no-marker
  counts, already-triaged and untriaged counts, provider-free eligibility
  counts, and conservative fallback projected attention class, priority,
  visible, and hidden counts.
- FOS-083 appends no source events, normalized activity rows, attention result
  rows, audit logs, seed rows, draft rows, decision rows, intention rows,
  result rows, Telegram plan/preflight/gate rows, scheduler jobs, outbox rows,
  migrations, or new tables. It does not call write-oriented triage services,
  live APIs, providers/OpenAI, connectors, Telegram/Slack, or delivery code.
  Its output is count-only operational metadata and must not expose row-level
  titles, summaries, actions, people, URLs, source object identifiers, raw
  refs, raw payloads, provider payloads, prompts, evidence refs, rendered
  digest text, chunk text, secrets, credential values, or hidden low-priority
  details. No-marker rows are not production truth, and attention triage writes
  remain a separate explicit local/dev step.
- FOS-084 adds a local/dev-only provider-free normalized activity triage
  operator command. It requires an explicit timezone-aware window, bounded
  `--max-items`, and the exact `TRIAGE NORMALIZED ACTIVITY` confirmation
  phrase before calling the existing `triage_normalized_activity_item` service
  with the provider-free fallback. It refuses production-like environments,
  excludes clearly synthetic local/dev rows by default, skips already-triaged
  rows, counts unsupported or invalid rows safely, and is idempotent by
  `activity_item_id`.
- FOS-084 writes only `attention_triage_results` rows and only through the
  existing strict schema-validated attention result service. It appends no
  source events, normalized activity rows, audit logs, seed rows, draft rows,
  decision rows, intention rows, result rows, Telegram plan/preflight/gate
  rows, scheduler jobs, outbox rows, migrations, or new tables. Its output is
  count-only operational metadata and must not expose row-level titles,
  summaries, actions, people, URLs, source object identifiers, raw refs, raw
  payloads, provider payloads, prompts, evidence refs, rendered digest text,
  chunk text, secrets, credential values, or hidden low-priority details.
  No-marker rows are not production truth; real-data readiness and persisted
  attention window discovery remain separate explicit checks.
- FOS-085 adds a local read-only persisted attention window reconciliation
  report. It compares attention-result `created_at` windows with optional
  linked normalized/source activity windows, labels synthetic/no-marker/mixed
  windows conservatively, and computes the current digest `text_sha256` without
  returning rendered digest text or chunk text.
- FOS-085 also compares the current digest hash with existing delivery draft
  hashes for the same window, limit, debug-evidence setting, and channel. It
  distinguishes successful delivery for different digest content from
  successful delivery for the current digest content. It appends no source
  events, normalized activity rows, attention results, audit logs, draft rows,
  decision rows, intention rows, result rows, Telegram plan/preflight/gate
  rows, scheduler jobs, outbox rows, migrations, or new tables. Its output is
  count-only operational metadata plus hashes and must not expose row-level
  titles, summaries, actions, people, URLs, source object identifiers, raw refs,
  raw payloads, provider payloads, prompts, evidence refs, rendered digest text,
  chunk text, secrets, credential values, or hidden low-priority details.
  No-marker rows are not production truth, and real stored local draft
  preparation remains separately human-gated.
- FOS-086 adds a local read-only no-marker persisted attention candidate
  report. It reads existing `attention_triage_results` for an explicit
  persisted window, excludes rows with detected synthetic/local/dev markers,
  and computes no-marker-only candidate count metadata plus digest hash/chunk
  metadata without returning rendered digest text, chunk text, raw content, row
  details, or evidence refs.
- FOS-086 compares the no-marker candidate hash with existing delivery draft
  hashes for the same window, limit, debug-evidence setting, and channel. It
  distinguishes prior successful delivery for different digest content from
  successful delivery for the current no-marker candidate content. It appends no
  source events, normalized activity rows, attention results, audit logs, draft
  rows, decision rows, intention rows, result rows, Telegram plan/preflight/gate
  rows, scheduler jobs, outbox rows, migrations, or new tables. No-marker rows
  are not production truth, and real stored local draft preparation remains a
  separate explicit downstream step.
- FOS-087 adds a local/dev-only no-marker persisted attention delivery draft
  preparation command. It writes only one sanitized
  `digest.delivery_draft.created` audit-log record through the existing
  delivery draft persistence path, and only after an explicit time window,
  exact confirmation phrase, local/dev environment check, and visible
  no-marker candidate check pass.
- FOS-087 draft payloads carry safe review metadata such as
  `marker_filter=no_marker_only`, `no_marker_not_production_truth=true`, the
  no-marker candidate `text_sha256`, candidate count/chunk metadata, excluded
  synthetic counts, optional linked activity window metadata, timestamp
  mismatch warnings, and prior-different-hash warnings. They remain delivery
  draft review artifacts, not source-of-truth company facts. FOS-087 does not
  append approval, intention, result, Telegram plan/preflight/gate, scheduler,
  worker, outbox, migration, or new-table records and does not call live APIs,
  providers/OpenAI, connectors, Telegram/Slack, or delivery code.
- FOS-088 adds a read-only no-marker persisted attention digest quality report.
  It reads existing no-marker candidate attention results and linked normalized
  activity/source-event metadata to compute duplicate-looking/noise metrics at
  rendered-shape, attention-result, normalized-activity, and source-event
  linkage layers. It returns counts, safe enum summaries, opaque cluster labels,
  candidate hash/chunk metadata, lifecycle status, warnings, and limitations
  only.
- FOS-088 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations,
  or tables. It does not expose raw titles, summaries, actions, source object
  identifiers, PR numbers, repository names, author names, rendered digest text,
  chunk text, raw payloads, evidence refs, secrets, or credentials, and it does
  not call live APIs, providers/OpenAI, connectors, Telegram/Slack, or delivery
  code. Duplicate-looking remains operational quality metadata, not proof of a
  semantic duplicate.
- FOS-089 adds a read-only no-marker duplicate root-cause linkage report. It
  reads existing no-marker candidate attention results and linked normalized
  activity/source event metadata to compute safe bucket counts, fanout metrics,
  likely origin, confidence, warnings, and limitations across source object,
  source event, normalized activity, attention result, and rendered-shape
  layers.
- FOS-089 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations,
  or tables. It does not modify renderer grouping, digest read-model grouping,
  source event dedupe, normalization dedupe, attention triage dedupe, or
  delivery behavior. It does not expose raw source object identifiers, PR
  numbers, repository names, author names, titles, summaries, actions, source
  bodies, evidence refs, rendered digest text, chunk text, raw payloads,
  secrets, credentials, or raw fingerprints and does not call live APIs,
  providers/OpenAI, connectors, Telegram/Slack, or delivery code.
- FOS-090 adds a read-only no-marker grouped digest preview. It reads existing
  no-marker candidate attention results and linked normalized activity/source
  event metadata to group repeated source-object visible items by source object
  for presentation planning only, returning count-only group metadata, opaque
  group labels, safe enum summaries, per-section counts, and a separate grouped
  preview hash/chunk metadata. Every visible item maps to exactly one group, the
  sum of group item counts equals the ungrouped visible count, and the canonical
  ungrouped candidate `text_sha256` is returned unchanged.
- FOS-090 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations,
  or tables. It does not modify renderer grouping, digest read-model grouping,
  delivery draft text, `text_sha256` lifecycle, source event dedupe,
  normalization dedupe, attention triage dedupe, or delivery behavior. It does
  not expose raw source object identifiers, PR numbers, repository names, author
  names, titles, summaries, actions, source bodies, evidence refs, rendered
  digest text, grouped preview text, chunk text, raw payloads, secrets,
  credentials, or raw fingerprints and does not call live APIs, providers/OpenAI,
  connectors, Telegram/Slack, or delivery code.
- FOS-091 adds a read-only no-marker grouped lifecycle compatibility report. It
  reuses the grouped preview (canonical candidate hash, grouped preview hash,
  duplicate-quality, canonical lifecycle) and reads existing window delivery
  draft/result lifecycle facts (per-draft `text_sha256` and a derived
  successful-delivery boolean) to classify whether a grouped preview would be
  treated as `already_sent` or a `new_unsent_presentation_variant` under the
  current hash-oriented duplicate guard, and flags
  `presentation_variant_duplicate_send_risk` and
  `requires_guard_extension_before_grouped_send`.
- FOS-091 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations,
  or tables. It does not modify renderer grouping, digest read-model grouping,
  delivery draft text, `text_sha256` lifecycle, draft/intention/result id
  derivation, the duplicate-success guard, source event dedupe, normalization
  dedupe, attention triage dedupe, or delivery behavior. The grouped hash is a
  presentation-variant hash and is not delivered content; a future grouped
  draft/send requires a guard extension or canonical-hash linkage. It does not
  expose raw source object identifiers, PR numbers, repository names, author
  names, titles, summaries, actions, source bodies, evidence refs, rendered
  digest text, grouped preview text, chunk text, raw payloads, secrets,
  credentials, or raw fingerprints and does not call live APIs, providers/OpenAI,
  connectors, Telegram/Slack, or delivery code.
- FOS-092 adds a read-only canonical-hash duplicate guard evaluator for
  presentation variants. It reads existing `digest.delivery_draft.created`,
  `digest.delivery_intention.created`, and `digest.delivery_result.recorded`
  audit metadata for an explicit delivery window, current presentation
  `text_sha256`, and optional explicitly linked canonical `text_sha256`, then
  reports whether the current presentation hash has a successful delivery result
  and whether a distinct canonical hash has a successful delivery result.
- FOS-092 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations, or
  tables. It does not enforce blocking in send paths yet, does not change
  renderer grouping, digest read-model grouping, delivery draft text,
  `text_sha256` lifecycle, draft/intention/result id derivation, delivery result
  writing, or delivery behavior, and does not claim semantic duplication. It
  only evaluates explicitly linked canonical/presentation hashes; grouping
  preview remains presentation planning, not source-of-truth mutation, and
  duplicate-success protection remains the final send-time guard.
- FOS-093 exposes the FOS-092 evaluator inside the read-only no-marker grouped
  lifecycle compatibility report. It does not add new storage. The report maps
  the grouped preview hash to the current presentation hash and the no-marker
  candidate hash to the linked canonical hash, then returns only sanitized
  evaluation metadata: current-hash success, linked-canonical success, future
  blocker/recommended-action codes, `enforced=false`, and
  `semantic_duplicate_claimed=false`.
- FOS-093 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations, or
  tables. It does not enforce blocking in send paths, does not change renderer
  grouping, digest read-model grouping, delivery draft text, `text_sha256`
  lifecycle, delivery result writing, or delivery behavior, and does not claim
  semantic duplication. It only applies to explicitly linked
  canonical/presentation hashes; grouping preview remains presentation planning,
  not source-of-truth mutation, and duplicate-success protection remains the
  final send-time guard.
- FOS-094 adds a read-only operator decision summary to the grouped lifecycle
  compatibility report. It does not add new storage. The summary is derived
  from existing lifecycle compatibility and canonical-hash guard evaluation
  metadata, and reports a sanitized decision for current-hash already-sent,
  explicitly linked canonical-hash blocker, not-blocked, or manual-review
  outcomes.
- FOS-094 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations, or
  tables. It does not enforce blocking in send paths, does not change renderer
  grouping, digest read-model grouping, delivery draft text, `text_sha256`
  lifecycle, delivery result writing, or delivery behavior, and does not claim
  semantic duplication. It only applies to explicitly linked
  canonical/presentation hashes; missing or insufficient evidence leads to
  conservative manual review, grouping preview remains presentation planning,
  and duplicate-success protection remains the final send-time guard.
- FOS-095 adds sanitized contract tests for the grouped lifecycle compatibility
  report. It does not add new storage. The tests cover
  `lifecycle_compatibility`, `canonical_hash_guard_evaluation`, and
  `operator_review_summary`, including required fields, stable decision values,
  `enforced=false`, `semantic_duplicate_claimed=false`, and sanitized JSON/text
  output.
- FOS-095 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations, or
  tables. It does not enforce blocking in send paths, does not change renderer
  grouping, digest read-model grouping, delivery draft text, `text_sha256`,
  API behavior, schema, delivery result writing, delivery execution, or
  scheduler behavior, and does not claim semantic duplication. Grouping preview
  remains presentation planning, and duplicate-success protection remains the
  final send-time guard.
- FOS-096 adds a decision-only `review-json` output mode for the grouped
  lifecycle compatibility report. It does not add new storage. The output
  contains only minimal safe report/window metadata,
  `lifecycle_compatibility`, `canonical_hash_guard_evaluation`,
  `operator_review_summary`, and safety flags.
- FOS-096 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations, or
  tables. It does not enforce blocking in send paths, does not change renderer
  grouping, digest read-model grouping, delivery draft text, `text_sha256`, API
  behavior, schema, delivery result writing, delivery execution, scheduler
  behavior, or automatic delivery, and does not claim semantic duplication.
  Grouping preview remains presentation planning, and duplicate-success
  protection remains the final send-time guard.
- FOS-097 improves grouped lifecycle report CLI help and adds a local synthetic
  review smoke mode. It does not add new storage. The smoke mode returns
  in-memory synthetic scenarios over `lifecycle_compatibility`,
  `canonical_hash_guard_evaluation`, and `operator_review_summary` so local
  operators can verify the sanitized decision surface without reading real
  local data.
- FOS-097 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations, or
  tables. It does not enforce blocking in send paths, does not change renderer
  grouping, digest read-model grouping, delivery draft text, `text_sha256`, API
  behavior, schema, delivery result writing, delivery execution, scheduler
  behavior, or automatic delivery, and does not claim semantic duplication.
  Grouping preview remains presentation planning, and duplicate-success
  protection remains the final send-time guard.
- FOS-098 adds optional grouped lifecycle review exit codes and sanitized JSON
  artifact output. It does not add new storage. Exit codes are derived only from
  `operator_review_summary.decision`; artifact output is limited to
  `review-json` and synthetic review smoke JSON, and artifact files are local
  review artifacts rather than source-of-truth records.
- FOS-098 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations, or
  tables. It rejects unsafe artifact paths and unsafe output modes, does not
  enforce blocking in send paths, does not change renderer grouping, digest
  read-model grouping, delivery draft text, `text_sha256`, API behavior, schema,
  delivery result writing, delivery execution, scheduler behavior, or automatic
  delivery, and does not claim semantic duplication. Grouping preview remains
  presentation planning, and duplicate-success protection remains the final
  send-time guard.
- FOS-099 adds a provider-free grouped lifecycle review operator doctor. It does
  not add new storage. The doctor checks CLI help/discoverability, synthetic
  review smoke output, `review-json` contract shape, review exit-code mapping,
  sanitized artifact writing, and unsafe artifact rejection using synthetic
  in-memory review data and a local temporary JSON artifact only.
- FOS-099 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations, or
  tables. It does not use real local data, does not enforce blocking in send
  paths, does not change renderer grouping, digest read-model grouping, delivery
  draft text, `text_sha256`, API behavior, schema, delivery result writing,
  delivery execution, scheduler behavior, or automatic delivery, and does not
  claim semantic duplication. Any doctor artifact is a local review/debug
  artifact only, grouping preview remains presentation planning, and
  duplicate-success protection remains the final send-time guard.
- FOS-100 adds a gated manual local grouped lifecycle review runner. It does not
  add new storage. The runner blocks by default unless
  `--allow-local-data-readonly` is passed, runs the provider-free doctor before
  delegation, forces sanitized `review-json`, requires a safe local artifact
  path, and rejects unsafe output modes or artifact paths before report
  execution.
- FOS-100 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations, or
  tables. It does not enforce blocking in send paths, does not change renderer
  grouping, digest read-model grouping, delivery draft text, `text_sha256`, API
  behavior, schema, delivery result writing, delivery execution, scheduler
  behavior, or automatic delivery, and does not claim semantic duplication.
  Runner artifacts are local review/debug artifacts only, grouping preview
  remains presentation planning, and duplicate-success protection remains the
  final send-time guard.
- FOS-102 adds safe bounded window presets and preflight planning to the manual
  grouped lifecycle review runner. It does not add new storage.
  `--lookback-hours` resolves UTC `--start-at`/`--end-at` values for local
  read-only debugging, and `--preflight-only` validates acknowledgement, doctor
  readiness, output mode, artifact path, and the resolved window without report
  execution.
- FOS-102 appends no source events, normalized activity rows, attention results,
  audit logs, draft rows, approval/decision rows, intention rows, result rows,
  Telegram plan/preflight/gate rows, scheduler jobs, outbox rows, migrations, or
  tables. It does not enforce blocking in send paths, does not change renderer
  grouping, digest read-model grouping, delivery draft text, `text_sha256`, API
  behavior, schema, delivery result writing, delivery execution, scheduler
  behavior, or automatic delivery, and does not claim semantic duplication.
  Runner artifacts are local review/debug artifacts only, grouping preview
  remains presentation planning, and duplicate-success protection remains the
  final send-time guard.
- FOS-104 adds sanitized manual-review diagnostics to grouped lifecycle review
  output. The diagnostics are derived from already sanitized lifecycle
  compatibility, canonical-hash guard evaluation, operator review summary, and
  resolved window metadata. They expose booleans, stable reason codes, and safe
  next-step/action codes only; they add no source events, normalized activity
  rows, attention results, audit logs, draft rows, approval/decision rows,
  intention rows, result rows, Telegram plan/preflight/gate rows, scheduler
  jobs, outbox rows, migrations, or tables.
- FOS-104 diagnostics are read-only reporting/debug metadata only. They do not
  enforce blocking in send paths, do not claim semantic duplication, do not
  change renderer grouping, digest read-model grouping, delivery draft text,
  `text_sha256`, API behavior, schema, delivery result writing, delivery
  execution, scheduler behavior, or automatic delivery. Runner artifacts remain
  local review/debug artifacts only, grouping preview remains presentation
  planning, and duplicate-success protection remains the final send-time guard.
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
