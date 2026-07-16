# FounderOS Roadmap

Status: roadmap is subordinate to the canonical control trio:
`../founderOS_MASTER_PLAYBOOK.md` (what), `../PROGRESS.md` (where), and
`DECISIONS.md` (why).

The current execution pointer is `../PROGRESS.md`: the local MVP foundations are
in place and Company World now combines bounded, sanitized Gmail evidence with
durable people/organization/affiliation/interaction profiles and explicit human
confirmation (DEC-073/DEC-074), while DEC-075 adds invite-only founder
enrollment, computed onboarding, explicit company selection, and a one-move
shell. DEC-076 completes the frontend-only spatial Company World board with
conservative affiliation placement and guided candidate resolution. DEC-077
makes the one-command loopback runtime the active operational target; full local
doctor/start/authenticated-browser/smoke/restore/stop acceptance passed on
2026-07-14. DEC-081 now makes the Living Headquarters loop the product direction:
`Штаб / Мир / Миссии`, with providers backstage as `Радары`. DEC-082 carries
that model through the full Living World and safe exact-profile navigation.
DEC-083 completes the Missions decision room around one active human decision,
a bounded loaded queue, evidence, consequences, and an explicit external gate.
DEC-084 establishes the isolated synthetic/runtime boundary for `/demo`; DEC-085
supersedes its presentation grammar with one minimalist desktop Living Command
Center, progressive-disclosure drawers, one decision modal, and a deterministic
contextual assistant. Mission-specific drill-down and state-following primary
actions now complete the reference loop without exposing the whole queue on the
surface. DEC-086 now fixes the promotion path: one workspace-scoped server-side
headquarters projection is now implemented locally as the shared, consistent
read boundary over real Company Brain, Company Map, Briefing, ActionProposal,
connector and membership state. It adds no migration/provider/LLM/write path;
LC-02 now implements the approved minimal command-center grammar in the
authenticated `/dashboard`: one server-ranked priority, three pulse metrics,
bounded queue/signals, progressive-disclosure drawers and an honest assistant
launcher all consume that contract without browser ranking or demo fixtures.
DEC-088 now completes LC-03: five server-computed onboarding steps, evidence and
role-aware next actions are part of the same Headquarters v2 snapshot, while a
compact modal replaces browser-derived readiness and the separate journey for
workspace users. DEC-089 now completes the bounded LC-05/LC-08 local decision
slice: exact entity disclosure fails closed, single local decisions are bound
to proposal/snapshot versions and idempotency, and an audit-backed receipt
survives a failed Headquarters refetch. Confirmed employee/customer renderers
are present, while their production mission relation projection remains
schema/data gated. The full phased acceptance ledger is
`LIVING_COMMAND_CENTER_CHECKLIST.md`. DEC-087 separately approves one
future modular Source Foundry intake/promotion plane — not one server per source
and not a second knowledge truth — after the real headquarters UI is accepted.
The reference still does not claim real provider or LLM readiness; a read-only
assistant query contract is the next product slice. The next external
gate remains one founder-approved scoped GitHub App read, not a hosted deploy.
External mutation and LLM narrative remain separate human-gated horizons. Docs
consolidation is complete; this roadmap is planning context, not the live task
source.

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
  `Briefing`, `BriefingItem`, `ActionProposal`, `ActionExecution`, proposal-scoped
  `ActionExecutionEvent`, `Person`, `Organization`, `Affiliation`, `Interaction`,
  and `CompanyWorldResolution` foundations exist.
- Auth/session foundations exist: a `sessions` table (ORM `UserSession`, stores
  only the sha256 token hash) and a `login_attempts` brute-force throttle table;
  account-active state reuses `User.status` (no `is_active`).
- Invite-only enrollment uses `founder_enrollment_invites`; only a SHA-256 token
  digest, expiry, and optional consumption/revocation receipts persist. TTL is
  capped at 168 hours; the raw fragment bearer never persists.
