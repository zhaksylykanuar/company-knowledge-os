# Feature: Attention

## Status

- Deterministic scoring: implemented
- Attention dashboard: implemented
- LLM-generated digest: planned
- Telegram delivery: planned

## Current Behavior

- Extracted tasks, risks, and decisions can be scored.
- Scores include importance, urgency, risk, confidence, attention, reasons, and evidence refs.
- Attention dashboard reads existing scores and builds top items, tasks, risks, decisions, and sources.
- Source activity digest email sectioning uses the attention triage contract
  through an in-memory deterministic projection.

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
- A future slice may apply semantic attention triage to uncertain email cases behind explicit config.

## Invariants

- Attention items must remain evidence-backed.
- Scoring should be explainable through stored reasons.
- Dashboard reads scored data; it should not silently create new facts.
- LLM-backed activity triage must validate strict JSON before any future persistence or digest use.

## Known Gaps

- No scheduled digest is visible.
- No Telegram delivery is implemented.
- Score refresh is explicit, not automatic.
