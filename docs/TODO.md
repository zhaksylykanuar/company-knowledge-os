# FounderOS TODO

Status: near-term backlog only. Historical completed task ledgers were removed
from this file during the 2026-06-29 repository audit; use `PROGRESS.md`,
`docs/CHANGELOG.md`, and git history for completed-work details.

Every implementation task must follow `AGENTS.md`: short task prompt, scoped
files, no unrelated edits, docs updated in the same task, and focused checks
first.

## Current Checkpoint

Implemented foundations:

- FastAPI backend with canonical `/api/v1` routes, async SQLAlchemy/Postgres,
  Alembic migrations, and one current Alembic head (`e8f9a0b1c2d3`).
- Evidence-first canonical spine: `SourceRecord`, `EvidenceRef`, `Repository`,
  `PullRequest`, `Task`, `ActionProposal`, `ActionExecution`, `Briefing`, and
  `BriefingItem` foundations.
- Email+password founder login on server-side sessions (Argon2id, httpOnly
  first-party cookie through the same-origin Next.js proxy, DB login throttle).
- GitHub manual/provider-token bridge and selected-repo issue/PR sync paths with
  idempotent canonical upserts, DB-level Repository identity guards, and no
  browser-shipped operator key. Local `.local/repos.json` can now bootstrap the
  offline repository surface before product connect.
- Deterministic Company Brain and persisted deterministic Founder Briefings with
  history and evidence refs. No LLM generation is currently implemented.
- Russian Next.js UI under `web/` with centralized copy in `web/lib/messages.ts`.
- Manual private-beta deploy/smoke runbooks; no auto-deploy workflow.

## Next Priority: GitHub Product Connect / Live Sync

Rationale: the workspace is mostly empty until a real data source is connected.
Do not spend the next feature slice on an LLM briefing over fixture/empty data.
Get real GitHub data flowing first, then add LLM narrative on top of validated,
evidence-backed records.

Done when:

- GitHub connect design is recorded in `docs/DECISIONS.md` before coding.
- GitHub App vs OAuth App choice is explicit; prefer GitHub App installation for
  workspace-scoped repository access unless a concrete product constraint says
  otherwise.
- Connection state is workspace-scoped and cannot bind an installation to the
  wrong workspace.
- Token/secret storage model is explicit: do not persist short-lived installation
  access tokens when they can be minted just-in-time; protect the GitHub App
  private key/webhook secret/any user OAuth refresh token with the existing
  secret-encryption posture.
- Repository selection/scope is minimal and read-only by default.
- Webhook signature verification uses the raw body and dedupes deliveries, or a
  polling-only v0 explicitly documents why webhooks are deferred.
- Sync writes through the existing idempotent normalization/upsert path.
- Two-workspace isolation tests cover connection, sync, briefing, and evidence
  dereference behavior.
- `uv run ruff check .`, `uv run alembic upgrade head`, `uv run alembic check`,
  `uv run pytest -q`, frontend checks if touched, and the tracked secret scan are
  green.

## Near-Term Backlog

1. **GitHub product connect / live sync.**
   Local repository surface is prepared from `.local/repos.json`; now build the
   connect flow, connection status UX, initial sync, reconciliation,
   rate-limit handling, and observability. Keep provider writes disabled.

2. **First auth-session production deploy.**
   Use the manual Railway runbooks: backup, deploy, manual `alembic upgrade
   head`, smoke. Do not add auto-deploy or provider-write smoke without explicit
   human approval.

3. **Briefings Chunk 2: LLM narrative over real evidence.**
   Add only after real connected data exists. LLM output must be strict JSON,
   schema-validated, evidence-backed, and persisted only after deterministic
   validation. LLMs must not mutate production data or call providers.

4. **Multi-user / teammate provisioning.**
   Add invite/provisioning flow after single-founder auth/session behavior is
   deployed and stable.

## Known Debts / Watch List

- Retained compatibility substrate (`source_events`, `normalized_activity_items`,
  `ingested_events`) still exists; do not drop it without a scoped migration and
  explicit approval.
- GitHub today is not a product connect flow; provider-token/manual bridge is an
  operator/admin bridge.
- Deploy remains manual and smoke-gated. Do not push, deploy, run migrations on
  production data, or call providers unless the human explicitly requests it.
- Raw storage + Postgres are the source of truth; Obsidian is export-only.

## Documentation Tasks For Future Work

- Update `PROGRESS.md` after every task.
- Add a `docs/DECISIONS.md` entry for durable architecture/security/deploy/data
  model changes.
- Update `docs/ROADMAP.md` only when phase-level direction changes.
- Add user-visible or operational changes to `docs/CHANGELOG.md`.
- Move deferred ideas to `docs/POST_MVP.md`; do not keep long completed ledgers
  in this file.
