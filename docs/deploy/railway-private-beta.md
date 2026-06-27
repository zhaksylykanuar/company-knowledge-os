# Railway Private-Beta Hosting Dry-Run Plan

Status: **dry-run preparation only**. This is the concrete hosting target plan
for FounderOS private beta. It does not create a Railway project, provision
services, deploy code, trigger remote CI, or run smoke against a live backend.

## Target recommendation

Use a **Railway-only split-service private-beta baseline** because the master
playbook names Railway as the MVP deployment target and the current app maps
cleanly to separate services:

1. **Backend service** - FastAPI/Uvicorn from the repository root.
2. **Frontend service** - Next.js from `web/`.
3. **Managed Postgres service** - required canonical datastore.
4. **Managed Redis service** - optional/deferred until a worker/job path requires
   it; keep `REDIS_URL` documented for compatibility.

Do not use the Railway CLI, auto-deploy-on-push, or deployment workflows in this
chunk. When a human approves provisioning, perform setup manually in the hosting
UI and copy only placeholder-free values into the hosting platform secret/env
manager.

## Service map

| Service | Source path | Build/install command | Start command | Required |
|---|---|---|---|---|
| Backend API | repository root | `uv sync --frozen` / `RAILPACK_BUILD_CMD` | `uv run uvicorn app.main:app --host 0.0.0.0 --port <platform-port>` / `RAILPACK_START_CMD` | Yes |
| Frontend web | `web/` | `npm ci && npm run build` / `RAILPACK_BUILD_CMD` | `npm run start -- --port <platform-port>` / `RAILPACK_START_CMD` | Yes |
| Postgres | managed database | platform-managed | platform-managed | Yes |
| Redis | managed database/cache | platform-managed | platform-managed | Optional/deferred |

Use the platform-provided service port placeholder for backend and frontend
start commands. Do not hardcode private-beta port numbers in tracked files.

## Manual setup checklist

This checklist is intentionally written as a dry-run map. Do not perform these
steps until a human explicitly approves provisioning.

1. Confirm local gates are green:
   - `bash scripts/check_no_secrets.sh --tracked`
   - `UV_NO_SYNC=1 uv run ruff check . --no-cache`
   - `UV_NO_SYNC=1 uv run pytest -q -p no:cacheprovider`
   - `cd web && npm test && npm run build && npm run typecheck && npm run lint`
2. Choose the private-beta commit SHA to deploy.
3. Create a Railway project manually only after approval.
4. Add a managed Postgres service and note only the env variable name
   `DATABASE_URL` in tracked docs.
5. Add managed Redis only if the approved deploy plan requires it; otherwise keep
   Redis deferred and document the decision in the deploy log.
6. Add a backend service from the repository root.
7. Add a frontend service from `web/`.
8. Configure exact backend and frontend domains in the hosting UI.
9. Configure backend env names from `templates/railway-backend.env.example`.
10. Configure frontend env names from `templates/railway-frontend.env.example`.
11. Take a database backup before running migrations against private-beta data.
12. Run migrations once through a manual backend command after backup.
13. Start services.
14. Run read-only private-beta smoke from an operator machine.
15. Record smoke result and commit SHA in the deploy log without secret values.

## Backend service dry-run details

Backend service settings:

- **Root directory:** repository root.
- **Install command:** `uv sync --frozen`.
- **Migration command:** `uv run alembic upgrade head` after backup and before
  traffic.
- **Start command:** `uv run uvicorn app.main:app --host 0.0.0.0 --port <platform-port>`.
- **Railpack variables:** set `RAILPACK_BUILD_CMD` and `RAILPACK_START_CMD`; the rehearsal showed current Railway Railpack may not honor legacy Nixpacks command variables.
- **Database URL runtime:** set `DATABASE_URL` to a `postgresql+asyncpg` Railway reference for the managed Postgres service so the app boots with the async driver.
- **Health check:** `GET <backend-public-origin>/health`.

Backend env names:

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
- `ENABLE_LLM`
- `ENABLE_WRITE_ACTIONS`
- `REQUIRE_APPROVAL_FOR_WRITES`
- `FOS_GITHUB_WRITE_ALLOWED_REPOS`
- `FOS_GITHUB_SYNC_ALLOWED_REPOS`
- `FOUNDEROS_ENABLE_REAL_CONNECTORS`
- `FOUNDEROS_REQUIRE_CONNECTOR_SCOPE`

Backend private-beta defaults:

- ENABLE_WRITE_ACTIONS disabled by default.
- `ENABLE_LLM` disabled by default.
- `FOUNDEROS_ENABLE_REAL_CONNECTORS` disabled unless a human approves a scoped
  read-only provider test.
- GitHub write and sync allowlists remain explicit and repository-scoped.

## Frontend service dry-run details

Frontend service settings:

- **Root directory:** `web/`.
- **Install/build command:** `npm ci && npm run build`.
- **Start command:** `npm run start -- --port <platform-port>`.
- **Railpack variables:** set `RAILPACK_BUILD_CMD` and `RAILPACK_START_CMD` for the frontend service as well.
- **Public API base:** `NEXT_PUBLIC_API_BASE_URL` points at the backend public
  origin.

Frontend env names:

- `NEXT_PUBLIC_API_BASE_URL`

Current private-beta UX still requires browser-local Settings:

- API base URL or default from `NEXT_PUBLIC_API_BASE_URL`;
- operator API key;
- owner email;
- workspace ID.

Production auth/session and GitHub OAuth/onboarding remain later hardening work.

## Domain, CORS, and API-base mapping

Use placeholder domains in planning only:

- backend public origin: `<railway-backend-domain>`;
- frontend public origin: `<railway-frontend-domain>`;
- backend `API_BASE_URL`: backend public origin;
- frontend `NEXT_PUBLIC_API_BASE_URL`: backend public origin;
- backend `FOUNDEROS_CORS_ALLOWED_ORIGINS`: frontend public origin;
- backend `FOUNDEROS_CORS_ALLOW_CREDENTIALS`: configured only when the auth model
  requires credentialed browser requests.

Do not use wildcard CORS. If browser API calls fail after deploy, verify the
frontend domain, backend domain, `NEXT_PUBLIC_API_BASE_URL`, browser Settings API
base URL, and `FOUNDEROS_CORS_ALLOWED_ORIGINS` before changing code.

## Postgres path

Postgres is required for private beta.

Dry-run mapping:

- Railway managed Postgres service provides the value for `DATABASE_URL`.
- The backend service receives `DATABASE_URL` through the hosting secret/env
  manager.
- For app runtime, use the `postgresql+asyncpg` driver form in `DATABASE_URL`; for an operator-run local migration against Railway Postgres, use the public Postgres URL only inside the subprocess environment and never print it.
- Alembic reads the configured `DATABASE_URL` through `migrations/env.py`.
- A database backup is required before the first private-beta migration.
- Restore-from-backup is the rollback boundary for data-impacting migration
  failures.

Never paste a real database URL into docs, `.env.example`, templates, CI, or
issues.

## Redis path

Redis is optional/deferred for the current private-beta HTTP smoke path. Keep
`REDIS_URL` in the env contract because the app settings include it and future
worker/job paths may require it.

Dry-run decision:

- If the hosting budget and setup allow it, add Railway managed Redis and set
  `REDIS_URL` through the secret/env manager.
- If not, record Redis as deferred and do not add a worker process.
- Do not block read-only HTTP smoke solely on Redis unless a task introduces a
  Redis-backed runtime requirement.

## Migration dry run

Before migration:

```bash
uv run alembic heads
uv run alembic current
```

After backup and approval:

```bash
uv run alembic upgrade head
```

After migration:

```bash
uv run alembic current
```

Known retained-substrate Alembic drift remains a tracked cleanup topic. Do not
perform ad-hoc schema edits during private-beta setup.

Rehearsal note: `railway run` executes locally with values from the linked Railway environment, so private Railway database hostnames may not resolve from the operator machine. Use the public Postgres connection only for the local Alembic subprocess, keep it out of logs, and keep backend runtime on the private Railway reference.

## Smoke dry run

Configure smoke env names on the operator machine only:

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

The smoke is read-only/deterministic and does not call ActionProposal execute,
selected repository issue sync, selected repository PR sync, provider-token
setup, local-sync, normalize-local, post-execution-result sync, OpenAI/LLM APIs,
or provider write endpoints.

## Rollback dry run

Rollback choices:

1. **Before migration:** redeploy the previous commit SHA.
2. **After migration, before user data changes:** restore the pre-migration
   database backup, then redeploy the previous commit SHA.
3. **After smoke failure:** keep provider writes disabled, stop promotion,
   restore from backup if data-impacting, and record the failed step without
   secret values.

Do not rely on Alembic downgrade for private-beta rollback. Historical migrations
include irreversible operations.

## Later live provider smoke

A live provider smoke is not part of this dry-run plan. It requires a separate human approval and a separate
human approval with:

- exact repository target;
- `FOS_GITHUB_WRITE_ALLOWED_REPOS` scoped to that target;
- `FOS_GITHUB_SYNC_ALLOWED_REPOS` scoped to that target;
- `ENABLE_WRITE_ACTIONS` enabled only for the bounded test window;
- explicit ActionProposal evidence refs and confirmation;
- cleanup/rollback plan;
- post-smoke provider-write disablement.

## Do not do in FOS-025E

- Do not create a Railway project.
- Do not provision Postgres or Redis.
- Do not configure domains.
- Do not add real env values.
- Do not deploy backend or frontend.
- Do not add auto-deploy-on-push workflows.
- Do not run live provider smoke.
- Do not call provider write endpoints.
