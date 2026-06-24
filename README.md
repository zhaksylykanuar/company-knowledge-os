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
- The canonical product gap remains wiring the full GitHub-first MVP through
  the user-facing web flow and then continuing through the execution chunks.

## Quick Start

```bash
uv run python scripts/start_local.py
```

Then verify:

```bash
uv run ruff check .
uv run pytest -q
```

For frontend work:

```bash
cd web
npm run typecheck
npm run build
npm run lint
```

## Development & CI

### Quick local checks

Reproduce the CI gates locally:

```bash
uv sync --frozen
uv run ruff check .
uv run alembic upgrade head
uv run pytest -q
bash scripts/check_no_secrets.sh --tracked
```

### CI parity before opening a PR

`.github/workflows/ci.yml` runs `uv sync --frozen`, `uv run alembic upgrade head`,
ruff, pytest, and the tracked-secret scan against a pinned Postgres image. All
actions are pinned by full commit SHA. Running the commands above reproduces CI
locally.

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
app/            FastAPI app, services, connectors, db models, static local UI
web/            Next.js product shell
docs/           canonical docs index, decisions, roadmap, runbooks, features
scripts/        local operator and diagnostic CLIs
tests/          pytest suite
migrations/     Alembic migrations
```

## Safety Boundaries

- Raw storage + Postgres are source truth; Obsidian is export-only.
- Every extracted task/risk/decision must carry `evidence_refs`.
- LLM output used in pipelines must be strict JSON and schema-validated.
- LLMs must not directly mutate production data.
- External writes require human approval and a separate execution gate.
