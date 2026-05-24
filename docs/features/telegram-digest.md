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
- Hidden low-priority digest items must remain count-only in preview, persisted
  draft, and delivery-oriented surfaces. Evidence refs remain debug-only and
  safe-formatted.

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
  approved persisted delivery drafts.
- Bot credential handling and real Telegram send execution for delivery
  intentions.
- Public creation/update APIs for delivery result records.
- Telegram credential validation against Telegram for delivery intentions.
- API-backed or scheduled operator review flows for delivery intentions.
- Scheduler, connector, inbound Q&A, LLM summarization, or digest inference
  logic in the Telegram outbound delivery adapter.