- Canonical `tasks` now have a partial unique index
  `uq_tasks_workspace_provider_external_id` and idempotent `ON CONFLICT` upserts
  across the GitHub sync path. Canonical `repositories` also have a
  workspace/provider/full_name unique guard for cross-path GitHub identity.
- Existing migrations are at one Alembic head/current: `b4d5e6f7a8c9`.
- Evidence refs are a repository invariant.
- `source_events` / `normalized_activity_items` / `ingested_events` are retained
  compatibility substrate; FOS-009 repointed workspace repository reads to
  canonical `repositories` first.

Missing:

- No further canonical model is required for the current local Company
  World path. Broader normalized entities and post-MVP graph models remain
  chunk-scoped rather than implied by the playbook vision.

Next step: the current schema and Company Map contract are sufficient for the
reviewed UX-02 snapshot, and the DEC-077 local lifecycle is accepted. The first
GitHub App real read remains a separate human-approved gate; physical substrate
drop remains later.

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
- GitHub App product-connect foundation exists: config/status reports safe
  readiness, DEC-052 chooses GitHub App installation as the product path, and
  `/api/v1/workspaces/{workspace_id}/github/connections/app-installation`
  records a workspace-scoped installation without provider calls or persisted
  installation tokens.
- Polling-only GitHub App live read sync exists in the backend:
  `/api/v1/workspaces/{workspace_id}/github/connections/app-installation/sync`
  mints a just-in-time installation token, reads explicitly requested
  installation repositories/issues/PRs, and persists through existing canonical
  normalization without storing the token or performing provider writes
  (DEC-053).
- `/github` renders each known repository with an adjacent explicit GitHub App
  read-only sync button over that endpoint; it keeps no browser secrets, has no
  bulk sync control, and shows no-write/token persistence boundaries.
- Tests verify mocked GitHub App synced data flows into Company Brain and
  persisted deterministic Briefings with evidence while another workspace cannot
  see the synced canonical state/evidence refs.
- Safe GitHub provider HTTP status/message/rate-limit details surface on live
  read errors without leaking authorization headers, tokens, or provider payload
  dumps.
- Selected repository issue sync exists for explicitly allowlisted repositories:
  `/api/v1/workspaces/{workspace_id}/github/repositories/issues/sync`.
- Selected repository PR sync exists for explicitly allowlisted repositories:
  `/api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync`.
- Company Brain repo-audit read model remains available and can bootstrap from
  `.local/repos.json` as an offline GitHub repository surface.
- Email+password login on server-side sessions exists:
  `POST /api/v1/auth/login|logout`, `GET /api/v1/auth/me`,
  `POST /api/v1/auth/change-password`, with `require_session` /
  `get_current_actor` (session-or-operator-key) auth and a DB login throttle.
- Invite-only founder enrollment exists at `POST /api/v1/auth/enroll`; it
  consumes an operator-issued one-time token and atomically creates the founder,
  workspace, owner membership, and normal browser session.
- Founder Briefing persistence exists: `POST .../briefings/manual` stores the
  deterministic briefing, and `GET .../briefings` / `GET .../briefings/{id}`
  expose workspace-scoped history.
- Local Jira/Gmail/Drive connector foundations exist as import/list APIs over
  sanitized canonical `SourceRecord`/`Task` rows, and internal Documents exist as
  workspace-scoped CRUD/search/version-history APIs with Company Brain and
  briefing integration. These paths are local-only and do not call providers.
- Normalized entities are exposed as a read-only Company Brain projection API
  (`GET .../company-brain/entities`) without a physical `NormalizedEntity`
  table.
- LLM paths are gated/off by default.

Missing:

- First human-approved real-provider read run.
- LLM briefing narrative over real connected data.
- Email-delivered invites / SSO / password reset. Founder and teammate one-time
  links exist locally, but external delivery is still deferred.
