# FounderOS Changelog

## 2026-07-01

### Changed

- Added GitHub App product-connect foundation: backend config/status contract,
  workspace-scoped app-installation connection recording without provider calls
  or persisted installation tokens, and a `/github` UI panel showing app
  readiness, local repository surface count, and external writes disabled.

## 2026-06-30

### Changed

- Added offline GitHub repository-surface preparation from `.local/repos.json`:
  repo audit and repository inventory now accept the root local repo list as a
  fallback discovery snapshot, and `scripts/prepare_github_local_snapshot.py`
  writes the canonical `.local/discovery/github/<snapshot>/raw/repos.json` layout
  plus a safe local repo allowlist snippet without provider calls or secrets.

- Added a DB-level GitHub repository identity guard:
  `uq_repositories_workspace_provider_full_name` on
  `(workspace_id, provider, full_name)`. Migration `e8f9a0b1c2d3` de-duplicates
  existing duplicate repository rows, re-points pull requests to the keeper, and
  makes repository upsert race-safe across the `external_id` and `full_name`
  paths before GitHub product connect/live sync.

## 2026-06-29

### Changed

- Persisted deterministic Founder Briefings: `Briefing` / `BriefingItem` tables
  and history endpoints now store/reopen generated manual briefings while the
  generator remains deterministic and LLM-free. New single Alembic head:
  `e7f8a9b0c1d2`.
- Audited the active documentation set and clarified the source-of-truth matrix
  in `docs/README.md`. `docs/TODO.md` was reduced from a completed-work ledger
  to a near-term backlog focused on GitHub product connect/live sync before LLM
  briefing narrative.
- Updated `README.md`, `PROGRESS.md`, `docs/ROADMAP.md`,
  `founderOS_MASTER_PLAYBOOK.md`, `AGENTS.md`, and `CLAUDE.md` to reflect that
  deterministic Founder Briefings are now persisted and that current LLM rules
  remain forward-looking.
- Added documentation-maintenance rules for future agents and Make convenience
  targets for backend, frontend, combined checks, and tracked-secret scan.
- Expanded `.gitignore` for common generated/cache/build artifacts.

### Removed

- Removed three obsolete grouped-lifecycle operator scripts that were no longer
  referenced and failed import because their required report module had already
  been removed in earlier cleanup.

## 2026-06-28

### Added

- Email+password founder login on server-side, revocable sessions. Added
  `password_service` (Argon2id), `session_service` plus a `sessions` table (the
  DB stores only the sha256 hash of the cookie token), and the auth endpoints
  `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`,
  and `POST /api/v1/auth/change-password` (the last revokes other sessions). New
  `require_session` dependency and a `get_current_actor` resolver that accepts
  either a session cookie (preferred) or the operator API key.
- DB-backed login brute-force throttle (`login_attempts` table): after a
  configured number of failures an email is locked for a configured window;
  known and unknown emails throttle identically and the API returns a generic
  error. Tunable via `FOUNDEROS_LOGIN_MAX_FAILED_ATTEMPTS` /
  `FOUNDEROS_LOGIN_LOCKOUT_MINUTES`.
- Idempotent admin provisioning command `scripts/create_admin_user.py` (seeds the
  single founder/admin user from `FOUNDEROS_ADMIN_*` env vars; re-running updates
  the password without creating a duplicate).
- Same-origin Next.js proxy so the session cookie stays first-party across the
  split frontend/backend deploy: `web/next.config.mjs` rewrites `/api/*` and
  `/health` to `FOUNDEROS_API_PROXY_TARGET` (falls back to
  `NEXT_PUBLIC_API_BASE_URL`).
- A `/login` page, `AuthGate`, session client (`web/lib/auth.ts` /
  `web/lib/session.ts`), and a Settings→account / change-password page.
- Canonical-task uniqueness: a partial unique index
  `uq_tasks_workspace_provider_external_id` (`workspace_id`, `source_provider`,
  `external_id` where `external_id IS NOT NULL`) plus dedupe migration
  `f7b8c9d0e1a2`.
- Central Russian UI message catalog `web/lib/messages.ts`.

### Changed

- GitHub normalization upserts (`Task`, `PullRequest`, `SourceRecord`,
  `Repository`) are now idempotent via PostgreSQL `INSERT ... ON CONFLICT DO
  UPDATE`, fixing duplicate rows on re-sync. `Task.updated_at` is documented as a
  "last synced" marker (bumped every sync); user-facing recency uses
  `source_updated_at`.
- The frontend no longer uses browser operator-key/owner-email config
  (`web/lib/config.ts` removed); workspace is derived from the session, and
  browser requests carry neither the operator key nor `owner_email`.
- Connector-token encryption now fails closed outside local/dev unless a
  dedicated `FOUNDEROS_SECRET_ENCRYPTION_KEY` is set (no longer reuses the API
  auth key as encryption material outside local).
