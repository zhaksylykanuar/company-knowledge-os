# FounderOS Changelog

## 2026-06-23

### Added

- Added root canonical docs:
  `founderOS_MASTER_PLAYBOOK.md`, `EXECUTION_PLAN.md`, and `PROGRESS.md`.
- Added this changelog as the missing required playbook control doc.
- Added `docs/README.md` as the single docs navigation entry.
- Added `docs/_audit/DOCS_AUDIT.md` before any archive/removal action.
- Added `docs/_archive/MANIFEST.md` to document reversible archive moves.

### Changed

- Updated documentation navigation to make the root canonical trio the primary
  source of truth.
- Preserved current useful feature/runbook docs as supporting docs subordinate
  to the canonical playbook and execution plan.
- Replaced large historical ledger docs at selected paths with slim current
  status / compatibility docs while archiving the originals.

### Archived

- Archived older playbook, vision, audit, dirty-tree, backlog, agent-stub,
  Telegram/manual-pilot, Jira rebuild, and historical ledger docs under
  `docs/_archive/`.

### Safety

- No application code, tests, migrations, raw storage, generated Obsidian vault
  files, env files, or secrets were intentionally modified.
