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
  offline repository surface before product connect and can be promoted into
  canonical workspace `Repository` rows for the local `/github` UI.
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
- Deterministic Company Brain, dashboard Source Coverage over the existing
  Company Brain endpoint, and persisted deterministic Founder Briefings with
  history, evidence refs, and local source-coverage signals. No LLM generation
  is currently implemented.
- Local-only ActionProposal bridge from briefing items to `internal_todo`
  proposals; approval/execution remains local and external writes are disabled.
- ActionProposals review now has local status filters/counts for proposed,
  approved, rejected, and all proposals; filtering does not call providers or
  mutate backend state.
- Action execution audit events render as structured local timeline entries with
  explicit external-write boundary and no raw provider payload dumps.
- ActionProposals evidence drawer defaults to the first evidence ref in the
  current local review filter and falls back to a safe placeholder when no
  evidence exists.
- ActionProposals review groups proposals by origin (briefing item, GitHub
  issue, internal todo) with counts and an origin badge, surfaces briefing
  `internal_todo` payload metadata (item key, category, severity, next step,
  related entities), and the evidence drawer shows a default-vs-manual context
  hint plus an evidence-ref count.
- ActionProposals review now also has a local origin filter (all sources,
  briefing-derived, GitHub issue, internal todo) composed with the existing
  status filter. Counts are computed within the current status focus and no
  provider calls, backend mutations, external writes, or LLM calls are started.
- ActionProposals review has bulk local review controls for visible `proposed`
  proposals in the current status/origin filter intersection: select visible,
  clear selection, approve selected locally, or reject selected locally. Hidden,
  approved, and rejected proposals are not selected or mutated; provider
  execution and external writes remain disabled.
- Bulk local ActionProposal review is backed by admin-only backend endpoints
  (`bulk-approve` / `bulk-reject`) with per-proposal success/failure results and
  partial-success semantics, rather than frontend-only one-request-per-card
  orchestration. The endpoints dedupe IDs and never start provider execution,
  external writes, or LLM calls.
- Local ActionProposal approve/reject decisions (single and bulk successes) now
  append sanitized no-write audit events to the existing per-proposal timeline,
  so post-bulk review history is visible without creating `ActionExecution`
  rows or calling providers.
- The ActionProposals UI can load that recorded decision history for any decided
  proposal (approved or rejected, GitHub or internal) via a read-only
  "load decision history" control, so the persisted trail is reachable without
  going through the approved-GitHub-issue execution preview.
- Founder Briefing UI now has a local item category filter and a default
  evidence drawer selection from the first visible item, with briefing-specific
  default/manual context and evidence-ref counts. This works only on the loaded
  deterministic briefing and starts no provider calls, external writes, or LLM
  calls.
- Founder Briefing history cards now show persisted coverage summaries
  (repos/open work/evidence/mode) and item/evidence deltas against the currently
  open briefing when one is loaded. This is local comparison over already-loaded
  history data only.
- Founder Briefing now cross-links local `ActionProposal` rows back to briefing
  items, shows per-item/action-status counts, avoids blind duplicate local
  action creation when an open action already exists, and links into `/actions`
  with briefing/proposed focus. This reads local DB state only and starts no
  provider calls, external writes, or LLM calls.
- Dashboard now includes a local private-beta readiness panel backed by the
  existing Company Brain endpoint. It summarizes canonical data/evidence,
  session-auth boundary, manual deploy runbook, deferred provider reads,
  external-writes-off, and LLM boundary without deploying, pushing, calling
  providers, performing external writes, or invoking LLM.
- `/github` now has client-side local repo-surface focus filters over the
  already-loaded repository list: all repos, active, archived, private, and with
  evidence refs. This helps prepare repo review/audit without provider calls,
  bulk sync, external writes, or changing the explicit per-repository read-only
  sync boundary.
- `/audit` now surfaces the deterministic repository audit (all repos) that was
  already computed by `load_repo_audit()` but previously had no UI. It shows
  per-repo facts, risk flags, summary counts, guardrails, and local focus
  filters, and can create local `internal_todo` ActionProposals
  (`source=repo_audit`) per repository. ActionProposals review has a matching
  `audit` origin. Read-only: no network calls, provider writes, or LLM.
- `/audit` can now import structured JSON findings from an external/full
  repo-audit result through the backend endpoint
  `POST .../actions/proposals/import-repo-audit` into local `internal_todo`
  ActionProposals (`source=repo_audit_import`) with per-finding partial
  failures. Valid findings must include `repository_full_name` (`owner/repo`)
  and `evidence_refs`; known secret-like fragments in imported text are
  redacted. This is local-only and starts no provider calls, external writes,
  or LLM.