- Public health split: `GET /health` is a minimal no-auth liveness probe; env
  and feature-flag detail moved to `GET /health/detail` behind the operator key.
- Account-active state reuses `User.status` (`active`/`disabled`); no `is_active`
  boolean was added.
- `ingested_events` Alembic drift reconciled (migration `a8c9d0e1f2b3`, indexes
  and constraints only — no data change). New single Alembic head:
  `c0e1f2a3b4d5`.
- Decisions recorded as DEC-041…DEC-047 in `docs/DECISIONS.md`.

### Safety

- The DB stores only session-token hashes; passwords are Argon2id-hashed and
  never returned. The admin-provisioning command never prints the password. No
  external provider writes, deploy, or push were part of this phase.

## 2026-06-27

### Security

- FOS-027B1 — private-beta blocker hardening pass 1. Made API auth fail-closed
  outside local: `enforce_fail_closed_auth` aborts backend startup when a
  non-local `APP_ENV` runs with auth disabled or without a configured API key
  (env-var names only in errors, never values). Added a shared frontend
  `safeHref` helper plus a `SourceLink` component so untrusted, server-provided
  URLs (evidence/source URLs, `external_result_url`) render as anchors only for
  http(s); `javascript:`/`data:`/`vbscript:`/malformed values render as
  non-clickable text. Removed stale `app/agents` bytecode and reconciled
  CLAUDE.md / SECURITY_BASELINE.md / README.md references to deleted LLM/agent
  code and a deleted boundary doc. No deploy, no push, no provider writes.

### Changed

- Bootstrapped the minimal private-beta workspace/owner context in the deployed
  Railway database through the supported operator workspace bootstrap API, then
  ran the full read-only deployed smoke successfully across health/auth,
  workspace read, GitHub connection status read, Company Brain read,
  operational work read, and deterministic transient briefing generation.
  Provider writes, selected repo live sync, ActionProposal execute, LLM, and
  real connectors remained disabled/not called; secret values and operational
  IDs are intentionally omitted.
- Ran the authenticated Railway private-beta setup/rehearsal: created the
  rehearsal project with backend, frontend, and managed Postgres services; Redis
  was skipped. Backend/frontend deployments reached success, Railway Postgres was
  migrated to Alembic head, backend health/frontend load/CORS/API auth behavior
  were verified, and read-only deployed smoke passed in health/auth-only mode.
- Updated the Railway runbook/templates with rehearsal findings: current Railway
  Railpack requires `RAILPACK_BUILD_CMD`/`RAILPACK_START_CMD`, and backend
  runtime `DATABASE_URL` must use the `postgresql+asyncpg` driver form while
  local operator migrations use the public Postgres URL only inside the
  subprocess environment.
- The earlier workspace-scoped deployed-smoke blocker was resolved by FOS-026C
  using the supported operator bootstrap API. Provider writes, LLM, real
  connectors, selected repo live sync, and ActionProposal execute remained
  disabled/not called. Secret values are intentionally omitted.

## 2026-06-26

### Added

- Added `docs/deploy/railway-private-beta.md`, selecting the Railway-only
  split-service private-beta dry-run target implied by the master playbook. The
  plan maps backend API, frontend web, managed Postgres, managed/deferred Redis,
  service commands, domain/CORS/API-base, env names, migration dry run, smoke
  dry run, rollback dry run, operator checklist, and later live-provider-smoke
  approval boundaries without provisioning or deploying.
- Added placeholder-only Railway backend, frontend, and smoke env templates under
  `docs/deploy/templates/`, plus hosting-doc safety tests for required sections,
  placeholder-only values, no secret-shaped values, no auto-deploy workflows,
  and no provider-write/sync commands.

- Added `docs/deploy/private-beta.md`, a manual private-beta deploy runbook for
  the split backend API process, frontend web process, managed Postgres, and
  managed/deferred Redis model. The runbook documents backend/frontend commands,
  migration verification, backup and rollback policy, required env names,
  CORS/API-base setup, GitHub connection boundaries, and read-only post-deploy
  smoke.
- Added deploy-doc safety tests covering required env names, required commands,
  DB/migration/rollback documentation, read-only smoke/provider-write
  boundaries, absence of secret-shaped values, and absence of auto-deploy
  workflow commands.

- Added FOS-025C frontend/full-stack deploy-readiness CI gates. The CI workflow
  now has separate backend and frontend jobs: backend keeps the existing secret
  scan, dependency sync, ruff, Alembic upgrade, and full pytest gates while
  explicitly running docs/smoke/CORS/CI contract tests; frontend runs `npm ci`,
  `npm test`, `npm run build`, `npm run typecheck`, and `npm run lint` from
  `web/`.
