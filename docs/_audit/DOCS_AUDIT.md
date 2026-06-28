# Documentation Audit Before Consolidation

Date: 2026-06-23
Branch: `chore/docs-consolidation`
Removal mode requested: `archive`

Post-purge correction (2026-06-24): this file contains the original
pre-consolidation audit plus later reconciliation notes. Current runtime truth
after DEC-029/FOS-PURGE-01 is: API namespace is `/api/v1`; static `/ui` and its
dedicated HTML/test artifact are removed; `source_events` /
`normalized_activity_items` / `ingested_events` remain intentionally retained
until FOS-009.

Post-DEC-031 correction (2026-06-24): `EXECUTION_PLAN.md` and
`docs/_archive/**` are no longer part of the current control set. Mentions below
describe the pre-purge audit path unless explicitly marked current.

## Scope And Inputs

Canonical incoming files found and read:

- `/Users/anuarzh/Downloads/founderOS_MASTER_PLAYBOOK.md`
- `/Users/anuarzh/Downloads/files1/FOUNDEROS_EXECUTION_PLAN.md`
- `/Users/anuarzh/Downloads/files1/PROGRESS.md`

Repository instructions read before edits:

- `docs/index.md`
- `AGENTS.md`
- `CLAUDE.md`

Tracked documentation/instruction inventory source:

- `git ls-files` filtered for `*.md`, `README*`, `AGENTS.md`, `CLAUDE.md`,
  `.cursorrules`, `.cursor/**`, `.github/**/*.md`, `docs/**`.

Out-of-scope local/generated markdown was observed but not read as source truth
or printed:

- `.operator_outputs/**/*.md`
- `.pytest_cache/README.md`
- `obsidian_vault/**/*.md`

These are local/generated/export artifacts, not consolidation targets.

## Current Repository State

| Area | Verified state before consolidation |
|---|---|
| Git | Clean worktree before this audit report. Started from `feat/platform-part2-computed-repo-brain`; created `chore/docs-consolidation` for this work. |
| Backend | FastAPI app under `app/` with many protected/local routes and service modules. |
| Database | SQLAlchemy model modules exist under `app/db/`; canonical identity, integration/sync, and action models now exist. |
| Migrations | 25 tracked Alembic migration files under `migrations/versions/`. |
| Frontend | Next.js shell exists under `web/`; current pages are dashboard, github, briefings, actions, settings, plus shared shell/components. |
| Static UI | Historical at audit time: static founder UI still existed. Current post-purge state: static `/ui` is removed; `web/` is the product frontend shell. |
| Tests | 175 top-level `tests/test_*.py` files plus 3 eval tests were present in inventory. |
| Docs | 52 tracked documentation/instruction files, 14,052 lines total before incoming canonical files. |

## Code Map For Documentation Decisions

This audit does not modify code. Code was inspected only to understand whether
docs describe current behavior, target behavior, or stale generations.

Current DB model families observed:

- Core/event/source: `AuditLog`, `IngestedEvent`, `SourceDocument`,
  `DocumentChunk`, `SourceEvent`, `NormalizedActivityItemRecord`.
- Canonical MVP foundations now present: `User`, `Workspace`, `Membership`,
  `IntegrationConnection`, `SyncJob`, `ActionProposal`, `ActionExecution`.
- Graph/second-opinion/operator surfaces: `EntityRecord`, `EntityLinkRecord`,
  `EntityAliasRecord`, `SecondOpinionFinding`, `MetricSnapshot`,
  `StatusSnapshotRecord`, `SharePack`, `AgentProposal`, `DataAvailability`.
- Gmail/attention/extraction surfaces: `GmailThread`, `GmailMessage`,
  `GmailAttachment`, `EmailThreadState`, `AttentionTriageResultRecord`,
  `AttentionTriageFeedbackRecord`, `ExtractedTask`, `ExtractedDecision`,
  `ExtractedRisk`.

Current API families observed:

- Historical at audit time: MVP-ish workspace/GitHub/action/briefing routes were
  under `/v1/...`; DEC-023 later migrated active runtime routes to `/api/v1/...`.
- Historical at audit time: local founder/operator routes and static UI routes
  still existed; DEC-029/FOS-PURGE-01 removed the static `/ui` surface and
  Lineage-2 routers.

Current frontend map observed:

- `web/` exists and is a minimal Next.js shell.
- `web/app/github/page.tsx` still states frontend API calls are not wired.
- `web/lib/api.ts` uses `X-FounderOS-API-Key`, `owner_email`, and browser-local
  operator settings.

> Note (auth phase): superseded — this is the audit-time snapshot.
> `web/lib/config.ts` and the browser-local operator settings were removed;
> `web/lib/api.ts` is now same-origin (session cookie, no operator key/owner
> email), and the frontend is gated behind email+password login (DEC-043).

