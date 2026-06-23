# FounderOS Docs Index

Compatibility entry for older tooling. The canonical docs entry is
[`README.md`](README.md).

## Current Truth vs Target Direction

- Current operating truth: the root canonical trio
  [`../founderOS_MASTER_PLAYBOOK.md`](../founderOS_MASTER_PLAYBOOK.md),
  [`../EXECUTION_PLAN.md`](../EXECUTION_PLAN.md), and
  [`../PROGRESS.md`](../PROGRESS.md), plus required control docs linked from
  [`README.md`](README.md).
- Target direction: only the root master playbook is authoritative for MVP.
  Older target docs were archived.
- Historical traceability: archived FOS ledgers and implementation inventories
  live under [`_archive/`](_archive/); they are not the current feature
  contract when they conflict with the canonical files.

## Start Here

- [`README.md`](README.md): single current docs navigation entry.
- [`../AGENTS.md`](../AGENTS.md): agent operating rules.
- [`../CLAUDE.md`](../CLAUDE.md): AI/token/extraction rules.

## Repo Navigation Rules

- Do not scan the whole repo unless explicitly needed.
- Prefer `rg`, `find`, and targeted files.
- Future behavior changes must update the relevant docs in the same task.
