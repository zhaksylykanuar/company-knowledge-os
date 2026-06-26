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
- The canonical product gap remains production/private-beta hardening: concrete
  deploy target wiring, production auth, GitHub OAuth/onboarding, and a deployed
  smoke run.

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

Set `NEXT_PUBLIC_API_BASE_URL` for the frontend build/runtime, or enter the API
base URL in the browser Settings page. The Settings page also stores the local
operator API key, owner email, and workspace ID in browser local storage for the
current local/operator MVP.

### 4. Bootstrap/check workspace context

The backend exposes `/api/v1/workspaces/bootstrap` for operator workspace setup.
For product pages to load, the browser Settings page needs:

- `NEXT_PUBLIC_API_BASE_URL` or an API base URL override.
- `API_AUTH_HEADER_NAME` as the backend API-key header name.
- An operator API key accepted by `API_AUTH_KEY` or `FOUNDEROS_API_KEYS`.
- An owner email for operator workspace access.
- A workspace ID returned by the workspace bootstrap/list/read API.

## Private-beta deployment foundation

FOS-025B adds the first deploy foundation only; it does **not** deploy the app.
A private-beta deploy still needs a hosting target, DB/Redis bindings, production
auth decisions, provider onboarding, backups, and a real deployed smoke run.

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

Minimum frontend env name:

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
uv run pytest -q
bash scripts/check_no_secrets.sh --tracked
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
docs/           canonical docs index, decisions, roadmap, runbooks, features
scripts/        local operator, smoke, and diagnostic CLIs
tests/          pytest suite
migrations/     Alembic migrations
```

## Safety Boundaries

- Raw storage + Postgres are source truth; Obsidian is export-only.
- Every extracted task/risk/decision must carry `evidence_refs`.
- LLM output used in pipelines must be strict JSON and schema-validated.
- LLMs must not directly mutate production data.
- External writes require human approval and a separate execution gate.
