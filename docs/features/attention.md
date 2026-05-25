# Feature: Attention

## Status

- Deterministic scoring: implemented
- Attention dashboard: implemented
- Feedback storage: implemented
- Normalized activity item persistence foundation: implemented
- Attention triage result persistence and single-activity bridge foundation:
  implemented
- Persisted attention digest read model and deterministic text renderer:
  implemented
- Protected persisted attention digest preview endpoints: implemented
- Synthetic manual pilot persisted attention digest preview artifact: implemented
- Read-only persisted attention digest operator preview script: implemented
- Read-only persisted attention digest delivery draft preview: implemented
- Audit-log-backed persisted attention digest delivery draft review records:
  implemented
- Audit-log-backed persisted attention digest delivery draft approval decisions:
  implemented
- Read-only persisted attention digest delivery readiness preview: implemented
- Audit-log-backed persisted attention digest delivery intention records:
  implemented
- Pure Telegram delivery plan preview for delivery intentions: implemented
- Read-only delivery intention operator review command: implemented
- Read-only Telegram execution preflight for delivery intentions: implemented
- Delivery result audit contract for future Telegram sends: implemented
- Read-only bounded Telegram execution gate preview: implemented
- Test-only bounded Telegram delivery intention send command: implemented
- Local/dev-only synthetic persisted attention digest seed command: implemented
- Duplicate-success protection for test-only Telegram sends: implemented
- Local approved-draft manual pilot handoff command: implemented
- Read-only manual pilot status report by sample/window: implemented
- Read-only persisted attention window discovery for manual pilots:
  implemented
- Read-only real stored local data readiness discovery: implemented
- Read-only stored source event normalization preview: implemented
- Local/dev-only stored source event normalization command: implemented
- GitHub/Jira/Drive activity normalization: implemented
- LLM-generated digest: planned
- Telegram delivery: planned

## Current Behavior

- Extracted tasks, risks, and decisions can be scored.
- Scores include importance, urgency, risk, confidence, attention, reasons, and evidence refs.
- Attention dashboard reads existing scores and builds top items, tasks, risks, decisions, and sources.
- Source activity digest email sectioning uses the attention triage contract
  through an in-memory deterministic projection.
- Attention triage feedback can be stored and retrieved for future
  `AttentionContext.recent_feedback` use.
- Stored feedback is loaded as bounded advisory context for email triage calls
  that classify existing `EmailThreadState` rows.
- Strictly validated `NormalizedActivityItem` records can be persisted as safe
  metadata for future durable source-event-to-attention linkage.
- Supported stored `SourceEvent` rows can be projected provider-free into
  persisted normalized activity rows idempotently by `source_event_id`.
- Strictly validated `AttentionTriageResult` records can be persisted as safe
  metadata for future feedback linkage.
- One persisted `NormalizedActivityItem` can be classified provider-free or
  with an injected test provider through `AttentionTriageAgent`, then persisted
  as one linked `AttentionTriageResult` by `activity_item_id`.
- Persisted `AttentionTriageResult` rows can be read provider-free as a digest
  read model for explicit timezone-aware windows. The read model groups visible
  rows into daily digest section keys, keeps hidden/no-action low-priority rows
  count-only, and optionally enriches visible items from linked
  `NormalizedActivityItem` rows.
- Persisted attention digest read models can be rendered provider-free as
  deterministic text. The renderer shows only safe item fields, keeps hidden
  low-priority rows count-only, and exposes evidence refs only in debug mode
  through the existing safe evidence formatter.
- Protected preview endpoints can return the persisted attention digest read
  model and rendered text for explicit timezone-aware windows. They read only
  persisted attention digest data, do not run triage or providers, keep hidden
  low-priority rows count-only, and expose evidence refs only through explicit
  safe debug output.
- The manual pilot dry run includes a synthetic persisted attention digest
  preview artifact rendered through the same deterministic provider-free
  renderer. The pilot artifact does not read database data, call APIs, run
  triage, call providers or OpenAI, or send Telegram/Slack messages.
- A local read-only operator preview script can render stored persisted
  attention digest data for an explicit timezone-aware window. It uses the real
  deterministic persisted attention digest renderer, does not run triage, does
  not call APIs, providers/OpenAI, connectors, Telegram/Slack, scheduler, or
  delivery code, keeps hidden low-priority items count-only, and exposes
  evidence refs only through safe debug output.
- A protected read-only delivery draft preview can build an inert human-review
  artifact from already-rendered persisted attention digest text. The draft is
  provider-free, is not persisted, is not an approval, does not send Telegram or
  Slack messages, does not run scheduler or delivery code, keeps hidden
  low-priority items count-only, and exposes evidence refs only through safe
  debug output.