- Broader multi-repository issue/PR sync beyond explicitly approved repository
  scope.

Next step: follow `../PROGRESS.md`; configure the founder-owned GitHub App and
approve one explicit scoped read-only sync. This remains the main external gate
before LLM briefing work.

Definition of Done:

- Services are unit-tested.
- Provider logic is isolated from routes.
- No secrets in logs or browser payloads.
- Errors are typed/sanitized.
- External writes remain approval-gated.

## Phase 3 - Frontend Core

Current status: `web/` is a Living Headquarters shell behind a server-side
session. Invite-only `/start` and the in-Headquarters computed onboarding cover
first run; `/dashboard` is `Штаб` with one evidence-aware mission, a compact
Company World, current-snapshot signals, and a world pulse. Workspace context
comes from memberships and requires an explicit choice when ambiguous.

Done:

- Legacy static `/ui` has been removed; `web/` is the only product frontend
  shell to extend.
- `/login`, session client, `AuthGate`, and Settings→account/change-password
  gate the app behind email+password. `/start` consumes an invite; for an account
  with a workspace, `/onboarding` enters the real Headquarters and opens the
  five-step server-computed modal. Required readiness, evidence and next action
  come from the same snapshot; zero-workspace recovery remains separate. Founder
  and teammate setup bearers are fragment-only and cleared after capture. The
  old browser operator-key/owner-email config remains removed.
- Shared shell/status copy is Russian through `web/lib/messages.ts`; computed
  setup copy stays with the Headquarters modal and zero-workspace recovery page
  (no i18n framework yet).
- Company Brain has a product dashboard panel backed by canonical GitHub
  repositories/tasks/PRs and source refs.
- Next.js + TypeScript, a typed API client, and session-derived workspace context
  exist. The primary navigation has three everyday zones (`Штаб / Мир / Миссии`);
  provider routes and settings remain backstage as `Радары / Настройки`, with a
  compact desktop rail and three-item mobile bottom navigation.
- `/dashboard` derives one mission, a real-data mini-world, a current evidence
  snapshot, and truthful metrics from canonical source records, proposed actions,
  Company Map candidates, briefings, team membership, connectors, and role.
  Missing reads, empty states, declared proposal refs, truncated windows, and
  server-resolved Company Map evidence remain distinct. It does not invent a
  since-last-visit delta, health score, trend, or autonomous action.
- `/briefings` surfaces deterministic manual briefing history with returned
  evidence refs in a frontend evidence drawer.
- `/briefings` persists generated deterministic briefings and lists/reopens
  briefing history.
- `/actions` surfaces local ActionProposal list/create/approve/reject plus
  guarded execution preview/audit controls.
- `/actions` renders persisted execution audit events and local receipt/readiness
  state for preview and blocked execution attempts.
- `/actions` exposes live GitHub issue execution controls only when backend
  capabilities enable them, requires explicit confirmation, and renders external
  issue receipt links only from backend success.
- DEC-083 recomposes those contracts into one decision room: one mixed-status
  loaded window (up to 100), one compact queue, and one active console for the
  selected proposal. Loaded-window metrics remain stable under local filters;
  evidence, approve/reject, preview, and history never leak across mission
  selection. Pending provider work locks mission, workspace, and global shell
  navigation; stale cross-workspace responses are ignored, and a sanitized
  successful outcome stays pinned through refresh. A separate audit-history
  read failure cannot downgrade that confirmed result into a retryable action
  error. External preview remains
  explicit and bulk review adds a separate consequence check. No backend,
  schema, RBAC, provider/write, or LLM boundary changes.
- `/connectors` surfaces the MVP connector registry (GitHub/Jira/Gmail/Drive)
  from `GET /api/v1/workspaces/{workspace_id}/connectors`, with local
  connection counts and read-only/no-provider-call/no-secret-read boundaries.
