# Feature Contract: Telegram Digest

## Status

- Telegram bot/interface: planned
- Daily digest generation: planned
- Telegram delivery: planned
- Telegram Q&A: planned
- Internal deterministic source activity digest builder: implemented
- Protected source activity digest API: implemented
- Protected rendered source activity digest text API: implemented
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
- Scheduler, connector, inbound Q&A, LLM summarization, or digest inference
  logic in the Telegram outbound delivery adapter.
