# FounderOS TODO

Status: near-term task list only. This file intentionally excludes broad
post-MVP ideas.

Every implementation task must follow `AGENTS.md`: short task prompt, scoped
files, no unrelated edits, and focused checks first.

## Current Checkpoint

- Docs consolidation complete: current control docs are
  `founderOS_MASTER_PLAYBOOK.md`, `PROGRESS.md`, `docs/DECISIONS.md`,
  `docs/README.md`, `docs/ROADMAP.md`, `docs/TODO.md`, `docs/POST_MVP.md`, and
  `docs/CHANGELOG.md`; deleted historical docs are recoverable from git history
  / tag `pre-purge-20260624`.
- FOS-AUD-04: done - docs/test hygiene unblocked before DB work.
- FOS-DB-02: done - User, Workspace, and Membership identity foundation added.
- FOS-DB-03: done - IntegrationConnection and SyncJob foundation added.
- FOS-BE-01: done - workspace-aware operator compatibility contract added.
- FOS-GH-01: done - hybrid GitHub MVP path decision documented.
- FOS-GH-02: done - workspace-scoped GitHub repositories read API added.
- FOS-GH-03: done - workspace-scoped GitHub connection contract added.
- FOS-GH-04: done - operator-protected GitHub provider-token bridge added.
- FOS-GH-05: done - manual GitHub SyncJob record API added without live sync.
- FOS-GH-06/FOS-008: done - local GitHub normalization projection remains for manual SyncJobs, and `persist_if_supported=true` writes canonical repository records.
- FOS-GH-07/FOS-009: done - local GitHub normalization persists supported issue/PR records into canonical `tasks`/`pull_requests`, exposes operational-work read model, and repoints repository inventory to canonical `repositories` before retained `source_events` fallback.
- FOS-010: done - dashboard product controls read GitHub connection/local-sync state, run the supported local normalization backend path, report counts/warnings, and refresh canonical operational work without live OAuth/provider execution.
- FOS-FE-02/FOS-011: done - dashboard surfaces canonical GitHub operational work with issue/task and PR sections, repository labels, and open/all/closed/merged filters.
- FOS-012: done - dashboard surfaces deterministic Company Brain state from canonical GitHub repositories/tasks/PRs with source refs and explicit no-live-provider/no-AI capabilities.
- FOS-BRF-01: done - deterministic transient manual Founder Briefing v0 added.
- FOS-014: done - dashboard and `/briefings` surface the deterministic manual Founder Briefing with returned evidence refs in a frontend evidence drawer.
- FOS-ACT-01: done - local ActionProposal approval API foundation added without execution.
- FOS-ACT-02: done - approved GitHub issue proposals can execute through a guarded endpoint.
- FOS-015: done - dashboard and `/actions` surface local ActionProposal list/create/approve/reject with evidence refs and no external execution.
- FOS-016: done - product execution preview/audit surface shows dry-run GitHub issue readiness, blocks live execute when `enable_write_actions=false`, and requires backend capability plus explicit confirmation before live writes.
- FOS-017: done - execution preview and blocked execute paths persist proposal-scoped audit events and expose a local execution receipt/readiness model.
- FOS-018: done - approved GitHub issue execution code path is gated by runtime config, explicit confirmation, evidence refs, explicit GitHub write repository allowlist, idempotent receipt, and durable audit; automated tests mock the provider.
- FOS-019B: done - manual live GitHub issue smoke succeeded against an approved private smoke repository; exactly one issue was created through the gated `ActionProposal` execution path; receipt and audit are stored locally; external issue URL/id are intentionally omitted from public docs; no other repositories were modified.
- FOS-020: done - post-execution sync read the smoke issue back with safe read-only GitHub access, persisted it through canonical GitHub normalization, verified operational work + Company Brain + deterministic briefing visibility, and kept external execution idempotent.
- FOS-021: done - the approved smoke issue was closed after explicit human approval, closed-state sync was verified into canonical records/read models, and no additional GitHub issues or other repository changes were made.
- FOS-022: done - selected repository issue sync reads only explicitly
  allowlisted repositories, normalizes open/closed issues into canonical
  records, skips PR-shaped issue API records, and was verified against the
  approved smoke repository without external writes.