- A protected persisted delivery draft creation path can store an inert
  persisted attention digest delivery draft as one `audit_logs` review record.
  The persisted draft gets a deterministic `delivery_draft_id` derived from safe
  window metadata and the rendered text hash, stores only sanitized draft data,
  remains a review artifact rather than source-of-truth data, is not an
  approval, is not sent, and does not run scheduler, delivery, triage,
  providers/OpenAI, connectors, or live APIs. Recreating the same draft returns
  the existing audit-log-backed record instead of appending a duplicate.
- Persisted delivery draft retrieval reads the stored audit-log payload by
  `delivery_draft_id` without recomputing digest contents or writing new rows.
  Hidden low-priority items remain count-only, and evidence refs remain
  safe-formatted debug-only.
- Protected approval and rejection endpoints can record human decisions for a
  persisted attention digest delivery draft as separate `audit_logs` events.
  Approval and rejection are decision records only: they do not mutate the
  draft event, do not make the draft source-of-truth data, do not send
  Telegram/Slack messages, and do not execute delivery. The approval status API
  reads stored draft and decision events without recomputing digest contents.
- A protected delivery readiness endpoint can read a persisted delivery draft
  and its approval/rejection decision state by `delivery_draft_id` and report
  whether the draft is eligible for a future separately gated delivery path.
  Readiness is read-only, does not recompute digest contents, does not create
  outbox records, does not mutate draft or decision records, does not send
  Telegram/Slack messages, and does not execute approval or delivery. The
  response exposes only safe draft hash/window/chunk metadata, source-of-truth
  metadata, decision history, and inert safety flags.
- A protected delivery intention endpoint can append one sanitized
  `audit_logs` handoff record for an approved and ready persisted delivery
  draft. The intention is deterministic and idempotent by safe draft/readiness
  metadata, is execution metadata rather than a company fact, does not include
  rendered digest text or full digest snapshots, does not create a scheduler job
  or outbox worker, and does not send Telegram/Slack messages or invoke
  delivery adapters.
- A protected Telegram delivery plan endpoint can read a stored delivery
  intention and its referenced persisted delivery draft, then return
  deterministic Telegram chunk metadata for a future separately gated send path.
  The plan is a dry-run/pre-send review artifact only: it uses stored rendered
  text internally for hashing and chunking, but it does not return rendered text
  or chunk text, does not require bot credentials, does not call delivery
  adapters, does not append audit rows, does not create scheduler jobs or
  outbox records, and does not send Telegram/Slack messages.
- A local read-only operator review command can review the stored delivery
  chain by `delivery_intention_id`: delivery intention, referenced delivery
  draft, approval status, readiness, and Telegram delivery plan. The command is
  review-only, omits rendered digest text by default, never includes chunk
  text, and does not call APIs, create or mutate records, require bot
  credentials, call delivery adapters, run scheduler behavior, or send
  Telegram/Slack messages.
- A protected read-only Telegram execution preflight can inspect a stored
  delivery intention and existing Telegram delivery plan, then report whether
  Telegram bot token and chat ID configuration are present. The preflight
  returns only booleans and safe blockers, never credential values, never
  validates credentials against Telegram, never sends, never invokes delivery
  adapters, and always keeps delivery execution disabled.
- A delivery result audit contract can record and retrieve sanitized future
  Telegram send outcomes in `audit_logs` by deterministic `delivery_result_id`.
  Result records are execution outcome metadata, not source-of-truth company
  facts, and they never include rendered text, chunk text, credential values,
  raw Telegram responses, raw/provider/source payloads, hidden low-priority
  details, or newly exposed evidence refs. FOS-068 does not implement sending or
  expose a public result creation endpoint.
- A protected read-only bounded Telegram execution gate can inspect a stored
  delivery intention and combine approval, readiness, Telegram plan,
  credential-presence preflight, result-contract readiness, chunk bounds, and
  future operator-required fields. The gate keeps delivery execution disabled,
  requires a future bounded operator request, never exposes credential values,
  never validates credentials against Telegram, never creates delivery result
  records, and never sends Telegram/Slack messages.
- A local test-only bounded Telegram send operator command can send a stored
  delivery intention after explicit operator input. It requires
  `delivery_intention_id`, `execution_attempt_id`, bounded `max_chunks`,
  `test_mode=true`, and the exact confirmation phrase
  `SEND TEST TELEGRAM DIGEST`. It sends only after existing approval,
  readiness, intention, Telegram plan, preflight, and execution gate checks
  pass; sends only bounded chunks to the configured Telegram test chat; records
  sanitized delivery result audit metadata after the attempt; never prints or
  stores bot token, chat ID, rendered text, chunk text, raw Telegram responses,
  or hidden low-priority details; and adds no API send endpoint, scheduler,
  delivery worker, outbox table, production mode, automatic retry, or
  approval-triggered execution.
- A local/dev-only synthetic persisted attention digest seed command can create
  one clearly synthetic persisted attention sample when a local database has no
  visible persisted attention items. The command requires an explicit
  `sample_id`, timezone-aware `created_at`, and exact confirmation phrase. It
  writes only the synthetic persisted source/normalized activity/attention
  chain needed for the persisted digest read model, refuses production-like
  environments, is idempotent by deterministic IDs, calls no providers/OpenAI,
  connectors, Telegram/Slack, scheduler, or delivery worker, and does not create
  delivery drafts, approvals, intentions, plans, preflight/gate records, result
  records, sends, raw storage files, or Obsidian exports.