## Mapping Against Incoming Playbook

The incoming `founderOS_MASTER_PLAYBOOK.md` wins over all older repo playbooks,
vision docs, and planning docs. The canonical MVP line is:

```text
Login
-> Create Workspace
-> Connect GitHub
-> Sync GitHub
-> See Dashboard
-> See Company Brain entities
-> Generate Founder Briefing
-> Open Evidence
-> Approve Action Proposal
-> See External Action Result
```

The incoming `EXECUTION_PLAN.md` defines the execution order:

```text
CHUNK 0 Audit & Docs
-> CHUNK 1 Data Foundation
-> CHUNK 2 Connector Framework
-> CHUNK 3 GitHub E2E
-> CHUNK 4 Briefing MVP
-> CHUNK 5 Action Approval
-> CHUNK 6 Remaining Connectors
-> CHUNK 7 Polish + Repo Audit UI
-> CHUNK 8 Testing Gate + Deploy
```

Required canonical docs from playbook section 15.5:

- `docs/DECISIONS.md`
- `docs/ROADMAP.md`
- `docs/TODO.md`
- `docs/POST_MVP.md`
- `docs/CHANGELOG.md`

Current status: the first four exist; `docs/CHANGELOG.md` is missing.

## Documentation Inventory

Verdicts:

- KEEP: keep as canonical or supporting current-truth doc.
- MERGE: move unique useful content into a canonical doc, then archive original.
- STALE: archive as old generation/history.
- DUPLICATE: archive because another canonical doc should own the content.
- CONTRADICTS: conflicts with incoming playbook; record decision and archive or
  rewrite.
- ASK: do not touch without human decision.

