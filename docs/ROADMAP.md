# FounderOS Roadmap

Status: roadmap is subordinate to the canonical control trio:
`../founderOS_MASTER_PLAYBOOK.md` (what), `../PROGRESS.md` (where), and
`DECISIONS.md` (why).

The current execution pointer is `../PROGRESS.md`: CHUNK 8 / FOS-025F after
FOS-025E Railway hosting dry-run preparation. Docs consolidation is complete;
this roadmap is planning context, not the live task source.

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

Next step: follow `../PROGRESS.md` for human-approved manual hosting setup/dry deploy rehearsal, or production auth/GitHub onboarding hardening before deploy.

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
  `ActionProposal`, `ActionExecution`, and proposal-scoped
  `ActionExecutionEvent` audit foundations exist.
- Existing migrations are at one Alembic head/current: `a2b3c4d5e6f7`.
- Evidence refs are a repository invariant.
- `source_events` / `normalized_activity_items` / `ingested_events` are retained
  compatibility substrate; FOS-009 repointed workspace repository reads to
  canonical `repositories` first.

Missing:

- Persistent `Briefing` / `BriefingItem`.
- `NormalizedEntity` and related generalized entity tables after the GitHub
  spine proves the need.
- Person ambiguity remains open as ASK-1.

Next step: briefing UI and evidence drawer; physical substrate drop remains a
later migration/cleanup task.

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
- LLM paths are gated/off by default.

Missing:

- Full GitHub OAuth/product connect flow.
- Live GitHub OAuth/product sync execution path.
- Persistent briefing models.
- Broader multi-repository issue/PR sync beyond explicitly approved repository
  scope.

Next step: follow `../PROGRESS.md`; selected repository sync UI controls are now
exposed in the product dashboard (FOS-024).

Definition of Done:

- Services are unit-tested.
- Provider logic is isolated from routes.
- No secrets in logs or browser payloads.
- Errors are typed/sanitized.
- External writes remain approval-gated.

## Phase 3 - Frontend Core

Current status: minimal master frontend shell exists and the GitHub-first
dashboard/briefing/action surfaces are wired through guarded local contracts.

Done:

- Legacy static `/ui` has been removed; `web/` is the only product frontend
  shell to extend.
- Company Brain has a product dashboard panel backed by canonical GitHub
  repositories/tasks/PRs and source refs.
- Minimal Next.js + TypeScript app exists in `web/`.
- App shell, sidebar, MVP placeholder pages, browser-local operator settings,
  and typed API client foundation exist.
- Dashboard reads canonical GitHub operational work from the backend and shows
  issue/task and PR sections with open/all/closed/merged filters.
- Dashboard exposes honest GitHub local-sync controls over existing backend
  contracts and does not claim live OAuth/provider execution.
- Dashboard surfaces deterministic Company Brain state with summary counts,
  repositories, open issue/PR highlights, recent work, and source refs.
- Dashboard and `/briefings` surface deterministic manual briefing with returned
  evidence refs in a frontend evidence drawer.
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
- Login page.
- Workspace onboarding.
- Browser/product E2E coverage.
- The first human-gated live external write proof has been read back into
  canonical product state and closed after explicit human approval.
- Selected repository issue and PR sync now have read-only product UI controls
  in the dashboard (`SelectedRepositorySyncControls`), syncing one explicit
  allowlisted repository at a time without external writes.

Next step: extend selected sync UI to multiple allowlisted repositories without
adding external writes (after explicit human approval of additional repos).

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
- Manual Founder Briefing v0 can return a deterministic, transient,
  evidence-aware briefing from local workspace GitHub signals.
- Product dashboard and `/briefings` page can generate that manual briefing and
  inspect returned evidence refs in a frontend evidence drawer.
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

Next step: read-only product UI controls for selected repository issue+PR sync
shipped in FOS-024; extend to multi-repository selected sync next.

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
- Evidence drawer in the product frontend.
- Action failure UI in the product frontend.
- Filters/search/stale labels for the MVP web app.

Next step: wait until Phase 4 has a working E2E, then polish the actual path
users run.

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
- Deployed/full-stack smoke run.
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

Missing:

- Production auth/session decision.
- GitHub OAuth/onboarding path for private-beta users.
- Custom domain decision and setup.
- Worker service if/when queue runtime exists.
- Broader beta monitoring/alerting and backup verification.

Next step: harden production auth/GitHub onboarding and private-beta operator
handoff before broader beta use.

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