- Duplicate-success protection prevents the local test-only Telegram send
  command from sending a `delivery_intention_id` again when a prior sanitized
  delivery result for that intention is clearly `succeeded`, `sent=true`, and
  has delivered at least one chunk. Reusing the same `execution_attempt_id`
  remains idempotent and returns the stored result without sending. Failed,
  partial, skipped, malformed, or incomplete prior results do not silently count
  as successful duplicates, and there is no override flag in this slice.
- GitHub, Jira, and Drive source-event-like inputs can be mapped into
  `NormalizedActivityItem` objects without calling live providers or source
  APIs.

## Universal Activity Triage

- FOS-041 adds reusable contracts for a future universal attention triage layer.
- FOS-044 aligns those contracts with the QazTwin Company Knowledge OS
  playbook.
- The layer normalizes source activity from Gmail, GitHub, Jira, Drive, calendar, and other sources into a common `NormalizedActivityItem`.
- `NormalizedActivityItem` exposes `source`, `source_object_id`,
  `activity_type`, `title`, `actor`, `created_at`, `project`, `safe_summary`,
  `related_people`, `related_jira_keys`, `related_prs`, `related_files`, and
  `evidence_refs`.
- Providers return strict, schema-validated `AttentionTriageResult` objects
  with `attention_class`, `priority`, `show_in_digest`, `confidence`, `reason`,
  `recommended_action`, `owner`, `deadline`, and `evidence`.
- The confidence policy prevents low-confidence items from being silently hidden; uncertain items stay visible as review optional.
- The current implementation includes mocked and conservative fallback providers only. It does not call external APIs.
- OpenAI or Llama-compatible providers can be wired in a later slice once explicitly enabled and configured.

## OpenAI Provider Scaffold

- FOS-042 adds an OpenAI-compatible `AttentionTriageProvider` scaffold.
- The scaffold is disabled by default and is not wired into email thread rebuilding or digest rendering.
- It accepts an injected client for tests or future runtime wiring; it does not create a live provider client by default.
- Provider output is parsed as strict JSON and validated against `AttentionTriageResult`.
- Invalid JSON, invalid enum values, extra fields, provider errors, disabled config, or missing injected clients fall back to conservative triage.
- The confidence policy still prevents low-confidence output from being silently hidden.
- No external provider calls happen unless a later slice explicitly enables and wires a client.

## Email Attention Seam

- FOS-043 adds a disabled, non-mutating seam from `EmailThreadState` to `NormalizedActivityItem`.
- Existing email thread rows can now be classified through `AttentionTriageAgent` with fallback or injected mock providers.
- The seam does not write `AttentionTriageResult` back to the database and does not change digest rendering.
- The preview script uses conservative fallback behavior by default and prints only aggregate metadata.
- Source activity digest output still uses deterministic FOS-040
  `EmailThreadState` rows as source data.
- FOS-044 does not wire digest rendering to `AttentionTriageResult`; current
  digest behavior intentionally remains unchanged.
- FOS-045 wires email digest sectioning to an in-memory
  `AttentionTriageResult` projection derived from existing deterministic
  `EmailThreadState` fields. The projection applies the confidence policy
  before section mapping.
- FOS-045 is email-only. It does not persist `AttentionTriageResult`, does not
  add schema or migrations, and does not call live providers.
- FOS-046 adds provider-free DB-backed feedback storage and retrieval for the
  playbook feedback actions: `marked_important`, `marked_noise`,
  `marked_no_action`, `marked_reply_required`, `always_show_similar`, and
  `always_hide_similar`.
- Feedback is stored as user context for future triage calls, not as
  fine-tuning data. API, CLI, and UI submission entrypoints are deferred.
- FOS-050 loads stored feedback into `AttentionContext.recent_feedback` for the
  live email triage classification path. Feedback remains advisory context only:
  it is not fine-tuning data, not a deterministic show/hide override, and it
  does not mutate `EmailThreadState` rows.
- FOS-050 does not change deterministic digest behavior. Email digest sectioning
  still uses the in-memory deterministic projection from FOS-045.
- FOS-051 adds provider-free `AttentionTriageResult` persistence. It stores
  only validated result fields and evidence refs, plus source identifiers and
  an optional future `activity_item_id`; it does not store prompts, raw source
  bodies, provider payloads, or unvalidated JSON.
- FOS-051 does not auto-persist live email/provider triage results, change
  deterministic digest behavior, add feedback overrides, add API/CLI/UI
  controls, or add `normalized_activity_items` persistence. Feedback
  `triage_result_id` remains nullable and advisory.
