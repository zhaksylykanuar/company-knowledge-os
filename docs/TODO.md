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
- GitHub App product-connect foundation: DEC-052 chooses GitHub App
  installation over OAuth/PAT for product onboarding; backend config/status and
  workspace-scoped installation connection recording exist without provider
  calls or persisted installation tokens.
- GitHub App live read-sync foundation: DEC-053 keeps v0 polling-only and
  explicitly repository-scoped; backend can mint just-in-time installation
  tokens, read installation repositories/issues/PRs for requested repositories,
  and persist through existing idempotent normalization without storing tokens or
  performing provider writes. `/github` now renders known repositories with an
  adjacent explicit single-repository read-only sync button for each repo; no
  bulk sync control exists. Tests verify mocked synced data reaches
  Company Brain and persisted deterministic Briefings with evidence while
  workspace B cannot see workspace A's synced canonical state/evidence. Safe
  provider error/rate-limit details surface HTTP status/message/retry metadata
  without leaking tokens or provider payloads.
- Deterministic Company Brain and persisted deterministic Founder Briefings with
  history and evidence refs. No LLM generation is currently implemented.
- Russian Next.js UI under `web/` with centralized copy in `web/lib/messages.ts`.
- Manual private-beta deploy/smoke runbooks; no auto-deploy workflow.

## Next Priority: GitHub App Real Read Run Readiness

Rationale: the workspace is mostly empty until a real data source is connected.
Do not spend the next feature slice on an LLM briefing over fixture/empty data.
The GitHub App backend + product UI sync foundation now exists, mocked synced
evidence is verified across Company Brain/Briefings, and safe live-read
error/rate-limit details are exposed. Next, perform the first real read run only
after explicit human approval, then add LLM narrative on top of validated
records.

Done when:

- DEC-052 remains the product-connect decision: GitHub App installation,
  workspace-scoped binding, backend-only private key/webhook secret, and
  no persisted short-lived installation access tokens.
- DEC-053 remains the live-sync v0 decision: polling-only, admin-triggered,
  explicit repository scope; webhooks deferred until raw-body signature
  verification and delivery dedupe exist.
- Repository selection/scope is minimal and read-only by default; do not add a
  "sync everything" control.
- Sync writes through the existing idempotent normalization/upsert path.
- Two-workspace isolation tests cover connection, sync, briefing, and evidence
  dereference behavior. ✅ covered for mocked GitHub App live sync.
- `uv run ruff check .`, `uv run alembic upgrade head`, `uv run alembic check`,
  `uv run pytest -q`, frontend checks if touched, and the tracked secret scan are
  green.

## Near-Term Backlog

1. **GitHub App real read run readiness.**
   Backend polling-only live read sync, `/github` explicit repo control, and
   mocked synced-evidence isolation tests are in place; safe rate-limit/error
   observability is in place. Next: run the first real scoped read sync only
   after explicit human approval.

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
