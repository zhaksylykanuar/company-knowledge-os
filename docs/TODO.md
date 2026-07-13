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
  Alembic migrations, and one current Alembic head (`b4d5e6f7a8c9`).
- Evidence-first canonical spine: `SourceRecord`, `EvidenceRef`, `Repository`,
  `PullRequest`, `Task`, `ActionProposal`, `ActionExecution`, `Briefing`, and
  `BriefingItem` foundations.
- Normalized-entities read surface is now in place (DEC-070): the endpoint
  `GET /api/v1/workspaces/{id}/company-brain/entities` projects canonical
  Company Brain rows into an evidence-backed entity list + summary, and the
  dashboard `NormalizedEntitiesPanel` renders that list with type/provider
  breakdowns and source refs. This is a read-only projection (no
  `NormalizedEntity` table yet) and starts no provider calls, sync, external
  writes, or LLM.
- A dedicated navigable Company Brain view is now in place (DEC-071): the
  `/company-brain` page + sidebar entry compose the Company Brain and
  normalized-entities panels so the founder can reach the MVP "See Company Brain
  entities" step directly. The normalized-entities panel also has a client-side
  `entity_type` focus filter over the already-loaded projection. Read-only; no
  new data path, provider calls, sync, external writes, or LLM.
- Durable Company World is in place (DEC-073/DEC-074): `/company-brain` leads
  with the workspace-membership-
  gated, workspace-scoped `company-map` projection. It shows confirmed
  workspace members plus
  evidence-backed external-contact and organization candidates, confirmed
  durable profiles, and sanitized Gmail interactions. Member+ can confirm or
  dismiss a server-resolved candidate idempotently; viewer remains read-only.
  Candidate roles are never inferred as customer/decision maker;
  the newest-100-message window and truncation are visible; raw bodies/snippets
  are excluded. Existing RBAC is preserved: viewer can read workspace data but
  cannot confirm/mutate; cross-workspace access is rejected. Confirmation is a
  local canonical write with source provenance; no provider call, external
  write, raw-source mutation, or LLM path was added.
- The UX-02 spatial Company World board is in place (DEC-076): the founder's
  company is the visual center, while team, confirmed network, and discovery
  candidates occupy distinct contours. A confirmed person is placed under an
  organization only when exact durable affiliation fields agree and a human-
  authored relationship exists; similarity is never drawn as fact. The focused
  inspector keeps profile-local touchpoints visible while evidence and
  technical boundaries stay collapsed until requested. Candidate resolution
  asks one plain-language question at a time without changing member+/viewer,
  version, idempotency, or server-evidence contracts. This frontend-only slice
  adds no backend API, migration, provider call/write, or LLM path. Local
  acceptance is complete: 272 frontend tests plus typecheck/lint/build, 537
  backend tests plus Ruff/Alembic, and desktop 1024/1280 px / mobile 390×844
  browser QA without overlap, overflow, console warnings or console errors.
- Guided shell and founder onboarding are in place (DEC-075): an operator-issued
  one-time `/start` link atomically creates the founder/company/owner membership
  and session; `/onboarding` derives source/map/team readiness from real data;
  multiple companies require explicit selection. `/dashboard` is now «Сегодня»
  with one deterministic next move and three signals, while five primary zones
  replace the old flat technical navigation. Role-gated admin operations remain
  available in context. A new teammate automatically receives one one-time setup
  link and chooses their own password; the inviter cannot set credentials.
  Public signup and email delivery stay closed.
