# FounderOS TODO

Status: near-term task list only. This file intentionally excludes broad
post-MVP ideas.

Every implementation task must follow `AGENTS.md`: short task prompt, scoped
files, no unrelated edits, and focused checks first.

## Current Checkpoint

- Docs consolidation active: canonical trio added, audit report committed, and
  old documentation generations are being archived under `docs/_archive/`.
- FOS-AUD-04: done - docs/test hygiene unblocked before DB work.
- FOS-DB-02: done - User, Workspace, and Membership identity foundation added.
- FOS-DB-03: done - IntegrationConnection and SyncJob foundation added.
- FOS-BE-01: done - workspace-aware operator compatibility contract added.
- FOS-GH-01: done - hybrid GitHub MVP path decision documented.
- FOS-GH-02: done - workspace-scoped GitHub repositories read API added.
- FOS-GH-03: done - workspace-scoped GitHub connection contract added.
- FOS-GH-04: done - operator-protected GitHub provider-token bridge added.
- FOS-GH-05: done - manual GitHub SyncJob record API added without live sync.
- FOS-GH-06: done - local GitHub normalization projection added for manual SyncJobs.
- FOS-BRF-01: done - deterministic transient manual Founder Briefing v0 added.
- FOS-ACT-01: done - local ActionProposal approval API foundation added without execution.
- FOS-ACT-02: done - approved GitHub issue proposals can execute through a guarded endpoint.
- FOS-E2E-01: done - GitHub-first backend E2E smoke flow covered with local mocks.
- FOS-FE-01: done - minimal Next.js MVP shell scaffolded in `web/`.
- Next task: FOS-FE-02 - Wire frontend to backend GitHub-first flow.

## FOS-AUD-02 - Checkpoint/scope split current dirty tree

Goal: make the current dirty tree reviewable before any new implementation.

Likely files:

- `docs/_audit/DOCS_AUDIT.md`
- `docs/_archive/MANIFEST.md`
- Canonical docs only; no application code edits.

Acceptance criteria:

- Docs-only consolidation files are isolated from application changes.
- No useful working code is deleted.
- Post-MVP surfaces are marked FREEZE/POST_MVP, not removed.

Checks to run:

- `git status --short`
- `git diff --check`
- Docs tests if available.

## FOS-DB-01 - Data-model reconciliation spec

Goal: map the current DB model to the canonical master playbook model before
creating migrations.

Likely files:

- `docs/data-model.md`
- `docs/DECISIONS.md`
- Possibly a new docs-only reconciliation note.

Acceptance criteria:

- Existing tables are mapped to canonical playbook concepts.
- Reuse/adapt/new-table decisions are explicit.
- Missing canonical models are listed.
- No migrations or application code changes in this task.

Checks to run:

- `git diff --check`
- Docs tests if available.

## FOS-DB-02 - Add User/Workspace/Membership models

Status: done.

Goal: add the canonical identity and workspace foundation required by the
master playbook.

Likely files:

- `app/db/*`
- `migrations/versions/*`
- Focused model tests.
- Relevant docs update.

Acceptance criteria:

- User, Workspace, and Membership models exist.
- Membership supports owner/admin/member/viewer shape or documented MVP subset.
- Migrations apply cleanly.
- Models import cleanly.
- No plaintext secret fields are introduced.

Checks to run:

- Focused model tests.
- `UV_NO_SYNC=1 uv run alembic upgrade head`
- `UV_NO_SYNC=1 uv run ruff check .`

## FOS-DB-03 - Add IntegrationConnection/SyncJob canonical models

Status: done.

Goal: add canonical provider connection and sync tracking models aligned with
the master playbook.

Likely files:

- `app/db/*`
- `migrations/versions/*`
- Focused model tests.
- `docs/data-model.md`

Acceptance criteria:

- IntegrationConnection model exists.
- SyncJob model exists.
- Token fields are encrypted or explicitly secret-safe by contract.
- Sync status/cursor/count/error fields match the MVP contract.
- Migrations apply cleanly.

Checks to run:

- Focused model tests.
- `UV_NO_SYNC=1 uv run alembic upgrade head`
- `UV_NO_SYNC=1 uv run ruff check .`

## FOS-BE-01 - Workspace-aware auth contract

Status: done.

Goal: define how login, current user, workspace access, and protected routes
work before changing API behavior.

Likely files:

- Auth/security docs first.
- Later: `app/api/auth.py`, auth services, tests.

Acceptance criteria:

- Contract covers login/logout/me.
- Contract covers workspace membership checks.
- API-key local/dev behavior is reconciled with user login.
- No route behavior changes happen before the contract is accepted.

Checks to run:

- Docs tests for the contract task.
- Focused auth tests when code is implemented later.

## FOS-GH-01 - Decide GitHub OAuth vs existing Source Control product path

Status: done.

Goal: choose the product path for GitHub-first MVP before building GitHub
OAuth/sync UI.

Likely files:

- `docs/DECISIONS.md`
- `docs/ROADMAP.md`
- Source integration docs.

Acceptance criteria:

- Decision states whether MVP uses GitHub OAuth directly, Source Control as the
  product abstraction, or a staged hybrid.
- Decision covers token storage, workspace scope, sync trigger, evidence
  persistence, and approved write boundary.
- No live provider call is made.

Checks to run:

- `git diff --check`
- Docs tests if available.

## FOS-GH-02 - GitHub repositories read API from existing evidence/source layer

Status: done.

Goal: expose workspace-scoped GitHub repository data from stored evidence/source
records without requiring live provider calls by default.

Likely files:

- API route/service files.
- Repository source/inventory services.
- Focused API tests.
- Docs update.

Acceptance criteria:

- Protected read API returns GitHub repositories from stored evidence/source
  layer.
- Workspace access is enforced with the FOS-BE-01 contract.
- Operator `owner_email` context works for the current local/operator mode.
- Response includes provenance/freshness.
- Response does not imply repo equals Jira project.
- Tests prove no provider call or external write occurs.
- No raw secrets or raw provider payloads are returned.

Checks to run:

- Focused API tests.
- `UV_NO_SYNC=1 uv run ruff check .`
- `git diff --check`

## FOS-GH-03 - GitHub connection contract using IntegrationConnection

Status: done.

Goal: define and expose the MVP GitHub connection contract on top of the
canonical `IntegrationConnection` model without adding OAuth yet.

Likely files:

- GitHub connection API route/service files.
- Pydantic request/response schemas.
- Focused API/service tests.
- `docs/TODO.md`

Acceptance criteria:

- Workspace access is enforced with the FOS-BE-01 contract.
- API reads GitHub `IntegrationConnection` records without exposing token fields.
- No OAuth callback or live provider call is added.
- Connection status covers empty/local bridge, connected, error, revoked, and
  disabled records.
- Tests prove no external writes occur.

Checks to run:

- Focused GitHub connection contract tests.
- `UV_NO_SYNC=1 uv run ruff check .`
- `git diff --check`

## FOS-GH-04 - GitHub OAuth start/callback or provider-token connection

Status: done.

Goal: choose and implement the smallest approved connection creation path for
GitHub on top of `IntegrationConnection`.

Likely files:

- GitHub connection route/service files.
- OAuth or provider-token contract tests.
- Security/config docs if token handling is introduced.
- `docs/TODO.md`

Acceptance criteria:

- Workspace access is enforced.
- Connection creation stores only encrypted token fields or a documented safe
  placeholder contract.
- No repository sync or external write is triggered by connecting.
- Error handling covers missing config, denied callback, and duplicate
  connection cases.
- Tests prove no token value is returned.

Checks to run:

- Focused GitHub connection creation tests.
- `UV_NO_SYNC=1 uv run ruff check .`
- `git diff --check`

## FOS-GH-05 - Manual GitHub sync job record using SyncJob

Status: done.

Goal: add the MVP endpoint that records a manual GitHub sync intent as a local
`SyncJob` without running a worker or calling GitHub.

Likely files:

- GitHub sync-job route/service files.
- Focused SyncJob API tests.
- `docs/TODO.md`

Acceptance criteria:

- Workspace access is enforced.
- Existing GitHub `IntegrationConnection` is required.
- Endpoint creates a queued `SyncJob` with provider `github`.
- No worker execution, provider call, or external write happens.
- Response is local/read-only with `is_live: false`.

Checks to run:

- Focused GitHub sync-job tests.
- `UV_NO_SYNC=1 uv run ruff check .`
- `git diff --check`

## FOS-GH-06 - Normalize GitHub repositories/issues/PRs into existing graph/source substrate or compatibility layer

Status: done.

Goal: define and implement the first small normalization bridge for GitHub data
without duplicating canonical SourceRecord/EvidenceRef work.

Likely files:

- GitHub normalization service files.
- Existing graph/source compatibility files.
- Focused normalization tests.
- `docs/TODO.md`

Acceptance criteria:

- Existing GitHub repository/issue/PR records map to one clear graph/source
  substrate.
- Evidence/source references are preserved where available.
- No live provider calls or external writes occur.
- Existing repository read and SyncJob APIs remain unchanged.

Checks to run:

- Focused GitHub normalization tests.
- `UV_NO_SYNC=1 uv run ruff check .`
- `git diff --check`