- Added CI deploy-readiness contract tests that assert frontend gates exist and
  the workflow does not include live smoke, selected repository sync,
  ActionProposal execute, provider-token setup, or provider secret usage.

- Added the FOS-025B private-beta deploy/smoke foundation: explicit backend
  CORS settings, placeholder-only env template, read-only private-beta smoke
  script, `make smoke`, and local/private-beta run documentation.
- The smoke script checks only safe health/auth/workspace/read-model endpoints
  plus deterministic manual briefing generation, and forbids ActionProposal
  execute, selected repository sync, provider-token setup, local-sync,
  normalize-local, post-execution-result sync, and provider write endpoints.
- Added focused tests for CORS config, smoke endpoint safety, no API-key output,
  placeholder-only env examples, and docs env-name coverage.

### Changed

- Added read-only selected repository sync controls to the product dashboard
  (`SelectedRepositorySyncControls`) near the existing GitHub sync, Company
  Brain, and operational work panels.
- The controls discover the GitHub connection id from the existing
  connection-status endpoint instead of hardcoding it, validate an explicit
  `owner/repo` repository name client-side (non-empty, single slash, no
  spaces), and call the existing selected issue and PR sync endpoints
  read-only, one explicit allowlisted repository at a time.
- Added typed frontend API helpers `syncSelectedRepositoryIssues`,
  `syncSelectedRepositoryPullRequests`, and a combined
  `syncSelectedRepositoryGitHubWork`, plus request/response types for selected
  issue and PR sync.
- The controls render missing-settings, missing-connection, invalid-input,
  per-action loading, success summaries (repositories synced; issues
  synced/open/closed; PRs synced/open/closed/merged; skipped PR-shaped issue
  records), backend allowlist/permission/generic errors, and empty/no-records
  states; they show explicit read-only / no-external-write copy and avoid raw
  JSON and private identifiers.
- A successful selected sync refreshes the Company Brain and GitHub operational
  work panels through the existing dashboard refresh signal; no backend
  contract change was required and no GitHub write is performed.
- Added read-only selected repository pull request sync under the GitHub
  workspace namespace:
  `/api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync`.
- Selected PR sync requires the explicit read-sync repository allowlist before
  token decrypt/provider reads, fetches only selected repositories with a
  read-only GitHub pulls client, and normalizes open/closed/merged PRs into
  canonical `SourceRecord` + `PullRequest` records through the existing GitHub
  normalization path.
- Selected PR sync keeps repository identity stable after selected issue sync,
  so the same `owner/repo` repository row is reused instead of creating a
  duplicate; PR read models also de-dupe by repository and PR number.
- Selected PR sync is covered with read-only provider mocks for the approved
  repository scope and performs no GitHub issue, PR, comment, merge, close, or
  other provider write.
- Added read-only selected repository issue sync under the GitHub workspace
  namespace:
  `/api/v1/workspaces/{workspace_id}/github/repositories/issues/sync`.
- Selected issue sync requires an explicit read-sync repository allowlist before
  token decrypt/provider reads, fetches only selected repositories, skips
  PR-shaped issue API records, and normalizes open/closed issues into canonical
  `SourceRecord` + `Task` records through the existing GitHub normalization
  path.
- Product GitHub issue read models now de-dupe alternate historical issue
  identifiers by repository and issue number so a real issue is not double
  counted in operational work or Company Brain.
- Selected issue sync was verified read-only against the approved smoke
  repository: one closed issue synced, open count stayed zero, ActionExecution
  receipt counts stayed unchanged, and no new GitHub writes occurred.
- Closed the approved smoke issue after explicit human approval and verified the
  closed state through the existing post-execution sync path.
- Closed-state sync updated canonical GitHub work records so operational work no
  longer counts the smoke issue as open, Company Brain sees the closed issue,
  and deterministic briefing remains evidence-backed.
- No additional GitHub issues were created and no comments, PRs, releases,
  labels, assignees, titles, bodies, repository settings, or other repositories
  were modified.
- Added a read-only post-execution sync route for executed GitHub issue
  `ActionProposal` receipts:
  `/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/sync-execution-result`.
- The post-execution sync path validates an executed/succeeded receipt, reads
  the provider issue through the encrypted GitHub connection, creates a local
  manual SyncJob, and reuses canonical GitHub normalization to upsert
  `SourceRecord` + `Task`.
- Post-execution sync was verified for the gated live GitHub smoke issue:
  operational work and Company Brain see the synced issue, deterministic
  briefing reflects the normalization evidence, and no duplicate external
  execution occurred.
- Manual live GitHub issue smoke succeeded through the gated `ActionProposal`
  execution path against an approved private smoke repository.
- Exactly one GitHub issue was created; receipt and durable audit are stored
  locally; external issue URL/id are intentionally omitted from public docs.
- No other repositories were modified, and the next step is explicit smoke issue
  closeout/cleanup approval.

## 2026-06-25

