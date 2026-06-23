# FounderOS Docs

This is the single navigation entry for the current FounderOS documentation set.

## Reading Order

1. [`../founderOS_MASTER_PLAYBOOK.md`](../founderOS_MASTER_PLAYBOOK.md) -
   canonical product, MVP scope, data model, API, frontend, AI, security, test,
   deploy, and backlog source of truth.
2. [`../EXECUTION_PLAN.md`](../EXECUTION_PLAN.md) - orchestration order, chunk
   gates, and driver prompts.
3. [`../PROGRESS.md`](../PROGRESS.md) - live state and next task pointer.
4. [`DECISIONS.md`](DECISIONS.md) - durable repo decisions and explicit
   conflict resolutions.
5. [`ROADMAP.md`](ROADMAP.md), [`TODO.md`](TODO.md),
   [`POST_MVP.md`](POST_MVP.md), and [`CHANGELOG.md`](CHANGELOG.md) - working
   planning layer.

## Current Truth vs Target Direction

- Canonical MVP truth lives in the root playbook, execution plan, progress file,
  and required docs listed above.
- Supporting feature/runbook docs describe current repository behavior only when
  linked from this file.
- Archived docs under [`_archive/`](_archive/) are historical traceability, not
  current source of truth.
- Generated Obsidian vault files are export artifacts and are not source truth.

## Required Control Docs

- [`DECISIONS.md`](DECISIONS.md)
- [`ROADMAP.md`](ROADMAP.md)
- [`TODO.md`](TODO.md)
- [`POST_MVP.md`](POST_MVP.md)
- [`CHANGELOG.md`](CHANGELOG.md)

## Current Supporting Docs

- [`data-model.md`](data-model.md) - current database/model reconciliation
  against the master playbook.
- [`github-integration-decision.md`](github-integration-decision.md) - current
  staged GitHub MVP bridge decision.
- [`dev-env.md`](dev-env.md) - local development setup.
- [`operator_runtime_setup.md`](operator_runtime_setup.md) - local operator
  runtime notes.
- [`obsidian-bridge.md`](obsidian-bridge.md) - Obsidian export-only bridge.
- [`security/api-boundary.md`](security/api-boundary.md) - API boundary and
  write/action guard contract.
- [`source-connectors.md`](source-connectors.md) - connector execution, scopes,
  receipts, and safety rules.
- [`runbooks/guarded-operations.md`](runbooks/guarded-operations.md) - guarded
  execution and diagnostics.
- [`runbooks/google-local-backfill.md`](runbooks/google-local-backfill.md) -
  current Gmail/Drive local backfill safety path.
- [`runbooks/jira-operating-model.md`](runbooks/jira-operating-model.md) - Jira
  planning model and repo-as-component rule.

## Feature Docs

- [`features/company-brain.md`](features/company-brain.md)
- [`features/drive.md`](features/drive.md)
- [`features/extraction.md`](features/extraction.md)
- [`features/gmail.md`](features/gmail.md)
- [`features/ingestion.md`](features/ingestion.md)
- [`features/local-ui.md`](features/local-ui.md)
- [`features/obsidian-export.md`](features/obsidian-export.md)
- [`features/retrieval.md`](features/retrieval.md)
- [`features/source-events.md`](features/source-events.md)
- [`features/source-integrations.md`](features/source-integrations.md)
- [`features/attention.md`](features/attention.md)
- [`features/knowledge-graph.md`](features/knowledge-graph.md)
- [`features/telegram-digest.md`](features/telegram-digest.md)

## Archive

The archive is reversible and preserves old relative paths under
[`_archive/`](_archive/). See [`_archive/MANIFEST.md`](_archive/MANIFEST.md) for
what moved and why.
