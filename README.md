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
- Frontend: guided Next.js product shell under [`web/`](web/README.md). The
  primary zones are «Сейчас / Компания / Спросить / Настройки»;
  the legacy local/operator static UI has been removed and must not return.
- Current implemented foundations include evidence-backed ingestion/extraction,
  workspace-scoped Company Brain and Company World, workspace/GitHub/action
  backend foundations, guarded execution boundaries, and a broad pytest suite.
- Invite-only founder enrollment and login are built: a one-time operator-issued
  link creates the founder, company workspace, owner membership, and revocable
  browser session atomically. Email+password auth uses Argon2id hashes, an
  httpOnly first-party cookie via the same-origin proxy, a durable per-email DB
  throttle, and shared pre-Argon2 admission for login/enrollment/password setup.
  The local single-process backend uses bounded memory counters; an atomic
  Redis backend covers approved multi-worker topology. Only hashes of
  invite/setup/session bearer tokens are stored. An
  already-issued session for a disabled account is revoked on its next
  validation. The operator API key remains
  for server/CI/admin tooling. See the local full-stack path below.
- Founder Briefings persist deterministic briefing history and can generate
  local evidence-backed ActionProposals from Jira/Gmail/Drive/document context.
  GitHub App product-connect plus polling-only live read-sync backend/UI are in
  place. `/settings/integrations/github` includes the primary owner/admin
  self-service wizard:
  App creation, installation, OAuth/PKCE verification, explicit repository
  selection, and per-repository read-only sync. Workspace App secrets and PKCE
  state are protected; temporary OAuth/installation tokens are not persisted.
  Connected owners/admins can revise the repository subset through the same UI
  without interrupting the saved selection before an atomic save; managed
  connections never fall back to environment authorization when their durable
  credential/installation relation is missing.
  Mocked synced-evidence isolation for Company Brain/Briefings and safe
  rate-limit/error observability are covered. Real GitHub completion and the
  first scoped provider read still require human confirmation.
  Company World now has workspace-owned durable people/organization profiles,
  explicit human confirm/dismiss decisions, evidence-backed affiliations and
  sanitized interaction history; viewer remains read-only.
  Local Jira/Gmail/Drive import/list connectors, internal Documents, normalized
  entities, teammate provisioning/setup links, and sanitized request logging are
  in place. The active product now runs locally through `make local`. Remaining
  product gaps are the first human-approved GitHub App real read run, one
  approved generative-AI smoke, email delivery for team/founder invites,
  password reset, and broader multi-user hardening. Workspace AI/privacy
  settings already provide encrypted key lifecycle, model/reasoning/budget
  controls, explicit provider-policy acknowledgement and a synthetic
  no-company-data connection check. `/settings/memory` provides exact,
  preview-bound correction and forgetting for FounderOS-authored documents;
  provider-backed evidence-safe deletion remains a separate gap.

## Local full-stack run path

Diagnose prerequisites, then start the complete product from the repository
root:

```bash
make local-doctor
make local
```

`make local` preserves `.local/` and configured raw storage, starts/reuses PostgreSQL, applies current
Alembic migrations, launches FastAPI on loopback, launches Next.js with the
correct same-origin proxy, and opens the product. Redis is optional for the
current synchronous runtime. The canonical browser origin is
`http://127.0.0.1:3000`; do not substitute `localhost`, because the listener and
one-time invite handoff intentionally use the exact IPv4 loopback address.
Existing founders return through `/login`; an
empty local database opens the private first-founder enrollment path without
printing its bearer token.

The only local runtime file is `.env.local` at the repository root. It is
generated/maintained by the local bootstrap and is not committed. OpenAI,
GitHub, Jira, Gmail and Drive credentials do not belong there: enter and verify
them in `/settings/ai` or `/settings/integrations`. See
[`docs/operations/secrets-and-environment.md`](docs/operations/secrets-and-environment.md).

Run `make local-liveness-smoke` for the public liveness gate. Authenticated
session, workspace and browser gates are deliberately separate:
`make local-session-smoke`, `make local-workspace-smoke`, and
`make local-browser-smoke`; they require the documented credential environment
names and never print their values. Before risky data/schema work, run
`make local-stop` and then `make local-backup`; it proves a database restore and
verifies the raw-storage archive. `make local-stop` never deletes the database
volume, raw storage, or `.local/`. See
[`docs/operations/local-runtime.md`](docs/operations/local-runtime.md) for the
complete runbook and manual troubleshooting fallback. A local bundle remains on
the same failure domain; use
[`docs/operations/disaster-recovery.md`](docs/operations/disaster-recovery.md)
for encrypted independent copies and full restore drills.

### Founder enrollment fallback

Normally `make local` handles the empty-database browser handoff. If automatic
browser opening is intentionally disabled or fails, create a short-lived,
one-time founder link after migrations are current. TTL is 1–168 hours (72 by
default). No raw token persists: the database stores its SHA-256 digest, expiry,
and optional consumption/revocation receipts. The raw URL is printed once and
must be handled like a credential (never paste it into logs, docs, commits, or
chat):

```bash
UV_NO_SYNC=1 uv run python scripts/create_founder_invite.py \
  --base-url http://127.0.0.1:3000 \
  --ttl-hours 72
```

