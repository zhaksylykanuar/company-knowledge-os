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
  Alembic migrations, and one current Alembic head (`c5d6e7f8a9b0`).
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
- The Living Headquarters foundation is in place (DEC-081): the everyday shell
  is now `Штаб / Мир / Миссии`, with `Радары / Настройки` backstage and still
  reachable on mobile. `/dashboard` leads with one evidence-aware mission, its
  explanation, a compact real-data Company World, a current-snapshot signal
  feed, and a small world pulse. It distinguishes empty/error/partial states,
  marks truncated counts as lower bounds, and does not call a current snapshot
  a since-last-visit delta. Proposal evidence refs are presented as declared
  source references rather than server-verified facts. This slice changes no
  backend API, schema, provider/write gate, RBAC, or LLM path.
- The full Living World surface is in place (DEC-082): `/company-brain` is now
  one command bar, one current review rail, a filterable real-data world scene,
  and one contextual profile inspector. Existing Company Map affiliation,
  candidate-resolution, evidence, window, idempotency, and RBAC contracts remain
  authoritative. `Штаб` mini-map selections and evidence-backed world missions
  deep-link to an exact current-workspace profile through an opaque selector;
  email/domain-shaped candidate keys are never written into the URL, and stale
  or foreign selectors resolve to no entity. Touchpoints stay local history of
  their routed parent profile. Candidate totals and candidate-organization
  people counts are lower bounds when the Gmail window is truncated, including
  an explicitly partial zero state. Canonical Company Brain/entities details
  load only after their disclosure opens. Frontend-only: no schema,
  provider call/write, external action, RBAC, or LLM change.
- The Missions decision room is in place (DEC-083): `/actions` now leads with a
  compact bounded queue and exactly one active human decision console. Why-now,
  consequence, evidence, local approve/reject, external preview, and history
  stay scoped to that active mission; changing missions resets transient
  preview/confirmation state. Pending provider operations lock mission,
  workspace, and shell navigation; stale cross-workspace responses are ignored,
  and a sanitized successful outcome stays pinned through refresh. A later
  audit-history read failure remains a separate warning rather than making the
  completed action look retryable. The page
  loads one mixed-status window of at most 100 proposals, filters it locally,
  and labels its pulse as loaded-window metrics rather than workspace totals.
  Bulk review requires an explicit consequence disclosure. Existing
  ActionProposal RBAC, persisted decision audit, evidence, receipts, and
  external-write gate remain unchanged; no provider call/write or LLM starts
  automatically.
- The desktop product reference is in place (DEC-084/DEC-085): `/demo` is a
  gated, synthetic, API-free Living Command Center, not a tour. One priority,
  three pulse metrics, the next decisions, and recent signals form the default
  surface; sources, evidence, people, customer history, documents, the decision,
  and its receipt use one drawer/modal layer. A deterministic session-only
  assistant answers from the same synthetic fixtures, exposes citation chips,
  and can navigate or prepare a decision without executing it. The completed
  simulation updates the headquarters and queue together; promoted and queued
  missions open their own source-scoped context cards instead of a generic
  detail dump. It is not production
  data and does not prove source or LLM readiness. Development enables the exact
  public route locally; production requires `FOUNDEROS_DEMO_ENABLED=true`.
  Desktop 1280×720 is the only contract; mobile/tablet remain out of scope.
- Post-auth Command Mode is in place (DEC-078): all five primary zones lead
  with one current mission, the next useful control, and its expected result.
  Secondary forms, filters, readiness diagnostics, evidence, and technical
  boundaries remain accessible through progressive disclosure. Source and
  decision guidance is role-aware and distinguishes failed/attention states
  without inventing progress. This is a frontend-only interaction change; API,
  persistence, RBAC, provider/write, and LLM contracts are unchanged. Static
  frontend acceptance is green; the older tool-blocked five-zone UX-03 pass was
  not reused as evidence, while newer `Штаб`, GitHub radar, and full `Мир`
  slices each have their own targeted desktop/mobile browser acceptance.
- The first provider-specific Source Command Center is in place on `/github`
  (DEC-079): one role-aware mission, a three-step source flow, four bounded
  repository metrics, one selected-repository read action, a compact work pulse,
  and progressive disclosure for readiness/provenance details. Repository and
  issue/PR counts are explicitly the loaded sample, viewer guidance stays
  read-only, a non-connected installation cannot enable sync, and a partial
  read refreshes available work without being labelled as full success.
  Authenticated visual QA passed on real local data at 1280×720 and 390×844
  without horizontal overflow. This is the reference interaction grammar for
  later Jira/Gmail/Drive detail-page work, not a generic connector engine.
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
- GitHub App setup is now workspace-managed self-service (DEC-080). Owner/admin
  uses the `/github` wizard to create a private read-only App, install it,
  complete OAuth + PKCE user verification, and save an explicit non-empty
  repository subset. Credentials and the PKCE verifier are encrypted; state is
  hashed; OAuth and installation tokens are never persisted. The connection is
  disabled until selection completes, and viewer remains read-only. The old
  env/manual connection endpoints are compatibility-only and fail closed.
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
- `/github` now owns the primary setup flow. Legacy env readiness remains hidden
  compatibility diagnostics; it does not define managed setup readiness. The
  wizard itself performs no provider read until the human confirms GitHub,
  verifies the installation, saves the repository subset, and later presses the
  separate one-repository sync action.
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
- Local readiness is now exposed through the canonical doctor/start/smoke/
  backup/stop commands and `docs/operations/local-runtime.md`; provider, write,
  and LLM boundaries remain visible in their relevant product surfaces.
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
- Canonical local runtime runbook and one-command lifecycle (DEC-077):
  `make local-doctor`, `make local`, `make local-smoke`, `make local-backup`,
  and `make local-stop`.
