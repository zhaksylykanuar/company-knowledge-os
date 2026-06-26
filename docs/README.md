# FounderOS Docs

This is the single navigation entry for the current FounderOS documentation set.
After the Lineage-2 purge (DEC-029), the documentation is the canonical set only.

## Reading Order

1. [`../founderOS_MASTER_PLAYBOOK.md`](../founderOS_MASTER_PLAYBOOK.md) -
   canonical product, MVP scope, data model, API, frontend, AI, security, test,
   deploy, and backlog source of truth (**what** to build).
2. [`../PROGRESS.md`](../PROGRESS.md) - live state and next task pointer
   (**where** we are).
3. [`DECISIONS.md`](DECISIONS.md) - durable repo decisions and explicit
   conflict resolutions (**why**).
4. [`ROADMAP.md`](ROADMAP.md), [`TODO.md`](TODO.md),
   [`POST_MVP.md`](POST_MVP.md), and [`CHANGELOG.md`](CHANGELOG.md) - working
   planning layer.

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