Open the returned URL in the local browser. `/start` creates the founder account,
company workspace, owner membership, and session in one transaction, then opens
the guided `/onboarding` journey. Public signup without an issued invite stays
closed.

If an unconsumed URL is leaked or sent to the wrong person, revoke it by the
returned invite UUID. Unknown, expired, used, and revoked tokens all fail with
the same generic response:

```bash
UV_NO_SYNC=1 uv run python scripts/revoke_founder_invite.py \
  --invite-id <invite-uuid>
```

The operator API key and the `/api/v1/workspaces/bootstrap` endpoint remain for
machine/CI/admin tooling only; they are not part of the founder browser login.

### Teammate onboarding contract

An owner/admin adds a teammate from Settings without choosing that person's
password. For a brand-new local account, the response shows one
`/setup-password#token=...` link once. No email is sent and the recipient's
identity is not verified by this slice, so transfer the link manually over a
trusted direct channel and treat it like a credential. The raw token is not
stored, the link is single-use, and the browser removes it from the address
immediately after capture.

An existing active account with no membership may be attached without changing
its credentials and without issuing a new setup link. If that account already
belongs to another workspace, provisioning fails with 409 and creates no
membership; a future self-accepted invitation flow must handle that case. The
API does not accept `initial_password`, so an inviter can never establish or
replace a teammate's credential.

Public password input is bounded before hashing: login accepts 1–256 characters;
founder enrollment, teammate setup, and password change require 8–256
characters. Invalid/reused setup tokens fail before Argon2 work.

## Local GitHub repository surface

If a local GitHub repository export exists at `.local/repos.json`, FounderOS can
use it as an offline repository surface before or without a verified live
connection. The repo audit and repository inventory read models accept that file
directly when no canonical discovery snapshot exists.

To also write the canonical local discovery layout and a safe repository
allowlist snippet, run:

```bash
uv run python scripts/prepare_github_local_snapshot.py \
  --source .local/repos.json \
  --workspace .local \
  --snapshot-id local-repos-current
```

This writes `.local/discovery/github/local-repos-current/raw/repos.json` and
`.local/github-repositories.env`. The helper is offline-only: it makes no GitHub
provider calls, stores no tokens/secrets, and keeps provider writes disabled by
default.

## Human-gated external operations

The first real GitHub App read and the final external-action-result smoke remain
separate human-approved gates. Normal GitHub setup now starts in
`/settings/integrations/github`; the managed browser-session read is still one
explicit repository-scoped action and does not require a terminal env toggle.
Local startup itself never starts a provider read, external write, or LLM
execution. Asking FounderOS uses the deterministic exact-snapshot path unless
the LLM feature gate and a checked workspace AI configuration with explicit
provider-data-policy acknowledgement are all active. Even then the path is
read-only, sends only bounded
normalized facts, requests `store=false` and falls back locally on any provider
or evidence-validation failure. Provider credentials and GitHub App setup are
workspace-owned product settings with no environment fallback.
See
[`docs/deploy/github-app-first-real-read-run.md`](docs/deploy/github-app-first-real-read-run.md)
and
[`docs/deploy/external-action-result-smoke.md`](docs/deploy/external-action-result-smoke.md).

Use `.env.example` only as a bootstrap/deployment placeholder reference. The
application loads `.env.local`, not a second `.env` file. Never commit local env
files, provider credentials, API keys, encrypted secrets, raw storage, local
database archives, or operator outputs. Moving to local operation also does not
authorize stopping or deleting an older hosted service; restore proof and a
separate explicit human approval are required for every external retirement
phase.

## Development & CI

### Quick local checks

Reproduce the backend CI gates locally only against an explicit dedicated
loopback PostgreSQL test target. Its database name must contain a standalone
test marker (for example, `founderos_test`); the marker is a guard, not proof
that the database is empty or disposable. The operator must provision the
dedicated target. The wrapper refuses the product database from ambient
`DATABASE_URL`, `.env`, or `.env.local` even when the credentials or loopback
hostname spelling differ:

```bash
FOUNDEROS_TEST_DATABASE_URL='<loopback-postgresql-test-url>' make backend-check
```

`make backend-check` validates the target before running frozen dependency
sync, Ruff, Alembic upgrade/schema check, the full pytest suite, and the tracked
secret scan with `APP_ENV=test` and all external execution gates disabled.
The same guard runs from `tests/conftest.py` before the application engine is
imported. Bare pytest therefore refuses to collect tests unless `APP_ENV=test`
and `FOUNDEROS_TEST_DATABASE_URL` identify a dedicated target different from
the product targets in `.env`, `.env.local`, or the ambient environment.
`make check` has the same dedicated-test-target requirement because it includes
the backend target:

```bash
make frontend-check
FOUNDEROS_TEST_DATABASE_URL='<loopback-postgresql-test-url>' make check
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
`uv run alembic upgrade head`, `uv run alembic check`, ruff, pytest,
docs/smoke contract tests, and the tracked-secret scan) against a pinned
Postgres image and the dedicated `ckdos_test` database. It also runs frontend
quality gates from `web/`: `npm test`, `npm run build`,
`npm run typecheck`, and `npm run lint`. All GitHub Actions are pinned by full
commit SHA. Running the backend and frontend commands above reproduces CI
locally. CI readiness checks are offline/read-only and do not call providers,
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
docs/           canonical docs index, decisions, roadmap, changelog, operations guides
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
