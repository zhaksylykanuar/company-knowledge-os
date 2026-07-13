# FounderOS Private-Beta Deploy Runbook

Status: **manual runbook only**. This document defines the first concrete
private-beta deployment path. It does not deploy FounderOS, does not add an
auto-deploy workflow, and does not authorize provider writes.

## Target-specific dry-run plan

The current concrete hosting target recommendation is the Railway-only split-service path in [`railway-private-beta.md`](railway-private-beta.md). Use that document for service mapping, placeholder env templates, domain/CORS mapping, migration dry run, smoke dry run, and rollback dry run.

## Deployment model

Use a simple split deployment for the private beta:

1. **Backend API process** - FastAPI served by one Uvicorn process from this
   repository.
2. **Frontend web process** - Next.js app served from `web/` after a production
   build.
3. **Managed Postgres** - persistent source of truth for canonical state.
4. **Managed Redis** - optional while the backend remains one process; required
   if it becomes the shared limiter or a future worker/job path depends on it.
   The current private-beta HTTP smoke path does not use Redis directly.

The local `docker-compose.yml` remains a local development dependency file for
Postgres and Redis. It is not the private-beta deployment target.

No worker process is required for the current GitHub-first private-beta smoke
path. Add a worker only after a task explicitly introduces a queue-backed runtime
contract.

Keep exactly one Uvicorn process/replica for this baseline. The pre-Argon2 login
admission controller is process-local: its per-IP, global, and concurrent limits
do not aggregate across workers. A shared edge or Redis-backed login limiter is a
required prerequisite for multiple Uvicorn workers or backend replicas.
It currently keys clients by ASGI `request.client.host`. Before exposing the
login route publicly, verify with two external source IPs that the Railway/Next
proxy path preserves distinct trusted client identity, or replace per-IP
admission with an edge/shared limiter. Do not enable unrestricted forwarded-header
trust on a publicly reachable backend.

## Preflight checklist

Before provisioning or deploying, verify locally:

```bash
git status --short --branch
git diff --check
bash scripts/check_no_secrets.sh --tracked
UV_NO_SYNC=1 uv run ruff check . --no-cache
UV_NO_SYNC=1 uv run pytest -q -p no:cacheprovider
cd web && npm test && npm run build && npm run typecheck && npm run lint
```

Do not continue if the worktree is dirty with unrelated changes, tracked-secret
scan fails, migrations fail, backend tests fail, or frontend deploy-readiness
checks fail.

## Required backend env names

Configure these on the backend service. Values must be set in the hosting
platform secret/env manager and must not be committed to git:

- `APP_ENV`
- `APP_NAME`
- `API_BASE_URL`
- `DATABASE_URL`
- `REDIS_URL`
- `RAW_STORAGE_DIR`
- `API_AUTH_ENABLED`
- `API_AUTH_KEY`
- `API_AUTH_HEADER_NAME`
- `FOUNDEROS_API_KEYS`
- `FOUNDEROS_SECRET_ENCRYPTION_KEY`
- `FOUNDEROS_CORS_ALLOWED_ORIGINS`
- `FOUNDEROS_CORS_ALLOW_CREDENTIALS`
- `FOUNDEROS_LOGIN_MAX_FAILED_ATTEMPTS`
- `FOUNDEROS_LOGIN_LOCKOUT_MINUTES`
- `FOUNDEROS_LOGIN_RATE_LIMIT_WINDOW_SECONDS`
- `FOUNDEROS_LOGIN_RATE_LIMIT_PER_IP`
- `FOUNDEROS_LOGIN_RATE_LIMIT_GLOBAL`
- `FOUNDEROS_LOGIN_MAX_CONCURRENT_ATTEMPTS`
- `FOUNDEROS_LOGIN_ATTEMPT_RETENTION_HOURS`
- `ENABLE_LLM`
- `ENABLE_WRITE_ACTIONS`
- `REQUIRE_APPROVAL_FOR_WRITES`
- `FOS_GITHUB_WRITE_ALLOWED_REPOS`
- `FOS_GITHUB_SYNC_ALLOWED_REPOS`
- `FOUNDEROS_ENABLE_REAL_CONNECTORS`
- `FOUNDEROS_REQUIRE_CONNECTOR_SCOPE`

Optional only when the corresponding feature is intentionally enabled:

- `OPENAI_API_KEY`
- `FOS_OPENAI_API_KEY`
- `FOUNDEROS_GITHUB_REPOS`
- `FOUNDEROS_GITHUB_APP_ID`
- `FOUNDEROS_GITHUB_APP_SLUG`
- `FOUNDEROS_GITHUB_APP_PRIVATE_KEY` or
  `FOUNDEROS_GITHUB_APP_PRIVATE_KEY_PATH`