- FOS-023: done - selected repository PR sync reads only explicitly allowlisted
  repositories, normalizes open/closed/merged PRs into canonical records,
  avoids duplicate repository rows after selected issue sync, de-dupes PR read
  models by repository+number, and performs no external writes.
- FOS-024: done - product dashboard exposes read-only selected repository
  issue and PR sync controls that discover the GitHub connection id from the
  existing connection-status endpoint, validate explicit `owner/repo` input,
  call the existing selected sync endpoints, render loading/success/allowlist/
  permission/error/empty states without raw JSON or private IDs, and refresh
  Company Brain plus operational work after a successful sync; no backend
  contract change and no external writes.
- FOS-E2E-01: done - GitHub-first backend E2E smoke flow covered with local mocks.
- FOS-FE-01: done - minimal Next.js MVP shell scaffolded in `web/`.
- FOS-025B: done - first private-beta deploy/smoke foundation added: explicit backend CORS config, placeholder-only env contract, read-only smoke script, `make smoke`, and local/private-beta docs; no deploy and no external writes.
- FOS-025C: done - CI now enforces backend docs/smoke/CORS/CI contract tests and frontend `npm test`, build, typecheck, and lint gates without provider calls or external writes.
- FOS-025D: done - manual private-beta deploy runbook/config path added under `docs/deploy/private-beta.md`; no deploy, no auto-deploy workflow, and no provider writes.
- Next task: choose/prepare actual hosting target for a human-approved dry deploy rehearsal, or harden production auth/GitHub onboarding before deploy.


## FOS-025B - Private-beta deploy/smoke foundation

Status: done.

Goal: create the first production/private-beta deploy foundation without
deploying and without external writes.

Implemented:

- Explicit backend CORS config with local-safe defaults and exact-origin
  production env contract.
- Read-only private-beta smoke script under `scripts/smoke_private_beta.py`.
- `make smoke` target.
- Placeholder-only `.env.example` covering backend, frontend, CORS, GitHub
  scopes, and smoke env names.
- README and web README local full-stack/private-beta smoke guidance.
- Focused tests for CORS config, smoke endpoint safety, no API-key output, env
  placeholder contract, and docs env-name coverage.

Safety contract:

- The smoke script must not call ActionProposal execute, selected repository
  issue sync, selected repository PR sync, provider-token setup, local-sync,
  normalize-local, post-execution-result sync, or provider write endpoints.
- The smoke script reports step names and HTTP status only; it must not print API
  keys, env values, raw response bodies, provider payloads, tokens, encrypted
  secrets, or credential fields.

Checks to run:

- `git diff --check`
- `bash scripts/check_no_secrets.sh --tracked`
- `UV_NO_SYNC=1 uv run ruff check . --no-cache`
- `UV_NO_SYNC=1 uv run pytest -q tests/test_docs_navigation_integrity.py -p no:cacheprovider`
- `UV_NO_SYNC=1 uv run pytest -q tests/test_private_beta_smoke.py tests/test_cors_config.py -p no:cacheprovider`
- `UV_NO_SYNC=1 uv run pytest -q -p no:cacheprovider`
- `cd web && npm run typecheck && npm run build && npm run lint`

## FOS-025C - Frontend/full-stack deploy-readiness gates

Status: done.

Goal: make deploy-readiness checks enforceable in CI before private-beta deploy.

Implemented:

- Split `.github/workflows/ci.yml` into clear backend and frontend jobs.
- Backend CI preserves tracked-secret scan, `uv sync --frozen`, ruff, Alembic
  upgrade, and full pytest.
- Backend CI now explicitly runs docs navigation plus private-beta smoke, CORS,
  and CI deploy-readiness contract tests before the full suite.
- Frontend CI runs `npm ci`, `npm test`, `npm run build`,
  `npm run typecheck`, and `npm run lint` from `web/`.
- Added `tests/test_ci_deploy_readiness.py` to assert frontend gates exist and
  CI does not contain forbidden live smoke, selected sync, execute, or provider
  secret usage.

Safety contract:

- CI does not call `make smoke` or a live backend.
- CI does not require provider tokens or GitHub provider secrets.
- CI does not call ActionProposal execute, selected repository sync,
  provider-token setup, local-sync, normalize-local, post-execution-result sync,
  or provider write endpoints.

Checks to run:

- `git diff --check`
- `bash scripts/check_no_secrets.sh --tracked`
- `UV_NO_SYNC=1 uv run ruff check . --no-cache`
- `UV_NO_SYNC=1 uv run pytest -q tests/test_ci_deploy_readiness.py -p no:cacheprovider`
- `UV_NO_SYNC=1 uv run pytest -q -p no:cacheprovider`
- `cd web && npm test && npm run build && npm run typecheck && npm run lint`

## FOS-025D - Private-beta deploy runbook/config path

Status: done.

Goal: define the concrete no-surprises private-beta deploy path before any
deployment is attempted.

Implemented:

- Added `docs/deploy/private-beta.md`.
- Documented the split backend API process, frontend web process, managed
  Postgres, and managed/deferred Redis model.
- Documented backend install, migration, start, health, env-name, CORS, API auth,
  GitHub connection, and provider-write-disabled requirements.
- Documented frontend install, build, start, API-base, browser Settings, and
  private-beta limitations.
- Documented migration head/current verification, backup-before-migration, and
  restore-from-backup rollback policy.
- Documented read-only post-deploy `make smoke` and what it must not call.
- Added deploy docs tests for env names, required commands, DB/rollback content,
  read-only smoke boundaries, secret-shaped values, and absence of auto-deploy
  workflow commands.

Safety contract:

- No deploy is performed by this task.
- No automatic deploy workflow is added.
- No cloud-provider secret/config value is added.
- Provider writes remain disabled by default and live provider smoke remains
  human-approved only.

## FOS-025E - Hosting target dry-run preparation

Status: todo.

Goal: prepare the actual private-beta hosting target using the runbook without
performing an unapproved deployment.

Acceptance criteria:

- Target platform and service mapping are chosen explicitly.
- Required manual setup checklist exists for backend, frontend, Postgres, Redis,
  domains, env names, and smoke.
- Human approval is required before any deploy or external write.

## FOS-AUD-02 - Checkpoint/scope split current dirty tree

Status: done / historical.

Goal: make the current dirty tree reviewable before any new implementation.

Likely files:

- `docs/_audit/DOCS_AUDIT.md`
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

Status: done via DEC-028, DEC-030, and `docs/_audit/DOCS_AUDIT.md`; no
standalone `docs/data-model.md` remains after DEC-029/DEC-031 cleanup.

Goal: map the current DB model to the canonical master playbook model before
creating migrations.

Likely files:

- `docs/DECISIONS.md`
- `docs/_audit/DOCS_AUDIT.md`

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

## FOS-GH-06 / FOS-008 - Normalize GitHub repositories into projection or canonical repository tables

Status: done.

Goal: define and implement the first small normalization bridge for GitHub data.
`persist_if_supported=false` remains projection-only; `persist_if_supported=true`
persists repositories into canonical `SourceRecord` and `Repository` rows.

Likely files:

- GitHub normalization service files.
- Focused normalization tests.
- `docs/TODO.md`

Acceptance criteria:

- Existing GitHub repository records map to projection output and, when
  requested, canonical `source_records`/`repositories`.
- Evidence/source references are preserved in sanitized `SourceRecord` payloads
  where available.
- No live provider calls or external writes occur.
- Existing repository read and SyncJob APIs remain unchanged.
- Canonical `EvidenceRef`, issue, and pull request persistence remains deferred
  to the next GitHub spine step.

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
- Legacy static `/ui` has been removed; product UI work stays in `web/`.

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

## FOS-016 - Product guarded execution preview/audit surface

Status: done.

Goal: make approved local GitHub issue proposals inspectable in the product
before any external write path can be called.

Acceptance criteria:

- Product UI can request a dry-run execution preview for an approved proposal.
- Preview validates state/action/payload and does not call GitHub.
- UI shows execution eligibility, preview details, audit/status history, and
  missing-evidence warnings without inventing refs.
- `/execute` is blocked when `enable_write_actions=false`.
- Live execution UI requires backend capability, connection id, and explicit
  confirmation.
- No raw provider payload dumps are shown in the product.

Checks to run:

- Focused action/proposal/execution tests.
- Frontend action execution tests.
- `UV_NO_SYNC=1 uv run ruff check .`
- `UV_NO_SYNC=1 uv run pytest -q`
- `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build`.

## FOS-017 - Persistent execution audit trail

Status: done.

Goal: make preview and blocked execution attempts durable and inspectable before
any live GitHub write proof.

Acceptance criteria:

- Preview creates or reuses proposal-scoped `execution_preview_generated` audit
  events.
- Blocked execute creates or reuses confirmation-missing or
  confirmation-received-but-disabled audit events.
- Audit events are workspace/proposal scoped, deterministic, sanitized, and do
  not use `source_events`, legacy `audit_logs`, or `ActionExecution` overloads.
- Backend exposes a proposal-scoped audit endpoint and local receipt/readiness
  view.
- Product UI renders persisted audit events and keeps timestamp fallback when
  the audit trail is empty.
- No live provider call, OAuth flow, AI/LLM call, or external write is added.

Checks to run:

- Focused action/proposal/execution/audit tests.
- Alembic heads/current/upgrade/check, allowing only documented retained
  substrate drift.
- `UV_NO_SYNC=1 uv run ruff check .`
- `UV_NO_SYNC=1 uv run pytest -q`
- `npm test`, `npm run build`, `npm run typecheck`, and `npm run lint`.

## FOS-018 - Human-gated live GitHub issue execution path

Status: done / implemented behind gates; manual live smoke later succeeded in
FOS-019B.

Goal: allow an approved local GitHub issue `ActionProposal` to reach the
existing GitHub issue executor only after strict runtime, confirmation,
evidence, idempotency, and audit gates pass.

Acceptance criteria:

- `enable_write_actions=false` still blocks execution and records audit.
- `confirm_external_write=true` is required.
- Proposal must be approved, target GitHub issue creation, have a valid
  repository/title payload, have a connected GitHub connection, and include
  evidence refs for live execution.
- Target repository must be present in the explicit non-secret write allowlist
  (`FOS_GITHUB_WRITE_ALLOWED_REPOS`, or `FOS_GITHUB_SMOKE_REPO` for the single
  smoke target). Broad token scope and variable names such as `READONLY` are not
  trusted as safety boundaries.
- Successful mocked execution persists an `ActionExecution` receipt and
  `execution_succeeded` audit event.
- Provider failure persists failed receipt/audit without leaking tokens/raw
  payloads.
- Repeated execute returns the existing successful receipt and does not call the
  provider again.
- Product UI shows live execution controls only when backend capabilities allow,
  requires explicit confirmation, and renders external issue id/url only from
  backend success.
- Automated tests mock the provider boundary.
- FOS-019B manually proved the path against an approved private smoke
  repository: exactly one GitHub issue was created, receipt/audit are stored
  locally, external issue URL/id are omitted from public docs, and no other
  repositories were modified.

Checks to run:

- Focused action/proposal/execution tests.
- GitHub-first backend E2E.
- `UV_NO_SYNC=1 uv run ruff check .`
- `UV_NO_SYNC=1 uv run pytest -q`
- `npm test`, `npm run build`, `npm run typecheck`, and `npm run lint`.

## FOS-020 - Post-execution sync verification

Status: done.

Goal: verify the successfully created smoke issue can flow back into the
canonical GitHub-first read path without causing duplicate execution.

Implemented:

- Added `POST /api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/sync-execution-result`.
- The endpoint validates an executed/succeeded GitHub issue proposal receipt,
  reads the provider issue through the encrypted GitHub connection, creates a
  local manual SyncJob, and reuses canonical GitHub normalization.
- The sync path upserts canonical `SourceRecord` + `Task`, not retained
  `source_events`.
- Sync audit events record `execution_result_sync_started` and
  `execution_result_synced`.
- No GitHub write, issue close, comment, PR, release, repo setting, OAuth, or
  LLM call is part of this path.

Acceptance criteria status:

- Done - synced the created smoke issue back into canonical records through the supported
  GitHub/local sync path.
- Done - operational work can see the synced issue from canonical records.
- Done - Company Brain can see the synced issue from canonical records/source
  refs.
- Done - deterministic briefing reflects the sync through returned
  normalization evidence; issue-specific briefing text is not invented.
- Done - the original executed proposal remains idempotent; execution row count
  stayed single and no duplicate external execution occurred.
- Done - public docs continue to omit private issue URL/id and local workspace/
  proposal/connection/evidence identifiers.

Checks to run:

- Focused GitHub sync/normalization and action execution idempotency tests.
- Docs navigation test if docs change.
- `UV_NO_SYNC=1 uv run ruff check .`
- `UV_NO_SYNC=1 uv run pytest -q`
- `npm test`, `npm run build`, `npm run typecheck`, and `npm run lint`.