- Email+password founder login uses server-side sessions (Argon2id, httpOnly
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
- `/github` also surfaces first real-read readiness from already-loaded local
  state: GitHub App env configured/missing, workspace-scoped installation
  connection state, local repository surface count, blockers, and the next human
  step. This mirrors the offline preflight without starting sync, provider read,
  provider write, secret read, external write, or LLM.
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
- ActionProposals review now also includes a local readiness summary over the
  already-loaded list: needs-decision proposals, approved GitHub issue proposals
  ready for execution preview, local-only internal follow-ups, proposals missing
  evidence refs, and proposals with reported execution receipts. The summary
  gives a deterministic next-step hint and starts no execute call, sync,
  provider call, external write, or LLM.
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
- The legacy global `/audit` product page and dashboard overview are retired
  (DEC-073): filesystem Company Brain preview endpoints now require the
  operator API key and reject browser sessions. The workspace-scoped backend
  endpoint `POST .../actions/proposals/import-repo-audit` remains available for
  importing sanitized findings into local `internal_todo` ActionProposals
  (`source=repo_audit_import`) with per-finding partial failures. Valid findings
  must include `repository_full_name` (`owner/repo`)
  and `evidence_refs`; known secret-like fragments in imported text are
  redacted. This is local-only and starts no provider calls, external writes,
  or LLM.
- `/actions` now separates audit-origin proposals by audit source: deterministic
  local repo audit vs imported external audit. The audit origin filter has a
  local audit-source subfilter, source-specific badges, richer payload metadata,
  and query support (`audit_source=deterministic|imported`) while bulk selection
  and the evidence drawer follow the final visible subset. No provider calls,
  external writes, or LLM are started.
- The private-beta readiness panel now includes a manual deploy/smoke runbook
  checklist from the deploy docs: local gates, Postgres backup, manual
  migration, split backend/frontend services, read-only smoke, and rollback
  boundary. It is display-only and starts no deploy, push, provider call,
  external write, production data mutation, or LLM.
- The `/dashboard` source-coverage panel now also shows a local breakdown from
  the already-loaded Company Brain payload: closed work (closed issues / merged
  PRs), recent-activity count, repositories with vs. without source refs, and
  evidence counts by kind. No new endpoints, provider calls, external writes, or
  LLM are added.
- The same source-coverage panel now derives deterministic "what to check next"
  guidance from the already-loaded Company Brain payload: canonical data
  readiness, evidence gaps, open-work review, live-provider boundary, and AI
  boundary. It is display-only and starts no sync, provider call, external write,
  deploy, or LLM.
- Connector framework registry is now in place (DEC-056): `GET
  /workspaces/{id}/connectors` and `/connectors` show the MVP provider set
  (`github`, `jira`, `gmail`, `drive`), local connection counts, available vs.
  planned status, and read-only/no-provider-call/no-secret-read boundaries.
  GitHub links to `/github`, Jira links to `/jira`, Gmail links to `/gmail`,
  and Google Drive links to `/drive`; the MVP provider set now has local
  product surfaces.
- Jira local connector foundation is now in place (DEC-057): `GET
  /workspaces/{id}/jira/issues`, admin-only `POST
  /workspaces/{id}/jira/issues/import`, and `/jira` support local-only
  pasted/exported issue JSON import into canonical `SourceRecord` + `Task` rows
  with evidence refs. No Jira provider call, sync, external write, LLM, or
  secret read is performed.
- Gmail local connector foundation is now in place (DEC-058): `GET
  /workspaces/{id}/gmail/messages`, admin-only `POST
  /workspaces/{id}/gmail/messages/import`, and `/gmail` support local-only
  pasted/exported message JSON import into canonical `SourceRecord` (message
  record type) rows with evidence refs and no persisted raw body. No Gmail
  provider call, sync, external write, LLM, or secret read is performed.
- Google Drive local connector foundation is now in place (DEC-059): `GET
  /workspaces/{id}/drive/files`, admin-only `POST
  /workspaces/{id}/drive/files/import`, and `/drive` support local-only
  pasted/exported file metadata JSON import into canonical `SourceRecord`
  (file record type) rows with evidence refs and no persisted raw document
  body. No Drive provider call, sync, external write, LLM, or secret read is
  performed.
- Workspace Company Brain and Dashboard Source Coverage now surface aggregate
  local connector SourceRecord coverage (DEC-060): `source_records.total`,
  provider counts, and record-type counts across GitHub/Jira/Gmail/Drive are
  visible without exposing raw payloads, email bodies, document contents,
  provider calls, sync, external writes, or LLM.
- The deterministic Founder Briefing now includes a `connector-source-coverage`
  item (DEC-061) built from the Company Brain `source_records` aggregate, so
  local Jira/Gmail/Drive imports are visible in the briefing flow (not only on
  the dashboard). Aggregate-only: no raw payloads, provider calls, sync,
  external writes, or LLM.
- Company Brain now promotes task-shaped local Jira records (DEC-062):
  canonical `Task(source_provider='jira')` rows appear in `work.issues`,
  `work.recent`, issue summary counts, and evidence with provider/project scope.
  Gmail/Drive are not coerced into tasks.
- Company Brain now exposes Gmail messages and Drive files as first-class read
  sections (DEC-063): `communications.messages` and `documents.files` render
  sanitized local SourceRecord payload fields with source refs, without raw
  email/document bodies, provider calls, sync, external writes, or LLM.
- Founder Briefing now summarizes first-class non-GitHub Company Brain read
  models (DEC-064): local Jira work, Gmail message signals, and Drive file
  signals appear as additive evidence-backed briefing items. The generator reads
  only local Company Brain sections/source refs and adds no provider calls,
  sync, external writes, raw body/content rendering, or LLM.
- Persisted Founder Briefings can now generate local non-GitHub action
  proposals (DEC-065): member+ users can turn evidence-backed Jira/Gmail/Drive
  briefing items into local `internal_todo` ActionProposal rows through the
  backend endpoint and Briefing UI bulk control. Missing evidence and existing
  open actions are skipped; no provider calls, sync, external writes, secret
  reads, or LLM are started. Internal document context now participates in the
  same bridge (DEC-069): `internal-document-context` can create a local
  evidence-backed follow-up ActionProposal when a persisted briefing item has
  document evidence refs, without copying raw document body text.
- Internal Documents module is now implemented (DEC-066): workspace-scoped
  `Document` CRUD + search API (`/api/v1/workspaces/{id}/documents`), a
  `/documents` frontend page (list/search/create/detail), and Company Brain
  `documents.notes` integration with evidence. Documents store `body_markdown`
  plus a deterministic plain-text projection; no provider calls, external
  writes, secret reads, or LLM. Founder Briefing now also surfaces those notes
  as `internal-document-context` (DEC-067), without copying raw markdown/body
  text. Document version history is now implemented (DEC-068): create and
  effective updates append immutable local `DocumentVersion` snapshots, empty
  or idempotent PATCH requests are no-ops, the API exposes
  `/documents/{document_id}/versions`, and `/documents` detail renders
  selectable version snapshots with markdown body + metadata. The `/documents`
  detail view now also supports in-product edit (title, body, tags, status) and
  guarded delete through the existing PATCH/DELETE routes, so the Documents
  module CRUD is reachable end-to-end and version history grows past version 1
  through the UI. NormalizedEntity linkage remains a later slice.
- Russian Next.js UI under `web/` with centralized copy in `web/lib/messages.ts`.
- Manual private-beta deploy/smoke runbooks; no auto-deploy workflow.
- Manual final external-action-result smoke runbook:
  `docs/deploy/external-action-result-smoke.md` documents the one-action,
  human-approved write smoke needed to prove the final MVP flow step after
  deploy and read-only provider proof. It is not part of normal read-only smoke,
  CI, provider-read, provider-token setup, or LLM paths.
- Basic application request logging is now in place (DEC-072): a sanitized ASGI
  `RequestLoggingMiddleware` logs method/path/status/duration at
  `FOUNDEROS_LOG_LEVEL` (default `INFO`) without query values, headers, bodies,
  tokens, or provider payloads. No new dependency, table, migration, provider
  call, external write, or LLM.
- A deterministic offline MVP completion audit is now in place
  (`app/services/mvp_completion_audit.py` + `scripts/mvp_completion_audit.py` +
  `tests/test_mvp_completion_audit.py`). It maps every §1.5 MVP requirement and
  §1.4 main-flow step to authoritative in-repo evidence and separates
  locally-complete work from the human-gated remainder. Current result: local
  scope complete (29/29), full MVP not complete because staging/prod deployment
  and the first real external action result are human/external gated. Run
  `uv run python scripts/mvp_completion_audit.py` to re-check before claiming
  completion.
- A sanitized private-beta release handoff report is now in place
  (`scripts/private_beta_release_handoff.py` / `make release-handoff`). It
  combines local git state, MVP completion audit, GitHub App real-read preflight,
  and ordered human-gated next steps without deploy, provider calls, external
  writes, database access, secret reads, or LLM.

## Next Priority: Human-gated deploy and read-only smoke

Rationale: UX-01 and UX-02 now provide the guided first-run loop and the spatial
Company World surface over the existing evidence and write boundaries. Local
UX-02 acceptance and the offline sanitized release handoff are complete on a
clean exact commit. Exact commit `85b5e1f` is published in Draft PR #33 and all
GitHub checks are green. Do not expand the local UX again; resume the explicitly
human-gated private-beta deployment path once a restorable backup boundary is
available.

Done when:

- [x] Desktop 1024/1280 px, keyboard/focus and 390×844 mobile browser acceptance
  passes for the current UX-02 snapshot; controls remain at least 44 px and the
  CSS preserves the reduced-motion presentation boundary.
- [x] Backend regression plus the repository's final Ruff, Alembic, secret, and
  whitespace gates pass for the same reviewed snapshot.
- [x] `make release-handoff` is run against that exact commit and its sanitized
  output is attached for human review.
- [x] The reviewed feature branch is published, Draft PR #33 is open, and all
  backend/frontend/dependency-review/CodeQL checks are green.
- [ ] Establish a restorable production Postgres backup boundary. The current
  Railway Trial plan reports `maxBackupsCount=0`, so no managed snapshot can be
  created; either enable Railway backup entitlement and verify the snapshot, or
  separately approve and restore-test a logical backup procedure.
- [x] Compatible application rollback source `541a0df` is preserved in the
  published branch history and build-verified against production head
  `a2b3c4d5e6f7`: backend 316 tests/Ruff and frontend 80 tests/build/typecheck/
  lint are green. The running Railway archive still has no exact source SHA, and
  the rollback frontend has two moderate dependency findings, so this source is
  bounded to emergency rollback.
- The human-approved Railway sequence completes backup, migration, deploy, and
  read-only smoke without silently widening provider or write scope.
- Distinct client-IP behavior behind Railway/Next is proven with a two-client
  smoke, or the process-local admission boundary is replaced with an approved
  shared edge/Redis limiter before public launch.
- Provider writes, live LLM generation, and other production mutations remain
  separately approved gates.

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
  rejected, GitHub or internal) via a read-only control. The `/actions` review
  page now has a local readiness summary for needs-decision proposals,
  preview-ready approved GitHub proposals, local-only follow-ups, missing
  evidence, and reported execution receipts. Further polish is deferred until
  after release/deploy evidence; provider reads, writes, and AI generation
  remain separately approved gates.

