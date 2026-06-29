# FounderOS Roadmap

Status: roadmap is subordinate to the canonical control trio:
`../founderOS_MASTER_PLAYBOOK.md` (what), `../PROGRESS.md` (where), and
`DECISIONS.md` (why).

The current execution pointer is `../PROGRESS.md`: CHUNK 8 hardening is closed
(FOS-027B2 + sync-layer idempotency), email+password / server-side-session login
is built, and deterministic Founder Briefings now persist history. The next
horizon is real connected data (GitHub product connect/live sync) before an LLM
briefing narrative. Docs consolidation is complete; this roadmap is planning
context, not the live task source.

## Phase 0 - Project Setup

Current status: done.

Done:

- Documentation inventory was captured in `docs/_audit/DOCS_AUDIT.md`.
- Canonical control docs are in place and navigated from `docs/README.md`.
- Historical duplicate docs were removed in DEC-029/DEC-031 cleanup; recovery is
  through git history / tag `pre-purge-20260624`.
- `docs/CHANGELOG.md` exists.

Missing:

- None for the current MVP path.

Next step: follow `../PROGRESS.md`; do not treat this roadmap as the live task
queue.

Definition of Done:

- Current control docs exist.
- `docs/DECISIONS.md`, `docs/ROADMAP.md`, `docs/TODO.md`,
  `docs/POST_MVP.md`, and `docs/CHANGELOG.md` exist.
- `docs/README.md` is the current docs entry.
- `git diff --check` passes.
- Docs tests pass if available.

## Phase 1 - Database / Core Models

Current status: spine-subset done; remaining canonical models are chunk-scoped.

Done:

- Canonical `User`, `Workspace`, `Membership`, `IntegrationConnection`,
  `SyncJob`, `SourceRecord`, `EvidenceRef`, `Repository`, `PullRequest`, `Task`,
  `Briefing`, `BriefingItem`, `ActionProposal`, `ActionExecution`, and proposal-scoped
  `ActionExecutionEvent` audit foundations exist.
- Auth/session foundations exist: a `sessions` table (ORM `UserSession`, stores
  only the sha256 token hash) and a `login_attempts` brute-force throttle table;
  account-active state reuses `User.status` (no `is_active`).
- Canonical `tasks` now have a partial unique index
  `uq_tasks_workspace_provider_external_id` and idempotent `ON CONFLICT` upserts
  across the GitHub sync path.
- Existing migrations are at one Alembic head/current: `e7f8a9b0c1d2` (after the
  task-uniqueness, `ingested_events`-drift, sessions/login-throttle, and
  briefing-persistence migrations).
- Evidence refs are a repository invariant.
- `source_events` / `normalized_activity_items` / `ingested_events` are retained
  compatibility substrate; FOS-009 repointed workspace repository reads to
  canonical `repositories` first.

Missing:

- `NormalizedEntity` and related generalized entity tables after the GitHub
  spine proves the need.
- Person ambiguity remains open as ASK-1.

Next step: GitHub product connect/live sync identity work; physical substrate
drop remains a later migration/cleanup task.

Definition of Done:

- Current models are mapped to master canonical models.
- Reuse/adapt/new decisions are explicit before migrations.
- No plaintext token fields are introduced.
- Future migrations have focused tests.

## Phase 2 - Backend Core

Current status: backend spine is green for local/mocked flow; product/live flow
is still incomplete.

Done:

- FastAPI app with modular routes and services.
- Workspace/operator auth helpers, identity foundation, GitHub connection,
  repository read, manual sync job, local normalization, canonical repository
  persistence, canonical issue/PR persistence, briefing v0, action approval,
  and guarded mocked GitHub issue execution.
- Operational GitHub work read model exists for canonical issues/PRs:
  `/api/v1/workspaces/{workspace_id}/github/operational-work`.
- Workspace-scoped Company Brain read model exists for deterministic canonical
  GitHub repository/work/evidence state:
  `/api/v1/workspaces/{workspace_id}/company-brain`.
- Selected repository issue sync exists for explicitly allowlisted repositories:
  `/api/v1/workspaces/{workspace_id}/github/repositories/issues/sync`.