- `/jira`, `/gmail`, and `/drive` provide local-only import/list product paths;
  `/documents` provides internal document CRUD/search/version history; and
  `/company-brain` provides a dedicated Company Brain + normalized-entities
  view.
- `/company-brain` leads with the spatial Company World board (DEC-073/074/076):
  the founder's company is central, while team, confirmed network, and discovery
  candidates occupy distinct contours. A confirmed person is nested under an
  organization only when exact durable affiliation fields agree and a human-
  authored relationship exists; otherwise the person remains standalone.
  Similar names/domains and candidate organization keys are not treated as
  facts. The focused inspector shows profile-local touchpoints and keeps
  evidence plus technical capability/window/warning disclosures collapsed until
  requested. Resolution asks one plain-language question at a time while
  preserving member+/viewer, candidate-version, idempotency, and server-evidence
  contracts. The board adds no backend API, migration, provider call/write, or
  LLM path. Local acceptance is complete: 272 frontend tests plus
  typecheck/lint/build, 537 backend tests plus Ruff/Alembic, and desktop
  1024/1280 px / mobile 390×844 browser QA without overlap, overflow, console
  warnings or console errors.
- DEC-082 promotes that board into the full Living World operating surface: one
  compact real-metric command bar, one current candidate rail, local zone
  filters, the spatial scene, and a sticky/inline contextual profile. `Штаб`
  selections and evidenced candidate missions use opaque workspace-resolved
  selectors to open an exact profile without placing raw email/domain-shaped
  Company Map keys in the URL. Stale or foreign selectors resolve to no entity.
  Closed Company Brain/entity details mount lazily. This remains frontend-only
  and preserves the existing Company Map/RBAC/evidence contracts.
- Product controls mirror backend roles: source setup/import/sync and action
  review/execution require owner/admin; briefing generation and local action
  creation require member+; Company World resolution requires member+; viewer
  retains evidence-backed read access only.
- `/github` shows GitHub App real-read readiness over already-loaded local
  state, including env/installation/repo-surface blockers, without starting a
  provider call.
- Frontend typecheck/build/lint scripts exist and pass.

Missing:

- Email delivery for founder/team invites, password reset, and SSO. Founder
  enrollment, local teammate provisioning, `/settings` team UI, and one-time
  `/setup-password` links exist without external delivery.
- Automated browser/product E2E coverage; the LOCAL-01 authenticated manual
  browser acceptance has passed.
- Selected repository issue and PR sync controls remain on source-focused
  routes rather than the default «Сегодня» screen; each syncs one explicit
  allowlisted repository without external writes.
- First GitHub App real read run and email/SSO invite delivery remain missing.
  Live Jira/Gmail/Drive provider OAuth/sync remains deferred beyond the
  local-import MVP surface.

Next step: follow `../PROGRESS.md`. Add the deterministic workspace-scoped
read-only assistant contract over the same Headquarters service and snapshot,
with normalized citations and no LLM, persistence or mutation. Keep one
explicit founder-approved GitHub read as the next external gate; keep provider
reads human-gated and never add browser-stored operator credentials. Durable
business-profile authoring and external execution remain separate gated work.

Definition of Done:

- `web/` app runs locally.
- A founder can enroll by one-time link and understand the guided real-state
  onboarding without terminal/DB knowledge after the link is issued.
- The user sees one unambiguous company and one next move; the three everyday
  zones and backstage radar/settings access work on desktop and mobile.
- Unknown/empty/RBAC states are honest and actionable.
- Frontend lint/test/build checks exist and pass.

## Phase 4 - GitHub-First E2E

Current status: guarded product flow includes the live GitHub issue execution
code path behind runtime config, explicit confirmation, evidence policy,
idempotent receipt, and durable audit. A prior manual live GitHub issue smoke
proved the write path; the current missing live step is the first GitHub App
real-provider read run for the product installation path.

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
- Manual smoke previously created exactly one approved GitHub issue, synced the
  execution result back into canonical state, and closed/synced that smoke issue
  after explicit human approval. Private issue URLs and identifiers stay out of
  public docs.