- FOS-052 adds provider-free `normalized_activity_items` persistence. It stores
  only validated `NormalizedActivityItem` fields and evidence refs, plus an
  optional `source_event_id` for durable source-event linkage; it does not store
  prompts, raw source bodies, provider payloads, secrets, or unvalidated JSON.
- FOS-052 does not auto-project live Gmail/GitHub/Jira/Drive/meeting events,
  change deterministic digest behavior, add feedback behavior, add API/CLI/UI
  controls, or add human approval/action flows. `AttentionTriageResult`
  `activity_item_id` remains optional.
- FOS-053 adds a provider-free bridge from one stored supported `SourceEvent`
  to one persisted `NormalizedActivityItem`. The bridge reuses the existing
  source activity mapping, validates through the shared
  `NormalizedActivityItem` contract, preserves safe evidence refs and
  `source_event_id`, and is idempotent by `source_event_id`.
- FOS-053 does not run attention triage over persisted activities, change
  deterministic digest behavior, add feedback behavior, ingest live provider
  data, add API/CLI/UI controls, or add human approval/action flows.
- FOS-054 adds a provider-free bridge from one persisted
  `NormalizedActivityItem` to one persisted `AttentionTriageResult`. The bridge
  loads bounded recent feedback into `AttentionContext` as advisory context,
  classifies through `AttentionTriageAgent` with fallback or injected test
  providers, validates the strict result contract before persistence, links the
  stored result by `activity_item_id`, and is service-level idempotent by
  `activity_item_id`.
- FOS-054 does not call live providers or OpenAI, change deterministic digest
  behavior, add batch triage, retriage/versioning, API/CLI/UI controls, human
  approvals, scheduler behavior, or feedback override logic.
- FOS-055 adds a provider-free persisted attention digest read model. It reads
  existing `attention_triage_results` rows for an explicit time window, applies
  the existing low-confidence visibility policy at read time, groups visible
  rows into work actions, manual actions, waiting external reply, important
  updates, and review optional sections, and keeps hidden/no-action
  low-priority rows in a count-only summary.
- FOS-055 can safely enrich visible digest items from linked
  `normalized_activity_items` metadata through `activity_item_id`, but missing
  linked activity rows do not fail the read model. It does not call live
  providers or OpenAI, run triage, replace existing source activity digest
  behavior, change rendering, add scheduler/delivery, add human approval/UI, or
  change feedback behavior.
- FOS-056 adds deterministic text rendering for the persisted attention digest
  read model. It renders the five visible daily attention sections, keeps
  hidden/no-action low-priority rows count-only, and limits debug evidence refs
  to the existing safe evidence formatting keys.
- FOS-056 does not call live providers or OpenAI, add API/CLI/UI controls,
  add Telegram/Slack delivery, add scheduler behavior, replace the existing
  source activity digest renderer, add human approvals, or change feedback
  behavior.
- FOS-057 adds protected provider-free preview endpoints for persisted
  attention digest JSON and rendered text. The endpoints read existing
  persisted attention digest data, use explicit time windows, preserve
  hidden/no-action low-priority rows as count-only summaries, and expose
  evidence refs only via safe debug formatting.
- FOS-057 does not call live providers or OpenAI, run triage, add scheduler or
  Telegram/Slack delivery, add migrations, change feedback behavior, replace
  source activity digest endpoints, or add human approval/action execution.
- FOS-058 adds a synthetic manual pilot preview artifact for persisted
  attention digest text. It uses the real deterministic persisted attention
  digest renderer with an in-memory sample shaped like the persisted read
  model, keeps hidden low-priority items count-only, and treats evidence refs
  as safe debug-style context only.
- FOS-058 does not read stored data, call APIs, run triage, call live providers
  or OpenAI, add scheduler/delivery wiring, add Telegram/Slack sending, change
  API endpoints, add migrations, or change feedback behavior.
- FOS-059 adds `scripts/preview_persisted_attention_digest.py`, a local
  read-only operator preview for persisted attention digest text. It requires
  explicit timezone-aware `--start-at` and `--end-at` values, accepts bounded
  limits and text/JSON output, reads existing persisted digest data, sanitizes
  JSON output, and renders text with the deterministic persisted attention
  digest renderer.
- FOS-059 does not call live providers or OpenAI, run triage, call APIs or
  connectors, add Telegram/Slack delivery, add scheduler behavior, add approval
  execution, change API endpoints, add migrations, or mutate production data.
- FOS-060 adds an inert read-only delivery draft preview for persisted
  attention digest text. It derives a human-review draft from the existing
  persisted attention digest read model and deterministic renderer, includes
  stable text and chunk metadata for review, and marks the draft as not
  approved, not sent, not persisted, and delivery-disabled.
- FOS-060 does not call live providers or OpenAI, run triage, call APIs or
  connectors, send Telegram/Slack messages, add scheduler behavior, add
  approval execution, add approval state persistence, add migrations, or mutate
  production data. Telegram and Slack remain delivery/interface surfaces only,
  not the source of truth.
