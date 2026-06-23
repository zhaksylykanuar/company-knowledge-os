# FounderOS TODO

Status: near-term task list only. This file intentionally excludes broad
post-MVP ideas.

Every implementation task must follow `AGENTS.md`: short task prompt, scoped
files, no unrelated edits, and focused checks first.

## Current Checkpoint

- FOS-AUD-04: done - docs/test hygiene unblocked before DB work.
- FOS-DB-02: done - User, Workspace, and Membership identity foundation added.
- FOS-DB-03: done - IntegrationConnection and SyncJob foundation added.
- FOS-BE-01: done - workspace-aware operator compatibility contract added.
- FOS-GH-01: done - hybrid GitHub MVP path decision documented.
- Next task: FOS-GH-02 - Workspace-scoped GitHub repositories read API from existing source/evidence layer.

## FOS-AUD-02 - Checkpoint/scope split current dirty tree

Goal: make the current dirty tree reviewable before any new implementation.

Likely files:

- `docs/CURRENT_DIRTY_TREE_PLAN.md`
- Git staging/checkpoint plan only; no application code edits.

Acceptance criteria:

- Dirty tree is grouped by logical scope.
- Docs-only alignment files are isolated from pre-existing application changes.
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

## FOS-FE-01 - Minimal web shell plan

Goal: plan the master-playbook Next.js shell without building it in the same
task.

Likely files:

- `docs/ROADMAP.md`
- A frontend plan/spec doc if needed.

Acceptance criteria:

- Pages are listed: login, dashboard, connectors, GitHub, Company Brain,
  briefings, actions, settings.
- API client and auth assumptions are explicit.
- Required frontend checks are listed.
- Static `/ui` remains local/operator UI.

Checks to run:

- `git diff --check`
- Docs tests if available.

## FOS-BRF-01 - Manual Founder Briefing v0 with evidence refs

Goal: create the MVP manual Founder Briefing path from stored evidence.

Likely files:

- Briefing service/API files.
- Tests.
- UI files later.
- Docs update.

Acceptance criteria:

- Briefing items include evidence refs.
- Missing evidence produces no factual claim.
- Output is deterministic or LLM output is strict JSON and validated.
- No external writes occur.

Checks to run:

- Focused briefing/evidence tests.
- `UV_NO_SYNC=1 uv run ruff check .`
- `git diff --check`

## FOS-ACT-01 - ActionProposal approval model/API

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
- Approval state is auditable.
- AI cannot approve or execute writes directly.

Checks to run:

- Focused action/approval/guard tests.
- `UV_NO_SYNC=1 uv run alembic upgrade head`
- `UV_NO_SYNC=1 uv run ruff check .`
