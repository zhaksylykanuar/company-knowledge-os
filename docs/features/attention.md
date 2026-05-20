# Feature: Attention

## Status

- Deterministic scoring: implemented
- Attention dashboard: implemented
- Feedback storage: implemented
- Normalized activity item persistence foundation: implemented
- Attention triage result persistence and single-activity bridge foundation:
  implemented
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
- Persisted normalized activity items and attention results are not yet used as
  digest inputs.
- GitHub/Jira/Drive digest integration is not implemented.
