# company-knowledge-os (FounderOS)

FounderOS is an evidence-backed operating layer for a founder and small team.
The canonical MVP is now defined by the root playbook and execution plan: one
web product, one backend, connected company sources, Company Brain, Founder
Briefing, evidence for every AI claim, and human-approved external actions.

## Current Source Of Truth

Read in this order:

1. [`founderOS_MASTER_PLAYBOOK.md`](founderOS_MASTER_PLAYBOOK.md)
2. [`EXECUTION_PLAN.md`](EXECUTION_PLAN.md)
3. [`PROGRESS.md`](PROGRESS.md)
4. [`docs/README.md`](docs/README.md)

The docs archive under [`docs/_archive/`](docs/_archive/) is reversible history,
not current product truth.

## Status

- Backend: FastAPI, SQLAlchemy async, Alembic, Postgres, Redis, Pydantic.
- Frontend: minimal Next.js shell under [`web/`](web/README.md), plus existing
  local/operator static UI at `/ui`.
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