- FOS-061 persists inert persisted attention digest delivery drafts as
  audit-log-backed review records. It adds a protected creation endpoint that
  appends one sanitized `digest.delivery_draft.created` audit event when the
  deterministic `delivery_draft_id` does not already exist, plus a protected
  retrieval endpoint for later review by ID.
- FOS-061 does not add approval execution, approval state transitions,
  scheduler behavior, Telegram/Slack sending, delivery wiring, migrations, a
  new table, live API calls, providers/OpenAI, connector calls, source event
  projection, triage/retriage, or feedback behavior changes. Persisted drafts
  are review artifacts only and are not source-of-truth facts.
- FOS-062 records human approval/rejection decisions for persisted attention
  digest delivery drafts as audit-log-backed events and exposes a protected
  approval status API. Decision events store only sanitized reviewer/note and
  draft hash metadata, are idempotent for repeated same decisions, and reject
  conflicting terminal decisions.
- FOS-062 does not add approval-triggered execution, scheduler behavior,
  Telegram/Slack sending, delivery wiring, migrations, a new table, live API
  calls, providers/OpenAI, connector calls, source event projection,
  triage/retriage, or feedback behavior changes. Telegram and Slack remain
  delivery/interface surfaces only, not the source of truth.
- FOS-063 adds a protected read-only delivery readiness preview for persisted
  digest delivery drafts. Readiness answers whether a draft has been approved
  and is eligible for a future separately gated delivery path, but it is not
  delivery execution, does not create an outbox/intention record, and does not
  mutate source-of-truth data, draft records, or approval decision records.
- FOS-063 does not add approval-triggered execution, scheduler behavior,
  Telegram/Slack sending, delivery wiring, delivery outbox/intention records,
  migrations, a new table, live API calls, providers/OpenAI, connector calls,
  source event projection, triage/retriage, or feedback behavior changes.
  Telegram and Slack remain delivery/interface surfaces only, not the source of
  truth.
- FOS-064 adds audit-log-backed delivery intention records for approved and
  ready persisted delivery drafts. A delivery intention is a durable handoff
  artifact for a future separately gated delivery execution path; it is not
  delivery execution, not an outbox worker, not a scheduler job, and not
  source-of-truth company data.
- FOS-064 does not add approval-triggered execution, scheduler behavior,
  Telegram/Slack sending, delivery adapter execution, delivery workers, an
  outbox table, migrations, a new table, live API calls, providers/OpenAI,
  connector calls, source event projection, triage/retriage, or feedback
  behavior changes. Telegram and Slack remain delivery/interface surfaces only,
  not the source of truth.
- FOS-065 adds a protected pure Telegram delivery plan preview for delivery
  intentions. The plan exposes safe deterministic chunk hashes and lengths for
  future delivery review, but it omits rendered text and chunk text, does not
  require bot credentials, does not call delivery adapters, does not append
  audit rows, does not create scheduler jobs, delivery result events, outbox
  records, migrations, or new tables, and does not send Telegram/Slack
  messages.
- FOS-066 adds `scripts/review_digest_delivery_intention.py`, a local
  read-only operator review command for a stored `delivery_intention_id`. It
  composes existing stored delivery intention, delivery draft, approval status,
  readiness, and Telegram plan services without calling APIs or recomputing the
  digest. Default output omits rendered digest text and chunk text; optional
  rendered text output uses only the stored sanitized draft text.
- FOS-066 does not create or mutate delivery drafts, decisions, readiness,
  intentions, Telegram plans, audit logs, scheduler jobs, delivery result
  events, outbox records, source-of-truth data, or new tables. It does not add
  approval-triggered execution, Telegram/Slack sending, bot credential
  handling, delivery adapter execution, migrations, live API calls,
  providers/OpenAI, connector calls, source event projection, triage/retriage,
  or feedback behavior changes.
- FOS-067 adds a protected read-only Telegram execution preflight for delivery
  intentions. The preflight reuses the stored intention and Telegram plan
  checks, reports credential presence booleans for Telegram bot token and chat
  ID, and returns safe blockers including the explicit
  `delivery_execution_not_implemented` no-send blocker.
- FOS-067 does not return, print, store, or validate Telegram credential
  values, call Telegram/Slack APIs, invoke delivery adapters, create audit
  rows, create scheduler jobs, delivery result events, outbox records,
  migrations, or new tables, and does not send Telegram/Slack messages.
- FOS-068 adds a delivery result audit contract for future bounded Telegram send
  outcomes. The contract stores sanitized `digest.delivery_result.recorded`
  events in existing `audit_logs`, keyed by deterministic `dres_` delivery
  result IDs, and adds protected read-only retrieval for stored result metadata.
- FOS-068 does not implement Telegram sending, use bot credentials, validate
  credentials against Telegram, expose result creation APIs, call delivery
  adapters, create scheduler jobs, delivery workers, outbox records/tables,
  migrations, or new tables. Delivery results remain audit metadata only and are
  not source-of-truth company facts.
