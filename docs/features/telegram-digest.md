# Feature Contract: Telegram Digest

## Status

Telegram digest is not part of the canonical GitHub-first MVP spine. Existing
guarded/manual digest and delivery work is frozen as post-MVP support unless a
future scoped task explicitly reactivates it.

## Product Intent

Legacy manual text MVP still supported means historical digest tooling may
remain usable for local/operator review, but it is not the current status source
for product execution. The root `PROGRESS.md` and `EXECUTION_PLAN.md` own the
current execution state.

## Source Of Truth

- Root canonical trio: `../../founderOS_MASTER_PLAYBOOK.md`,
  `../../EXECUTION_PLAN.md`, `../../PROGRESS.md`.
- Current post-MVP parking: `../POST_MVP.md`.
- Archived original ledger: `../_archive/docs/features/telegram-digest.md`.

## Source Inputs: Current vs Target

Current safe inputs are stored evidence/read models and explicit local/manual
review artifacts. Target Telegram Q&A, scheduler, webhook, and push behavior are
post-MVP and require fresh approval.

## Historical Implementation Ledger (Archived)

Historical implemented slices: the detailed FOS ledger and delivery-chain notes
were archived with the original file. They are retained for traceability but are
not the current status source.

## Boundaries

- No production scheduler or bot send is approved by this doc.
- No Telegram/Slack delivery happens without human approval and a separate
  execution gate.
- Raw source bodies, secrets, chat IDs, and provider payloads must not be
  printed in reports.