## FOS-E2E-01 - GitHub-first backend E2E smoke flow

Status: done.

Goal: cover the backend-only GitHub-first MVP path through existing API
contracts, local repository inventory fakes, and a mocked GitHub issue client.

Likely files:

- `tests/test_github_first_backend_e2e.py`
- `docs/TODO.md`
- `docs/ROADMAP.md`

Acceptance criteria:

- Workspace bootstrap, GitHub connection, repository read, sync job,
  normalization, manual briefing, action proposal, approval, and mocked issue
  execution are covered in one smoke flow.
- No real GitHub calls, live provider calls, LLM calls, workers, or external
  writes occur during the test.
- The response and stored execution data do not expose plaintext or encrypted
  token values.

Checks to run:

- `UV_NO_SYNC=1 uv run pytest -q tests/test_github_first_backend_e2e.py -p no:cacheprovider`
- `UV_NO_SYNC=1 uv run ruff check . --no-cache`
- `UV_NO_SYNC=1 uv run pytest -q -p no:cacheprovider`

## FOS-FE-01 - Minimal web shell plan

Status: done.

Goal: scaffold the master-playbook frontend shell without implementing the full
GitHub-first UI flow.

Likely files:

- `web/*`
- `docs/ROADMAP.md`
- `docs/DECISIONS.md`
- `docs/TODO.md`

Acceptance criteria:

- Next.js + TypeScript shell exists in `web/`.
- App shell, sidebar, placeholder MVP pages, API client, and local operator
  settings exist.
- Frontend typecheck/build/lint checks pass.
- Static `/ui` remains local/operator UI.

Checks to run:

- `git diff --check`
- `npm run typecheck`
- `npm run build`
- `npm run lint`

## FOS-FE-02 - Wire frontend to backend GitHub-first flow

Goal: connect the `web/` shell to the existing workspace, GitHub, briefing, and
action APIs without adding new backend behavior.

Likely files:

- `web/app/dashboard/page.tsx`
- `web/app/github/page.tsx`
- `web/app/briefings/page.tsx`
- `web/app/actions/page.tsx`
- `web/lib/api.ts`

Acceptance criteria:

- Settings-driven API calls use `X-FounderOS-API-Key`, `owner_email`, and
  `workspace_id` from browser-local operator config.
- Dashboard/GitHub/Briefings/Actions pages read existing backend APIs.
- External write execution remains disabled or separately confirmed.
- No OAuth, provider calls, backend route changes, or migrations are added.

Checks to run:

- `npm run typecheck`
- `npm run build`
- `npm run lint`
- Focused backend tests only if frontend wiring reveals a contract issue.

## FOS-BRF-01 - Manual Founder Briefing v0 with evidence refs

Status: done.

Goal: create the MVP manual Founder Briefing path from stored evidence.

Likely files:

- Briefing service/API files.
- Tests.
- UI files later.
- Docs update.

Acceptance criteria:

- Briefing items include evidence refs.
- Missing evidence produces no factual claim.
- Output is deterministic, transient, and no-LLM.
- No external writes occur.

Checks to run:

- Focused briefing/evidence tests.
- `UV_NO_SYNC=1 uv run ruff check .`
- `git diff --check`

## FOS-ACT-01 - ActionProposal approval model/API

Status: done.

Goal: add the canonical human approval foundation for external writes.

Likely files:

- `app/db/*`
- `migrations/versions/*`
- Action service/API/tests.
- Security/API boundary docs.

Acceptance criteria:

- ActionProposal and ActionExecution canonical models exist or are explicitly
  mapped to existing proposal/audit structures.
- External writes require human approval.
- Approval does not execute provider actions in FOS-ACT-01.
- Approval state is auditable.
- AI cannot approve or execute writes directly.

Checks to run:

- Focused action/approval/guard tests.
- `UV_NO_SYNC=1 uv run alembic upgrade head`
- `UV_NO_SYNC=1 uv run ruff check .`

## FOS-ACT-02 - Execute approved GitHub issue action safely

Status: done.

Goal: execute only approved GitHub issue action proposals through the guarded
backend path.

Acceptance criteria:

- Execution requires owner/admin workspace role.
- Execution requires `confirm_external_write=true`.
- Execution requires a connected GitHub `IntegrationConnection`.
- Success creates `ActionExecution` and marks the proposal executed.
- Failure creates failed execution state without leaking tokens.
- Tests mock the GitHub issue client; no live provider calls are made.

Checks to run:

- Focused execution/action/GitHub tests.
- `UV_NO_SYNC=1 uv run ruff check .`
- `UV_NO_SYNC=1 uv run pytest -q`
