# Feature: Attention

## Status

Current operating truth:

- Deterministic attention scoring, feedback, persisted attention digest read
  models, preview/reporting CLIs, and guarded local/manual review paths exist.
- Manual/test-only delivery draft, approval, intention, preflight, execution
  gate, and bounded Telegram test-send support exists behind explicit gates.
- Production target gaps remain: autonomous scheduler/outbox execution,
  production push delivery, and unrestricted live-provider execution are not
  current runtime behavior.

## Current Behavior

Attention is a supporting current-code surface, not the canonical GitHub-first
MVP spine. It may read stored evidence and produce safe reports/previews. It
must not call live providers, execute delivery, or mutate external systems
without the explicit approval and execution gates documented in the master
playbook and security docs.

## Historical Implementation Ledger (Archived)

The detailed FOS ledger was archived to
`../_archive/docs/features/attention.md`. It is retained for traceability but is
not the current feature contract; use this `Status`, `Current Behavior`, and
the canonical playbook/progress files for current truth.

## Invariants

- Every attention item that asserts a fact must be evidence-backed.
- Missing evidence yields empty/insufficient-evidence output, not invented
  facts.
- Debug output must not expose raw private source bodies, secrets, or provider
  payloads.
- Delivery remains human-approved and separately gated.

## Known Gaps

- Production scheduler/outbox delivery is not the current contract.
- Live-provider execution remains explicitly gated.
- Attention expansion is frozen unless tied to the canonical GitHub-first MVP.