- Selected repository PR sync exists for explicitly allowlisted repositories:
  `/api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync`.
- Company Brain repo-audit read model remains available.
- Email+password login on server-side sessions exists:
  `POST /api/v1/auth/login|logout`, `GET /api/v1/auth/me`,
  `POST /api/v1/auth/change-password`, with `require_session` /
  `get_current_actor` (session-or-operator-key) auth and a DB login throttle.
- Founder Briefing persistence exists: `POST .../briefings/manual` stores the
  deterministic briefing, and `GET .../briefings` / `GET .../briefings/{id}`
  expose workspace-scoped history.
- LLM paths are gated/off by default.

Missing:

- Full GitHub OAuth/product connect flow.
- Live GitHub OAuth/product sync execution path.
- LLM briefing narrative over real connected data.
- Multi-user / teammate provisioning beyond the single seeded founder.
- Broader multi-repository issue/PR sync beyond explicitly approved repository
  scope.

Next step: follow `../PROGRESS.md`; GitHub product connect/live sync should
precede LLM briefing work because the workspace is otherwise mostly empty.

Definition of Done:

- Services are unit-tested.
- Provider logic is isolated from routes.
- No secrets in logs or browser payloads.
- Errors are typed/sanitized.
- External writes remain approval-gated.

## Phase 3 - Frontend Core

Current status: the `web/` shell is now gated behind a `/login` page and a
server-side session; the GitHub-first dashboard/briefing/action surfaces are
wired through guarded local contracts and workspace is derived from the session.
User-facing copy is Russian via a central message catalog.

Done:

- Legacy static `/ui` has been removed; `web/` is the only product frontend
  shell to extend.
- A `/login` page (`web/app/login/page.tsx`) plus an `AuthGate` redirect, a
  session client (`web/lib/auth.ts`/`session.ts`), and a Settings→account /
  change-password page gate the app behind email+password login; the old
  operator-key/owner-email browser config (`web/lib/config.ts`) was removed and
  workspace is derived from the session.
- All user-facing copy is centralized in `web/lib/messages.ts` (Russian; no i18n
  framework).
- Company Brain has a product dashboard panel backed by canonical GitHub
  repositories/tasks/PRs and source refs.
- Minimal Next.js + TypeScript app exists in `web/`.
- App shell, sidebar, MVP placeholder pages, session-derived workspace context,
  and a typed API client foundation exist.
- Dashboard reads canonical GitHub operational work from the backend and shows
  issue/task and PR sections with open/all/closed/merged filters.
- Dashboard exposes honest GitHub local-sync controls over existing backend
  contracts and does not claim live OAuth/provider execution.
- Dashboard surfaces deterministic Company Brain state with summary counts,
  repositories, open issue/PR highlights, recent work, and source refs.
- Dashboard and `/briefings` surface deterministic manual briefing with returned
  evidence refs in a frontend evidence drawer.
- `/briefings` persists generated deterministic briefings and lists/reopens
  briefing history.
- Dashboard and `/actions` surface local ActionProposal list/create/approve/
  reject plus guarded execution preview/audit controls.
- `/actions` renders persisted execution audit events and local receipt/readiness
  state for preview and blocked execution attempts.
- `/actions` exposes live GitHub issue execution controls only when backend
  capabilities enable them, requires explicit confirmation, and renders external
  issue receipt links only from backend success.
- Frontend typecheck/build/lint scripts exist and pass.

Missing:

- Tailwind/shadcn or final product UI system.
- Self-serve workspace onboarding / multi-user invite (today the single founder
  is seeded via `scripts/create_admin_user.py`).
- Browser/product E2E coverage.
- Selected repository issue and PR sync now have read-only product UI controls
  in the dashboard (`SelectedRepositorySyncControls`), syncing one explicit
  allowlisted repository at a time without external writes.
- GitHub product connect/onboarding and multi-user invites remain missing.

Next step: keep product UI honest while GitHub connect/live sync is added; do
not add browser-stored operator credentials.

Definition of Done:

- `web/` app runs locally.
- User can navigate through the MVP shell.
- Connector cards are visible.
- Empty states are helpful.
- Frontend lint/test/build checks exist and pass.

