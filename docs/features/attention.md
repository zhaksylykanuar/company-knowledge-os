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
- Source activity digest behavior still uses the existing deterministic triage path.

## Universal Activity Triage

- FOS-041 adds reusable contracts for a future universal attention triage layer.
- The layer normalizes source activity from Gmail, GitHub, Jira, Drive, calendar, and other sources into a common `NormalizedActivityItem`.
- Providers return strict, schema-validated `AttentionTriageResult` objects with attention class, action type, priority, digest visibility, confidence, ownership, safety flags, and short summaries.
- The confidence policy prevents low-confidence items from being silently hidden; uncertain items stay visible as review optional.
- The current implementation includes mocked and conservative fallback providers only. It does not call external APIs.
- OpenAI or Llama-compatible providers can be wired in a later slice once explicitly enabled and configured.

## Invariants

- Attention items must remain evidence-backed.
- Scoring should be explainable through stored reasons.
- Dashboard reads scored data; it should not silently create new facts.
- LLM-backed activity triage must validate strict JSON before any future persistence or digest use.

## Known Gaps

- No scheduled digest is visible.
- No Telegram delivery is implemented.
- Score refresh is explicit, not automatic.