- FOS-069 adds a protected read-only bounded Telegram execution gate preview for
  delivery intentions. The gate combines stored approval/readiness, Telegram
  plan, credential-presence preflight, result-contract readiness, chunk bounds,
  and future operator confirmation requirements.
- FOS-069 does not implement Telegram sending, use or expose bot credentials,
  validate credentials against Telegram, create delivery result records, expose
  POST/PUT/PATCH execution APIs, call delivery adapters, create scheduler jobs,
  delivery workers, outbox records/tables, migrations, or new tables.
- FOS-070 adds a local test-only bounded Telegram send command for delivery
  intentions. The command is the first real send path, but it is not production
  delivery: it requires explicit operator IDs, `test_mode=true`, a low
  `max_chunks` bound, and the exact confirmation phrase before it can use the
  configured Telegram test chat.
- FOS-070 records sanitized `digest.delivery_result.recorded` metadata after an
  attempt and does not print or store bot token, chat ID, rendered digest text,
  chunk text, raw Telegram responses, hidden low-priority details, or newly
  exposed evidence refs. It adds no API send endpoint, scheduler, delivery
  worker, outbox table, production mode, automatic retry, approval-triggered
  execution, schema change, migration, or new table.
- FOS-071 adds `scripts/seed_local_persisted_attention_digest.py`, a
  local/dev-only synthetic persisted attention digest seed command. It creates
  one clearly labeled synthetic local sample through stored
  `ingested_events`, `source_events`, `normalized_activity_items`, and
  `attention_triage_results` rows so a matching persisted attention digest
  window can become non-empty for local delivery testing.
- FOS-071 requires an explicit `sample_id`, timezone-aware `created_at`, and
  exact confirmation phrase `SEED LOCAL SYNTHETIC DIGEST`; refuses
  production-like environments; uses deterministic IDs for idempotency; and
  fails closed on conflicting existing rows. The seed is not live ingestion, is
  not source-of-truth company data, does not call providers/OpenAI/connectors,
  does not send Telegram/Slack messages, does not create delivery
  drafts/approvals/intentions/results, and does not edit raw storage or
  Obsidian.
- FOS-072 adds duplicate-success protection to the local test-only Telegram
  send command. If a stored `delivery_intention_id` already has a successful
  sent `digest.delivery_result.recorded` audit event, a new
  `execution_attempt_id` is refused before the Telegram sender is invoked and no
  new delivery result audit row is created. The same `execution_attempt_id`
  remains idempotent. Failed, partial, skipped, malformed, or incomplete prior
  results do not silently count as successful duplicates.
- FOS-072 adds no override flag, API send endpoint, production mode, scheduler,
  delivery worker, outbox table, automatic retry, approval-triggered execution,
  schema change, migration, or new table. Scheduler/automatic delivery remains
  deferred until repeated manual bounded sends are safe.
- FOS-073 adds a local read-only delivery intention send status report command
  that summarizes safe delivery result metadata by `delivery_intention_id` and
  shows whether duplicate-success protection would block a new execution
  attempt. The report does not send Telegram/Slack messages, read bot
  credentials, create delivery results or audit events, call APIs, or expose
  rendered text, chunk text, credential values, raw Telegram responses, raw
  provider payloads, hidden low-priority details, or newly exposed evidence refs.
- FOS-073 does not change same-attempt idempotency in the send command and does
  not treat failed, partial, skipped, malformed, or incomplete prior results as
  successful duplicates. It adds no override flag, API send endpoint,
  production mode, scheduler, delivery worker, outbox table, automatic retry,
  schema change, migration, or new table.
- FOS-074 adds a local manual pilot delivery draft preparation command for an
  explicit persisted attention digest window. The command refuses
  production-like environments, requires the exact confirmation phrase
  `PREPARE MANUAL PILOT DRAFT`, checks that the persisted digest has visible
  rows, and persists only one inert audit-log-backed delivery draft through the
  existing draft persistence path.
- FOS-074 is not approval, not delivery intention creation, not Telegram/Slack
  sending, and not scheduler/automation. Human approval remains a separate
  explicit step. The command prints safe next-step command shapes for approval,
  readiness, intention creation, review, send-status, execution-gate, and the
  bounded test send, while keeping hidden low-priority items count-only and
  avoiding rendered text, chunk text, credentials, raw payloads, and newly
  exposed evidence refs. It adds no API send endpoint, production mode,
  scheduler, worker, outbox table, automatic retry, migration, or new table.
- FOS-075 adds already-sent/stale draft visibility to the same manual pilot
  preparation command. When the command returns an existing or newly created
  delivery draft, it reads associated delivery intention and delivery result
  audit rows and warns with `delivery_draft_already_successfully_sent` if any
  associated result is clearly successful and sent.