- `/github` now surfaces first-real-read readiness from local state and still
  exposes only explicit per-repository read sync controls, not a bulk sync.

Missing:

- First approved real-provider read run.
- Physical retained-substrate drop after the canonical repository read path is
  stable.
- Multi-repository selected sync from the product UI beyond one explicit
  repository at a time. External issue/PR URLs and local workspace/proposal/
  connection/evidence identifiers are intentionally omitted from public docs.

Next step: prepare the first GitHub App real read run with strict
workspace/installation/repository scoping before adding LLM briefing intelligence.

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
- More live-provider failure UX after the first real GitHub App read run.
- Browser/product E2E coverage for the MVP web app.

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
- FOS-025B historically added a read-only hosted-smoke script. DEC-077 now adds
  `make local-smoke` as the active health/readiness gate without provider writes.
- FOS-025C added frontend deploy-readiness gates to CI: `npm test`, build,
  typecheck, and lint, plus backend docs/smoke/CORS/CI contract tests.
- Current local frontend tests cover the GitHub product connect/readiness UI,
  action readiness, normalized entities, local connectors, documents, and
  dashboard readiness surfaces.

Missing:

- Automated browser/product GitHub-first E2E tests. The manual local product
  lifecycle and authenticated five-zone browser pass are complete.

Next step: add focused tests with each implementation slice; do not add broad
test scaffolding before the relevant feature exists.

Definition of Done:

- Backend tests green.
- Frontend lint/test/build green.
- GitHub E2E covered.
- AI validation covered.
- Action approval path covered.

## Phase 7 - Local Operation

Current status: DEC-077 makes the loopback local runtime the active MVP target.
Historical hosted rehearsal evidence is retained below, but it is not the
current operating path.

Done:

- `make local-doctor`, `make local`, `make local-smoke`, `make local-backup`, and
  `make local-stop` define the supported local lifecycle.
- Docker Compose PostgreSQL exists; Redis is optional for the current
  synchronous runtime.
- `docs/operations/local-runtime.md` is the canonical operator runbook.
- Backend CI shape exists.
- Live doctor/start/same-origin smoke/returning login/onboarding/five-zone
  browser/backup/stop acceptance passed on the founder's machine.
- A private PostgreSQL/raw bundle passed checksum, same-major isolated restore,
  Alembic/count, raw-digest and credential-decryptability proof.
- Graceful `SIGHUP` cleanup and verified orphan cleanup after a simulated
  supervisor crash passed without deleting local data.

Historical hosted rehearsal evidence (retained as history; target-specific
runbooks/templates were removed by DEC-077 and remain recoverable from git):

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
  Argon2id, DB login throttle), plus one-time hash-only founder enrollment.
  Secret encryption is fail-closed outside local
  (`FOUNDEROS_SECRET_ENCRYPTION_KEY`).
- Sanitized request logging is in place for application request lines
  (method/path/status/duration only) with `FOUNDEROS_LOG_LEVEL`/`LOG_LEVEL`.

Missing:

- First human-approved GitHub App live read sync after local acceptance.
- Any future hosted target, custom domain, worker, monitoring, or public
  multi-worker security boundary; all are deferred to a new decision.

Next step: configure the founder-owned GitHub App and approve one explicit
scoped read-only sync. Do not stop or delete any older hosted resource without a
separate explicit human approval after restore proof.

Definition of Done:

- `make local` reaches healthy loopback backend/frontend endpoints.
- Login/enrollment and guided onboarding work locally.
- The local GitHub surface and readiness guidance work; the first real GitHub
  App connect and scoped provider sync remain separate human-approved gates.
- Briefing works.
- Sanitized logs are visible.
- Logical backup and restore path is proven.
- `make local-stop` preserves `.local/`, the database volume, and backups.

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