2. **Founder-facing briefing polish.**
   Deterministic briefing cards, source coverage signals, item category filter,
   default evidence drawer, richer history comparison, and briefing-to-local-
   action bridge are in place. Briefing/action cross-links are now in place:
   existing local actions are summarized on briefing items, duplicate creation is
   guarded for open actions, and `/actions` can open with briefing/proposed
   focus. `/actions` also now distinguishes
   deterministic vs imported audit-origin proposals with a local subfilter,
   badges, query focus, and richer payload metadata. The unsafe global audit
   page/overview are retired; the private-beta readiness panel displays the manual
   deploy/smoke runbook phases without executing them. The `/dashboard` source-
   coverage panel now also has a local breakdown (closed work, recent activity,
   repos with/without source refs, evidence-by-kind) plus deterministic next-step
   guidance for data/evidence/open-work/provider/AI boundaries. `/connectors`
   now surfaces the MVP connector registry for GitHub/Jira/Gmail/Drive, and
   `/jira`, `/gmail`, and `/drive` provide local-only connector import/list
   paths. Company Brain/Dashboard source coverage now also exposes aggregate
   local connector SourceRecord counts, and the deterministic Founder Briefing
   now includes a connector-source-coverage item (DEC-061). Jira issues are now
   first-class Company Brain work items (DEC-062), and Gmail/Drive have
   first-class read sections (DEC-063). Internal document context can now also
   generate a local evidence-backed ActionProposal through the same persisted
   briefing bridge (DEC-069). `/actions` now turns those generated proposals into
   a clearer local review/readiness loop with counts for pending decisions,
   preview-ready GitHub issue proposals, local-only follow-ups, missing evidence,
  and reported execution receipts. Further briefing polish is deferred until
  after release/deploy evidence; provider reads, writes, and AI generation
  remain separately approved gates.

