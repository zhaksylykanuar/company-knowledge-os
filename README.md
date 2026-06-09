# company-knowledge-os (FounderOS)

An operational, evidence-backed knowledge layer for a software team. It ingests
activity (manual notes, Gmail, Drive, and normalized GitHub/Jira/Telegram
events), normalizes it into a shared activity contract, extracts tasks / risks /
decisions with supporting evidence, scores and triages what needs attention, and
produces deterministic digests — all under a strict safety model.

Core principle: **AI drafts and recommends; humans approve; the system executes
only behind separately gated, audited boundaries.**

## Status

- **Implemented (deterministic core):** manual text ingestion, raw-storage +
  Postgres source of truth, rule-based extraction with `evidence_refs`,
  deterministic search / Q&A / scoring / attention dashboard, Obsidian export,
  normalized source events, persisted attention digest read model + renderer,
  and a large family of **read-only operator/diagnostic tools** under `scripts/`
  (no-marker candidate / quality / duplicate-root-cause / grouped-preview /
  grouped-lifecycle reports, guarded-execution doctors, connector config
  doctors).
- **Scaffolded but gated/off by default:** LLM-based attention triage and
  extraction (`ENABLE_LLM=false`), inert delivery drafts + audit-logged
  approval/intention/result records, and a bounded test-only Telegram send path.
- **Planned (not implemented):** scheduled daily digest delivery, production
  Telegram/Slack bot behavior, production GitHub/Jira sync, and
  approval-triggered execution.

Authoritative, up-to-date detail lives in [`docs/`](docs/index.md), not in this
README.

## Tech stack

Python 3.12 · FastAPI · SQLAlchemy (async) + Postgres · Redis · Alembic ·
Pydantic · OpenAI SDK (gated) · `uv` for env/deps · `ruff` + `pytest`.

## Prerequisites

- Python 3.12+
- `uv` for dependency management
- Docker (for local Postgres + Redis via `docker-compose.yml`)

## Quick start

```bash
# 1. Install dependencies
uv sync

# 2. Start local services (Postgres + Redis)
docker compose up -d postgres redis

# 3. Apply database migrations
uv run alembic upgrade head

# 4. Run the API
uv run uvicorn app.main:app --reload
```

Verify the API is up with the `/health` route, then follow
[`docs/mvp-quickstart.md`](docs/mvp-quickstart.md) to ingest a manual note and
inspect extracted tasks/risks/decisions, search, ask, attention, and the
source-activity digest.

## Health checks

```bash
uv run ruff check .          # lint (must be clean)
uv run pytest -q             # full test suite
./scripts/check_no_secrets.sh   # staged-secret scan
```

## Configuration

Copy the template and fill in your own local values (never commit real secrets):

```bash
cp .env.example .env
```

Key flags (see `app/core/config.py` for all):

- `ENABLE_LLM` (default `false`) — gate OpenAI-backed extraction/triage.
- `ENABLE_WRITE_ACTIONS` / `REQUIRE_APPROVAL_FOR_WRITES` — write/approval guards.
- `API_AUTH_ENABLED` / `API_AUTH_KEY` — optional API-key auth.
- `ATTENTION_TRIAGE_*`, `DIGEST_*` — triage confidence policy and digest output.

`.env`, `secrets/`, `raw_storage/`, `obsidian_vault/`, and `operator_outputs/`
are git-ignored and local-only.

## Repository layout

```
app/            FastAPI app
  api/          HTTP routes (health, knowledge, digest, gmail, drive, ...)
  services/     business logic (extraction, scoring, attention, digest, guards)
  agents/       extraction runners (rule-based + gated LLM) and schemas
  connectors/   Gmail / Drive / GitHub / Jira clients
  db/           SQLAlchemy models
  integrations/ source registry, payload mapper, ingestion boundary
scripts/        read-only operator / diagnostic CLIs
tests/          pytest suite
migrations/     Alembic migrations
docs/           architecture, data model, features, runbooks, decisions
```

## Where to read more

- [`docs/index.md`](docs/index.md) — navigation map for everything below.
- [`AGENTS.md`](AGENTS.md) — operating rules for AI agents working in this repo.
- [`CLAUDE.md`](CLAUDE.md) — AI / token / extraction boundaries.
- [`SECURITY_BASELINE.md`](SECURITY_BASELINE.md) — threat model and baseline.
- [`docs/architecture.md`](docs/architecture.md) · [`docs/data-model.md`](docs/data-model.md) · [`docs/backlog.md`](docs/backlog.md)

## Safety boundaries

- Raw storage + Postgres are the source of truth; Obsidian is export-only.
- Every extracted task/risk/decision must carry `evidence_refs`; missing
  evidence yields empty/`null`/insufficient-evidence, never invented facts.
- LLM output used in pipelines must be strict-JSON and schema-validated before
  persistence; LLMs must not directly mutate production data.
- Delivery drafts/results are review/outcome metadata, not source of truth;
  sends stay behind human approval and a separately gated execution path.