## Phase 4 - GitHub-First E2E

Current status: guarded product flow includes the live GitHub issue execution
code path behind runtime config, explicit confirmation, evidence policy,
idempotent receipt, and durable audit. Automated tests use mocked provider
execution; manual live external-write smoke is still missing.

Done:

- Some GitHub read-only/evidence/source pieces exist.
- Repository source inventory and repo audit foundations exist.
- Provider boundaries are guarded by default.
- GitHub MVP integration path decision is documented as a hybrid staged path.
- Workspace-scoped GitHub repositories read API exists over the local
  source/evidence inventory bridge.
- Workspace-scoped GitHub connection list/status/detail contract exists over
  `IntegrationConnection`.
- Operator-protected provider-token bridge can create/update encrypted GitHub
  `IntegrationConnection` records without live provider calls.
- Manual GitHub SyncJob record API can create/list/detail queued local sync
  intents without live provider calls or worker execution.
- Local GitHub normalization can transform repository inventory into
  founderOS-compatible projection output and, when explicitly requested, persist
  repositories into canonical `source_records`/`repositories` without live sync.
- Product dashboard controls can run the supported local GitHub normalization
  path, show missing/unsupported/error/success states, and refresh canonical
  operational work after success.
- Dashboard UI reads canonical GitHub operational work and displays synced
  issues/tasks plus pull requests from the FOS-009 backend path.
- Company Brain dashboard panel reads canonical GitHub repositories, issue/task
  records, pull requests, and source refs without reading retained
  `source_events` as primary truth.
- Manual Founder Briefing v0 can generate and persist a deterministic,
  evidence-aware briefing from local workspace GitHub signals.
- Product dashboard and `/briefings` page can generate that manual briefing,
  inspect returned evidence refs in a frontend evidence drawer, and reopen
  persisted briefing history.
- Local ActionProposal approval foundation can store, approve, and reject
  workspace-scoped proposals without external execution.
- Product dashboard and `/actions` page can list, create, approve, and reject
  local ActionProposal records with evidence refs and no external execution.
- Approved GitHub issue proposals can execute through the guarded backend path
  with local `ActionExecution` tracking.
- Product dashboard and `/actions` page can preview approved GitHub issue
  execution readiness, inspect persisted proposal-scoped audit events and local
  receipt/readiness state, and keep live execution disabled unless backend
  capability explicitly enables it.
- Approved GitHub issue proposals can reach the existing GitHub issue executor
  only after strict gates pass; successful mocked execution records
  `ActionExecution` receipt plus durable success audit, and duplicate execute
  returns the existing receipt without another provider call.
- Backend E2E smoke coverage exercises the GitHub-first path from workspace
  bootstrap through mocked approved issue execution.

Missing:

- Full GitHub OAuth implementation path.
- Actual GitHub sync execution through the product flow.
- Physical retained-substrate drop after the canonical repository read path is
  stable.
- Multi-repository selected sync from the product UI beyond one explicit
  repository at a time. External issue/PR URLs and local workspace/proposal/
  connection/evidence identifiers are intentionally omitted from public docs.

Next step: implement GitHub product connect/live sync with strict
workspace/installation scoping before adding LLM briefing intelligence.

Definition of Done:

- User connects GitHub through UI.
- Sync completes.
- Data is visible in Dashboard and Company Brain.
- Briefing is generated with evidence.
- Approved action creates a GitHub issue.
- External result is visible and audited.

## Phase 5 - Edge Cases & Polish

Current status: partially ahead of schedule in backend/operator surfaces.

Done:

- Some guarded error handling, retries, source receipts, source diagnostics,
  and stale/provenance labels exist.

Missing:

- Edge-case handling tied to the GitHub-first E2E.
- Token-expired handling in the product flow.
- Action failure UI in the product frontend.
- Filters/search/stale labels for the MVP web app.

Next step: polish only the real connected-data path as it lands; do not polish
fixture-only empty states into false product readiness.

Definition of Done:

- No dead-end screens in the GitHub-first flow.
- User understands sync/action failures.
- Retries are possible and safe.
- Evidence is inspectable from every factual claim.

## Phase 6 - Testing