- FOS-075 is read-only status aside from the existing inert draft creation path:
  it does not approve, create delivery intentions, create delivery results, or
  send. Operators should use a fresh digest window or synthetic sample before
  another manual pilot when this warning appears. The send command's
  duplicate-success guard remains the final protection, and scheduler/automatic
  delivery remains deferred.
- FOS-076 adds a local/dev-only fresh manual pilot seed-and-draft command. It
  combines synthetic persisted attention seeding with inert delivery draft
  preparation for repeated manual pilots, while preserving the same explicit
  seed and prepare confirmation phrases and production-like environment
  refusal.
- FOS-076 is not approval, not delivery intention creation, not Telegram/Slack
  sending, and not scheduler/automation. Human approval remains a separate
  explicit step. The command prints safe next-step command shapes, warns if the
  resulting draft is already associated with a successful send, keeps synthetic
  data out of company truth, keeps hidden low-priority items count-only, and
  adds no API send endpoint, production mode, scheduler, worker, outbox table,
  automatic retry, migration, or new table.
- FOS-077 adds a local approved-draft manual pilot handoff command. Starting
  from an explicit already-human-approved `delivery_draft_id`, it verifies
  approval and readiness, refuses already-sent/stale drafts, creates or returns
  the deterministic `delivery_intention_id`, and prints safe review,
  send-status, Telegram plan, execution-gate, and bounded send command
  summaries.
- FOS-077 is not approval, not Telegram/Slack sending, not delivery result
  creation, and not scheduler/automation. It writes only the existing sanitized
  `digest.delivery_intention.created` audit event when needed, remains
  idempotent for the same ready draft, exposes no rendered text, chunk text,
  credentials, raw Telegram/provider payloads, hidden low-priority details, or
  newly exposed evidence refs, and adds no API send endpoint, production mode,
  worker, outbox table, automatic retry, migration, or new table.
- FOS-078 adds `scripts/report_manual_pilot_status.py`, a local read-only
  manual pilot status report for an explicit persisted attention digest window
  and optional synthetic `sample_id`. The report summarizes safe digest counts,
  matching delivery draft state, approval state, delivery intention state,
  delivery result counts, duplicate guard state, stale/already-sent status, and
  a recommended next action.
- FOS-078 creates no seeds, drafts, approvals, intentions, Telegram plans,
  preflight/gate records, delivery results, scheduler jobs, worker/outbox
  records, migrations, or tables. It does not read bot credentials, call
  Telegram/Slack or live APIs, expose rendered text, chunk text, raw payloads,
  secrets, hidden low-priority details, or newly exposed evidence refs. Human
  approval remains separate, duplicate-success protection at send time remains
  the final guard, and scheduler/automatic delivery remains deferred.
- FOS-079 adds `scripts/list_persisted_attention_digest_windows.py`, a local
  read-only operator discovery command for explicit persisted attention time
  ranges. It splits the range into bounded candidate windows, reports safe
  digest counts, lifecycle metadata, duplicate/stale status, and recommended
  next actions, and labels synthetic/local/dev windows only when the existing
  safe local seed marker is detectable.
- FOS-079 does not create seeds, drafts, approvals, intentions, Telegram plans,
  preflight/gate records, delivery results, scheduler jobs, worker/outbox
  records, migrations, or tables. It does not read Telegram credentials, call
  Telegram/Slack or live APIs, or expose rendered text, stored digest text,
  chunk text, item details, raw payloads, secrets, hidden low-priority details,
  or newly exposed evidence refs. Absence of a synthetic marker is not treated
  as production truth, and scheduler/automatic delivery remains deferred.
- FOS-080 adds `scripts/report_real_stored_local_data_readiness.py`, a local
  read-only readiness command for moving from synthetic manual pilots toward
  real stored local data review. It scans `source_events`,
  `normalized_activity_items`, and `attention_triage_results` over an explicit
  bounded time range, reports count-only pipeline readiness metadata, labels
  synthetic/local/dev markers when safely detectable, and labels no-marker data
  conservatively without treating it as production truth.
- FOS-080 does not create source events, normalized activity rows, attention
  results, seeds, drafts, approvals, delivery intentions, Telegram plans,
  preflight/gate records, delivery results, scheduler jobs, worker/outbox
  records, migrations, or tables. It does not call live APIs, providers/OpenAI,
  connectors, Telegram/Slack, or delivery code, and it does not expose raw
  source bodies, provider payloads, item details, evidence refs, rendered text,
  chunk text, secrets, credentials, or hidden low-priority details.
- FOS-081 adds `scripts/preview_stored_source_event_normalization.py`, a local
  read-only source event normalization preview command. It scans stored
  `source_events` for an explicit window and reports count-only eligibility for
  future provider-free projection into `normalized_activity_items`, including
  already-normalized, eligible, unsupported, invalid/unpreviewable, synthetic
  skipped, and safe projected source/activity-type counts.
