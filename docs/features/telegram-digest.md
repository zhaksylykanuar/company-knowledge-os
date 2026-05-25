# Feature Contract: Telegram Digest

## Status

- Telegram bot/interface: planned
- Daily digest generation: planned
- Telegram delivery: planned
- Telegram Q&A: planned
- Internal deterministic source activity digest builder: implemented
- Protected source activity digest API: implemented
- Protected rendered source activity digest text API: implemented
- Protected persisted attention digest preview API: implemented
- Internal persisted attention digest text renderer: implemented
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
- Telegram outbound delivery adapter for already-rendered text: implemented
- Current implemented MVP: manual ingestion and processing through
  `POST /v1/knowledge/ingest-text-process` with evidence-backed
  `extracted_items_preview`

This document is a product and architecture contract for a future feature. It
does not describe an implemented Telegram bot, scheduled digest, Jira connector,
GitHub connector, Calendar connector, or full production sync.

## Product Intent

Telegram is intended to become the founder-facing interface for FounderOS. The
daily digest is intended to be a delivery mechanism that summarizes what changed,
what needs attention, and what needs human review.

Later, the founder should be able to ask questions in Telegram. Telegram should
only be an interface for submitting questions, receiving digests, and optionally
submitting founder notes for ingestion. Telegram is not the source of truth.

## Source Of Truth

- Raw storage and Postgres are authoritative.
- Obsidian is export-only.
- Telegram messages can become source events only when intentionally ingested.
- ChatGPT or the OpenAI API may help extract, summarize, or answer, but must not
  be treated as the database or source of truth.
- Generated digest prose is derived output, not authoritative source data.

## Planned Source Inputs

The future digest should be able to draw from evidence-backed data derived from:

- Gmail messages.
- Google Drive documents.
- Jira issues and activity.
- GitHub repository activity, including the `qaztwin` repository as a
  project-specific source example.
- Meeting transcripts.
- Calendar events.
- Manual Telegram founder notes, after explicit ingestion.

Each source must preserve raw input before downstream processing. Connector data
must be normalized into stored source events, source documents, and chunks before
it can be trusted by extraction, retrieval, Q&A, or digest workflows.
Future real source connectivity must follow the credentials, source identity,
activation, and allowlist contract in `source-integrations.md`.

## Planned Daily Digest Flow

The intended digest flow is:

1. Select an explicit timezone and date window.
2. Collect source events and source documents for that window.
3. Store raw inputs before processing.
4. Normalize inputs into `SourceEvent` records where applicable.
5. Create `SourceDocument` and `DocumentChunk` records where source content is
   document-like.
6. Run extraction on stored source content.
7. Validate strict JSON for any LLM pipeline outputs before persistence.
8. Persist only tasks, risks, and decisions that have `evidence_refs`.
9. Score or rank evidence-backed items with existing deterministic scoring.
10. Generate digest sections from validated evidence-backed data.
11. Mark uncertain or incomplete items as candidates needing human review.
12. Send the digest to Telegram.

Digest generation must not create new facts. If evidence is missing, the digest
should omit the item or mark it as insufficient evidence.

## Planned Telegram Q&A Flow

The intended Telegram Q&A flow is:

1. A Telegram question arrives at the backend.
2. The backend authenticates and validates the request.
3. The backend searches and retrieves relevant evidence from stored sources.
4. Any LLM receives only the relevant retrieved context needed to answer.
5. The answer includes evidence references.
6. If evidence is insufficient, the answer says so instead of guessing.
7. The answer is sent back to Telegram.

Telegram Q&A must not mutate production data directly. Any future write/action
path must require auth, feature flags, and explicit approval before execution.

## Daily Digest Content Contract

A future digest should use these sections when relevant evidence exists:

- Summary.
- Decisions.
- Tasks and follow-ups.
- Risks and blockers.
- Commitments and promises.
- Engineering signals from Jira and GitHub.
- Meetings and transcripts.
- Items needing human review.

Each section should distinguish confirmed evidence-backed knowledge from
candidates that need review. Items without evidence should not be presented as
trusted facts.

## Safety And Privacy Requirements