- `FOUNDEROS_GITHUB_APP_WEBHOOK_SECRET`
- `FOUNDEROS_GITHUB_APP_SETUP_URL`
- `FOUNDEROS_GITHUB_APP_CALLBACK_URL`
- `FOUNDEROS_JIRA_PROJECT_KEYS`
- `ENABLE_OBSIDIAN_EXPORT`
- `FOUNDEROS_ENABLE_OBSIDIAN_BRIDGE`
- `FOUNDEROS_OBSIDIAN_VAULT_NAME`
- `FOUNDEROS_OBSIDIAN_VAULT_PATH`
- `FOUNDEROS_OBSIDIAN_SYNC_MODE`

Fail-closed auth posture:

- The backend refuses to start when `APP_ENV` is non-local (e.g.
  `production`/`private-beta`) and `API_AUTH_ENABLED` is unset/false, or when
  auth is enabled but neither `API_AUTH_KEY` nor `FOUNDEROS_API_KEYS` is
  configured. Disabling auth is only permitted when `APP_ENV` is
  local/dev/test. This makes a forgotten auth flag a loud startup failure
  rather than a silent fail-open exposure.

Private-beta default policy:

- ENABLE_WRITE_ACTIONS remains disabled unless a human explicitly approves a
  bounded live-write smoke.
- `ENABLE_LLM` remains disabled unless a task explicitly enables an LLM path.
- `FOUNDEROS_ENABLE_REAL_CONNECTORS` remains disabled except for a scoped,
  human-approved read-only connector test.
- Broad provider token scope is not a safety boundary; explicit write and sync
  allowlists are still required.
- GitHub App product-connect config is server-side only. Private keys and
  webhook secrets are never browser env vars; installation access tokens should
  be minted just-in-time and not persisted.

## Required frontend env names

Configure these on the frontend service:

- `FOUNDEROS_API_PROXY_TARGET` — server-only backend URL the Next.js app proxies
  `/api/*` and `/health` to, so the session cookie stays first-party. Falls back
  to `NEXT_PUBLIC_API_BASE_URL`, then `http://localhost:8000`.
- `NEXT_PUBLIC_API_BASE_URL`

Production auth/session is now built: users sign in at `/login` with
email+password on a server-side session cookie (Argon2id, httpOnly, first-party
via the same-origin proxy). The browser sends no operator API key or manually
entered owner/workspace identifiers; available companies come from the session,
and multiple memberships require an explicit choice. Create the first founder
through a short-lived `scripts/create_founder_invite.py` URL (see the root
README). Public signup and email delivery remain closed. The operator API key
and `scripts/create_admin_user.py` recovery path remain for machine/admin use.
Founder and teammate setup bearers use URL fragments, not HTTP query strings;
the browser clears them immediately after capture. All login, setup-password,
and founder-enrollment sessions retain only printable User-Agent metadata capped
at 512 characters. Password inputs are capped before hashing: login accepts
1–256 characters, while enrollment, teammate setup, and password change require
8–256. A disabled account's live session is revoked when next validated.

In production, per-IP/global request windows and a concurrency limit reject
excess login work before Argon2; the durable DB throttle separately locks by
submitted email. Failed-login recording opportunistically removes DB throttle
rows older than `FOUNDEROS_LOGIN_ATTEMPT_RETENTION_HOURS` (24 hours by default).
The admission layer is process-local, so this runbook intentionally starts one
Uvicorn process only. Per-IP isolation behind the actual hosting proxy is not a
locally proven property; the two-external-client smoke above is a release gate,
not an implementation claim.

## Backend deployment procedure

1. Provision a backend service from this repository.
2. Configure the backend env names listed above using placeholders or secret
   manager entries only; do not put values in tracked files.
3. Install dependencies:

   ```bash
   uv sync --frozen
   ```

4. Run migrations before serving traffic:

   ```bash
   uv run alembic upgrade head
   ```

5. Verify migration metadata:

   ```bash
   uv run alembic heads
   uv run alembic current
   ```

