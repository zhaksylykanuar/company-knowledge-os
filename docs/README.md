# FounderOS Docs

This is the single navigation entry for the current FounderOS documentation set.
After the Lineage-2 purge (DEC-029), the active docs are intentionally small:
source-of-truth docs for the current product and audit-only history for
recovering deleted context.

## Reading Order

1. [`../README.md`](../README.md) - human/developer onboarding and local run
   path.
2. [`../founderOS_MASTER_PLAYBOOK.md`](../founderOS_MASTER_PLAYBOOK.md) -
   canonical product/MVP scope (**what** to build). Its status block is
   summarized from the live docs; it is not the live task tracker.
3. [`../PROGRESS.md`](../PROGRESS.md) - live state, gate health, and next task
   pointer (**where** we are).
4. [`DECISIONS.md`](DECISIONS.md) - durable repo decisions and explicit conflict
   resolutions (**why**).
5. [`ROADMAP.md`](ROADMAP.md), [`TODO.md`](TODO.md),
   [`POST_MVP.md`](POST_MVP.md), and [`CHANGELOG.md`](CHANGELOG.md) - planning,
   near-term backlog, deferred scope, and dated change history.

## Source-of-truth Matrix

| Question | Use |
|---|---|
| What is this project and how do I run it? | [`../README.md`](../README.md) |
| What is the MVP/product scope? | [`../founderOS_MASTER_PLAYBOOK.md`](../founderOS_MASTER_PLAYBOOK.md) |
| What is implemented right now and what is next? | [`../PROGRESS.md`](../PROGRESS.md) |
| Why was an architecture/product choice made? | [`DECISIONS.md`](DECISIONS.md) |
| What is the current development workflow for agents? | [`../AGENTS.md`](../AGENTS.md) and [`../CLAUDE.md`](../CLAUDE.md) |
| What are the safety/security boundaries? | [`../AGENTS.md`](../AGENTS.md), [`../CLAUDE.md`](../CLAUDE.md), [`../SECURITY_BASELINE.md`](../SECURITY_BASELINE.md) |
| What should be built next? | [`../PROGRESS.md`](../PROGRESS.md), then [`TODO.md`](TODO.md) |
| What is intentionally deferred? | [`POST_MVP.md`](POST_MVP.md) |
| How do we deploy/smoke private beta manually? | [`deploy/private-beta.md`](deploy/private-beta.md) and [`deploy/railway-private-beta.md`](deploy/railway-private-beta.md) |

## Deploy Runbooks

- [`deploy/private-beta.md`](deploy/private-beta.md) - manual private-beta deployment, migration, rollback, CORS, env-name, and smoke procedure.
- [`deploy/railway-private-beta.md`](deploy/railway-private-beta.md) - concrete Railway split-service dry-run plan and placeholder env templates.

## Required Control Docs

- [`DECISIONS.md`](DECISIONS.md)
- [`ROADMAP.md`](ROADMAP.md)
- [`TODO.md`](TODO.md)
- [`POST_MVP.md`](POST_MVP.md)
- [`CHANGELOG.md`](CHANGELOG.md)

## Audit Trail

- [`_audit/DOCS_AUDIT.md`](_audit/DOCS_AUDIT.md) - documentation consolidation +
  code-reality reconciliation.
- [`_audit/PURGE_AUDIT.md`](_audit/PURGE_AUDIT.md) - Lineage-2 purge
  classification and recovery instructions (tag `pre-purge-20260624`).

Older supporting/feature/runbook docs and the archive were removed in the
Lineage-2 purge; recover any from git tag `pre-purge-20260624` if needed.

## Future Agent Documentation Rules

- Update docs in the same task as the behavior change; do not leave a separate
  "docs later" task unless the current task is explicitly read-only.
- Keep `PROGRESS.md` short at the top: current state, gate health, next step.
  Historical session detail may stay below, newest first.
- Keep `TODO.md` focused on near-term work. Move deferred ideas to
  `POST_MVP.md` and remove completed task scaffolding when it becomes noise.
- Add a `DECISIONS.md` entry for durable architecture, security, deploy,
  data-model, or scope changes. Do not use changelog entries as substitutes for
  decisions.
- Do not write real secrets, token values, database URLs, provider payloads, raw
  private source bodies, chat IDs, or production smoke outputs into docs.
- Use placeholder env examples only (`<placeholder>`). `.env.example` and
  `docs/deploy/templates/*.env.example` are templates, not real config.
- Delete obsolete docs only when they are clearly superseded or recoverable from
  git history/tag. If unsure, preserve the file and document the uncertainty.
