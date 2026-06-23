# Feature Contract: Telegram Digest

## Status

- Telegram bot/interface: operator-launched long-polling bot implemented for
  allowlisted founder commands; production webhook/scheduler bot behavior is
  planned.
- Persisted attention digest read model and renderer: implemented; scheduled
  daily digest generation is planned.
- Telegram delivery: bounded adapter implemented for already-rendered text and
  test/manual pilot paths; production delivery cadence is planned.
- Telegram Q&A: planned
- Implemented status slices: founder bot command parsing, `/status` digest
  fallback, project alias detection, Jira/GitHub project status rendering, and
  Status Engine snapshot rendering/persistence for project answers.
- The all-project `/status` snapshot list suppresses no-evidence `unknown`
  project rows as noise; direct project questions may still show an honest
  low-confidence unknown snapshot.
- Telegram outbound delivery adapter for already-rendered text: implemented
  (used only by the bounded, test-only send path)
- Default-disabled scheduler/outbox execution guard baseline: implemented
- Legacy manual text MVP still supported: manual ingestion and processing through
  `POST /v1/knowledge/ingest-text-process` with evidence-backed
  `extracted_items_preview`

The persisted-attention digest read model and renderer, the
delivery-draft -> approval -> intention -> result lifecycle, guarded-execution
boundaries, and the no-marker diagnostic family (candidate / quality /
duplicate-root-cause / grouped-preview / grouped-lifecycle) that this Telegram
feature builds on are tracked authoritatively in
[`attention.md`](attention.md#status). That status list is intentionally not
duplicated here to avoid drift between the two documents.

This document is a product and architecture contract for Telegram as a founder
interface. It now has an operator-launched read-only bot slice, but it still
does not describe a production webhook bot, scheduled digest, Calendar
connector, or full production sync.

## Product Intent

Telegram is intended to become the founder-facing interface for FounderOS. The
daily digest is intended to be a delivery mechanism that summarizes what changed,
what needs attention, and what needs human review.

Later, the founder should be able to ask questions in Telegram. Telegram should
only be an interface for submitting questions, receiving digests, and optionally
submitting founder notes for ingestion. Telegram is not the source of truth.

## Founder Digest Format v2 (product contract, from day-1 pilot feedback)

Goal: save the founder's attention, not enumerate events.

Rendering rules:

1. Start with a one-line status: urgent / calm / action required.
2. Show at most 3 main items.
3. Group and hide low-priority events.
4. Never show technical fields: evidence refs, visible/hidden counts as raw
   fields, window timestamps, "Summary unavailable" placeholders.
5. Every important item must include: what happened, why it matters, what to
   do, and the source.
6. If no actions are needed, say it explicitly: "Действий не требуется".
7. If a security code/OTP is involved, never show the code itself — only warn
   that one arrived.
8. Short, clear, in Russian.
9. The whole digest must fit one phone screen.
10. Footer actions: [Открыть главное], [Показать всё], [Скрыть похожее].

Output template (digest body language is Russian by contract):

```text
🧠 Дайджест внимания • {дата/время}

{главный статус одной строкой}

🔥 Срочно
{если нет — "Нет"}

🟡 Стоит посмотреть
{1–3 пункта}

📭 Ждут моего ответа
{список или "Нет"}

📌 Проекты
{важные изменения или "Нет важных обновлений"}

🗂 Скрыто как шум
{количество и краткие категории}

{кнопки}
```

Section mapping to the existing `AttentionTriageResult` contract:

- 🔥 Срочно — `requires_my_attention` / `manual_action` with high priority.
- 🟡 Стоит посмотреть — `important_info` and high-confidence `review_optional`.
- 📭 Ждут моего ответа — `waiting_on_external` and reply-required items.
- 📌 Проекты — project-linked `important_info`.
- 🗂 Скрыто как шум — hidden/low-priority, grouped count by category only.
- [Скрыть похожее] maps to the existing feedback action `always_hide_similar`.

Delivery modes (target, staged):

1. Instant alert — only for genuinely urgent items.
2. Short digest — 2–4 times per day (morning/midday/evening).
3. Full log — available on demand via "Показать всё", never pushed.

Staging notes: the v2 renderer is a pure function over the persisted attention
read model and can ship within the current manual send loop. Meaningful section
placement requires LLM triage (deterministic fallback puts everything in
review_optional by design). Footer buttons and "Показать всё" require an inbound
Telegram bot slice; instant alerts and scheduled cadence require the scheduler
phase and stay behind the existing guards.

## Source Of Truth

- Raw storage and Postgres are authoritative.
- Obsidian is export-only.
- External APIs are raw event or interface boundaries, not interpreted truth.
- Telegram messages can become source events only when intentionally ingested.
- Telegram `/status` may persist derived `status_snapshots` for status history;
  those snapshots are read-model history derived from stored evidence, not new
  source-of-truth facts or action execution.
- ChatGPT or the OpenAI API may help extract, summarize, or answer, but must not
  be treated as the database or source of truth.
- Generated digest prose is derived output, not authoritative source data.

## Source Inputs: Current vs Target

Current supported stored/local paths:

- Persisted `AttentionTriageResult` rows for explicit digest windows.
- Stored `SourceEvent` rows normalized into activity items by guarded/local
  commands.
- Deterministic Gmail `EmailThreadState` rows when already present locally.
- Manual text ingestion remains supported as the legacy MVP path.

Target production source inputs:

- Gmail messages.
- Google Drive documents.
- Jira issues and activity.
- GitHub repository activity, including the `qaztwin` repository as a
  project-specific source example.
- Meeting transcripts.
- Calendar events.
- Manual Telegram founder notes, after explicit ingestion.

Each target source must preserve raw input before downstream processing. Connector data
must be normalized into stored source events, source documents, and chunks before
it can be trusted by extraction, retrieval, Q&A, or digest workflows.
Future real source connectivity must follow the credentials, source identity,
activation, and allowlist contract in `source-integrations.md`.
The current Jira read-only inventory path is access diagnostics and operating
model planning only. It reports safe classes/counts and does not ingest issues,
write Jira, persist raw storage, or expose Jira project or issue details.

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
- Live provider execution is default-denied at the provider adapter boundary.
  Local review, draft, plan, preflight, gate, and grouped lifecycle tooling must
  stay provider-free and no-send unless a separate bounded execution path
  explicitly supplies the live-provider acknowledgement. Telegram and Slack
  remain delivery/interface surfaces only, not source-of-truth stores.
- The same default-denied provider execution guard applies to OpenAI, Gmail, and
  Drive connector/client boundaries. Those external APIs are raw event/provider
  boundaries only; their responses must pass through the existing storage,
  normalization, and validation paths before any derived company knowledge is
  trusted.
- Production-affecting operations are default-denied unless a separate bounded
  operator execution path supplies an explicit production-operation
  acknowledgement. Delivery execution and Obsidian export are guarded operation
  classes; local review, digest, report, preflight, and grouped lifecycle tools
  remain no-send, non-enforcing, and not source-of-truth mutations. Scheduler,
  outbox, automatic delivery, migrations, and production DB operations remain
  out of scope.
- Raw-storage writes, manual knowledge ingestion, and persisted Gmail/Drive
  backfill writes also require the production-operation acknowledgement. Safe
  read-only previews and persist=false backfill checks remain available without
  source-of-truth mutation.
- Scheduler/outbox/background delivery execution is default-disabled and still
  out of scope. The bounded local Telegram send command remains a manual
  operator path only and asserts that it is not running as a scheduler, outbox
  drain, background dispatch, retry worker, or automatic delivery path before
  provider and production-operation gates can be reached. Delivery intentions
  remain durable handoff artifacts, and delivery results remain execution
  outcome metadata only. The concise operator summary lives in
  `../runbooks/guarded-operations.md`.
- Operator-facing delivery summaries, review artifacts, and diagnostics expose
  safe reason codes, classes, and counts only. Raw provider data, rendered
  message text, chunk text, source identifiers, hashes, credentials, and
  connection details remain out of those artifacts.
- The guarded-execution doctor is read-only, no-send, provider-free, and
  source-of-truth-mutation-free. It verifies the guard wiring and sanitizer
  diagnostics with synthetic checks only and does not approve, dispatch, send,
  schedule, or execute production operations.
- Guarded-execution audit-event metadata can summarize provider, production,
  scheduler, and sanitizer guard decisions for future logging or review. It is
  JSON-serializable sanitized metadata only: it is not persisted by this
  baseline, not a delivery result, not an approval, and not execution.
- Guarded-execution audit sinks are non-persistent no-op or in-memory
  collectors for safe summaries only. They do not create delivery results,
  audit rows, queues, outbox records, scheduler work, provider calls, sends, or
  source-of-truth mutations.
- The guarded-execution readiness report is read-only operator-review metadata
  only. It consolidates guard, doctor, sanitizer, audit, sink, docs, and
  remaining-risk status without persisting artifacts, sending, scheduling,
  calling providers, or approving production execution.
- Guarded-execution audit events, audit sink summaries, doctor output, and
  readiness report output use strict sanitized JSON contract validation.
  Validation exposes safe field names, reason codes, classes, and counts only,
  and it does not persist, approve, send, schedule, or mutate source-of-truth
  stores.
- GitHub and Jira connector readiness is a raw-event-source launchpad only.
  Live read-only API verification is a separate gated manual step; connector
  metadata stays sanitized, and provider payloads must pass through raw storage
  and validation boundaries before normalized activity mapping.
- The external connector read-only smoke CLI is no-live by default, synthetic
  when requested, and live-read-only only after explicit manual provider
  acknowledgement. GitHub portfolio comparison is seed-count metadata only;
  target organization inventory remains gated and not verified. Jira mapping
  status remains counts/classes only and does not affect digest rendering or
  delivery.
- The GitHub organization inventory CLI is no-live by default, synthetic when
  requested, and live-read-only only after explicit manual provider
  acknowledgement. It reports target organization migration readiness as
  counts/classes and sanitized failure classes only. It does not ingest GitHub
  events, transfer repositories, edit repository metadata, run scheduler work,
  or affect digest rendering or delivery.
- The Jira read-only inventory CLI is also no-live by default, synthetic when
  requested, and live-read-only only after explicit manual provider
  acknowledgement. It reports Jira inventory and portfolio mapping as
  counts/classes only and does not ingest issues, write raw storage or
  Postgres, mutate Jira, schedule work, or affect digest rendering/delivery.
- The Jira creation dry-run CLI is no-live and no-write. It produces a
  sanitized review artifact for future Jira structure approval, keeps
  issue-search inventory as a follow-up class, and does not affect digest
  rendering, delivery, storage, scheduler execution, or Jira state.
- The external connector configuration doctor checks GitHub/Jira environment
  variable presence by name only. It never prints values and does not call
  providers. The doctor and smoke CLI can load allowlisted connector variables
  from project-root `.env`, fall back to the older user-config connector file,
  or use an explicit env-file override; shell values take precedence, and
  diagnostics expose only status/count classes.
  Configured/partially-configured/not-configured classes only prepare the later
  manually acknowledged live-read-only smoke step.
- The ignored-file cleanup planner is read-only and no-delete. It reports
  ignored local file cleanup candidates as safe classes/counts only and does
  not read ignored contents, execute cleanup, call providers, schedule work, or
  affect delivery.
- Repository portfolio readiness is static onboarding metadata only. It reports
  product-area, lifecycle, priority, safe action-class counts, and target-org
  migration classes for future GitHub/Jira planning. The canonical future
  owner is `qtwin-io`, while the seed catalog remains planning metadata only.
  It does not execute repository transfers, repository edits, archive
  operations, secret rotation, provider calls, sends, scheduler work, or
  source-of-truth mutation.
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
- Normalized activity triage readiness preview is read-only operational
  metadata only. It may scan stored `normalized_activity_items` for an explicit
  bounded window and report count-only already-triaged, untriaged,
  synthetic/no-marker, provider-free eligibility, and conservative fallback
  projected attention class/priority/visibility counts. It must not create
  attention results, call write-oriented triage services, call live
  APIs/providers/OpenAI/connectors, Telegram, or Slack, read Telegram
  credentials, or expose raw source bodies, provider payloads, item titles,
  summaries, actions, source object identifiers, evidence refs, rendered text,
  chunk text, secrets, credentials, or hidden low-priority details. No-marker
  data is not production truth; future triage writes must be separate explicit
  local/dev operator actions.
- Provider-free normalized activity triage is a local/dev-only explicit
  operator action. It may classify stored `normalized_activity_items` into
  `attention_triage_results` through the existing strict schema-validated
  provider-free service only after an explicit time window, bounded max item
  count, and exact confirmation phrase. It refuses production-like
  environments, remains idempotent by `activity_item_id`, and writes only
  attention result rows. It must not create source events, normalized activity
  rows, delivery artifacts, approvals, intentions, results, scheduler jobs,
  outbox records, migrations, or tables; call live APIs/providers/OpenAI/
  connectors, Telegram, or Slack; read Telegram credentials; or expose raw
  source bodies, provider payloads, item details, source object identifiers,
  evidence refs, rendered text, chunk text, secrets, credentials, or hidden
  low-priority details. No-marker data is not production truth, and downstream
  human approval remains separate.

## Historical Implementation Ledger (Archived)

The remaining FOS-* notes are retained for traceability. They are not the
current status source; use the top `Status`, `Product Intent`, delivery
contract, and `Source Of Truth` sections for current truth. New status changes
should go to the changelog or backlog instead of extending this ledger.

Historical implemented slices:

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
- FOS-083 adds `scripts/preview_normalized_activity_triage_readiness.py`, a
  local read-only normalized activity triage readiness preview command. It
  reports count-only normalized activity totals, safe source/activity-type
  counts, synthetic/no-marker counts, already-triaged and untriaged counts,
  provider-free eligibility counts, and conservative fallback projected
  attention class, priority, visible, and hidden counts.
- FOS-083 does not create source events, normalized activity rows, attention
  results, seeds, drafts, approvals, delivery intentions, Telegram plans,
  preflight/gate records, delivery results, scheduler jobs, worker/outbox
  records, migrations, or tables. It does not call live APIs, providers/OpenAI,
  connectors, Telegram/Slack, write-oriented triage services, or delivery code,
  and it does not expose raw source bodies, provider payloads, item titles,
  summaries, actions, source object identifiers, evidence refs, secrets,
  credentials, rendered text, chunk text, or hidden low-priority details. The
  next step after accepted preview may be a separate explicit local/dev
  provider-free triage write command; scheduler and automatic delivery remain
  deferred.
- FOS-084 adds `scripts/triage_normalized_activity_items.py`, a local/dev-only
  provider-free normalized activity triage command. It writes only
  `attention_triage_results` through the existing strict schema-validated
  provider-free service after an explicit timezone-aware window, bounded
  `--max-items`, and exact confirmation phrase; it refuses production-like
  environments and remains idempotent for already-triaged normalized activity
  items.
- FOS-084 does not create source events, normalized activity rows, seeds,
  drafts, approvals, delivery intentions, Telegram plans, preflight/gate
  records, delivery results, scheduler jobs, worker/outbox records, migrations,
  or tables. It does not call live APIs, providers/OpenAI, connectors,
  Telegram/Slack, or delivery code, and it does not expose raw source bodies,
  provider payloads, item titles, summaries, actions, source object
  identifiers, evidence refs, secrets, credentials, rendered text, chunk text,
  or hidden low-priority details. The next step after accepted local triage is
  to rerun real stored local data readiness and persisted attention window
  discovery; scheduler and automatic delivery remain deferred.
- FOS-085 adds `scripts/report_persisted_attention_window_reconciliation.py`,
  a local read-only reconciliation report for persisted attention windows. It
  compares attention-result write-time windows with optional linked
  normalized/source activity windows, labels synthetic/no-marker/mixed windows
  conservatively, and computes current digest hash metadata without returning
  rendered digest text or chunk text.
- FOS-085 compares the current digest `text_sha256` with existing delivery
  draft hashes and separates prior successful sends for different digest
  content from successful sends for the current digest content. It does not
  create drafts, approvals, delivery intentions, Telegram plans,
  preflight/gate records, delivery results, scheduler jobs, worker/outbox
  records, migrations, or tables; call live APIs, providers/OpenAI,
  connectors, Telegram/Slack, or delivery code; or expose raw source bodies,
  provider payloads, item details, source object identifiers, evidence refs,
  secrets, credentials, rendered text, chunk text, or hidden low-priority
  details. Real stored local draft preparation should wait until
  reconciliation shows the current digest content is not already sent and
  timestamp/linkage status is understood.
- FOS-086 adds `scripts/report_no_marker_persisted_attention_candidates.py`,
  a local read-only no-marker persisted attention candidate report for mixed
  persisted windows. It excludes synthetic/local/dev attention results,
  reports no-marker-only candidate counts, computes candidate hash/chunk
  metadata without returning rendered text or chunk text, and compares the
  candidate hash to existing delivery draft hashes.
- FOS-086 does not treat no-marker rows as production truth, create drafts,
  approvals, delivery intentions, Telegram plans, preflight/gate records,
  delivery results, scheduler jobs, worker/outbox records, migrations, or
  tables; call live APIs, providers/OpenAI, connectors, Telegram/Slack, or
  delivery code; or expose raw source bodies, provider payloads, item details,
  source object identifiers, evidence refs, secrets, credentials, rendered
  text, chunk text, or hidden low-priority details. Real stored local draft
  preparation should wait until this no-marker candidate report is reviewed and
  accepted.
- FOS-087 adds
  `scripts/prepare_no_marker_persisted_attention_delivery_draft.py`, a
  local/dev-only command that prepares an inert no-marker persisted attention
  delivery draft after explicit confirmation. It requires an explicit
  timezone-aware persisted attention window, fixes
  `marker_filter=no_marker_only`, excludes synthetic/local/dev attention
  results, refuses production-like environments, and stores safe draft review
  metadata for the no-marker candidate hash, excluded synthetic counts,
  `no_marker_not_production_truth`, timestamp mismatch warnings, and prior
  successful delivery for different digest content.
- FOS-087 creates only the delivery draft audit record. It does not approve,
  reject, create delivery intentions, create Telegram plans, create
  preflight/gate records, create delivery results, send Telegram/Slack
  messages, add scheduler/worker/outbox behavior, add migrations or tables, or
  call live APIs, providers/OpenAI, connectors, Telegram/Slack, or delivery
  code. Human approval remains a separate explicit step, and duplicate-success
  protection remains the final send-time guard.
- FOS-088 adds
  `scripts/report_no_marker_persisted_attention_digest_quality.py`, a local
  read-only no-marker persisted attention digest quality report for manual
  pilots. It reports duplicate-looking/noisy no-marker candidate items through
  safe aggregate clusters and count-only metrics before another real/no-marker
  send is considered.
- FOS-088 never exposes raw titles, summaries, actions, source object
  identifiers, PR numbers, repository names, author names, rendered text, chunk
  text, raw payloads, evidence refs, secrets, or credentials. Opaque cluster
  labels are report labels, not database identifiers, and duplicate-looking is
  not proof of semantic duplication. The report creates no drafts, approvals,
  delivery intentions, Telegram plans, preflight/gate records, delivery
  results, scheduler jobs, worker/outbox records, migrations, or tables; it does
  not call live APIs, providers/OpenAI, connectors, Telegram/Slack, or delivery
  code.
- FOS-089 adds
  `scripts/report_no_marker_persisted_attention_duplicate_root_cause.py`, a
  local read-only duplicate root-cause linkage report for no-marker persisted
  attention candidates. It uses count-only opaque buckets to distinguish likely
  source-object repetition, source-event repetition, normalization fanout,
  attention-result fanout, rendered-shape collision, mixed signals, and
  insufficient linkage before any future dedupe or grouping work.
- FOS-089 does not create drafts, approvals, delivery intentions, Telegram
  plans, preflight/gate records, delivery results, sends, scheduler jobs,
  worker/outbox records, migrations, or tables. It does not change the renderer,
  digest read model, source event normalization, or attention triage, and it
  does not call live APIs, providers/OpenAI, connectors, Telegram/Slack, or
  delivery code. It never exposes raw source object identifiers, PR numbers,
  repository names, author names, titles, summaries, actions, source bodies,
  evidence refs, rendered text, chunk text, secrets, credentials, raw payloads,
  or raw fingerprints. Human approval remains a separate downstream step, and
  duplicate-success protection remains the send-time guard.
- FOS-090 adds
  `scripts/report_no_marker_persisted_attention_grouped_preview.py`, a local
  read-only no-marker grouped digest preview. It groups repeated source-object
  no-marker candidate items by source object for presentation planning only,
  preserves visible item counts, reports grouped entry counts and per-section
  counts separately, and computes a separate grouped preview hash/chunk metadata
  without exposing grouped text. It returns the canonical ungrouped candidate
  `text_sha256` unchanged.
- FOS-090 does not change the real persisted digest read model, renderer,
  delivery draft text, `text_sha256`, or delivery behavior, and does not dedupe
  or delete raw source events. It creates no drafts, approvals, delivery
  intentions, Telegram plans, preflight/gate records, delivery results, sends,
  scheduler jobs, worker/outbox records, migrations, or tables, and does not
  call live APIs, providers/OpenAI, connectors, Telegram/Slack, or delivery
  code. It never exposes raw titles, summaries, actions, source object
  identifiers, PR numbers, repository names, author names, evidence refs,
  rendered text, chunk text, secrets, credentials, raw payloads, or raw
  fingerprints. Grouping preview does not prove semantic duplication and is not
  a source-of-truth mutation; human approval remains a separate downstream step,
  and send-time duplicate-success protection remains the final guard. Scheduler
  and automatic delivery remain deferred.
- FOS-091 adds
  `scripts/report_no_marker_persisted_attention_grouped_lifecycle_compatibility.py`,
  a local read-only no-marker grouped lifecycle compatibility report. It compares
  the canonical no-marker candidate `text_sha256`, the grouped preview
  `text_sha256`, and the window's existing delivery draft/result lifecycle, and
  explains whether a grouped preview would be treated as already-sent or as a
  new/unsent presentation variant under the current hash-oriented duplicate
  guard. It flags `presentation_variant_duplicate_send_risk` when the grouped
  hash differs from an already-sent canonical candidate hash and the grouped
  hash itself has no successful delivery.
- FOS-091 does not create drafts, approvals, delivery intentions, Telegram
  plans, preflight/gate records, delivery results, sends, scheduler jobs,
  worker/outbox records, migrations, or tables, and does not change the
  renderer, read model, delivery draft text, `text_sha256` lifecycle, or the
  duplicate guard. It does not call live APIs, providers/OpenAI, connectors,
  Telegram/Slack, or delivery code, and never exposes raw titles, summaries,
  actions, source object identifiers, PR numbers, repository names, author
  names, evidence refs, rendered text, grouped preview text, chunk text,
  secrets, credentials, raw payloads, or raw fingerprints. The grouped hash is a
  presentation-variant hash, not delivered content; a future grouped draft/send
  requires a guard extension or canonical-hash linkage. Human approval remains a
  separate downstream step, send-time duplicate-success protection remains the
  final guard, and scheduler/automatic delivery remains deferred.
- FOS-092 adds a service-level read-only canonical-hash duplicate guard
  evaluator for presentation variants. It accepts an explicit current
  presentation `text_sha256`, an optional explicitly linked canonical
  `text_sha256`, and a delivery window, then reads existing delivery
  draft/intention/result audit metadata to report direct current-hash success,
  distinct canonical-hash success, and a future-safe blocker code for
  presentation variants of already-delivered canonical content.
- FOS-092 does not enforce blocking in the send path yet, does not create or
  mutate drafts, approvals, intentions, Telegram plans, preflight/gate records,
  delivery results, sends, scheduler jobs, worker/outbox records, migrations, or
  tables, and does not claim semantic duplication. It only evaluates explicitly
  linked canonical/presentation hashes. Grouping preview remains presentation
  planning, not source-of-truth mutation, and duplicate-success protection
  remains the final send-time guard.
- FOS-093 exposes that read-only evaluator inside the no-marker grouped
  lifecycle compatibility report for review. It uses the grouped preview hash as
  the current presentation hash and the no-marker candidate hash as the linked
  canonical hash, then reports sanitized current-hash success,
  linked-canonical success, future blocker/recommended-action metadata,
  `enforced=false`, and `semantic_duplicate_claimed=false`.
- FOS-093 does not enforce blocking in send paths, does not create or mutate
  drafts, approvals, intentions, Telegram plans, preflight/gate records,
  delivery results, sends, scheduler jobs, worker/outbox records, migrations, or
  tables, and does not claim semantic duplication. It only applies to explicitly
  linked canonical/presentation hashes. Grouping preview remains presentation
  planning, not source-of-truth mutation, and duplicate-success protection
  remains the final send-time guard.
- FOS-094 adds a sanitized, read-only operator review summary to the grouped
  lifecycle compatibility report. The summary is derived from lifecycle
  compatibility plus canonical-hash guard evaluation metadata, and reports
  whether the grouped presentation is already sent by current hash, potentially
  blocked by an explicitly linked canonical hash, not blocked, or needs manual
  review because evidence is insufficient.
- FOS-094 does not enforce blocking in send paths, does not create or mutate
  drafts, approvals, intentions, Telegram plans, preflight/gate records,
  delivery results, sends, scheduler jobs, worker/outbox records, migrations, or
  tables, and does not claim semantic duplication. It only applies to explicitly
  linked canonical/presentation hashes; missing or insufficient evidence leads
  to conservative manual review. Grouping preview remains presentation
  planning, not source-of-truth mutation, and duplicate-success protection
  remains the final send-time guard.
- FOS-095 adds sanitized contract tests for the grouped lifecycle compatibility
  report. The tests cover `lifecycle_compatibility`,
  `canonical_hash_guard_evaluation`, and `operator_review_summary`, and fail if
  required fields disappear, stable operator decision values change,
  enforcement becomes true, semantic duplication is claimed, or unsafe output
  appears.
- FOS-095 is reporting/review contract hardening only. It does not enforce
  blocking in send paths, does not change renderer behavior, draft body
  generation, `text_sha256`, API behavior, schema, delivery execution, or
  scheduler behavior, and does not claim semantic duplication. Grouping preview
  remains presentation planning, not source-of-truth mutation, and
  duplicate-success protection remains the final send-time guard.
- FOS-096 adds a decision-only `review-json` output mode for the grouped
  lifecycle compatibility report. The mode returns only minimal safe
  report/window metadata, `lifecycle_compatibility`,
  `canonical_hash_guard_evaluation`, `operator_review_summary`, and safety
  flags, while omitting full-report-only sections not needed for operator
  decision review.
- FOS-096 is read-only reporting/review only. It does not enforce blocking in
  send paths, does not change renderer behavior, draft body generation,
  `text_sha256`, API behavior, schema, delivery execution, delivery results,
  scheduler behavior, or automatic delivery, and does not claim semantic
  duplication. Grouping preview remains presentation planning, not
  source-of-truth mutation, and duplicate-success protection remains the final
  send-time guard.
- FOS-097 improves CLI help for grouped lifecycle report output modes and adds
  a local synthetic review smoke mode. The help exposes `text`, `json`, and
  `review-json` as read-only modes, and the smoke mode returns in-memory
  synthetic scenarios for the sanitized decision surface without reading real
  local data.
- FOS-097 is reporting/debug only. The synthetic smoke mode is provider-free,
  read-only, local, and synthetic. It does not enforce blocking in send paths,
  claim semantic duplication, create drafts, approvals, intentions, delivery
  results, sends, audit rows, or source-of-truth mutations, and does not change
  renderer behavior, draft body generation, `text_sha256`, API behavior,
  schema, delivery execution, delivery results, scheduler behavior, or
  automatic delivery. Grouping preview remains presentation planning, not
  source-of-truth mutation, and duplicate-success protection remains the final
  send-time guard.
- FOS-098 adds optional review exit codes for grouped lifecycle local/operator
  automation. The exit codes are derived only from
  `operator_review_summary.decision` and are review/reporting signals, not
  send-path enforcement.
- FOS-098 also adds optional sanitized artifact output for `review-json` and
  synthetic review smoke output. Artifact files are local review artifacts, not
  source of truth, and the CLI rejects unsafe artifact paths and unsafe output
  modes. This remains provider-free/read-only for smoke and non-enforcing for
  all modes; it does not create drafts, approvals, intentions, delivery results,
  sends, audit rows, or source-of-truth mutations, does not claim semantic
  duplication, and does not change renderer behavior, draft body generation,
  `text_sha256`, API behavior, schema, delivery execution, delivery results,
  scheduler behavior, or automatic delivery. Grouping preview remains
  presentation planning, and duplicate-success protection remains the final
  send-time guard.
- FOS-099 adds a provider-free grouped lifecycle review operator doctor. The
  doctor is a local synthetic self-check for output-mode help, synthetic review
  smoke, decision-only `review-json` contract checks, review exit-code mapping,
  sanitized artifact writing, and unsafe artifact rejection.
- FOS-099 is reporting/debug only. It does not use real local data, does not
  require provider credentials, DB access, raw storage, Obsidian export,
  Telegram/Slack/OpenAI/Gmail/Jira/GitHub, or live APIs, and any doctor artifact
  is a local review/debug artifact only. It does not enforce blocking in send
  paths, does not claim semantic duplication, does not create drafts, approvals,
  intentions, delivery results, sends, audit rows, or source-of-truth mutations,
  and does not change renderer behavior, draft body generation, `text_sha256`,
  API behavior, schema, delivery execution, delivery results, scheduler
  behavior, or automatic delivery. Grouping preview remains presentation
  planning, and duplicate-success protection remains the final send-time guard.
- FOS-100 adds a gated manual local grouped lifecycle review runner intended for
  future human-operated read-only local verification. The runner blocks by
  default unless `--allow-local-data-readonly` is passed, runs the provider-free
  doctor before delegation, and only allows sanitized `review-json` plus a safe
  local artifact path.
- FOS-100 is manual/read-only/debug tooling, not send-path enforcement. It
  rejects unsafe output modes and unsafe artifact paths before report
  delegation, does not claim semantic duplication, does not create drafts,
  approvals, intentions, delivery results, sends, audit rows, or
  source-of-truth mutations, and does not change renderer behavior, draft body
  generation, `text_sha256`, API behavior, schema, delivery execution, delivery
  results, scheduler behavior, or automatic delivery. Runner artifacts are
  local review/debug artifacts only, grouping preview remains presentation
  planning, and duplicate-success protection remains the final send-time guard.
- FOS-102 adds safe bounded window presets and a preflight mode to the manual
  grouped lifecycle review runner. `--lookback-hours` can resolve UTC
  `--start-at`/`--end-at` values for local read-only debugging, while
  `--preflight-only` validates acknowledgement, doctor readiness, output mode,
  artifact path, and the resolved window without report execution.
- FOS-102 keeps the runner manual/read-only/debug only. It remains blocked by
  default unless `--allow-local-data-readonly` is passed, runs the provider-free
  doctor before acknowledged delegation, requires sanitized `review-json` and a
  safe artifact path for local-data runs, does not enforce blocking in send
  paths, does not claim semantic duplication, does not create drafts,
  approvals, intentions, delivery results, sends, audit rows, or
  source-of-truth mutations, and does not change renderer behavior, draft body
  generation, `text_sha256`, API behavior, schema, delivery execution, delivery
  results, scheduler behavior, or automatic delivery. Artifacts remain local
  review/debug artifacts only, grouping preview remains presentation planning,
  and duplicate-success protection remains the final send-time guard.
- FOS-104 adds sanitized manual-review diagnostics to grouped lifecycle review
  output. The diagnostics are derived from sanitized lifecycle compatibility,
  canonical-hash guard evaluation, operator review summary, and resolved window
  metadata, and expose stable reason/action codes so `manual_review_needed`
  results can be debugged without exposing raw content.
- FOS-104 diagnostics are read-only reporting/debug metadata only. They do not
  enforce blocking in send paths, do not claim semantic duplication, do not
  create drafts, approvals, intentions, delivery results, sends, audit rows, or
  source-of-truth mutations, and do not change renderer behavior, draft body
  generation, `text_sha256`, API behavior, schema, delivery execution, delivery
  results, scheduler behavior, or automatic delivery. Artifacts remain local
  review/debug artifacts only, grouping preview remains presentation planning,
  and duplicate-success protection remains the final send-time guard.
- FOS-106 removes raw hash values from grouped lifecycle `review-json`,
  synthetic smoke, doctor, and manual-runner artifact output. Operator-facing
  artifacts use booleans and relationship categories instead of raw hash
  identifiers, while internal read-only lifecycle comparison and duplicate-guard
  evaluation may still use hashes.
- FOS-106 is reporting/debug sanitization only. Sanitized review artifacts are
  local review/debug artifacts only, not source of truth. It does not enforce
  blocking in send paths, does not claim semantic duplication, does not create
  drafts, approvals, intentions, delivery results, sends, audit rows, or
  source-of-truth mutations, and does not change renderer behavior, draft body
  generation, `text_sha256`, API behavior, schema, delivery execution, delivery
  results, scheduler behavior, or automatic delivery. Grouping preview remains
  presentation planning, and duplicate-success protection remains the final
  send-time guard.
- FOS-108 adds a gated grouped lifecycle review window sweep runner for local
  operator debugging. The runner compares sanitized review decisions and
  diagnostics across multiple bounded lookback windows, supports preflight-only
  checks, writes only sanitized local review/debug artifacts under a safe output
  directory, and produces a conservative aggregate review decision.
- FOS-108 is manual/read-only/debug tooling. It remains default-blocked unless
  `--allow-local-data-readonly` is passed, runs the provider-free doctor before
  acknowledged sweep delegation, does not enforce blocking in send paths, does
  not claim semantic duplication, does not create drafts, approvals,
  intentions, delivery results, sends, audit rows, or source-of-truth
  mutations, and does not change renderer behavior, draft body generation,
  `text_sha256`, API behavior, schema, delivery execution, delivery results,
  scheduler behavior, or automatic delivery. Artifacts remain local
  review/debug artifacts only, grouping preview remains presentation planning,
  and duplicate-success protection remains the final send-time guard.
- FOS-110 fixes grouped lifecycle sweep delegation outcome handling. Delegated
  review exit codes `0`, `10`, `20`, and `30` are completed window outcomes,
  including `30` for `manual_review_needed`, so acknowledged sweeps continue
  through all requested windows when every delegated result is a valid review
  outcome.
- FOS-110 keeps aggregate decisions aligned with aggregate exit codes:
  `manual_review_needed` wins first, followed by
  `blocked_by_linked_canonical_hash`, `already_sent_by_current_hash`, and
  all-`not_blocked`. Unexpected delegated failures still fail with sanitized
  metadata only. The sweep remains default-blocked, doctor-gated,
  sanitized-output-only, no-send, non-enforcing, and not a source-of-truth
  mutation.
- FOS-112 routes acknowledged sweep windows through the gated manual runner
  boundary and classifies the captured delegated review return code there.
  Valid review outcomes `0`, `10`, `20`, and `30` remain completed window
  outcomes, including `30` for `manual_review_needed`; unexpected return codes
  or malformed delegated output still fail with sanitized metadata only.
- FOS-112 preserves the same operator boundaries: default-blocked,
  doctor-gated, sanitized-output-only, no-send, non-enforcing, and not a
  source-of-truth mutation.
- FOS-114 fixes the upstream delegated report boundary inside the manual runner
  used by grouped lifecycle sweep windows. Valid delegated report review
  outcomes `0`, `10`, `20`, and `30` are classified before failure handling,
  so `30` for `manual_review_needed` remains a valid completed review outcome
  when sanitized review output is present.
- FOS-114 keeps unexpected return codes, malformed output, decision/code
  mismatches, and sanitizer failures as sanitized failures only. It preserves
  default blocking, doctor gating, explicit local-readonly acknowledgement,
  no-send behavior, non-enforcement, source-of-truth immutability, human
  approval boundaries, and duplicate-success protection.
- FOS-116 fixes the nested sweep/manual review contract by validating the
  per-window manual review artifact as the durable sanitized payload after a
  valid delegated review outcome. Captured delegated stdout may be diagnostic
  text, so valid outcomes `0`, `10`, `20`, and `30` can complete sweep windows
  when the artifact is present, safe, and decision-aligned.
- FOS-116 keeps missing or malformed artifacts, unexpected return codes,
  decision/code mismatches, and sanitizer failures as sanitized failures only.
  The tooling remains default-blocked, doctor-gated, explicit-acknowledgement,
  sanitized-output-only, no-send, non-enforcing, and not a source-of-truth
  mutation.
- FOS-118 closes the remaining nested delegated report contract gap. The
  manual runner now passes its safe artifact path to the delegated report
  command and validates that durable sanitized artifact after a valid review
  outcome, so delegated report stdout is not required to be the review payload.
  Missing or malformed report artifacts, unexpected return codes,
  decision/code mismatches, and sanitizer failures remain sanitized failures.
- FOS-120 makes the delegated report review-json artifact contract explicit.
  The report artifact carries a stable review-json schema marker, and the
  manual runner distinguishes that artifact from a full compatibility report
  before validation. Full reports are converted through the same sanitized
  formatter; ambiguous, missing, malformed, mismatched, or unsafe artifacts
  remain sanitized failures.
- FOS-122 tightens the CLI-level delegated report artifact contract. The manual
  runner requests `review-json` at the exact delegated artifact path, accepts
  schema-marked review artifacts, markerless legacy review-json artifacts, or
  full compatibility reports only after sanitized conversion, and fails safely
  for wrong-path, wrong-schema, malformed, mismatched, or unsafe artifacts.
- FOS-124 refines markerless delegated review-json handling to key off the
  required safe review sections instead of a single status value. Delegated
  report failures now include sanitized contract diagnostics only: boundary,
  exit-code class, artifact presence, schema kind, contract status, validator,
  and missing field names.
- FOS-126 fixes the manual-runner to report delegated CLI invocation. The
  compatibility report command is default-blocked for non-synthetic review
  execution unless `--allow-local-data-readonly` is present, and the manual
  runner passes that acknowledgement so the delegated command reaches the
  artifact-writing review path. Parser/default-block/infrastructure exits
  remain sanitized delegated failures with CLI contract diagnostics.
- FOS-126 preserves doctor gating, explicit local-readonly acknowledgement,
  sanitized output/artifacts, no-send behavior, non-enforcement,
  source-of-truth immutability, human approval boundaries, and
  duplicate-success protection.
- FOS-128 fixes the remaining sweep to manual to report delegated review
  path when the acknowledged report command reaches a local read-only runtime
  blocker before writing its review artifact. In artifact-backed `review-json`
  review-exit-code mode, the report command now writes a conservative
  sanitized `manual_review_needed` artifact instead of returning an
  artifactless infrastructure code.
- FOS-128 keeps parser errors, missing acknowledgement, default-block exits,
  wrong modes, missing/malformed artifacts, decision/code mismatches, and
  unsafe artifacts as sanitized failures. It preserves no-send,
  non-enforcement, source-of-truth immutability, human approval boundaries, and
  duplicate-success protection.
- FOS-018 adds a Telegram outbound delivery adapter for already-rendered plain
  text only. It can build plain `sendMessage` payloads, split long text into
  Telegram-safe chunks, and send chunks through an injected transport.

Still not implemented / target gaps:

- Production Telegram webhook bot.
- Production scheduler-managed Telegram bot/digest cadence.
- Scheduled daily digest generation.
- End-to-end scheduled Telegram digest delivery.
- Free-form Telegram Q&A beyond allowlisted command/status handling.
- Full Jira sync.
- Full GitHub repository sync.
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