| File | Role | Verdict | Reason | Action |
|---|---|---|---|---|
| `AGENTS.md` | Agent operating rules | KEEP | Current repo instructions; no conflict with incoming playbook except start-doc path will need updating if `docs/index.md` moves. | Update links/rules only as needed. |
| `CLAUDE.md` | AI/extraction boundaries | KEEP | Matches playbook invariants: strict JSON, evidence, no direct mutation. | Keep. |
| `README.md` | Root project entry | MERGE | Useful current setup and layout, but must point to canonical trio and `docs/README.md`. | Update, keep. |
| `NOTES.md` | Pointer note | DUPLICATE | Already says not source of truth; becomes redundant after `docs/README.md`. | Archive after index is created. |
| `SECURITY_BASELINE.md` | Security summary | MERGE | Useful baseline; overlaps with playbook security and `docs/security/api-boundary.md`. | Keep short root baseline or merge to security docs; update links. |
| `docs/index.md` | Current docs index | MERGE | Useful navigation, but task requires one entry at `docs/README.md`. | Merge into `docs/README.md`, then archive or replace with pointer. |
| `docs/ALIGNMENT_AUDIT.md` | Previous repo/playbook audit | STALE | Point-in-time audit; already contradicted by current code state (`web/` and canonical models now exist). | Archive. |
| `docs/CURRENT_DIRTY_TREE_PLAN.md` | Previous dirty-tree plan | STALE | Worktree is currently clean; plan is a historical snapshot. | Archive. |
| `docs/DECISIONS.md` | Project decisions | KEEP | Required by playbook and already records master playbook precedence. | Update with this consolidation decision/conflicts. |
| `docs/ROADMAP.md` | Roadmap | KEEP | Required by playbook; mostly aligned but needs canonical chunk/order cleanup. | Update from incoming playbook/execution plan. |
| `docs/TODO.md` | Near-term tasks | KEEP | Required by playbook; current task list reflects later progress than old audit. | Update to canonical current chunk/task shape if needed. |
| `docs/POST_MVP.md` | Deferred ideas | KEEP | Required by playbook; correct place for post-MVP/operator surfaces. | Update with archived-generation references. |
| `docs/CHANGELOG.md` | Change history | KEEP | Required by playbook but missing. | Create. |
| `docs/backlog.md` | Old FOS ticket list | DUPLICATE | Overlaps `docs/TODO.md` and incoming `EXECUTION_PLAN.md`. | Merge any still-unique ticket IDs into `TODO` or `POST_MVP`, then archive. |
| `docs/playbook.md` | FounderOS Playbook v2 | CONTRADICTS | Older operating playbook with different phase model and Telegram/digest emphasis. Incoming master wins. | Merge reusable execution principles if absent, record conflict, archive. |
| `docs/playbook-digital-twin.md` | Digital twin target playbook v3 | CONTRADICTS | Large target architecture generation; not the MVP source of truth and conflicts with master MVP order. | Move unique future ideas to `POST_MVP`, record conflict, archive. |
| `docs/vision.md` | North star summary | CONTRADICTS | Short target map tied to older digital-twin/Telegram-first usage gates. | Merge non-conflicting future vision to `POST_MVP`, archive. |
| `docs/architecture.md` | Current and target architecture | MERGE | Useful current-truth/code map; target pipeline differs from incoming master order. | Split current truth into `docs/README.md` or `DECISIONS`; archive if redundant. |
| `docs/data-model.md` | Data-model reconciliation | KEEP | Useful current mapping between existing DB and playbook; current code confirms many canonical tables now exist. | Update if needed, keep as supporting doc. |
| `docs/github-integration-decision.md` | GitHub MVP path decision | KEEP | Current GitHub bridge decision explains code that exists now; aligned with safe staged path. | Keep or merge summary into `DECISIONS`. |
| `docs/coding-rules.md` | Coding rules | DUPLICATE | Mostly duplicates `AGENTS.md` and `CLAUDE.md`. | Merge any unique API-boundary notes, archive. |
| `docs/workflows.md` | Development workflow | MERGE | Useful docs-only/testing workflow; overlaps AGENTS and execution plan. | Merge critical rules, archive or keep as support if still linked. |
| `docs/dev-env.md` | Local dev runbook | KEEP | Current runtime setup; not replaced by playbook. | Keep and link from docs index. |
| `docs/mvp-quickstart.md` | Manual MVP quickstart | MERGE | Describes old manual ingestion MVP, not master GitHub-first MVP. | Move to archive or post-MVP/supporting runbook after preserving useful commands. |
| `docs/operator_runtime_setup.md` | Local operator setup | MERGE | Useful for current local operations but outside master user-facing MVP. | Keep as runbook or archive under support; mark non-canonical. |
| `docs/obsidian-bridge.md` | Obsidian bridge | KEEP | Current export-only behavior; aligns with invariant that Obsidian is not source truth. | Keep as supporting runbook. |
| `docs/decisions/0001-founder-os-core-architecture.md` | ADR | KEEP | Historical ADR still aligns with evidence/source-of-truth invariants. | Keep. |
| `docs/agents/chunking-agent.md` | Agent role stub | DUPLICATE | Small docs duplicate CLAUDE/feature docs; not part of incoming canonical set. | Merge role summary if useful, archive. |
| `docs/agents/digest-agent.md` | Agent role stub | DUPLICATE | Digest-specific old role doc; post-MVP relative to master. | Archive after POST_MVP mention. |
| `docs/agents/extraction-agent.md` | Agent role stub | DUPLICATE | Duplicates CLAUDE extraction contract. | Archive after preserving unique wording if any. |
| `docs/agents/ingestion-agent.md` | Agent role stub | DUPLICATE | Duplicates source/ingestion feature docs. | Archive. |
| `docs/agents/retrieval-agent.md` | Agent role stub | DUPLICATE | Duplicates retrieval feature docs. | Archive. |
| `docs/agents/validation-agent.md` | Agent role stub | DUPLICATE | Duplicates CLAUDE and API-boundary docs. | Archive. |
| `docs/features/ingestion.md` | Current ingestion feature | KEEP | Current behavior and invariants; supports existing code. | Keep as supporting feature doc. |
| `docs/features/extraction.md` | Current extraction feature | KEEP | Aligns with evidence/strict-validation invariants. | Keep. |
| `docs/features/retrieval.md` | Current retrieval feature | KEEP | Describes existing deterministic retrieval. | Keep as support; mark not master MVP spine if needed. |
| `docs/features/source-events.md` | Current source-events feature | KEEP | Important bridge between existing code and master source records. | Keep. |
| `docs/features/source-integrations.md` | Source integrations contract | KEEP | Current connector/credential safety; aligns with guarded sync posture. | Keep as supporting doc. |
| `docs/features/company-brain.md` | Company Brain contract | KEEP | Aligns with computed/provenance/evidence direction and repo-audit code. | Keep. |
| `docs/features/local-ui.md` | Static local UI contract | MERGE | Current code truth, but not the master Next.js product UI. | Keep only if clearly labelled local/operator; otherwise archive after index update. |
| `docs/features/gmail.md` | Gmail feature | KEEP | Current request-only/read-only behavior; master includes Gmail minimal later. | Keep as supporting current-truth doc. |
| `docs/features/drive.md` | Drive feature | KEEP | Current request-only/read-only behavior; master includes Drive minimal later. | Keep as supporting current-truth doc. |
| `docs/features/obsidian-export.md` | Obsidian export | KEEP | Matches export-only invariant. | Keep. |
| `docs/features/knowledge-graph.md` | Knowledge graph/second opinion | MERGE | Useful but mostly beyond master MVP order. | Move future/target portions to `POST_MVP`; keep only current-contract slice or archive. |
| `docs/features/attention.md` | Attention/digest ledger | MERGE | Has a current-status block but also a huge archived FOS ledger. | Preserve current behavior and archive historical ledger-heavy original. |
| `docs/features/telegram-digest.md` | Telegram digest contract/ledger | STALE | Telegram digest is post-MVP relative to incoming master; large historical ledger. | Move summary to `POST_MVP`, archive original. |
| `docs/runbooks/manual-pilot.md` | Manual pilot runbook | STALE | Manual digest/Telegram pilot is not the master GitHub-first MVP line. | Archive after POST_MVP note. |
| `docs/runbooks/google-local-backfill.md` | Google local backfill runbook | KEEP | Supports current Gmail/Drive safe local path; master has Gmail/Drive later. | Keep as supporting runbook. |
| `docs/runbooks/guarded-operations.md` | Guarded operations runbook | KEEP | Documents safety gates and local diagnostics; aligns with approval/read-only invariants. | Keep. |
| `docs/runbooks/jira-operating-model.md` | Jira operating model | KEEP | Useful Jira planning and reinforces repo != Jira project. | Keep as supporting runbook. |
| `docs/ops/jira-target-blueprint.md` | Jira target design | MERGE | Useful but not master MVP; belongs under post-MVP/Jira support. | Keep if labelled supporting, or archive after summary. |
| `docs/ops/jira-rebuild-audit.md` | Jira rebuild audit draft | STALE | Separate Jira migration generation, not current master MVP path. | Archive. |
| `docs/ops/jira-rebuild-runbook-draft.md` | Jira rebuild runbook draft | STALE | Future write migration draft outside master MVP. | Archive. |
| `docs/security/api-boundary.md` | API security boundary | KEEP | Current security contract; aligns with playbook baseline. | Keep. |
| `docs/source-connectors.md` | Connector runbook | KEEP | Current source connector safety and scoped sync rules. | Keep as supporting doc. |
| `web/README.md` | Next.js shell docs | KEEP | Current frontend shell exists and master requires web frontend. | Keep and update if links change. |
| `migrations/README` | Empty migration marker | ASK | Empty tracked file; may be intentional placeholder. | Do not touch unless human approves. |