- Do not put secrets in Telegram messages, logs, docs, examples, or commits.
- Do not commit bot tokens, chat IDs, API keys, webhook secrets, or private keys.
- Use placeholders such as `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and
  `YOUR_API_KEY` in examples.
- Telegram bot tokens and chat IDs must stay backend-only.
- Telegram bot tokens and chat IDs must stay out of the repo, and `.env` must
  not be committed.
- LLMs must not directly mutate production data.
- LLM outputs used in pipelines must be strict JSON and validated before
  persistence.
- Extracted tasks, risks, and decisions must have `evidence_refs`.
- Do not trust evidence-free extracted items.
- Do not hallucinate facts in digest or Q&A output.
- Digest generation must use an explicit timezone and date window.
- The digest must distinguish confirmed knowledge from candidates needing human
  review.
- Persisted delivery drafts are human-review artifacts only. They are not a
  source of truth for company facts, not approvals, and not delivery execution.
- Approval/rejection decisions for persisted delivery drafts are human decision
  records only. Approval does not send Telegram/Slack messages, execute
  delivery, mutate source-of-truth data, or make the draft authoritative.
- Delivery readiness for persisted delivery drafts is a read-only preview of
  whether an approved draft is eligible for a future separately gated delivery
  path. It does not create outbox records, send Telegram/Slack messages,
  execute delivery, mutate source-of-truth data, or mutate draft/decision
  records.
- Delivery intentions for persisted delivery drafts are durable handoff
  artifacts for a future separately gated delivery execution path. They are
  not delivery execution, not outbox workers, not scheduler jobs, and not
  source-of-truth company facts. They do not send Telegram/Slack messages,
  invoke delivery adapters, or mutate draft/decision/source-of-truth records.
- Telegram delivery plans for persisted delivery intentions are dry-run
  pre-send review artifacts only. They expose deterministic Telegram chunk
  metadata, not rendered digest text or chunk text, and they do not require bot
  credentials, send Telegram/Slack messages, invoke delivery adapters, create
  scheduler jobs, delivery result events, outbox records, or new tables.
- Local delivery intention operator review output is a derived review bundle,
  not source-of-truth company data. It reviews the stored chain from delivery
  intention to draft, approval status, readiness, and Telegram plan without
  calling APIs, using bot credentials, mutating records, creating audit logs,
  invoking delivery adapters, scheduling jobs, or sending Telegram/Slack
  messages. Default output omits rendered digest text and chunk text; optional
  rendered text output uses only the stored sanitized draft text.
- Telegram execution preflight for delivery intentions is read-only readiness
  metadata, not delivery execution. It checks stored delivery chain readiness
  and Telegram credential presence only, returns safe booleans and blockers,
  never returns or logs credential values, never validates credentials against
  Telegram, never sends Telegram/Slack messages, and never calls delivery
  adapters.
- Delivery result records for persisted delivery intentions are sanitized audit
  metadata for future bounded Telegram send outcomes, not source-of-truth company
  facts and not delivery execution. Result payloads must not include rendered
  text, chunk text, credentials, raw Telegram responses, raw/provider/source
  payloads, hidden low-priority details, or newly exposed evidence refs.
- Bounded Telegram execution gates for persisted delivery intentions are
  read-only readiness metadata, not delivery execution. They combine stored
  approval/readiness, Telegram plan, credential-presence preflight,
  result-contract readiness, chunk bounds, and future operator-required fields
  while keeping delivery execution disabled and never sending messages.
- Test-only bounded Telegram sends for persisted delivery intentions are local
  operator actions only. The command requires an explicit delivery intention ID,
  execution attempt ID, low `max_chunks` bound, `test_mode=true`, and the exact
  confirmation phrase `SEND TEST TELEGRAM DIGEST`; it sends only after stored
  approval/readiness/intention/plan/preflight/gate checks pass, sends only
  bounded chunks to the configured Telegram test chat, and records sanitized
  delivery result audit metadata after the attempt. It must not print or store
  bot token, chat ID, rendered text, chunk text, raw Telegram responses, hidden
  low-priority details, or newly exposed evidence refs. It is not production
  delivery and adds no API send endpoint, scheduler, delivery worker, outbox
  table, automatic retry, production mode, or approval-triggered execution.
- Local/dev-only synthetic persisted attention digest seed data may be created
  only through the explicit operator seed command when a local database has no
  visible persisted attention digest items. The seed must be clearly synthetic,
  must not be treated as company truth, and must not call providers/OpenAI,
  connectors, Telegram/Slack, scheduler, or delivery code. It does not create
  delivery drafts, approvals, intentions, plans, preflight/gate records, result
  records, or sends, and it does not edit raw storage or Obsidian.
- Test-only bounded Telegram sends must not duplicate a successful delivery
  intention. If an existing sanitized delivery result for the same
  `delivery_intention_id` is clearly `succeeded`, `sent=true`, and delivered at
  least one chunk, the local send command refuses a new `execution_attempt_id`
  before sending. Reusing the same `execution_attempt_id` remains idempotent.
  Failed, partial, skipped, malformed, or incomplete prior results do not
  silently count as successful duplicates. This slice has no override flag.
- Hidden low-priority digest items must remain count-only in preview, persisted
  draft, and delivery-oriented surfaces. Evidence refs remain debug-only and
  safe-formatted.
- Real stored local data readiness discovery is read-only operational metadata
  only. It may scan stored `source_events`, `normalized_activity_items`, and
  `attention_triage_results` for explicit bounded windows, but it must expose
  only safe counts and pipeline readiness booleans. It must not create source
  events, normalized items, attention results, delivery artifacts, approvals,
  intentions, results, or sends; call live APIs/providers/OpenAI/connectors,
  Telegram, or Slack; read Telegram credentials; or expose raw source bodies,
  provider payloads, item details, evidence refs, rendered text, chunk text,
  secrets, credentials, or hidden low-priority details. No-marker data is not
  production truth.
- Stored source event normalization preview is read-only operational metadata
  only. It may scan stored `source_events` for an explicit bounded window and
  report count-only eligibility for future provider-free projection into
  `normalized_activity_items`, but it must not create normalized activity rows,
  create attention results, call live APIs/providers/OpenAI/connectors,
  Telegram, or Slack, read Telegram credentials, or expose raw source bodies,
  provider payloads, item titles, summaries, actions, source object
  identifiers, evidence refs, rendered text, chunk text, secrets, credentials,
  or hidden low-priority details. A future projection write path must be a
  separate explicit local/dev operator action.
- Stored source event normalization is a local/dev-only explicit operator
  action. It may project supported stored `source_events` into
  `normalized_activity_items` through the existing provider-free service only
  after an explicit time window, bounded max event count, and exact
  confirmation phrase. It refuses production-like environments, remains
  idempotent by `source_event_id`, and writes only normalized activity rows.
  It must not create source events, attention results, delivery artifacts,
  approvals, intentions, results, scheduler jobs, outbox records, migrations,
  or tables; call live APIs/providers/OpenAI/connectors, Telegram, or Slack;
  read Telegram credentials; or expose raw source bodies, provider payloads,
  item details, source object identifiers, evidence refs, rendered text, chunk
  text, secrets, credentials, or hidden low-priority details. No-marker data is
  not production truth, and downstream human approval remains separate.

## Current Status

Implemented today:

- Manual text ingestion and processing through
  `POST /v1/knowledge/ingest-text-process`.
- Evidence-backed `extracted_items_preview` for persisted tasks, risks, and
  decisions.
- Deterministic search, ask, scoring, attention dashboard, and Obsidian export
  surfaces for stored knowledge.
- FOS-013 adds an internal deterministic source activity digest builder for an
  explicit timezone-aware time window. It summarizes stored `SourceEvent` rows
  only, includes source/event counts and traceable source activity entries, and
  does not infer decisions, tasks, or risks.
- FOS-014 exposes that deterministic source activity digest through the
  protected `GET /v1/digest/source-activity` API endpoint for explicit
  timezone-aware windows.
- FOS-015 documents a safe manual quickstart check for that endpoint in
  `docs/mvp-quickstart.md`.
- FOS-016 adds a deterministic non-LLM text renderer for existing source
  activity digest output.
- FOS-017 exposes rendered deterministic source activity digest text through the
  protected `GET /v1/digest/source-activity/text` API endpoint.
- FOS-038 wires deterministic `EmailThreadState` rows into the source activity
  digest so active Gmail conversations are grouped by reply state with days
  without reply and evidence refs. When thread states exist for the digest
  window, raw Gmail message events remain represented by aggregate counts rather
  than duplicated as the primary email section.
- FOS-039 makes the source activity digest operator-readable: the rendered text
  includes generated time, explicit window, grouped email reply states,
  deterministic short summaries, short normal-mode evidence counts, debug-only
  raw refs, duplicate source-event collapse, and mock/example data-quality
  notes.
- FOS-055 adds an internal provider-free persisted attention digest read model
  for explicit time windows. It groups existing `attention_triage_results` rows
  into attention-priority daily digest sections, keeps hidden/no-action
  low-priority rows count-only, and may enrich visible rows from linked
  `normalized_activity_items`. It does not replace the existing source activity
  digest, rendered text endpoint, scheduler, delivery, or Telegram behavior.
- FOS-056 adds deterministic text rendering for that persisted attention digest
  read model. The renderer is provider-free, shows only safe item fields, keeps
  hidden low-priority items count-only, and exposes evidence refs only in debug
  mode through the safe evidence formatter.
- FOS-056 does not add Telegram or Slack sending, scheduler behavior, API/CLI
  entrypoints, human approval UI, live providers, or production connector
  calls. Telegram and Slack remain delivery/interface surfaces only, not the
  source of truth.
- FOS-057 adds protected provider-free preview endpoints for persisted
  attention digest JSON and rendered text. The endpoints read existing
  persisted attention digest data, do not call providers or run triage, keep
  hidden low-priority items count-only, and expose evidence refs only via safe
  debug output.
- FOS-057 does not add Telegram or Slack sending, scheduler behavior, delivery
  wiring, migrations, live providers, or production connector calls. Telegram
  and Slack remain delivery/interface surfaces only, not the source of truth.
- FOS-058 adds a synthetic manual pilot preview artifact for persisted
  attention digest text. The artifact uses the real deterministic persisted
  attention digest renderer, is provider-free and synthetic-only, keeps hidden
  low-priority items count-only, and treats evidence refs as safe debug-style
  context rather than source-of-truth data.
- FOS-058 does not read stored data, call APIs, run triage, call providers or
  OpenAI, add scheduler behavior, add delivery wiring, add Telegram or Slack
  sending, change API endpoints, add migrations, or call live connectors.
  Telegram and Slack remain delivery/interface surfaces only, not the source of
  truth.
- FOS-059 adds a local read-only operator preview script for persisted
  attention digest text. The script reads stored persisted attention digest data
  for an explicit timezone-aware window, uses the real deterministic renderer,
  is provider-free, does not run triage, keeps hidden low-priority items
  count-only, and exposes evidence refs only through safe debug formatting.
- FOS-059 does not call APIs, providers/OpenAI, connectors, Telegram or Slack,
  scheduler, or delivery code. It does not add approval execution, scheduler
  behavior, delivery wiring, API changes, migrations, live API calls, or
  production data mutation. Telegram and Slack remain delivery/interface
  surfaces only, not the source of truth.
- FOS-060 adds a protected read-only persisted attention digest delivery draft
  preview. The draft is a human-review artifact derived from the existing
  persisted attention digest read model and already-rendered deterministic text;
  it is not an approval, is not persisted, is not sent, and is delivery-disabled.
- FOS-060 is provider-free, does not run triage, does not call APIs,
  providers/OpenAI, connectors, Telegram or Slack, scheduler, or delivery code,
  and does not add approval execution, approval state persistence, delivery
  wiring, migrations, live API calls, or production data mutation. Hidden
  low-priority items remain count-only, and evidence refs remain safe-formatted
  debug-only. Telegram and Slack remain delivery/interface surfaces only, not
  the source of truth.
- FOS-061 persists inert persisted attention digest delivery drafts as
  audit-log-backed review records. The creation endpoint stores one sanitized
  `digest.delivery_draft.created` audit event keyed by a deterministic
  `delivery_draft_id`, and the retrieval endpoint returns that stored draft for
  later human review.
- FOS-061 persisted drafts are not approvals, are not source-of-truth facts, and
  are not sent to Telegram or Slack. They store only sanitized rendered digest
  text, chunk metadata, safe source-of-truth metadata, and safe debug evidence
  refs when explicitly requested. This slice does not add approval execution,
  scheduler behavior, Telegram/Slack sending, delivery wiring, migrations, live
  API calls, providers/OpenAI, or connector calls.
- FOS-062 records approval/rejection decisions for persisted attention digest
  delivery drafts as audit-log-backed events and exposes a protected approval
  status API. Approval/rejection decisions are human decision records only; they
  do not send Telegram/Slack messages, execute delivery, mutate source-of-truth
  data, or make delivery drafts authoritative company facts.
- FOS-062 decision/status payloads expose only sanitized decision metadata,
  draft hash metadata, and inert safety flags. Hidden low-priority items remain
  count-only, and evidence refs remain safe-formatted debug-only. This slice
  does not add scheduler behavior, Telegram/Slack sending, delivery wiring,
  migrations, live API calls, providers/OpenAI, connector calls, or new tables.
- FOS-063 adds a protected read-only delivery readiness preview for persisted
  delivery drafts. Readiness reports whether a draft is approved and eligible
  for a future separately gated delivery path, while keeping delivery execution
  disabled. It does not create delivery outbox/intention records, send
  Telegram/Slack messages, execute approval or delivery, mutate source-of-truth
  data, mutate draft/decision records, run scheduler behavior, call live APIs,
  call providers/OpenAI, or add migrations/new tables.
- FOS-063 readiness payloads expose only sanitized draft hash/window/chunk
  metadata, source-of-truth metadata, decision history, and inert safety flags.
  Hidden low-priority items remain count-only, and evidence refs remain
  safe-formatted debug-only.
- FOS-064 adds audit-log-backed delivery intention records for approved and
  ready persisted delivery drafts. A delivery intention is a durable handoff
  artifact for a future separately gated delivery execution path, not delivery
  execution. It does not create a delivery outbox table, outbox worker, or
  scheduler job, does not send Telegram/Slack messages, does not invoke
  delivery adapters, does not mutate source-of-truth data, and does not mutate
  draft or decision records.
- FOS-064 intention payloads expose only sanitized draft/readiness hash,
  window, chunk, source-of-truth, and inert safety metadata. They do not include
  rendered digest text, full digest snapshots, raw/provider/prompt/source
  payloads, hidden low-priority item details, or newly exposed evidence refs.
  This slice does not add scheduler behavior, Telegram/Slack sending, delivery
  adapter execution, delivery workers, migrations, live API calls,
  providers/OpenAI, connector calls, an outbox table, or new tables.
- FOS-065 adds a pure Telegram delivery plan preview for delivery intentions.
  The plan uses stored draft rendered text internally only to compute
  deterministic Telegram chunk lengths and hashes for future review. It does
  not include rendered text or chunk text, require bot credentials, send
  Telegram/Slack messages, call delivery adapters, create scheduler jobs,
  delivery result events, outbox records, migrations, live API calls,
  providers/OpenAI, connector calls, or new tables.
- FOS-066 adds a local read-only operator review command for delivery
  intentions. The command reviews the existing delivery intention, referenced
  draft, approval status, readiness, and Telegram plan by
  `delivery_intention_id`. It does not call API endpoints or API clients,
  create or mutate delivery drafts, decisions, readiness, intentions, plans,
  audit logs, scheduler jobs, delivery result events, outbox records, or
  source-of-truth data, and it does not use bot credentials or send
  Telegram/Slack messages.
- FOS-067 adds a protected read-only Telegram execution preflight for delivery
  intentions. The preflight confirms the stored intention and Telegram plan are
  safe, checks only whether Telegram bot token and chat ID configuration are
  present, and returns explicit no-send blockers while delivery execution is
  not implemented.
- FOS-067 does not return, print, store, log, or validate Telegram credential
  values, send Telegram/Slack messages, call delivery adapters, create
  scheduler jobs, delivery result events, outbox records, migrations, live API
  calls, providers/OpenAI, connector calls, or new tables.
- FOS-068 adds a delivery result audit contract for future bounded Telegram send
  outcomes. It can store sanitized `digest.delivery_result.recorded` audit
  events in existing `audit_logs`, keyed by deterministic `dres_` result IDs,
  and exposes protected read-only retrieval for stored delivery result metadata.
- FOS-068 does not implement Telegram sending, use bot credentials, validate
  credentials against Telegram, expose POST/PUT/PATCH result APIs, call delivery
  adapters, create scheduler jobs, delivery workers, outbox records/tables,
  migrations, live API calls, providers/OpenAI, connector calls, or new tables.
- FOS-069 adds a protected read-only bounded Telegram execution gate preview for
  delivery intentions. It reports safe readiness booleans, blockers, required
  future operator fields, chunk bounds, and result-contract readiness without
  sending or creating result records.
- FOS-069 does not implement Telegram sending, use or expose bot credentials,
  validate credentials against Telegram, expose POST/PUT/PATCH execution APIs,
  call delivery adapters, create scheduler jobs, delivery workers, outbox
  records/tables, migrations, live API calls, providers/OpenAI, connector calls,
  or new tables.
- FOS-070 adds a local test-only bounded Telegram delivery intention send
  command. It is the first real send path, but it is explicitly operator-run,
  bounded, test-mode-only, and audited through sanitized delivery result
  metadata.
- FOS-070 requires `delivery_intention_id`, `execution_attempt_id`,
  `max_chunks`, `test_mode=true`, and the exact confirmation phrase before any
  send attempt. It uses configured backend Telegram credentials internally,
  never accepts credentials as CLI arguments, never prints or stores credential
  values, never exposes rendered text/chunk text/raw Telegram responses, and
  adds no API send endpoint, scheduler, delivery worker, outbox table,
  production mode, automatic retry, approval-triggered execution, migration, or
  new table.
- FOS-071 adds a local/dev-only synthetic persisted attention digest seed
  command for empty local databases. It writes one clearly labeled synthetic
  sample through the persisted attention source chain so
  `GET /v1/digest/persisted-attention` can return at least one visible item for
  the selected local test window.
- FOS-071 requires explicit `sample_id`, timezone-aware `created_at`, and the
  exact confirmation phrase `SEED LOCAL SYNTHETIC DIGEST`; refuses
  production-like environments; is deterministic/idempotent; and fails closed
  on conflicting existing rows. It is not live ingestion and does not call
  providers/OpenAI/connectors, use bot credentials, send Telegram/Slack
  messages, create delivery artifacts/results, edit raw storage or Obsidian,
  add migrations, or create new tables.
- FOS-072 adds duplicate-success protection to the local test-only bounded
  Telegram send command. A delivery intention with a prior successful sent
  delivery result cannot be sent again with a new `execution_attempt_id`; the
  same `execution_attempt_id` remains an idempotent replay with no Telegram
  transport call and no duplicate audit row.
- FOS-072 does not add an override flag, API send endpoint, production mode,
  scheduler, delivery worker, outbox table, automatic retry,
  approval-triggered execution, migration, or new table. Scheduler/automatic
  delivery remains deferred until repeated manual bounded sends are proven safe.
- FOS-073 adds a local read-only delivery intention send status report command.
  The report summarizes safe delivery result metadata for a
  `delivery_intention_id` and shows whether duplicate-success protection would
  block a new execution attempt. It does not send Telegram/Slack messages, read
  bot credentials, create delivery results or audit events, call APIs, or expose
  rendered text, chunk text, credential values, raw Telegram responses, raw
  provider payloads, hidden low-priority details, or newly exposed evidence refs.
- FOS-073 preserves the FOS-072 semantics: a prior successful/sent result should
  not be resent, same-attempt idempotency remains handled by the send command,
  and failed/partial/skipped prior attempts do not silently count as successful
  duplicates. It adds no API send endpoint, production mode, scheduler, worker,
  outbox table, automatic retry, migration, or new table.
- FOS-074 adds a local manual pilot delivery draft preparation command for an
  explicit persisted attention digest window. The command requires
  timezone-aware `start_at`/`end_at`, bounded `limit`, and the exact
  confirmation phrase `PREPARE MANUAL PILOT DRAFT`; refuses production-like
  environments; fails safely on empty windows; and persists only one inert
  delivery draft audit record through the existing draft persistence path.
- FOS-074 is not approval, not delivery intention creation, not Telegram/Slack
  sending, and not scheduler/automation. It prints safe next-step command
  shapes for the manual pilot flow and keeps human approval separate. It does
  not expose rendered text, chunk text, bot credentials, raw Telegram/provider
  payloads, hidden low-priority item details, or newly exposed evidence refs,
  and it adds no API send endpoint, production mode, scheduler, worker, outbox
  table, automatic retry, migration, or new table.
- FOS-075 adds read-only already-sent/stale draft visibility to the manual
  pilot preparation command. The command now reports associated delivery
  intentions and safe delivery result counts, and warns with
  `delivery_draft_already_successfully_sent` when the returned draft already has
  a successful/sent delivery result through an intention.
- FOS-075 does not approve, create delivery intentions, create delivery results,
  send Telegram/Slack messages, add an override flag, add an API send endpoint,
  add production mode, add scheduler/worker/outbox behavior, add automatic
  retry, add a migration, or create a table. Operators should not reuse an
  already-sent draft or intention for another send; they should prepare a fresh
  digest window or synthetic sample for the next manual pilot.
- FOS-076 adds `scripts/seed_and_prepare_manual_pilot_delivery_draft.py`, a
  local/dev-only command that creates a fresh synthetic persisted attention
  sample and prepares one inert delivery draft in one flow for repeated manual
  pilots. The command requires explicit `sample_id`, timezone-aware
  `created_at`, the exact seed confirmation phrase, and the exact prepare
  confirmation phrase.
- FOS-076 is not approval, not delivery intention creation, not Telegram/Slack
  sending, and not scheduler/automation. It prints safe next-step command
  shapes for approval, readiness, intention creation, review, send status,
  execution gate, and bounded test send. If the prepared draft is already tied
  to a successful send, it surfaces the FOS-075 stale warning and recommends a
  new sample/window. Synthetic data remains local/dev-only and not company
  truth, and the slice adds no API send endpoint, production mode, worker,
  outbox table, automatic retry, migration, or new table.
- FOS-077 adds `scripts/continue_manual_pilot_delivery_draft.py`, a local
  approved-draft handoff command for repeated manual pilots. The command starts
  from an explicit human-approved `delivery_draft_id`, requires the exact
  confirmation phrase `CREATE MANUAL PILOT DELIVERY INTENTION`, verifies
  readiness, refuses already-sent/stale drafts, creates or retrieves the
  deterministic delivery intention, and prints safe review, send-status,
  Telegram plan, execution-gate, and bounded send command summaries.
- FOS-077 is not approval, not Telegram/Slack sending, not delivery result
  creation, and not scheduler/automation. It writes only the existing
  sanitized delivery intention audit event when needed, remains idempotent for
  the same approved and ready draft, exposes no rendered text, chunk text,
  credentials, raw Telegram/provider payloads, hidden low-priority details, or
  newly exposed evidence refs, and adds no API send endpoint, production mode,
  worker, outbox table, automatic retry, migration, or new table.
- FOS-078 adds `scripts/report_manual_pilot_status.py`, a local read-only
  manual pilot status report for an explicit persisted digest window and
  optional synthetic `sample_id`. It summarizes safe digest counts, matching
  draft state, approval state, intention state, delivery result state,
  duplicate guard status, stale/already-sent status, and the recommended next
  manual action.
- FOS-078 does not create seeds, drafts, approvals, delivery intentions,
  Telegram plans, preflight/gate records, delivery results, scheduler jobs,
  workers, outbox records, migrations, or tables. It does not require or read
  Telegram credentials, call Telegram/Slack or live APIs, or expose rendered
  text, chunk text, raw payloads, secrets, hidden low-priority details, or newly
  exposed evidence refs. Human approval remains separate, duplicate-success
  protection remains the send-time guard, and scheduler/automatic delivery
  remains deferred until repeated manual bounded sends and real stored local
  data pilots are proven safe.
- FOS-079 adds `scripts/list_persisted_attention_digest_windows.py`, a local
  read-only persisted attention window discovery command for manual pilots. It
  scans an explicit bounded range, reports safe window-level digest counts,
  draft/approval/intention/result lifecycle state, duplicate/stale status, and
  recommended next action, and labels synthetic/local/dev windows only when a
  safe local seed marker is detected.
- FOS-079 is not seed creation, draft creation, approval, delivery intention
  creation, Telegram/Slack sending, scheduler, or automation. It does not
  require or read Telegram credentials, call Telegram/Slack or live APIs, expose
  rendered text, stored digest text, chunk text, digest item details, raw
  payloads, secrets, hidden low-priority details, or newly exposed evidence
  refs. Absence of a synthetic marker is not production truth, and scheduler
  remains deferred.
- FOS-080 adds `scripts/report_real_stored_local_data_readiness.py`, a local
  read-only real stored local data readiness command. It scans explicit bounded
  windows across `source_events`, `normalized_activity_items`, and
  `attention_triage_results`, returns count-only pipeline coverage and
  readiness metadata, labels synthetic/local/dev markers when safely detected,
  and labels no-marker data conservatively without treating it as production
  truth.
- FOS-080 does not create source events, normalized activity rows, attention
  results, seeds, drafts, approvals, delivery intentions, Telegram plans,
  preflight/gate records, delivery results, scheduler jobs, worker/outbox
  records, migrations, or tables. It does not call live APIs, providers/OpenAI,
  connectors, Telegram/Slack, or delivery code, and it does not expose raw
  source bodies, provider payloads, item details, evidence refs, rendered text,
  chunk text, secrets, credentials, or hidden low-priority details. Human
  approval and duplicate-success protection remain separate gates, and
  scheduler/automatic delivery remains deferred.
- FOS-081 adds `scripts/preview_stored_source_event_normalization.py`, a local
  read-only stored source event normalization preview command. It reports
  count-only source event totals, safe source/type counts, synthetic/no-marker
  counts, already-normalized counts, eligible/unsupported/invalid preview
  counts, and safe projected normalized activity source/activity-type counts for
  a future explicit projection command.
- FOS-081 does not create source events, normalized activity rows, attention
  results, seeds, drafts, approvals, delivery intentions, Telegram plans,
  preflight/gate records, delivery results, scheduler jobs, worker/outbox
  records, migrations, or tables. It does not call live APIs, providers/OpenAI,
  connectors, Telegram/Slack, or delivery code, and it does not expose raw
  source bodies, provider payloads, item titles, summaries, actions, source
  object identifiers, evidence refs, secrets, credentials, rendered text, chunk
  text, or hidden low-priority details. No-marker rows remain unlabeled local
  stored data, not production truth.
- FOS-082 adds `scripts/normalize_stored_source_events.py`, a local/dev-only
  stored source event normalization command. It writes only
  `normalized_activity_items` through the existing provider-free service after
  an explicit timezone-aware window, bounded `--max-events`, and exact
  confirmation phrase; it refuses production-like environments and remains
  idempotent for already-normalized source events.
- FOS-082 does not create source events, attention results, seeds, drafts,
  approvals, delivery intentions, Telegram plans, preflight/gate records,
  delivery results, scheduler jobs, worker/outbox records, migrations, or
  tables. It does not call live APIs, providers/OpenAI, connectors,
  Telegram/Slack, or delivery code, and it does not expose raw source bodies,
  provider payloads, item titles, summaries, actions, source object
  identifiers, evidence refs, secrets, credentials, rendered text, chunk text,
  or hidden low-priority details. The next step after accepted local
  normalization is a read-only normalized activity triage readiness report or
  explicit provider-free triage plan; scheduler and automatic delivery remain
  deferred.
- FOS-018 adds a Telegram outbound delivery adapter for already-rendered plain
  text only. It can build plain `sendMessage` payloads, split long text into
  Telegram-safe chunks, and send chunks through an injected transport.

Not implemented today:

- Telegram bot/interface.
- Telegram bot webhook.
- Telegram polling or `getUpdates`.
- Scheduled daily digest generation.
- End-to-end scheduled Telegram digest delivery.
- Telegram Q&A.
- Jira connector.
- GitHub repository connector.
- Calendar connector.
- Full production Gmail/Drive sync.
- LLM summarization for digests.
- Decision, task, risk, commitment, or recommendation inference in digest
  rendering.
- Telegram delivery, scheduler, connector, or digest inference logic behind the
  source activity endpoint.
- Telegram delivery, scheduler, connector, or digest inference logic behind the
  rendered source activity text endpoint.
- Telegram delivery, scheduler, connector, or digest inference logic behind the
  persisted attention digest preview endpoints.
- Telegram delivery, scheduler, connector, approval execution, or digest
  inference logic behind persisted attention digest delivery draft preview or
  audit-log-backed draft review records.
- Approval-triggered execution for persisted delivery drafts.
- Delivery execution, delivery workers, scheduler jobs, or outbox tables for
  automatic or production delivery of approved persisted delivery drafts.
- Production-mode Telegram send execution for delivery intentions.
- POST/PUT/PATCH execution APIs for delivery intentions.
- Public creation/update APIs for delivery result records.
- Telegram credential validation against Telegram for delivery intentions.
- API-backed or scheduled operator review flows for delivery intentions.
- Scheduler, connector, inbound Q&A, LLM summarization, or digest inference
  logic in the Telegram outbound delivery adapter.