6. Start the backend API process:

   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port <backend-port>
   ```

   Do not add `--workers` or a second replica until a shared edge/Redis login
   limiter is deployed and verified.

7. Verify the public health endpoint:

   ```bash
   curl -fsS <backend-public-origin>/health
   ```

Do not run selected repository sync, ActionProposal execute, provider-token
setup, local-sync, normalize-local, or post-execution-result sync as part of the
backend deploy command.

## Frontend deployment procedure

1. Provision a frontend service from `web/`.
2. Configure `NEXT_PUBLIC_API_BASE_URL` to point at the backend public origin.
3. Install dependencies:

   ```bash
   npm ci
   ```

4. Run deploy-readiness checks:

   ```bash
   npm test
   npm run build
   npm run typecheck
   npm run lint
   ```

5. Start the frontend process:

   ```bash
   npm run start -- --port <frontend-port>
   ```

6. Verify the frontend page loads. In an interactive backend admin shell whose
   stdout is not retained by a deploy/start job, create one short-lived founder
   link and pass the real frontend origin. TTL must be 1–168 hours (72 by
   default):

   ```bash
   UV_NO_SYNC=1 uv run python scripts/create_founder_invite.py \
     --base-url <frontend-origin> \
     --ttl-hours 72
   ```

   Treat the printed URL like a credential: transfer it directly to the founder
   and never paste it into deploy logs, tickets, docs, or chat. The founder opens
   `/start`, creates the company, and follows `/onboarding`; existing founders
   return through `/login`. The session cookie remains first-party through the
   same-origin proxy.

   If the unconsumed URL is leaked or sent to the wrong person, revoke it by the
   returned UUID before issuing another link:

   ```bash
   UV_NO_SYNC=1 uv run python scripts/revoke_founder_invite.py \
     --invite-id <invite-uuid>
   ```

   Unknown, expired, used, and revoked tokens intentionally return the same
   generic failure. Never create invite links in a retained build log.

7. When an owner/admin adds a brand-new teammate in Settings, FounderOS returns
   one fragment-only `/setup-password#token=...` link. The inviter does not set
   an initial password. This slice sends no email and does not verify the
   recipient, so copy the link once and transfer it manually over a trusted
   direct channel; never retain it in deploy logs, tickets, docs, or chat. An
   existing account already belonging to another workspace returns 409 and no
   membership is created until a future self-accepted invitation flow exists.

## Postgres and Redis requirements

### Postgres

Postgres is required. It is the canonical source of truth with raw storage. The
backend reads `DATABASE_URL` at startup and Alembic uses the same configured
source through `migrations/env.py`.

Requirements:

- managed Postgres with persistent storage;
- regular backups enabled before the first migration;
- restore path documented by the hosting provider;
- connectivity from the backend service;
- no real database URL in git, docs, CI, or logs.

### Redis

Redis is configured through `REDIS_URL` and exists in local Compose. For the
current private-beta HTTP smoke path, Redis is not directly exercised. Provision
managed Redis if the hosting platform makes it cheap and safe; otherwise mark it
as deferred while the backend remains one process. Before scaling to multiple
Uvicorn workers or replicas, add and verify either an edge-shared or Redis-backed
login limiter; merely setting `REDIS_URL` does not make the current process-local
controller shared.

## Migration, backup, and rollback

Before `uv run alembic upgrade head` against private-beta data:

1. Take a database backup through the hosting provider.
2. Enter a maintenance window and stop backend/worker writers. Revision
   `a3c4d5e6f7b8` adds a regular composite unique constraint to existing
   `source_records`; even though duplicate `(workspace_id, id)` values are
   impossible under the primary key, PostgreSQL may hold a write-blocking lock
   while it builds the backing index. Do not apply it under active ingestion.
   The current head `b4d5e6f7a8c9` then adds the
   `founder_enrollment_invites` table for hash-only, expiring, revocable founder
   links; it stores no raw bearer.
3. Record the current app commit SHA in the deploy log.
4. Record Alembic heads/current locally without printing database URLs:

   ```bash
   uv run alembic heads
   uv run alembic current
   ```

5. Apply migrations:

   ```bash
   uv run alembic upgrade head
   ```

6. Restart writers only after the migration succeeds, then run backend health
   and private-beta smoke.

Company World data migration is deliberately separate from schema migration.
After the new head is healthy, run the aggregate-only dry run for each intended
workspace from the backend environment:

```bash
uv run python scripts/backfill_company_world.py --workspace-id <workspace-uuid>
```

Review only the returned counts and warnings. The command never promotes
projected external candidates. If `conflicts` is zero and the backup is current,
an authorized human may apply membership profiles and missing interactions for
already confirmed people explicitly:

```bash
uv run python scripts/backfill_company_world.py \
  --workspace-id <workspace-uuid> \
  --apply
```

Re-run the dry run and require all `*_proposed` counts to be zero. Do not print
or attach emails, raw bodies, provider payloads, tokens, or database URLs.