## Generations From Rebuilds

| Generation | Representative docs | Character | Audit decision |
|---|---|---|---|
| G1: Knowledge OS/manual ingestion | `docs/mvp-quickstart.md`, `docs/backlog.md`, agent stubs | Manual text ingestion, extraction, Obsidian, deterministic search. | Preserve working invariants; archive duplicated planning docs. |
| G2: Local operator/digest/Telegram | `docs/playbook.md`, `docs/vision.md`, `docs/features/attention.md`, `docs/features/telegram-digest.md`, `docs/runbooks/manual-pilot.md` | Telegram/digest/status-engine direction with many FOS ledger entries. | Move to POST_MVP/history; not current MVP line. |
| G3: Digital twin target architecture | `docs/playbook-digital-twin.md` | Broad target architecture: company digital twin, graph, second opinion, Telegram Q&A. | Archive as target-generation document; incoming master wins for MVP. |
| G4: Previous alignment/dirty-tree audit | `docs/ALIGNMENT_AUDIT.md`, `docs/CURRENT_DIRTY_TREE_PLAN.md` | Point-in-time audit of an earlier dirty tree. | Archive because worktree and code state changed. |
| G5: Incoming master MVP line | incoming `founderOS_MASTER_PLAYBOOK.md`, `EXECUTION_PLAN.md`, `PROGRESS.md` | Modular monolith, UI-first GitHub E2E, evidence, human-approved actions. | Chosen as canonical line. |

Chosen line: G5. Supporting docs may remain only when they document current code
truth or safe operations and are clearly subordinate to the canonical trio.

## Code Duplicates / Conflicts To Report Only

Code is not changed by this documentation consolidation.

| Area | Observed duplication/drift | Why it matters | Proposed human decision |
|---|---|---|---|
| UI surfaces | Historical conflict: static `/ui` local/operator UI and Next.js `web/` shell both existed. | Master wants one user-facing web product. | Resolved by DEC-029/FOS-PURGE-01: static `/ui` removed; `web/` is the product frontend shell. |
| API base paths | Historical conflict: incoming playbook says `/api/v1`; existing routes were mostly `/v1/...`. | Docs can overpromise a different API namespace. | Resolved by DEC-023: active runtime namespace is `/api/v1`. |
| Source model naming | Playbook uses `SourceRecord`; repo has `IngestedEvent`, `SourceDocument`, `DocumentChunk`, `SourceEvent`. | Risk of duplicate source-of-truth tables if docs blindly follow playbook names. | Keep data-model reconciliation as bridge; do not add duplicate tables without explicit schema task. |
| Entity model naming | Playbook uses `NormalizedEntity`; repo has `EntityRecord`, `NormalizedActivityItemRecord`, extracted task/risk/decision tables. | Docs can imply one canonical entity table while code has graph and activity projections. | Preserve reconciliation docs until schema contract is finalized. |
| GitHub path | Playbook product flow says OAuth + sync; current code includes provider-token bridge, manual local sync job, normalization-local, mocked E2E. | Current implementation is safer but not full product OAuth E2E. | Keep staged bridge decision or explicitly choose OAuth migration. |
| Post-MVP surfaces | Telegram digest, share packs, Jira rebuild planning, second opinion, attention ledgers exist before full GitHub product E2E. | Docs may keep agents expanding non-spine work. | Freeze as POST_MVP/supporting docs until GitHub E2E is product-usable. |

