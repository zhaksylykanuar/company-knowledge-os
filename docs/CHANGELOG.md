# FounderOS Changelog

## 2026-06-24

### Added

- Added `POST /api/v1/workspaces/{workspace_id}/github/local-sync` as a compact
  product backend wrapper over existing manual SyncJob + local normalization
  behavior; it persists through the canonical local path and does not start live
  provider execution.
- Added dashboard GitHub local-sync controls that read connection status, show
  missing/unsupported/loading/error/success states, report normalized
  repository/issue/PR counts, and refresh canonical operational work after a
  successful local sync.
- Added backend and frontend tests for the local-sync control path, including
  no-live-provider flags, no-connection handling, idempotence, URL building,
  POST payload shape, and honest no-OAuth UI states.

### Changed

- Wired the dashboard to canonical GitHub operational work from
  `/api/v1/workspaces/{workspace_id}/github/operational-work`, including
  issue/task and PR sections, repository labels, filters, and loading/empty/error
  states.
- Added a lightweight frontend test command for the `web/` shell using
  TypeScript compilation plus Node's built-in test runner.
- Fast-forward merged the cleanup/FOS-008/doc-hygiene line into local `main`
  at `ef22360`; `main` is ahead of `origin/main` until an explicit push.
- Collapsed the current control docs to
  `founderOS_MASTER_PLAYBOOK.md`, `PROGRESS.md`, `docs/DECISIONS.md`,
  `docs/README.md`, `docs/ROADMAP.md`, `docs/TODO.md`,
  `docs/POST_MVP.md`, and `docs/CHANGELOG.md`.
- Marked FOS-009 as the next main-path task after FOS-008 canonical repository
  persistence.

### Removed

- Removed `EXECUTION_PLAN.md` from the active control set (DEC-031).
- Removed the live archive tree from the current docs set; historical material
  is recovered through git history / tag `pre-purge-20260624`.

## 2026-06-23

### Added

- Added root canonical docs for the incoming playbook line.
- Added this changelog as the missing required playbook control doc.
- Added `docs/README.md` as the single docs navigation entry.
- Added `docs/_audit/DOCS_AUDIT.md` before any archive/removal action.

### Changed

- Updated documentation navigation to make the root control docs the primary
  source of truth.
- Preserved current useful feature/runbook docs as supporting docs subordinate
  to the canonical playbook.
- Replaced large historical ledger docs at selected paths with slim current
  status / compatibility docs while archiving the originals.

### Archived

- Historical older playbook, vision, audit, dirty-tree, backlog, agent-stub,
  Telegram/manual-pilot, Jira rebuild, and ledger docs were later removed from
  the live tree by DEC-029/DEC-031.

### Safety

- No application code, tests, migrations, raw storage, generated Obsidian vault
  files, env files, or secrets were intentionally modified.