Rollback policy:

- If migration has not been applied, redeploy the previous app commit.
- If migration has been applied and smoke fails, prefer restore-from-backup for
  data-impacting failures; do not guess a downgrade path.
- Revision `a3c4d5e6f7b8` refuses to downgrade while any Company World profile,
  interaction, affiliation, organization, or resolution row exists. It takes
  exclusive locks on all five tables before checking them, so run downgrade only
  in the same stopped-writer maintenance window. Restore the pre-migration
  backup, or export and remove those rows through an explicitly reviewed data
  plan before retrying downgrade; never bypass the guard ad hoc.
- Some migrations are intentionally irreversible — notably `f7b8c9d0e1a2`
  (canonical-task dedupe), which DELETEs duplicate provider-keyed task rows
  before adding the unique index. Treat database backup as the rollback boundary.
- The known retained-substrate Alembic drift is tracked separately and is not a
  reason to run ad-hoc schema edits during private-beta deploy.

## CORS, domain, and API-base setup

Configure exact origins only:

- backend public origin in `API_BASE_URL`;
- frontend public API base in `NEXT_PUBLIC_API_BASE_URL`;
- browser-allowed frontend origins in `FOUNDEROS_CORS_ALLOWED_ORIGINS`;
- credential behavior in `FOUNDEROS_CORS_ALLOW_CREDENTIALS`.

Do not use wildcard CORS. The backend resolver ignores wildcard origins. Because
the frontend proxies `/api/*` same-origin, browser CORS is not exercised on the
normal path; `FOUNDEROS_CORS_ALLOWED_ORIGINS` matters only if the browser is
pointed directly at a separately hosted API. If the frontend cannot reach the
backend, check `FOUNDEROS_API_PROXY_TARGET` (or `NEXT_PUBLIC_API_BASE_URL`) and
`FOUNDEROS_CORS_ALLOWED_ORIGINS` first.

## GitHub connection setup

The preferred product path is the GitHub App installation foundation
(DEC-052/053): server-side App credentials, a workspace-scoped installation
connection, and one explicit repository read at a time. The manual encrypted
provider-token path remains an operator bridge, not browser onboarding. The
first real GitHub App read remains a separate human-approved gate.

Rules:

- never paste tokens into tracked files, docs, issue comments, PR comments, CI,
  shell history shared with others, or logs;
- provider-token setup is not part of deploy automation;
- write and read-sync repository allowlists are required even if the provider
  token has broad scope;
- provider writes stay disabled by default.

## Post-deploy smoke procedure

The private-beta smoke uses the existing read-only script. Configure smoke env
names in the operator shell or CI-like local environment, never in tracked files:

- `FOUNDEROS_SMOKE_API_BASE_URL`
- `FOUNDEROS_SMOKE_API_KEY`
- `FOUNDEROS_SMOKE_API_KEY_HEADER_NAME`
- `FOUNDEROS_SMOKE_OWNER_EMAIL`
- `FOUNDEROS_SMOKE_WORKSPACE_ID`
- `FOUNDEROS_SMOKE_EXPECT_AUTH`
- `FOUNDEROS_SMOKE_TIMEOUT_SECONDS`

Run:

```bash
make smoke
```

The smoke checks:

- `/health`;
- protected API-key behavior;
- workspace read;
- GitHub connection status read;
- Company Brain read;
- operational work read;
- deterministic manual briefing generation.

The smoke does not call:

- ActionProposal execute;
- selected repository issue sync;
- selected repository PR sync;
- provider-token setup;
- local-sync;
- normalize-local;
- post-execution-result sync;
- OpenAI or other LLM APIs;
- provider write endpoints.

A live provider smoke is separate. It requires explicit human approval, a bounded
repository allowlist, and a written rollback/cleanup plan.

## Security boundaries

- `.env`, `.env.local`, provider credentials, local secrets, raw storage,
  Obsidian vault files, and operator outputs stay out of git.
- `.env.example` remains placeholder-only.
- CI is offline/provider-free per DEC-037.
- Private-beta smoke is read-only per DEC-036.
- LLMs must not directly mutate production data.
- External writes require human approval, runtime capability, explicit
  confirmation, evidence refs, idempotency, and target allowlists.

## Explicit non-goals for this runbook

This runbook does not:

- deploy FounderOS;
- add an automatic deploy workflow;
- choose or store cloud-provider secrets;
- implement GitHub OAuth/onboarding (production auth/session login is already
  built; this runbook just deploys it);
- add public signup or email delivery for founder/team invitations;
- run live provider smoke;
- authorize provider writes.
