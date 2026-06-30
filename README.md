# company-knowledge-os (FounderOS)

FounderOS is an evidence-backed operating layer for a founder and small team.
The canonical MVP is defined by the root playbook: one web product, one backend,
connected company sources, Company Brain, Founder Briefing, evidence for every AI
claim, and human-approved external actions.

## Current Source Of Truth

Read in this order (control trio = what / where / why):

1. [`founderOS_MASTER_PLAYBOOK.md`](founderOS_MASTER_PLAYBOOK.md) — what to build.
2. [`PROGRESS.md`](PROGRESS.md) — where we are (live state).
3. [`docs/DECISIONS.md`](docs/DECISIONS.md) — why (decision history).
4. [`docs/README.md`](docs/README.md) — docs index.

## Status

- Backend: FastAPI, SQLAlchemy async, Alembic, Postgres, Redis, Pydantic.
- Frontend: minimal Next.js shell under [`web/`](web/README.md). The legacy
  local/operator static UI has been removed; do not restore `/ui`.
- Current implemented foundations include evidence-backed ingestion/extraction,
  source events, Company Brain preview/repo audit, workspace/GitHub/action
  backend foundations, guarded execution boundaries, and a broad pytest suite.
- Founder login is built: email+password on server-side, revocable sessions
  (Argon2id, httpOnly first-party cookie via a same-origin proxy, DB login
  throttle). The operator API key remains for server/CI/admin tooling. See
  step 4 below to provision the founder account.
- Founder Briefings now persist deterministic briefing history. The remaining
  product gaps are real GitHub product connect/live sync, LLM briefing narrative
  over real connected data, multi-user provisioning beyond the seeded founder,
  and the first production deploy of the auth phase.

## Local full-stack run path

### 1. Start local infrastructure

Use the project Compose file for local Postgres and Redis:

```bash
docker compose up -d postgres redis
```

### 2. Start the backend

The local bootstrap command prepares the gitignored local workspace, updates the
managed local env block, applies Alembic migrations, and starts FastAPI:

```bash
uv run python scripts/start_local.py
```