3. **First auth-session production deploy.**
  Dashboard now surfaces a local private-beta readiness checklist plus manual
  deploy/smoke runbook phases, but actual production launch still uses the
  manual Railway runbooks: backup, deploy, manual `alembic upgrade head`, smoke.
  After deploy and read-only proof, the final external action result is covered
  by `docs/deploy/external-action-result-smoke.md`. Do not add auto-deploy or
  provider-write smoke without explicit human approval. Before handoff, run
  `make release-handoff` and attach only the sanitized output to the human
  review.

4. **GitHub App real read run readiness (deferred).**
  Backend polling-only live read sync, `/github` explicit repo control, and
  mocked synced-evidence isolation tests are in place; safe rate-limit/error
  observability is in place. `/github` now adds local repo-surface filters so
  the founder can focus active/private/evidence-backed repos before choosing a
  scoped per-repo read. An offline readiness gate now exists (DEC-054):
  `github_app_real_read_run_readiness()`, the presence-only preflight
  `scripts/github_app_real_read_run_preflight.py`, offline unit tests, the
  runbook `docs/deploy/github-app-first-real-read-run.md`, and a matching
  display-only readiness section on `/github`. Current state
  (verified): the real read run is externally blocked — GitHub App env is unset
  and the installation connection is not recorded; unauthenticated network to
  `api.github.com` is reachable and the local repo surface (25) is present. Next
  (human): set GitHub App credentials, record the
  installation connection, then run one explicit scoped read sync only after
  explicit human approval.