- Manual final external-action-result smoke runbook:
  `docs/deploy/external-action-result-smoke.md` documents the one-action,
  human-approved write smoke needed to prove the final MVP flow step after a
  verified local stack and read-only provider proof. It is not part of normal
  local smoke, CI, provider-read, provider-token setup, or LLM paths.
- Basic application request logging is now in place (DEC-072): a sanitized ASGI
  `RequestLoggingMiddleware` logs method/path/status/duration at
  `FOUNDEROS_LOG_LEVEL` (default `INFO`) without query values, headers, bodies,
  tokens, or provider payloads. No new dependency, table, migration, provider
  call, external write, or LLM.
- A deterministic offline MVP completion audit is now in place
  (`app/services/mvp_completion_audit.py` + `scripts/mvp_completion_audit.py` +
  `tests/test_mvp_completion_audit.py`). It maps every §1.5 MVP requirement and
  §1.4 main-flow step to authoritative in-repo evidence and separates
  locally-complete work from the human-gated remainder. Current result:
  repository evidence is present for all 31 items (27/27 local and 4/4
  code-ready human/runtime-gated). The offline audit cannot attest runtime, but
  the live local lifecycle has now passed separately. Full external MVP remains
  unproven until the first GitHub connect, first scoped provider sync, and first
  real external action result are each proven with human approval. Run
  `uv run python scripts/mvp_completion_audit.py` to re-check before claiming
  completion.
- `make local-readiness` is the sanitized local repository-evidence report;
  `make release-handoff` and `scripts/private_beta_release_handoff.py` are
  compatibility aliases. The report combines local git state, MVP completion
  audit, GitHub App real-read preflight, and ordered human-gated next steps
  without deploy, provider calls, external writes, database access, secret
  reads, or LLM.

## Next Priority / Near-Term Backlog

1. **Promote the minimal command center into the real headquarters.**
   Execute `LC-00/LC-01` in
   [`LIVING_COMMAND_CENTER_CHECKLIST.md`](LIVING_COMMAND_CENTER_CHECKLIST.md):
   define and implement one read-only workspace-scoped `HeadquartersSnapshot`
   over existing data, move deterministic ranking to that service, and prove
   the contract before replacing `/dashboard`. No migration, provider call, LLM
   or write belongs in this first ticket. `/demo` remains reference-only.

2. **Add the first real read-only company assistant contract.**
   Introduce a bounded workspace-scoped query endpoint over existing read models
   with deterministic intents first: current priority, why-now, company/person,
   sources, briefing, waiting decisions, and evidence. Normalize citations and
   return `is_live`, `llm_used`, warnings, suggestions, and action proposals;
   do not persist chat, call an LLM, or mutate data in this slice. Conversation
   history, retrieval, generation, and writes require separate schema/security
   decisions. Detailed acceptance is `LC-07` in the command-center checklist.

3. **Finish the radar loop one provider at a time.**
   `/github` remains the reference command center and the next external gate is
   still one founder-approved, repository-scoped read through its UI wizard. Then
   bring Gmail, Drive, and Jira to the same setup → scoped read → visible result →
   receipt pattern. No bulk/background sync, provider write, LLM run, or hosted
   change is authorized by this backlog item.

4. **Add a real company-change boundary.**
   The new headquarters honestly shows a current evidence snapshot. Design the
   smallest persisted snapshot/event contract that can prove "since your last
   visit" changes, dedupe them, link each one to workspace-resolved evidence, and
   close a mission with a receipt. This requires a separate schema/data review and
   must not be simulated from browser-local timestamps. This is `LC-06` and
   remains schema/data-review gated.

## Known Debts / Watch List

- **Local backup continuity:** the current private bundle passed checksum,
  matching-major restore, Alembic/count, raw-digest and credential-decryptability
  proof. Keep creating a new verified bundle before future schema/data-risk work;
  a timestamped but unverified archive is never a rollback boundary.
- **Hosted retirement gate:** do not stop services, remove domains, delete a
  database/volume, or delete a project without separate explicit approval after
  a final logical archive passes restore proof and an observation window.
- **Future public auth topology:** the process-local per-IP login limiter is
  sufficient only for the current single-process loopback runtime. Any future
  public/multi-worker target requires shared edge/Redis limiting, trusted-proxy
  verification, monitoring, backups, and a new durable hosting decision.
- Teammate setup delivery is still manual over a trusted direct channel and does
  not verify the recipient. The authenticated admin endpoint also returns `409`
  when an email belongs to an account in another workspace; replace this with a
  recipient-accepted invitation flow before broader multi-tenant rollout.
- Retained compatibility substrate (`source_events`, `normalized_activity_items`,
  `ingested_events`) still exists; do not drop it without a scoped migration and
  explicit approval.
- GitHub App self-service code is complete locally, but the first real managed
  setup and provider read still require founder confirmation in GitHub plus one
  explicit scoped sync. Manual provider-token and env installation paths remain
  compatibility bridges, not the preferred product setup.
- Hosted operation is deferred. Do not push, deploy, mutate external data,
  retire external resources, or call providers unless the human explicitly
  requests the exact action.
- Raw storage + Postgres are the source of truth; Obsidian is export-only.

## Documentation Tasks For Future Work

- Update `PROGRESS.md` after every task.
- Add a `docs/DECISIONS.md` entry for future durable architecture/security/
  deploy/data-model changes.
- Update `docs/ROADMAP.md` only when phase-level direction changes.
- Add user-visible or operational changes to `docs/CHANGELOG.md`.
- Move deferred ideas to `docs/POST_MVP.md`; do not keep long completed ledgers
  in this file.