- FOS-081 does not create source events, normalized activity rows, attention
  results, seeds, drafts, approvals, delivery intentions, Telegram plans,
  preflight/gate records, delivery results, scheduler jobs, worker/outbox
  records, migrations, or tables. It does not call live APIs, providers/OpenAI,
  connectors, Telegram/Slack, or delivery code, and it does not expose raw
  source bodies, provider payloads, item titles, summaries, actions, source
  object identifiers, evidence refs, secrets, credentials, rendered text, chunk
  text, or hidden low-priority details. No-marker rows are not production
  truth, and a future projection write command must be separate and explicit.
- FOS-082 adds `scripts/normalize_stored_source_events.py`, a local/dev-only
  stored source event normalization command. It requires an explicit
  timezone-aware window, bounded `--max-events`, and the exact
  `NORMALIZE STORED SOURCE EVENTS` confirmation phrase before projecting
  supported stored `source_events` into `normalized_activity_items` through the
  existing provider-free projection service.
- FOS-082 writes only normalized activity rows, remains idempotent by
  `source_event_id`, skips already-normalized rows, counts unsupported or
  invalid rows safely, excludes synthetic/local/dev rows by default, and
  refuses production-like environments. It does not create source events,
  attention results, seeds, drafts, approvals, delivery intentions, Telegram
  plans, preflight/gate records, delivery results, scheduler jobs,
  worker/outbox records, migrations, or tables. It does not call live APIs,
  providers/OpenAI, connectors, Telegram/Slack, or delivery code, and it does
  not expose raw source bodies, provider payloads, item titles, summaries,
  actions, source object identifiers, evidence refs, secrets, credentials,
  rendered text, chunk text, or hidden low-priority details. No-marker rows are
  not production truth, and attention triage remains a separate explicit step.
- FOS-047 adds provider-free activity normalization for GitHub pull requests,
  Jira issues, and Drive documents. This slice is mapping-only: it does not
  call GitHub, Jira, Drive, OpenAI, or other live providers, and it does not
  wire those sources into digest generation.
- A future slice may apply semantic attention triage to uncertain email cases behind explicit config.

## Invariants

- Attention items must remain evidence-backed.
- Scoring should be explainable through stored reasons.
- Dashboard reads scored data; it should not silently create new facts.
- LLM-backed activity triage must validate strict JSON before any future persistence or digest use.
- Feedback storage must not write raw message bodies, provider payloads, or
  generated triage results.
- Normalized activity persistence must only write validated cross-source
  activity metadata and evidence refs.
- Attention result persistence must only write validated result metadata and
  evidence refs.

## Known Gaps

- No scheduled digest is visible.
- No Telegram delivery is implemented.
- Score refresh is explicit, not automatic.
- Feedback API, CLI, and UI controls are not implemented.
- Feedback API/buttons/action execution are not implemented.
- Stored feedback is not wired into deterministic digest behavior.
- Live email/provider triage results are not auto-persisted.
- Source events are not automatically batch-projected into persisted normalized
  activity items.
- Persisted normalized activity items are not batch-triaged.
- Persisted attention results have an internal digest read model, deterministic
  text renderer, protected preview endpoints, and synthetic manual pilot
  preview artifact, plus a read-only stored-data operator preview script and an
  inert delivery draft preview with audit-log-backed review records, but the
  existing source activity digest, scheduler, and delivery paths do not yet use
  it as their primary output.
- Persisted delivery drafts have approval/rejection decisions, a read-only
  delivery readiness preview, audit-log-backed delivery intention records, a
  pure Telegram delivery plan preview, and a local read-only operator review
  command plus read-only Telegram execution preflight for the stored chain.
  They now also have a delivery result audit contract for future outcomes and a
  read-only bounded execution gate preview. A local test-only bounded operator
  command can perform the first audited Telegram send path, but there is still
  no approval-triggered execution, scheduler, production mode, delivery worker,
  outbox table, credential validation against Telegram, API send endpoint, or
  automatic delivery wiring. Local/dev-only synthetic seed data can now be used
  to make an empty local persisted attention digest window visible for testing,
  but those rows are explicitly synthetic and not company truth.
- The test-only send path now refuses duplicate successful sends for the same
  delivery intention unless the operator is replaying the same
  `execution_attempt_id`; there is still no override, scheduler, or automatic
  delivery wiring.
- The manual pilot chain now has local commands for fresh synthetic seed plus
  draft preparation, stale draft warning, approved-draft handoff to delivery
  intention, send status reporting, and bounded test-only sending, but human
  approval remains separate and there is still no approval-triggered execution.
- Real stored local data pilot readiness can now be checked with count-only
  local reports over existing `source_events`, `normalized_activity_items`, and
  `attention_triage_results`, but batch projection, batch persisted attention
  triage, and real-data manual send rollout remain separate human-gated steps.
- Stored source event normalization can now be previewed count-only and then
  run through a separate explicit local/dev-only projection write command. The
  write command creates only `normalized_activity_items`; persisted attention
  triage and real-data manual send rollout remain separate human-gated steps.
- GitHub/Jira/Drive digest integration is not implemented.