## Sources Of Truth To Keep

After consolidation, the intended canonical set is:

- `founderOS_MASTER_PLAYBOOK.md`
- `PROGRESS.md`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/README.md`
- `docs/DECISIONS.md`
- `docs/ROADMAP.md`
- `docs/TODO.md`
- `docs/POST_MVP.md`
- `docs/CHANGELOG.md`

Post DEC-029/DEC-031, the supporting `docs/features/`, `docs/runbooks/`, and
`docs/security/` trees no longer remain in the live docs set. Future supporting
docs should be introduced only through a scoped task and must stay subordinate
to the canonical set.

## To Archive

Historical plan: resolved by DEC-029/DEC-031. The live archive tree was removed;
recover deleted material from git history / tag `pre-purge-20260624` if needed.

Primary archive candidates:

- `NOTES.md`
- `docs/ALIGNMENT_AUDIT.md`
- `docs/CURRENT_DIRTY_TREE_PLAN.md`
- `docs/backlog.md`
- `docs/playbook.md`
- `docs/playbook-digital-twin.md`
- `docs/vision.md`
- `docs/features/telegram-digest.md`
- `docs/runbooks/manual-pilot.md`
- `docs/ops/jira-rebuild-audit.md`
- `docs/ops/jira-rebuild-runbook-draft.md`
- `docs/agents/*.md`

Possible archive after merge/label:

- `docs/coding-rules.md`
- `docs/workflows.md`
- `docs/mvp-quickstart.md`
- `docs/features/attention.md`
- `docs/features/knowledge-graph.md`
- `docs/ops/jira-target-blueprint.md`

ASK:

- `migrations/README` is empty and tracked. It is not documentation debt enough
  to remove during this docs consolidation without explicit human approval.

## Merged Into What

Planned merge targets:

| Source | Target |
|---|---|
| `docs/index.md` | `docs/README.md` |
| old playbooks/vision target ideas | `docs/POST_MVP.md` and `docs/DECISIONS.md` |
| current safe operation rules | `AGENTS.md`, `CLAUDE.md`, `docs/security/api-boundary.md`, `docs/runbooks/guarded-operations.md` |
| GitHub MVP bridge decisions | `docs/DECISIONS.md`, preserving `docs/github-integration-decision.md` if still useful |
| old FOS/backlog items | `docs/TODO.md` or `docs/POST_MVP.md` |
| attention/Telegram historical ledgers | archive manifest plus short POST_MVP entry |

## Human Decisions Needed

- API namespace question resolved by DEC-023: active runtime namespace is
  `/api/v1`.
- Static UI question resolved by DEC-029/FOS-PURGE-01: `web/` is the product
  frontend shell and static `/ui` is removed.
- Decide later whether `migrations/README` should remain as a placeholder.

## Next Consolidation Actions

1. Commit this audit report by itself:
   `docs(audit): inventory of all docs before consolidation`.
2. Add the incoming canonical trio in one place, using root repo names:
   `founderOS_MASTER_PLAYBOOK.md`, `EXECUTION_PLAN.md`, `PROGRESS.md`.
3. Create/update required canonical docs, especially missing
   `docs/CHANGELOG.md` and new `docs/README.md`.
4. Archive STALE/DUPLICATE/CONTRADICTS docs to `docs/_archive/` with
   `docs/_archive/MANIFEST.md`.
5. Update links from root `README.md` and agent instructions.
6. Verify internal links and that `git diff` is docs-only.

---

## Code Reality vs FOS (audit 2026-06-24)

Verdict rubric: **DONE** = code + passing test/working endpoint meeting the FOS
acceptance criteria. **PARTIAL** = code exists but acceptance/canonical shape not
met. **MISSING** = no implementation under the canonical contract. Gate runs this
date: `alembic upgrade head` ✅ (head `f5a6b7c8d9e0`) · `ruff` ✅ · frontend
`next build` + `tsc` ✅ · `pytest` 1805 passed / 4 failed (doc-contract tests).

| FOS | Title | Status | Evidence (one line) |
|---|---|---|---|
| FOS-000 | Repo baseline audit | DONE | This audit; no code changed; PROGRESS/DECISIONS/_audit updated |
| FOS-001 | Project docs | DONE | `docs/{DECISIONS,ROADMAP,TODO,POST_MVP,CHANGELOG}.md` exist (4 doc-contract tests still red) |
| FOS-002 | Core DB models (22 §6) | PARTIAL | 8/22 canonical present; `tests/test_integration_models.py` green; 14 canonical tables absent |
| FOS-003 | Encryption utility | DONE | `app/services/secret_encryption.py` (Fernet); roundtrip in `tests/test_github_provider_token_connection.py` |
| FOS-004 | Connector base interface | MISSING | No `app/connectors/base.py` with ProviderClient/SyncResult/ProviderError contract |
| FOS-005 | Sync service | PARTIAL | No generic `sync_service.py`/SourceRecord; per-provider `app/services/github_sync_job_service.py` |
| FOS-006 | Normalization service | PARTIAL | No generic `normalization_service.py`/NormalizedEntity/EvidenceRef; `github_normalization_service.py` projects dicts |
| FOS-007 | GitHub OAuth | PARTIAL | No OAuth start/callback (§7.5); PAT-bridge connection, token encrypted; `tests/test_github_provider_token_connection.py` green |
| FOS-008 | GitHub sync repositories | DONE | `app/services/github_sync_job_service.py` + `/api/v1/.../github/repositories`; `tests/test_github_first_backend_e2e.py` (repos count==1) |
| FOS-009 | GitHub sync issues + PRs | PARTIAL | PR projection only; issues empty with warning (`github_normalization_service.py:26-27`) |
| FOS-010 | Connectors UI page | MISSING | No `web/app/connectors/page.tsx`; only stub `web/app/github/page.tsx` |
| FOS-011 | Dashboard v0 | PARTIAL | `app/services/founder_overview.py`; `web/app/dashboard/page.tsx` stub, not wired to live data |
| FOS-012 | Brain entity API + UI | PARTIAL | `app/api/company_brain.py` exists; no `web/app/brain` page |
| FOS-013 | Briefing backend | PARTIAL | `founder_briefing_service.py` deterministic/transient (no LLM, no Briefing rows); `tests/test_founder_briefing_api.py` green |
| FOS-014 | Briefing UI | MISSING | `web/app/briefings/page.tsx` 23-line stub; no evidence drawer |
| FOS-015 | Action proposal API | PARTIAL | `app/api/actions.py` approve/reject/execute + models + migration; `tests/test_action_proposals_api.py` green; no async worker |
| FOS-016 | GitHub create-issue action | PARTIAL | `github_issue_execution_service.py` + `tests/test_github_issue_execution_api.py` green; issue client mocked (no real write) |
| FOS-017 | Jira connector minimal | PARTIAL | `app/connectors/jira.py` + discovery/mapping; no `web/app/jira`; not in canonical Brain |
| FOS-018 | Gmail connector minimal | PARTIAL | `app/connectors/gmail.py` + gmail models + `app/api/gmail.py`; no `web/app/gmail` |
| FOS-019 | Drive connector minimal | PARTIAL | `app/connectors/google_drive.py` + `app/api/drive.py`; no `web/app/drive` |
| FOS-020 | Documents module | PARTIAL | `source_documents` (RAG) only; no canonical `Document` CRUD (§7.11); no `web/app/documents` |
| FOS-021 | Repo Audit UI | PARTIAL | `app/services/repo_audit.py` exists; no `web/app/repo-audit` page |
| FOS-022 | Smoke tests | PARTIAL | Backend `test_github_first_backend_e2e.py` + `test_external_connector_readonly_smoke.py` green; no `make smoke`/Makefile/prod smoke |

Totals: **DONE 4 · PARTIAL 16 · MISSING 3** (= 23). Strict progress 4/23 (17%).

Note on TODO drift: `docs/TODO.md` tracks a parallel scheme
(`FOS-AUD/DB/GH/BRF/ACT/E2E/FE-*`) with ~15 entries marked "done", which reads as
a near-complete backend MVP. Against the playbook's `FOS-000..022` that maps to
mostly PARTIAL backend work, not DONE.

Canonical model coverage (§6, 22 entities): present under canonical names = User,
Workspace, Membership, IntegrationConnection, SyncJob, ActionProposal,
ActionExecution, AuditLog (8). Absent as canonical tables (14) = SourceRecord,
EvidenceRef, NormalizedEntity, Project, Task, Repository, PullRequest,
MessageThread, DriveFile, Document, Goal, Insight, Briefing, BriefingItem.

Canonical frontend pages (§8): present (stubs) = `/dashboard`, `/github`,
`/briefings`, `/actions`, `/settings`. Absent = `/login`, `/connectors`,
`/brain`, `/jira`, `/gmail`, `/drive`, `/documents`, `/repo-audit`.

## Drift Resolved (audit 2026-06-24)

Decisions recorded in `docs/DECISIONS.md` (DEC-023..026) and ASK-1/ASK-2. No code,
migrations, tests, or config were changed.

| Drift | Verdict (playbook ref) | Where the conflict lives |
|---|---|---|
| API namespace historical drift | Canonical = `/api/v1` (§7.1) → **DEC-023**. Resolved: active runtime routes now use `/api/v1`. | `app/main.py` + active routers/tests/web references |
| SourceRecord vs source/event tables | Canonical = `SourceRecord`/`NormalizedEntity`/`EvidenceRef` (§6.7/6.9/6.8) → **DEC-024** | `app/db/event_models.py` (`source_events`), `graph_models.py` (`entities`), `source_models.py`, `models.py`; `EvidenceRef` only a Pydantic schema |
| Static UI vs Next.js `web/` | Product frontend = Next.js `web/` (§8); static `/ui` removed by DEC-029/FOS-PURGE-01. | `web/app/*` is the surviving product frontend shell |
| Post-MVP surfaces built before GitHub E2E | No-go / out of scope (§3.3/3.4, EXECUTION_PLAN #5/#6) → **DEC-026** (concretizes DEC-006/022) | telegram/digest/share-pack/second-opinion/role-view/jira-write/attention/meeting/knowledge-QA services in `app/services/` |
| Genuinely ambiguous | Not decided → **ASK-1** (23rd model / missing `Person`), **ASK-2** (rename-migrate vs add-alongside foundation strategy) | §6 defines 22; `assignee_person_id`/`author_person_id` imply undefined Person |

## Shape-Equivalence Analysis (FOS-002, ШАГ B — 2026-06-24)

Goal of the gate: decide whether canonicalization can be done by **renaming**
existing tables, or whether their shape diverges enough that a rename would be
destructive. Verdict columns: **yes** = present, same meaning; **no** = absent;
**other** = present under a different name/shape.

### `source_events` (`SourceEvent`) ↔ `SourceRecord` (§6.7)

| Canonical field (§6.7) | In code? | Type matches? |
|---|---|---|
| `id: uuid` | other — `id: Integer` autoincrement; external key is `source_event_id: str` | **no** (int vs uuid) |
| `workspace_id: uuid` | **no** — no tenancy column anywhere | **no** |
| `provider` (enum) | other — `source_system: str` (free) | partial |
| `connection_id: uuid` | **no** | **no** |
| `external_id: string` | other — `source_object_id: str` | partial (name + grain) |
| `record_type: string` | other — split into `source_object_type` + `event_type` | partial |
| `source_url` | yes | yes |
| `payload: jsonb` (req) | **no** — only `raw_object_ref: str` pointer; payload lives in `ingested_events.payload` | **no** (separate table) |
| `payload_hash: string` | **no** | **no** |
| `observed_at: datetime` | other — `source_event_ts` (nullable) / `created_at` | partial |
| `source_updated_at` | **no** | **no** |
| `sync_job_id` | **no** | **no** |
| `is_deleted: bool` | **no** | **no** |
| `created_at` | yes | yes |
| unique `(workspace_id, provider, external_id)` | **no** — unique is `(source_system, source_object_type, source_object_id, event_type, source_event_key)` | **no** |

**Grain mismatch:** `SourceEvent` = one row **per event** (append-only event log);
`SourceRecord` = one row **per external object** (upserted snapshot holding full
payload + hash). Different cardinality, different purpose.

### `entities` (`EntityRecord`) ↔ `NormalizedEntity` (§6.9)

| Canonical field (§6.9) | In code? | Type matches? |
|---|---|---|
| `id: uuid` | other — `id: Integer`; external key `entity_id: str` | **no** |
| `workspace_id: uuid` | **no** | **no** |
| `entity_type` (enum) | yes `entity_type: str` (free) | partial |
| `canonical_key` (req, unique per workspace) | other — `entity_id` (globally unique) is the key | **no** (uniqueness scope differs) |
| `title: string` (req) | other — `canonical_name` | partial (rename) |
| `status` | **no** | **no** |
| `summary: text` | **no** | **no** |
| `metadata: jsonb` | yes — `attrs` | yes (rename) |
| `first_seen_at` | **no** | **no** |
| `last_seen_at` | **no** | **no** |
| `created_at` / `updated_at` | yes | yes |
| (not in §6) | `canonical_entity_id`, `merge_status`, `merge_confidence`, run-id columns + satellite tables `entity_source_accounts`, `entity_aliases`, `entity_links` | extra identity/graph layer |

**Grain mismatch:** `entities` is a knowledge-graph node with an identity/merge
layer and three satellite tables; `NormalizedEntity` is a flat per-object snapshot.

### `EvidenceRef` (§6.8 = table) vs current

Currently `EvidenceRef` exists **only as a Pydantic schema** (`app/agents/schemas.py`)
bound to the RAG chunking subsystem (`source_document_id`, `chunk_id`,
`raw_object_ref`, `quote`) plus denormalized `evidence_refs` JSON arrays on many
tables. Canonical §6.8 wants a **table** with `workspace_id`, `source_record_id`
FK → `source_records` (req), `entity_id`, `quote`, `field_path`, `source_url`,
`confidence`. No table to rename; its FK target (`source_records`) does not
equivalently exist.

### Verdict

**NOT shape-equivalent.** Rename is not safe for `source_events` or `entities`
(different grain, Integer→uuid PK break, no `workspace_id` tenancy, payload in a
separate table, identity/graph layer). Per the FOS-002 directive's ШАГ B rule,
this **stops before ШАГ C (rename migration)** and asks the human. The only
non-destructive path is option (b): add new uuid-keyed, workspace-scoped canonical
§6 tables **alongside** the existing event/graph tables (which stay as the
compatibility substrate, consistent with DEC-013/DEC-015). Namespace `/v1` →
`/api/v1` (DEC-023) is independent and not blocked — **done 2026-06-24**.

## Load-Bearing Map (FOS-002 diagnostics — 2026-06-24)

Read-only check of whether the GitHub MVP spine reads/writes the `entities`
graph + identity satellites + `source_events`, or routes around them. Finding:
**the repo has two parallel data lineages; the MVP spine routes entirely around
the graph/event lineage.**

### Lineage 1 — GitHub MVP spine (recent, green-tested, canonical direction)

- **Tables:** `users`, `workspaces`, `memberships`, `integration_connections`,
  `sync_jobs`, `action_proposals`, `action_executions`.
- **Services:** `github_connection_service`, `github_sync_job_service`,
  `github_normalization_service` (projection-only — `persist_if_supported=False`,
  "persistent graph upsert is deferred"), `github_repository_read_service`,
  `action_proposal_service`, `founder_briefing_service` (transient),
  `company_brain_preview` (reads `.local` filesystem + `repo_audit`, no DB graph).
- **Routers:** `app/api/{github,actions,briefings,workspaces,company_brain}.py` —
  all import only `integration_models` / `action_models` / `identity_models`.
- **Does NOT touch** `entities`, `entity_aliases`, `entity_links`,
  `entity_source_accounts`, or `source_events`.
- **Missing canonical §6 persistence:** `SourceRecord`, `NormalizedEntity`,
  `EvidenceRef`, `Repository`, `PullRequest`, `Task`, `Project`, `Briefing` —
  currently projected/transient, not persisted.

### Lineage 2 — Graphiti / knowledge-graph generation (older, frozen post-MVP)

- **Tables:** `ingested_events` → `source_events` → `normalized_activity_items`
  → `entities` (+ `entity_aliases`, `entity_links`, `entity_source_accounts`,
  merge layer) → `knowledge_scores`, `second_opinion_findings`.
- **Services (load-bearing on the graph):** ingestion (`connector_ingestion`,
  `source_ingestion`, `source_events`), `knowledge_graph(_view)`,
  `graph_gardener`/`gardener_apply`, `graph_lift`/`graph_tree`,
  `entity_identity`/`entity_resolution`, `evidence_graph_lift`/`_trail`/`_explorer`,
  `second_opinion`, `metric_collector`, `jira_graph_mapping`/`github_graph_mapping`,
  and the founder-views generation (`founder_overview`, `sales_view`, `team_view`,
  `product_view`, `execution_view`, `command_center`, `role_views`), plus `digest`,
  `telegram_founder_bot`, `declaration_agents`, `data_quality_center`,
  `project_status_view`, `repository_source_inventory`, `connector_diagnostics`.
- **Routers:** `app/api/inbox.py` (second-opinion / knowledge-graph / founder-views
  / source-events / investor / sales / team / execution) and `app/api/digest.py`.
- These are exactly the **DEC-026 frozen post-MVP surfaces**.

### Implication for the A/B decision

- The graph IS loaded (entities + identity layer both used) — but **only by
  Lineage 2 (frozen post-MVP)**, not by the MVP spine.
- `founder_overview` (legacy founder-views, served at `/api/v1/founder/overview`)
  reads `entities` + `normalized_activity_items`; it is **not** the canonical web
  dashboard (FOS-011), which is an unwired stub in `web/`.
- So §6 canonical models map naturally onto **extending Lineage 1** (persist
  `SourceRecord`/`NormalizedEntity`/`EvidenceRef`/`Repository`/`PullRequest`/`Task`/
  `Project`/`Briefing` there), with **Lineage 2 marked legacy-to-retire**. This is
  branch A applied to the spine and yields one canonical line. Branch B
  ("ratify the existing model") is ambiguous because there are two existing models.
- This is the "decide consciously which pieces are canonical vs legacy" point.
  **STOPPED for human decision** (see ASK-2). No schema/model change made.