## FOS-021 - Smoke issue closeout / cleanup

Status: done.

Goal: close out the private smoke issue created during FOS-019B only after the
post-execution sync loop has been verified.

Acceptance criteria status:

- Done - human explicitly approved closing exactly the existing smoke issue.
- Done - exactly one external GitHub write occurred: close the approved smoke
  issue.
- Done - no new issue, comment, PR, release, repo setting change, label,
  assignee, title, body, or other repository content was modified.
- Done - closed state synced back through canonical GitHub normalization.
- Done - operational work no longer counts the issue as open and can see it in
  closed/all views.
- Done - Company Brain reports zero open issues and one closed issue for the
  smoke workspace state.
- Done - deterministic briefing remains evidence-backed through normalization
  evidence and does not invent closed-issue claims.
- Done - ActionExecution receipt count stayed single; `/execute` was not called.
- Done - public docs omit private issue URL/id and local identifiers.

Checks to run:

- Targeted action/execution tests if any cleanup code path changes.
- Docs navigation test if docs change.
- `UV_NO_SYNC=1 uv run ruff check .`
- `bash scripts/check_no_secrets.sh --tracked`

## FOS-022 - Selected repository issue sync

Status: done.

Goal: broaden the proven single executed-issue read-back path into a selected
repository issue sync path for approved repositories only.

Acceptance criteria:

- Done - the target repository set is explicit and human-approved.
- Done - sync reads issues from selected repositories without creating, closing,
  commenting on, or otherwise writing GitHub content.
- Done - a separate read-sync allowlist blocks non-approved repositories before
  token decrypt/provider calls.
- Done - canonical `SourceRecord` + `Task` upserts remain idempotent, and
  product read models de-dupe alternate historical issue identifiers by
  repository+number.
- Done - operational work and Company Brain reflect selected repository issue
  state.
- Done - briefing references selected repository sync only through returned
  evidence-backed records.
- Done - PR-shaped issue API records are skipped instead of being double-counted
  as issues.
- Done - private issue URLs and local IDs remain out of public docs.

Checks to run:

- Done - focused selected repository issue sync tests.
- Done - GitHub normalization/inventory, action/proposal, Company Brain,
  briefing, and backend E2E tests.
- Done - live read-only verification against the approved smoke repository only.
- Final task closeout checks: `git diff --check`, docs navigation, full pytest,
  `ruff`, and tracked secret scan.

## FOS-023 - Selected repository PR sync

Status: done.

Goal: extend the selected repository read-sync pattern to pull requests for
explicitly approved repositories only.

Implemented:

- Added `POST /api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync`.
- Added a read-only GitHub pull request client using only GET requests.
- Added selected repository PR sync over explicit read-sync allowlists.
- The endpoint validates selected repositories before token decrypt/provider
  calls, creates a local manual SyncJob, and reuses canonical GitHub
  normalization.
- Selected PR sync upserts canonical `SourceRecord` + `PullRequest` rows plus
  repository records, preserves open/closed/merged state, avoids duplicate
  repository rows after selected issue sync, and de-dupes PR read models by
  repository+number.
- No GitHub issue/PR/comment/merge/close/provider write is part of this path.

Acceptance criteria status:

- Done - the target repository set is explicit and human-approved.
- Done - sync reads PRs from selected repositories without creating, updating,
  merging, closing, commenting on, or otherwise writing GitHub content.
- Done - the same read-sync allowlist policy applies before token decrypt/provider
  calls.
- Done - canonical `SourceRecord` + `PullRequest` upserts remain idempotent.
- Done - operational work and Company Brain reflect selected repository PR state.
- Done - issue and PR records are not double-counted in read models when
  overlapping/historical identifiers exist.
- Done - private PR URLs and local IDs remain out of public docs.

Checks run:

- Done - focused GitHub selected PR sync tests.
- Done - existing GitHub normalization/inventory/selected issue sync tests.
- Done - Company Brain, briefing, backend E2E, action/proposal tests.
- Done - docs navigation test.
- Done - `UV_NO_SYNC=1 uv run ruff check . --no-cache`.
- Done - `UV_NO_SYNC=1 uv run pytest -q -p no:cacheprovider`.
- Done - `bash scripts/check_no_secrets.sh --tracked`.