### Added

- Added a non-secret live GitHub write repository allowlist for approved issue
  execution: `FOS_GITHUB_WRITE_ALLOWED_REPOS`, with `FOS_GITHUB_SMOKE_REPO` as
  a single-repository alias.
- Added durable `execution_repository_not_allowed` audit events for missing or
  non-matching write allowlists before any token decrypt or provider call.
- Added gated live GitHub issue execution behavior over the existing approved
  `ActionProposal` executor: runtime write capability, explicit confirmation,
  valid GitHub payload/connection, evidence refs, duplicate receipt return, and
  mocked-provider tests.
- Added durable execution attempt audit events for confirmation received,
  execution start, success, failure, block, and duplicate receipt return.
- Added frontend receipt rendering for successful external issue id/url and
  explicit live-write confirmation copy in `ActionExecutionControls`.
- Added proposal-scoped `action_execution_events` plus migration
  `a2b3c4d5e6f7` for durable, sanitized execution preview/blocked-attempt audit
  records.
- Added idempotent action execution audit helpers and
  `/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/audit`
  with a local execution receipt/readiness view.
- Added frontend audit-trail reads so `ActionExecutionControls` displays
  persisted audit events, local receipt state, and timestamp fallback when no
  events exist.
- Added dry-run GitHub issue execution preview endpoint at
  `/api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/execution-preview`.
- Added typed frontend helpers for action execution preview and explicit execute
  requests under the existing workspace action proposal namespace.
- Added `ActionExecutionControls` for preview-only execution readiness, external
  execution disabled state, missing-evidence warnings, fallback audit/status
  history, and explicit connection+confirmation UI when backend capabilities
  allow live writes.
- Added backend/frontend tests for execution preview URL/body contracts,
  disabled execution capability, confirmation gating, audit visibility, and no
  raw provider payload rendering.
- Added typed frontend helpers for local ActionProposal list, create, approve,
  and reject routes under
  `/api/v1/workspaces/{workspace_id}/actions/proposals`.
- Added `ActionProposalsPanel` for product local approval workflow: proposal
  list, manual local proposal creation, local approve/reject buttons, status
  summary, proposal audit timestamps, backend warnings, and evidence drawer
  links.
- Added frontend tests for action proposal URL/body construction, local
  approve/reject calls, unsupported transition errors, loading/missing/empty/
  unsupported/error states, evidence refs, and no external-write claims.

### Changed

- Live GitHub issue execution now blocks unless the target repository is
  explicitly allowlisted; broad token scope and variable names such as
  `READONLY` are not trusted as safety boundaries.
- Earlier bounded setup against an approved private smoke repository target was
  blocked by GitHub permissions, so no smoke candidate was prepared in that run
  and no real issue was created then.
- Live GitHub issue execution remains disabled by default and was not manually
  smoke-tested; automated checks use mocked provider/client boundaries only.
- Repeated execute on an already-succeeded proposal now returns the existing
  receipt without calling the provider again.
- Preview and blocked execute paths now record/reuse local audit events without
  calling GitHub or overloading `ActionExecution`, legacy `audit_logs`, or
  retained `source_events`.
- Blocked `/execute` when `enable_write_actions=false`, so approval and preview
  cannot silently cross into live provider writes in default environments.
- Wired `web/app/actions` and dashboard action panels to the guarded execution
  preview surface while keeping live writes capability-gated.
- Wired `web/app/dashboard` and `web/app/actions` to the local ActionProposal
  approval workflow while keeping external execution disabled in the UI.

## 2026-06-24

### Added

- Added typed frontend helpers for the manual deterministic Founder Briefing
  endpoint at `/api/v1/workspaces/{workspace_id}/briefings/manual`.
- Added `BriefingPanel` and `EvidenceDrawer` to render manual briefing
  sections, returned evidence refs, source links only when provided, and
  explicit no-live-provider/no-AI/no-action-execution boundaries.
- Added frontend tests for briefing URL/body construction, loading/missing/
  empty/unsupported/error/success states, evidence buttons, evidence drawer
  details, and avoidance of fake briefing/source data.
- Added `GET /api/v1/workspaces/{workspace_id}/company-brain`, a read-only
  deterministic Company Brain endpoint over canonical GitHub repositories,
  issue/task records, pull requests, and `SourceRecord` source refs.
- Added a dashboard Company Brain panel showing evidence-backed GitHub state,
  summary counts, repositories, open issue/PR highlights, recent work, source
  refs, and explicit no-live-provider/no-AI capability status.
- Added backend and frontend tests for the Company Brain GitHub evidence state,
  including empty state, canonical summary, evidence/source refs, ignored
  retained `source_events`, and UI loading/missing/error states.
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

- Wired the dashboard and `/briefings` page to generate the existing manual
  deterministic Founder Briefing and inspect returned evidence refs.
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