For a manual backend run, apply migrations first and then start Uvicorn:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --host <backend-host> --port <backend-port>
```

### 3. Start the frontend

In another shell:

```bash
cd web
npm install
npm run dev
```

The dev server proxies `/api/*` and `/health` to the backend, so the session
cookie stays first-party. Configure the proxy target with
`FOUNDEROS_API_PROXY_TARGET` (falls back to `NEXT_PUBLIC_API_BASE_URL`, then
`http://localhost:8000`). Then open the app and sign in at `/login` with the
founder account created in step 4.

### 4. Create the founder login user (email+password)

Provision the single admin/founder account for browser login. The command also
ensures the founder's workspace, so no operator key, owner email, or workspace ID
is entered in the browser — the workspace is derived from the session. The
password is read from an env var and is never printed or committed; re-running
updates the password idempotently (the email is unique, so no duplicate user is
created):

```bash
FOUNDEROS_ADMIN_EMAIL=founder@example.com \
FOUNDEROS_ADMIN_PASSWORD='<chosen-password>' \
UV_NO_SYNC=1 uv run python scripts/create_admin_user.py
```

Optional: `FOUNDEROS_ADMIN_NAME`, `FOUNDEROS_ADMIN_WORKSPACE_NAME`,
`FOUNDEROS_ADMIN_WORKSPACE_SLUG`. The founder then logs in at the web `/login`
page.

The operator API key and the `/api/v1/workspaces/bootstrap` endpoint remain for
machine/CI/admin tooling only; they are not part of the founder browser login.

## Private-beta deployment foundation

The concrete manual private-beta deployment path is documented in
[`docs/deploy/private-beta.md`](docs/deploy/private-beta.md), with the current
Railway dry-run target map in
[`docs/deploy/railway-private-beta.md`](docs/deploy/railway-private-beta.md). It defines the
backend API process, frontend web process, managed Postgres/Redis expectations,
migration/backup/rollback procedure, CORS/API-base setup, and read-only
post-deploy smoke command. It does **not** deploy the app or add an automatic
deploy workflow.

Minimum backend env names for a private-beta candidate:

- `APP_ENV`
- `API_BASE_URL`
- `DATABASE_URL`
- `REDIS_URL`
- `API_AUTH_ENABLED`
- `API_AUTH_KEY`
- `API_AUTH_HEADER_NAME`
- `FOUNDEROS_API_KEYS`
- `FOUNDEROS_SECRET_ENCRYPTION_KEY`
- `FOUNDEROS_CORS_ALLOWED_ORIGINS`
- `FOUNDEROS_CORS_ALLOW_CREDENTIALS`
- `ENABLE_WRITE_ACTIONS`
- `REQUIRE_APPROVAL_FOR_WRITES`
- `FOS_GITHUB_WRITE_ALLOWED_REPOS`
- `FOS_GITHUB_SYNC_ALLOWED_REPOS`

Minimum frontend env names:

- `FOUNDEROS_API_PROXY_TARGET` — server-only backend URL the Next.js app proxies
  `/api/*` and `/health` to, so the session cookie stays first-party
  (same-origin). Falls back to `NEXT_PUBLIC_API_BASE_URL`, then
  `http://localhost:8000`.
- `NEXT_PUBLIC_API_BASE_URL`

Private-beta smoke env names:

- `FOUNDEROS_SMOKE_API_BASE_URL`
- `FOUNDEROS_SMOKE_API_KEY`
- `FOUNDEROS_SMOKE_API_KEY_HEADER_NAME`
- `FOUNDEROS_SMOKE_OWNER_EMAIL`
- `FOUNDEROS_SMOKE_WORKSPACE_ID`
- `FOUNDEROS_SMOKE_EXPECT_AUTH`
- `FOUNDEROS_SMOKE_TIMEOUT_SECONDS`

Use `.env.example` only as a placeholder template; never commit real env files,
provider credentials, API keys, encrypted secrets, raw storage, or local operator
outputs.

## Smoke checks

Run the read-only private-beta smoke script through Make:

```bash
make smoke
```

The smoke script checks safe endpoints only: health, protected-auth behavior,
workspace read, GitHub connection status read, Company Brain read, operational
work read, and deterministic manual briefing generation. It never calls
ActionProposal execute, selected repository sync endpoints, provider write
endpoints, provider-token setup, local-sync, normalize-local, or
post-execution-result sync.

The smoke script reports only step names and HTTP status codes. It must not
print API keys, env values, raw response bodies, provider payloads, tokens, or
credential fields.

## Development & CI

### Quick local checks

Reproduce the backend CI gates locally:

```bash
uv sync --frozen
uv run ruff check .
uv run alembic upgrade head
uv run alembic check
uv run pytest -q
bash scripts/check_no_secrets.sh --tracked
```

Convenience Make targets wrap the same safe local gates:

```bash
make backend-check
make frontend-check
make check
```

For frontend work:

```bash
cd web
npm run typecheck
npm run build
npm run lint
```

### CI parity before opening a PR

`.github/workflows/ci.yml` runs backend gates (`uv sync --frozen`,
`uv run alembic upgrade head`, ruff, pytest, docs/smoke contract tests, and the
tracked-secret scan) against a pinned Postgres image. It also runs frontend
deploy-readiness gates from `web/`: `npm test`, `npm run build`,
`npm run typecheck`, and `npm run lint`. All GitHub Actions are pinned by full
commit SHA. Running the backend and frontend commands above reproduces CI
locally. CI smoke/deploy checks are offline/read-only and do not call providers,
selected repository sync, or external-write endpoints.

### Dependency automation

- **Renovate** keeps Python (`pep621`) dependencies and `uv.lock` current.
- **OpenSSF Scorecard** publishes a private SARIF supply-chain report.
- **Dependency Review** blocks vulnerable or disallowed-license dependency
  changes on pull requests.
- **uv Dependency Submission** publishes the uv.lock transitive coverage graph
  to GitHub on `main` only.
- GitHub Actions are SHA-pinned; bumps come from Renovate or manual SHA rotation.

## Repository Layout

```text
app/            FastAPI app, services, connectors, db models
web/            Next.js product shell
docs/           canonical docs index, decisions, roadmap, changelog, deploy guides
scripts/        local operator, smoke, and diagnostic CLIs
tests/          pytest suite
migrations/     Alembic migrations
```

Generated caches/build outputs (`__pycache__/`, `.pytest_cache/`,
`.ruff_cache/`, `.mypy_cache/`, `web/.next/`, `web/.tmp-test/`, coverage files,
local SQLite files, and `node_modules/`) are ignored and should not be tracked.

## Safety Boundaries

- Raw storage + Postgres are source truth; Obsidian is export-only.
- Every extracted task/risk/decision must carry `evidence_refs`.
- LLM output used in pipelines must be strict JSON and schema-validated.
- LLMs must not directly mutate production data.
- External writes require human approval and a separate execution gate.