Current status: strong backend coverage, incomplete product/E2E coverage.

Done:

- Full backend test suite passed during the audit.
- Lint and migration checks passed during the audit.
- Guard/evidence tests exist.
- GitHub-first backend E2E smoke test covers the local API path with mocked
  external provider execution.
- FOS-025B added a read-only private-beta smoke script plus `make smoke` for
  health/auth/workspace/read-model checks without provider writes.
- FOS-025C added frontend deploy-readiness gates to CI: `npm test`, build,
  typecheck, and lint, plus backend docs/smoke/CORS/CI contract tests.

Missing:

- Browser/product GitHub-first E2E tests.
- Deployed/full-stack smoke after auth-session deployment.
- Manual QA checklist for MVP.

Next step: add focused tests with each implementation slice; do not add broad
test scaffolding before the relevant feature exists.

Definition of Done:

- Backend tests green.
- Frontend lint/test/build green.
- GitHub E2E covered.
- AI validation covered.
- Action approval path covered.

## Phase 7 - Deployment

Current status: private-beta Railway rehearsal environment exists and deployed
read-only smoke passes; broader beta still needs production auth/GitHub
onboarding/custom-domain hardening.

Done:

- Local dev startup path exists.
- Docker Compose Postgres/Redis exists.
- Backend CI shape exists.
- FOS-025B added an explicit private-beta env-name contract, backend CORS
  config, placeholder-only `.env.example`, and read-only `make smoke`.
- FOS-025C added a CI frontend deploy-readiness job and explicit offline
  docs/smoke/CORS/CI contract checks.
- FOS-025D added `docs/deploy/private-beta.md`, a manual split-service deploy
  runbook with migration, backup, rollback, CORS/API-base, env-name, and smoke
  procedures.
- FOS-025E selected the Railway-only split-service dry-run target and added
  `docs/deploy/railway-private-beta.md` plus placeholder-only env templates.
- FOS-026B created the Railway rehearsal project with backend, frontend, and
  managed Postgres; Redis remained deferred.
- FOS-026C bootstrapped the minimal private-beta workspace/owner context and
  passed full read-only deployed smoke with provider writes, selected repo live
  sync, ActionProposal execute, LLM, and real connectors disabled/not called.
- FOS-027B1 hardened two private-beta blockers: API auth is now fail-closed
  outside local (startup aborts when a non-local `APP_ENV` runs without auth or
  a key), and untrusted server-provided URLs render through `safeHref`/
  `SourceLink` so only http(s) links are clickable (`javascript:`/`data:`
  values are rendered as text).
- Production auth is decided and built: email+password login on server-side,
  revocable sessions (httpOnly first-party cookie via a same-origin proxy,
  Argon2id, DB login throttle). Secret encryption is fail-closed outside local
  (`FOUNDEROS_SECRET_ENCRYPTION_KEY`).

Missing:

- First production deploy of the auth phase (the Railway rehearsal predates it);
  founder account provisioning + `FOUNDEROS_API_PROXY_TARGET` wiring in prod.
- GitHub OAuth/onboarding path for private-beta users.
- Custom domain decision and setup.
- Worker service if/when queue runtime exists.
- Broader beta monitoring/alerting and backup verification.

Next step: first auth-session production deploy/handoff, then GitHub
connect/live sync; keep deploy manual and smoke-gated.

Definition of Done:

- Production URL works.
- Login works.
- GitHub connect works.
- Sync works.
- Briefing works.
- Logs are visible.
- Rollback path exists.

## Phase 8 - Post-launch

Current status: many post-MVP/operator pieces already exist but should remain
frozen.

Done or partially present:

- Telegram/manual pilot.
- Share packs/investor view.
- Jira planning/dry-run surfaces.
- Second opinion and advanced diagnostics.
- Role-like/operator read models.

Missing:

- Productized post-launch expansion after MVP validation.
- Usage-based prioritization.

Next step: do not expand until GitHub-first MVP E2E is complete and used.

Definition of Done:

- MVP is launched.
- GitHub-first flow is stable.
- Expansion item has a real usage case.
- New surface reuses evidence_refs, approval gates, and source-of-truth rules.