5. **Multi-user / teammate provisioning.**
  Local teammate membership foundation is in place (DEC-055):
  owners/admins can list workspace members and create local `admin`/`member`/
  `viewer` memberships without sending email, calling an identity provider, or
  granting `owner`. Duplicate memberships, disabled users, and non-admin
  provisioning are rejected. `/settings` now surfaces the local members list and
  owner/admin local-provisioning form with explicit no-email/no-provider-write
  copy; viewer/member roles see read-only state. A brand-new account always gets
  exactly one one-time `/setup-password#token=...` link; only its token digest is
  stored, the teammate sets the password, and concurrent/repeated use is rejected.
  The inviter cannot submit an initial password. An existing account that already
  belongs to another workspace is not silently attached: the endpoint returns
  `409`, including under concurrent A/B attach. Next: build recipient-verified,
  self-accepted workspace invitations plus email/password-reset delivery after
  deploy stability.

## Known Debts / Watch List

- **Production backup gate:** Railway Trial currently permits zero volume
  backups. Production Alembic is `a2b3c4d5e6f7`, while reviewed code expects
  `b4d5e6f7a8c9` across 11 migrations. Do not enter the maintenance window or
  migrate until a restorable backup path is verified.
- **Application rollback limitation:** the running deployment has no recorded
  source SHA and its retained image is no longer rollback-eligible on Trial.
  Compatible source `541a0df` is preserved and build-verified, but is an
  emergency rollback build rather than proof of the exact old archive.
- **Public-deploy auth gate:** the process-local per-IP login limiter currently
  keys on `request.client.host`. Railway/Next proxy semantics have not yet proved
  that two external client IPs remain distinct. Keep one Uvicorn process and do
  not expose this as a public security boundary until a two-client deployment
  smoke confirms trusted forwarding or a shared edge/Redis limiter replaces it.
- Teammate setup delivery is still manual over a trusted direct channel and does
  not verify the recipient. The authenticated admin endpoint also returns `409`
  when an email belongs to an account in another workspace; replace this with a
  recipient-accepted invitation flow before broader multi-tenant rollout.
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
- Add a `docs/DECISIONS.md` entry for future durable architecture/security/
  deploy/data-model changes.
- Update `docs/ROADMAP.md` only when phase-level direction changes.
- Add user-visible or operational changes to `docs/CHANGELOG.md`.
- Move deferred ideas to `docs/POST_MVP.md`; do not keep long completed ledgers
  in this file.
