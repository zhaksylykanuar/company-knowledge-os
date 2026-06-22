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
  local founder UI, Company Brain preview/repo audit, Source Control request
  lifecycles, and a large family of **read-only operator/diagnostic tools**
  under `scripts/` (no-marker candidate / quality / duplicate-root-cause /
  grouped-preview / grouped-lifecycle reports, guarded-execution doctors,
  connector config doctors).
- **Scaffolded but gated/off by default:** LLM-based attention triage and
  extraction (`ENABLE_LLM=false`), inert delivery drafts + audit-logged
  approval/intention/result records, guarded read-only GitHub/Jira connector
  checks and Source Control runs, an operator-launched Telegram founder bot,
  and a bounded test/manual Telegram send path.
- **Planned:** scheduled daily digest delivery, production webhook/scheduler
  Telegram/Slack behavior, production source schedulers/webhooks, production
  Gmail/Drive connector execution, and approval-triggered external write
  execution.

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
# One command bootstraps the project-local runtime, runs migrations, and starts
# the backend on 127.0.0.1:8765.
uv run python scripts/start_local.py
```

Verify the API at `http://127.0.0.1:8765/health`, open
`http://127.0.0.1:8765/ui`, then follow
[`docs/mvp-quickstart.md`](docs/mvp-quickstart.md) to ingest a manual note and
inspect extracted tasks/risks/decisions, search, ask, attention, and the
source-activity digest.

## Health checks

Quick local checks:

```bash
uv run ruff check .          # lint (must be clean)
uv run pytest -q             # full test suite
./scripts/check_no_secrets.sh   # staged-secret scan
./scripts/check_no_secrets.sh --tracked   # CI-safe tracked-file scan
```

CI parity before opening a PR:

```bash
uv sync --frozen
uv run ruff check .
uv run alembic upgrade head
uv run pytest -q
bash scripts/check_no_secrets.sh --tracked
```

GitHub also runs CodeQL code scanning for Python and GitHub Actions workflows
via `.github/workflows/codeql.yml`. Treat CodeQL findings as release-blocking
until triaged or explicitly accepted.

Dependency Review runs on pull requests via
`.github/workflows/dependency-review.yml` and fails PRs that introduce
high-or-critical vulnerable runtime, development, or unknown-scope dependencies
recognized by GitHub's dependency graph.

uv Dependency Submission runs on `main` pushes and manual dispatch via
`.github/workflows/uv-dependency-submission.yml`. It submits the resolved
`uv.lock transitive coverage` to GitHub's dependency graph so Dependabot alerts
and repository dependency insights can include uv transitive dependencies. The
workflow intentionally does not run on untrusted PR heads because dependency
submission requires `contents: write`; PR-time enforcement stays with
Dependency Review.

OpenSSF Scorecard runs weekly via `.github/workflows/scorecard.yml` and uploads
SARIF to GitHub code scanning without publishing project results to the external
OpenSSF API. Use it as the repository-level supply-chain audit: dependency
updates, CI, token permissions, pinned actions, branch protection, and code
scanning posture.

All GitHub workflow actions are pinned by full commit SHA with the human tag
kept as a comment, for example `owner/action@<sha> # vX.Y.Z`. Service
containers are pinned by image digest. Dependabot tracks GitHub Actions update
availability, while maintainers perform manual SHA rotation when action tags
move: update the SHA and keep the commented tag for reviewability.

## Dependency automation

- `renovate.json` owns Python dependency updates for this uv project. It is
  limited to Renovate's PEP 621/uv lockfile path so dependency PRs must update
  `pyproject.toml` and `uv.lock` together, with weekly lockfile maintenance for
  transitive dependencies. Treat any Renovate PR that changes only one of those
  files as incomplete until `uv lock` / `uv sync --frozen` confirms parity.
- `.github/dependabot.yml` owns GitHub Actions updates only. Keeping the scopes
  separate avoids duplicate dependency PRs.
- Dependency PRs should pass the same CI parity gate above before merge.

## Configuration

For the default local workflow, let `scripts/start_local.py` call
`scripts/bootstrap_local_workspace.py`, which creates `.local/` and safely
updates the project-local env override without deleting existing local secrets.
For manual
configuration, copy the template and fill in your own values:

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

- [`docs/playbook.md`](docs/playbook.md) — operating playbook v2: phases, usage
  gates, weekly ritual, eval contract (what to build next and in which order).
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