- The `/audit` import form now previews parsed findings before import with
  per-finding valid/invalid status mirroring the backend rules, select-all-valid
  and clear-selection controls, and inline per-finding backend failures after a
  partial import, including subset-selection index remapping (only failed rows
  stay selected for retry, pasted text is preserved). Preview and selection are
  client-side only: no provider calls, external writes, or LLM.
- `/actions` now separates audit-origin proposals by audit source: deterministic
  local repo audit vs imported external audit. The audit origin filter has a
  local audit-source subfilter, source-specific badges, richer payload metadata,
  and query support (`audit_source=deterministic|imported`) while bulk selection
  and the evidence drawer follow the final visible subset. No provider calls,
  external writes, or LLM are started.
- Russian Next.js UI under `web/` with centralized copy in `web/lib/messages.ts`.
- Manual private-beta deploy/smoke runbooks; no auto-deploy workflow.

## Next Priority: Founder-facing coverage and briefing polish

Rationale: GitHub source foundation is sufficient for this phase and real
provider reads are intentionally deferred until explicit human approval. The next
slice should make the already-loaded canonical data more useful to the founder:
clear source coverage, deterministic briefing polish, and next-step visibility
without adding provider calls or LLM generation yet.

Done when:

- DEC-052 remains the product-connect decision: GitHub App installation,
  workspace-scoped binding, backend-only private key/webhook secret, and
  no persisted short-lived installation access tokens.
- DEC-053 remains the live-sync v0 decision: polling-only, admin-triggered,
  explicit repository scope; webhooks deferred until raw-body signature
  verification and delivery dedupe exist.
- Repository selection/scope stays minimal and read-only by default; do not add a
  "sync everything" control while GitHub is deferred.
- Sync writes through the existing idempotent normalization/upsert path.
- Two-workspace isolation tests cover connection, sync, briefing, and evidence
  dereference behavior. ✅ covered for mocked GitHub App live sync.
- `uv run ruff check .`, `uv run alembic upgrade head`, `uv run alembic check`,
  `uv run pytest -q`, frontend checks if touched, and the tracked secret scan are
  green.

## Near-Term Backlog

1. **Action review polish (local approval only).**
   Briefing items can now create local `internal_todo` proposals with evidence.
   Local status filters and structured execution audit timeline are in place.
   Evidence drawer defaults, origin grouping (briefing/GitHub/internal) with an
   origin badge, briefing `internal_todo` payload detail, and evidence
   drawer default-vs-manual context + evidence-ref count are in place. A local
   origin filter now composes with the status filter, and bulk local approve/
   reject controls are available for visible `proposed` proposals through
  backend bulk endpoints with partial-success results. Local approve/reject
  decisions now write no-provider audit events to the existing timeline, and the
  UI can load that decision history for any decided proposal (approved or
  rejected, GitHub or internal) via a read-only control. Next: continue
  Founder-facing coverage/briefing polish or deployment readiness while keeping
  provider writes and AI generation disabled.

2. **Founder-facing briefing polish.**
   Deterministic briefing cards, source coverage signals, item category filter,
   default evidence drawer, richer history comparison, and briefing-to-local-
   action bridge are in place. Briefing/action cross-links are now in place:
   existing local actions are summarized on briefing items, duplicate creation is
   guarded for open actions, and `/actions` can open with briefing/proposed
   focus. The `/audit` external-import UX is now hardened with a pre-import
   preview, per-finding validity, select-all-valid/clear controls, and inline
   per-finding backend failures. `/actions` also now distinguishes
   deterministic vs imported audit-origin proposals with a local subfilter,
   badges, query focus, and richer payload metadata. Next: consider deployment
   readiness or a dashboard card linking to `/audit`, while keeping provider
   writes and AI generation disabled.

3. **First auth-session production deploy.**
  Dashboard now surfaces a local private-beta readiness checklist, but actual
  production launch still uses the manual Railway runbooks: backup, deploy,
  manual `alembic upgrade head`, smoke. Do not add auto-deploy or
  provider-write smoke without explicit human approval.

4. **GitHub App real read run readiness (deferred).**
  Backend polling-only live read sync, `/github` explicit repo control, and
  mocked synced-evidence isolation tests are in place; safe rate-limit/error
  observability is in place. `/github` now adds local repo-surface filters so
  the founder can focus active/private/evidence-backed repos before choosing a
  scoped per-repo read. Run the first real scoped read sync only after explicit
  human approval.

5. **Multi-user / teammate provisioning.**
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
