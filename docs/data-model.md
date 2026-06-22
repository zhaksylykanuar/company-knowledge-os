# founderOS Data Model Reconciliation

## 1. Purpose

founderOS already has a strong persistence foundation: raw ingestion events, source events, source documents, graph entities, attention triage, audit logs, agent proposals, source-control run requests, and several founder/operator read models.

The master playbook requires a canonical MVP data model. That model should not be added blindly on top of the current database, because several existing tables already represent parts of the same concepts. This document maps existing tables and model areas to the canonical playbook model so FOS-DB-02 and later migrations avoid duplicate tables, conflicting relationships, incompatible entities, and parallel sources of truth.

The safe path is existing -> canonical reconciliation first, then narrow migrations.

## 2. Current Database / Model Inventory

| Existing model/table | Purpose | Current usage | Related services/routes | Keep/adapt decision |
|---|---|---|---|---|
| `AuditLog` / `audit_logs` | Append-only operational audit events with actor, correlation/trace IDs, before/after refs, agent/approval lineage, and payload. | Existing audit trail for ingestion, delivery, evidence, source-control, Obsidian/export, and share-pack actions. | `app/api/events.py`, `app/services/audit_log.py`, `app/services/digest_builder.py`, `app/services/source_control.py`, `app/services/source_run_service.py`, `app/services/share_pack_service.py` | KEEP_AND_ADAPT |
| `IngestedEvent` / `ingested_events` | Raw-ish ingestion event envelope with source IDs, idempotency key, raw object ref, payload, and status. | Foundation for provider/source ingestion and idempotent event capture. | `app/api/events.py`, `app/services/source_ingestion.py`, `tests/test_events_pipeline.py` | KEEP_AND_ADAPT |
| `SourceDocument` / `source_documents` | Source-backed document metadata and raw object reference. | Drive/Gmail document ingestion, chunking, extraction, and evidence lookup. | `app/api/drive.py`, `app/api/gmail.py`, `app/services/drive_ingestion.py`, `app/services/extraction_pipeline.py`, `app/services/source_document_index.py` | KEEP_AND_ADAPT |
| `DocumentChunk` / `document_chunks` | Chunk-level text/evidence record tied to a source document. | Extraction, scoring, evidence display, and chunk-level provenance. | `app/services/chunking.py`, `app/services/extraction_pipeline.py`, `app/services/source_document_index.py` | KEEP_AND_ADAPT |
| `AgentRun` / `agent_runs` | Extraction/agent execution lineage for source documents and chunks. | Run tracking for extraction pipeline and provenance of extracted facts. | `app/services/extraction_pipeline.py`, extraction tests | KEEP |
| `ExtractedTask` / `extracted_tasks` | Evidence-backed task candidate extracted from source material. | Founder/operator task read model and extraction output. | `app/services/extraction_pipeline.py`, `app/services/metric_collector.py`, extraction tests | KEEP_AND_ADAPT |
| `ExtractedDecision` / `extracted_decisions` | Evidence-backed decision extracted from source material. | Decision read model and briefing/insight source candidate. | `app/services/extraction_pipeline.py`, `app/services/metric_collector.py`, extraction tests | KEEP_AND_ADAPT |
| `ExtractedRisk` / `extracted_risks` | Evidence-backed risk extracted from source material. | Risk read model, attention scoring, second-opinion context. | `app/services/extraction_pipeline.py`, `app/services/metric_collector.py`, extraction tests | KEEP_AND_ADAPT |
| `SourceEvent` / `source_events` | Normalized source event with source object identity, event type, source timestamp, raw ref, evidence refs, and metadata. | Current central source event layer for Jira/GitHub/Gmail/Drive-style activity. | `app/services/source_ingestion.py`, `app/services/evidence_explorer.py`, `app/services/repository_source_inventory.py`, `app/services/jira_graph_mapping.py` | COMPATIBILITY_LAYER |
| `NormalizedActivityItemRecord` / `normalized_activity_items` | Normalized activity feed item derived from source events. | Digest, metrics, attention triage, and timeline-style founder read models. | `app/services/source_ingestion.py`, `app/services/metric_collector.py`, `app/services/attention_triage.py`, digest services | KEEP_AND_ADAPT |
| `EntityRecord` / `entities` | Current graph entity table with type, canonical name, attrs, canonical entity relation, merge status, and lineage. | Company graph, Jira/project/entity mapping, graph tree, repo/company-brain context. | `app/services/graph_resolver.py`, `app/services/jira_graph_mapping.py`, `app/services/graph_tree.py`, `app/services/evidence_explorer.py` | COMPATIBILITY_LAYER |
| `EntitySourceAccount` / `entity_source_accounts` | Maps graph entities to source-system account IDs. | Identity/entity matching across external providers. | `app/services/graph_resolver.py`, graph tests | KEEP_AND_ADAPT |
| `EntityAliasRecord` / `entity_aliases` | Alias table for graph entity resolution. | Canonicalization and founder-confirmed aliases. | `app/services/graph_resolver.py`, graph tests | KEEP_AND_ADAPT |
| `EntityLinkRecord` / `entity_links` | Evidence-backed graph relationships between entities. | Graph tree, related entities, ownership/project relationships. | `app/services/graph_resolver.py`, `app/services/graph_tree.py`, `app/services/evidence_explorer.py` | KEEP_AND_ADAPT |
| `KnowledgeScore` / `knowledge_scores` | Score record for importance, urgency, risk, confidence, and attention. | Ranking and attention-oriented founder/operator surfaces. | `app/services/knowledge_scoring.py`, `app/services/metric_collector.py` | KEEP_AND_ADAPT |
| `AttentionTriageResultRecord` / `attention_triage_results` | Attention classification, priority, digest visibility, reason, action, owner/deadline, evidence refs. | Attention triage and digest candidate selection. | `app/services/attention_triage.py`, `app/services/digest_builder.py`, attention tests | KEEP_AND_ADAPT |
| `AttentionTriageFeedbackRecord` / `attention_triage_feedback` | Human feedback on attention triage results. | Feedback loop for triage decisions. | attention triage services/tests | KEEP |
| `GmailThread` / `gmail_threads` | Gmail provider thread snapshot. | Gmail read-only ingestion and source-backed thread context. | `app/api/gmail.py`, Gmail ingestion services/tests | KEEP_AND_ADAPT |
| `GmailMessage` / `gmail_messages` | Gmail provider message snapshot with raw object ref and payload. | Gmail read-only ingestion and evidence/source context. | `app/api/gmail.py`, Gmail ingestion services/tests | KEEP_AND_ADAPT |
| `GmailAttachment` / `gmail_attachments` | Gmail attachment metadata and raw object ref. | Gmail attachment inventory and evidence context. | Gmail ingestion services/tests | KEEP |
| `EmailThreadState` / `email_thread_states` | Aggregated thread state with participants, reply state, triage class, digest flags, and evidence refs. | Email founder/operator state, digest, triage context. | email state/attention services, digest services | KEEP_AND_ADAPT |
| `AgentProposal` / `agent_proposals` | Human-reviewable proposal from an agent with payload, source snapshot, evidence refs, confidence, status, decision fields, and reversibility. | Existing approval-like layer for bounded AI suggestions. | `app/services/agent_proposals.py`, proposal-related tests | KEEP_AND_ADAPT |
| `MetricSnapshot` / `metric_snapshots` | Point-in-time metrics by key/scope. | Dashboard/read-model support. | `app/services/metric_collector.py`, metric tests | DO_NOT_TOUCH_NOW |
| `AgentRunLog` / `agent_run_logs` | Agent run lifecycle and counts/errors summary. | Operational observability and run history. | agent run logging services/tests | KEEP |
| `DataAvailability` / `data_availability` | Availability state for metrics/read models. | Dashboard readiness and missing-data messaging. | metric/readiness services/tests | KEEP |
| `FounderDeclaration` / `founder_declarations` | Founder-declared facts and configuration payloads. | Declared company/founder context and second-opinion comparisons. | `app/services/declarations.py`, declaration tests | KEEP_AND_ADAPT |
| `SourceControlState` / `source_control_states` | Per-source control state, pause/status, last sync/action, watermarks, config status. | Operator control plane for source syncing. | `app/services/source_control.py`, `app/api/source_control.py`, source-control tests | KEEP_AND_ADAPT |
| `SourceRunRequest` / `source_run_requests` | Requested/approved/started/finished source-control action with snapshots, result, idempotency, external-side-effect flag, and audit ref. | Human-controlled source run lifecycle and guarded provider actions. | `app/services/source_run_service.py`, `app/api/source_control.py`, action-center services | KEEP_AND_ADAPT |
| `SecondOpinionFinding` / `second_opinion_findings` | Declared-vs-observed finding with evidence/source refs, severity, confidence, status, and visibility. | Company Brain / second-opinion insight surface. | `app/services/second_opinion.py`, `app/services/action_center.py`, company-brain services | KEEP_AND_ADAPT |
| `StatusSnapshotRecord` / `status_snapshots` | Computed status summary for an entity with color, changes, work, blockers, risks, conflicts, recommendations, confidence, and evidence refs. | Founder/company status read model. | status services/tests, company-brain UI paths | POST_MVP_FREEZE |
| `SharePack` / `share_packs` | Investor/share export package with sections, evidence coverage, redaction manifest, included entities/findings/sources, and lifecycle fields. | Post-MVP/share-pack operator surface. | `app/services/share_pack_service.py`, share-pack API/tests | POST_MVP_FREEZE |

## 3. Canonical Master Playbook Models

| Canonical model | MVP required? | Existing exact match? | Existing similar model/table | Decision |
|---|---|---|---|---|
| `User` | Yes | No | API-key auth only; no user table. | ADD_NOW |
| `Workspace` | Yes | No | Some tables have `company_id`, `organization_id`, or `scope`, but no canonical workspace. | ADD_NOW |
| `Membership` | Yes | No | No user-workspace membership table. | ADD_NOW |
| `IntegrationConnection` | Yes | No | `SourceControlState`, provider config/status conventions. | ADD_NOW |
| `SyncJob` | Yes | No | `SourceRunRequest`, `AgentRunLog`, source watermarks. | ADD_NOW |
| `SourceRecord` | Yes | No | `IngestedEvent`, `SourceEvent`, `SourceDocument`, Gmail provider tables. | COMPATIBILITY_LAYER |
| `EvidenceRef` | Yes | No | JSON `evidence_refs` fields, `DocumentChunk`, `SourceEvent`, source refs. | COMPATIBILITY_LAYER |
| `NormalizedEntity` | Yes | No | `EntityRecord`, `EntityAliasRecord`, `EntityLinkRecord`, `NormalizedActivityItemRecord`. | COMPATIBILITY_LAYER |
| `Project` | Yes | No | `EntityRecord` with project-like entity types, `StatusSnapshotRecord`, Jira graph mapping. | COMPATIBILITY_LAYER |
| `Task` | Yes | No | `ExtractedTask`, source activity items, Jira source events. | COMPATIBILITY_LAYER |
| `Repository` | Yes for GitHub-first E2E | No | Repository source inventory and repo audit outputs derived from source events/discovery snapshots. | ADD_LATER |
| `PullRequest` | Yes for GitHub-first E2E | No | GitHub/source events and normalized activity items. | ADD_LATER |
| `MessageThread` | Yes for source context | No | `EmailThreadState`, `GmailThread`, `GmailMessage`. | ADAPT_EXISTING |
| `DriveFile` | Yes for source context | No | `SourceDocument` with Drive metadata/raw refs. | ADAPT_EXISTING |
| `Document` | Yes | Partial | `SourceDocument` and `DocumentChunk`; canonical internal document semantics are not separated yet. | COMPATIBILITY_LAYER |
| `Goal` | Later MVP context | No | `FounderDeclaration`, declarations payloads, status snapshots. | ADD_LATER |
| `Insight` | Yes | No | `SecondOpinionFinding`, `AttentionTriageResultRecord`, `KnowledgeScore`, extracted decisions/risks. | ADAPT_EXISTING |
| `Briefing` | Yes | No | Digest/read-model services only; no canonical briefing table. | ADD_LATER |
| `BriefingItem` | Yes | No | Attention triage results, normalized activity, findings, extracted tasks/risks/decisions. | ADD_LATER |
| `ActionProposal` | Yes | Partial | `AgentProposal`, `SourceRunRequest`. | ADAPT_EXISTING |
| `ActionExecution` | Yes | Partial | `SourceRunRequest`, `AuditLog`, source-control lifecycle fields. | ADAPT_EXISTING |
| `AuditLog` | Yes | Yes, mostly | `AuditLog` / `audit_logs`. | USE_EXISTING_AS_CANONICAL |

## 4. Existing → Canonical Mapping

| Existing area | Closest canonical concept | Match quality | Risk | MVP decision |
|---|---|---|---|---|
| Existing source events / ingested events | `SourceRecord` | partial | Creating a new `source_records` table without mapping could split raw/source identity across `ingested_events`, `source_events`, and canonical records. | Use compatibility mapping first; do not duplicate source truth in FOS-DB-02. |
| Existing source documents/chunks | `Document`, `DriveFile`, `EvidenceRef` | partial | `SourceDocument` is a provider/source artifact, while canonical `Document` may also represent founderOS-authored/internal docs. | Keep existing source document/chunk layer; define `EvidenceRef` adapter to point at document/chunk/source-event refs. |
| Existing graph entities | `NormalizedEntity` | close | A parallel normalized entity table would fork canonical entity identity and merge state. | Treat graph tables as the current normalized entity substrate; add compatibility semantics before a new table. |
| Existing normalized activity | `NormalizedEntity`, `Insight`, timeline/read-model concepts | partial | Activity items are events/read-model rows, not durable canonical entities. | Keep as activity feed; use it as input to future insight/briefing models. |
| Existing attention triage | `Insight`, `BriefingItem` | partial | Triage rows can look like briefing items but do not have briefing membership, ordering, or publication lifecycle. | Adapt as briefing-item source material; add canonical briefing tables later. |
| Existing agent proposals | `ActionProposal` | close | Status, approval, reversibility, and payload semantics may diverge from playbook action proposals if a second table is added blindly. | Reconcile fields before adding or adapting canonical action proposal. |
| Existing source-control requests | `IntegrationConnection`, `SyncJob`, `ActionProposal`, `ActionExecution` | partial | Current requests combine control-plane action, run lifecycle, approval fields, and execution result. | Add connection/sync foundation separately, then map run requests to jobs/executions. |
| Existing audit logs | `AuditLog` | close | A duplicate audit log would make compliance and debugging ambiguous. | Use existing `audit_logs` as canonical baseline; add workspace/user refs later if needed. |
| Existing repo audit outputs | `Repository`, `EvidenceRef`, `NormalizedEntity` | weak | Repo audit is currently computed/preview-style and may not persist canonical repository rows. | Keep computed repo audit as evidence-backed read model until GitHub-first E2E defines repository persistence. |
| Existing Company Brain preview models | Briefing context / brain entities / `Insight` | weak | Preview/read-model state can be mistaken for canonical source of truth. | Keep as read-model context; do not make it canonical persistence in FOS-DB-02. |
| Existing Gmail tables and email thread state | `MessageThread`, `SourceRecord`, `EvidenceRef` | close | Provider snapshots and aggregated thread state can drift if a new canonical message thread table is independent. | Adapt existing email thread state; define canonical mapping before adding thread duplicates. |
| Existing extracted tasks/decisions/risks | `Task`, `Insight`, `BriefingItem` | partial | Extracted facts are evidence-backed candidates, not necessarily canonical founderOS work items. | Keep as evidence-backed candidates; promote through compatibility layer or explicit human workflow later. |
| Existing status snapshots and second-opinion findings | `Insight`, `Project`, briefing context | partial | Read-model findings and status summaries can be over-promoted into canonical entities. | Use findings as insight sources; freeze broad status/share surfaces until GitHub-first MVP E2E is stable. |
| Existing declarations and metrics | `Goal`, briefing context, workspace context | partial | Declarations are founder-provided facts, while goals need explicit lifecycle and ownership. | Keep declarations; add goals later after identity/workspace foundation. |

## 5. Collision Risks

| Risk | Consequence | Safe MVP approach |
|---|---|---|
| Duplicate source records | Provider/source facts could exist in both existing ingestion tables and a new canonical table with different IDs and freshness rules. | Keep `ingested_events`, `source_events`, and source documents as current source substrate; add `SourceRecord` only through a documented compatibility adapter or a carefully scoped migration. |
| `source_events` vs `SourceRecord` | Source event identity, idempotency, and raw refs could diverge. | Treat `source_events.source_event_id` plus provider fields as the current canonical source-event identity until a migration explicitly reconciles it. |
| Existing audit logs vs `AuditLog` | Two audit histories would weaken traceability and approval evidence. | Use existing `audit_logs` as the canonical audit baseline; extend later for workspace/user references instead of adding a parallel audit table. |
| Graph entities vs `NormalizedEntity` | Entity identity, aliases, merge status, and relationships could split. | Reuse graph tables as the normalized-entity substrate and add compatibility naming/constraints incrementally. |
| Existing agent proposals vs `ActionProposal` | Human approval state could split between proposal systems. | Reconcile `AgentProposal` fields with playbook semantics before adding new action proposal persistence. |
| Source-control requests vs `IntegrationConnection` / `ActionExecution` | A source run request could be confused with a connection, sync job, approval proposal, or execution result. | Add `IntegrationConnection` and `SyncJob` as separate foundations, then map `SourceRunRequest` to job/execution lifecycle deliberately. |
| Documents/chunks vs `Document` | Provider source documents could be confused with founderOS-authored documents. | Preserve `SourceDocument`/`DocumentChunk`; use `Document` naming carefully or defer until source/evidence compatibility is explicit. |
| Attention triage vs `BriefingItem` / `Insight` | Triage rows may be displayed as briefing facts without briefing lifecycle or review semantics. | Use triage as input to `BriefingItem`, not as the briefing item itself. |
| Existing API-key auth vs `User` / `Workspace` / `Membership` | New workspace-aware models could break operator routes or create ambiguous actor identity. | Add identity models without changing auth behavior first; introduce workspace-aware auth contract in FOS-BE-01. |
| Existing static `/ui` assumptions vs future workspace-aware UI | Local/operator UI could assume global data while the Next.js app expects workspace-scoped data. | Keep static `/ui` as local/operator UI; make future web shell workspace-aware separately. |

## 6. MVP Database Decision

### 6.1 What to add now

Add canonical identity first:

1. `User`
2. `Workspace`
3. `Membership`

Then add connection/sync foundation:

4. `IntegrationConnection`
5. `SyncJob`

Then define compatibility mapping for source and evidence:

6. `SourceRecord`, `EvidenceRef`, and `NormalizedEntity` should be implemented either as compatibility adapters over existing tables or as narrowly scoped canonical tables only after field-level reconciliation confirms no duplicate source of truth.

Then add founder-facing workflow foundations:

7. `Briefing`
8. `BriefingItem`
9. `ActionProposal`
10. `ActionExecution`

### 6.2 What to adapt instead of duplicate

Adapt or wrap these existing areas rather than duplicating them:

| Existing area | Adaptation decision |
|---|---|
| `audit_logs` | Use as canonical `AuditLog` baseline; add workspace/user refs later if required. |
| `ingested_events`, `source_events`, `source_documents`, `document_chunks` | Treat as source/evidence substrate; add `SourceRecord`/`EvidenceRef` compatibility before new persistence. |
| `entities`, `entity_aliases`, `entity_source_accounts`, `entity_links` | Treat as current normalized entity graph; map to `NormalizedEntity`. |
| `normalized_activity_items` | Keep as activity/read-model input to insights and briefings. |
| `attention_triage_results` | Use as briefing/insight source material, not canonical briefing rows. |
| `agent_proposals` | Reconcile with `ActionProposal` before adding another approval model. |
| `source_control_states`, `source_run_requests` | Map carefully to `IntegrationConnection`, `SyncJob`, and `ActionExecution`. |
| `gmail_threads`, `gmail_messages`, `email_thread_states` | Adapt to `MessageThread` and source/evidence compatibility. |
| `second_opinion_findings`, `knowledge_scores`, extracted decisions/risks | Use as insight candidates and ranking context. |

### 6.3 What to leave untouched

Do not touch these during FOS-DB-02:

- Existing source ingestion tables and services.
- Existing audit log table and audit-writing services.
- Existing graph entity tables and resolver services.
- Existing attention triage tables and digest behavior.
- Existing agent proposal and source-control request lifecycle.
- Existing Gmail/Drive/source document tables.
- Existing static `/ui` local/operator assumptions.
- Existing post-MVP surfaces such as share packs and broader status snapshots.

### 6.4 What to freeze as post-MVP

Keep these areas in the repository, but do not expand them before GitHub-first MVP E2E is stable:

- `share_packs` and investor/share-pack flows.
- Broad `status_snapshots` expansion beyond current read models.
- Advanced second-opinion workflows beyond MVP insight sources.
- Scheduler/outbox expansion and Telegram/manual pilot delivery flows.
- Jira write planning.
- Role agents, multi-model council, natural-language rule compiler, sandbox workflow execution.
- Advanced diagnostics, marketplace/plugins, mobile app, and compliance hardening beyond MVP baseline.

## 7. Recommended Migration Plan

### Migration 1 — Identity foundation

| Item | Detail |
|---|---|
| Purpose | Add canonical `User`, `Workspace`, and `Membership` without changing current API-key/operator behavior. |
| Likely files | New identity model module under `app/db/`; Alembic migration under `migrations/versions/`; metadata import in `migrations/env.py`; focused identity model tests. |
| Tests required | Model/constraint tests for user uniqueness, workspace uniqueness, membership uniqueness, membership role/status values, and Alembic metadata import. |
| Rollback caution | Do not bind existing source rows to workspace IDs in the same migration; avoid destructive backfills. |
| Acceptance criteria | Tables exist, constraints are enforced, metadata is visible to Alembic, existing routes/services continue to work unchanged. |

### Migration 2 — Connection/sync foundation

| Item | Detail |
|---|---|
| Purpose | Add canonical `IntegrationConnection` and `SyncJob` while preserving existing source-control state/run request behavior. |
| Likely files | New or existing integration DB model module; Alembic migration; source-control compatibility tests. |
| Tests required | Connection uniqueness per workspace/provider/account, sync job status lifecycle, no regression in `SourceControlState` and `SourceRunRequest` tests. |
| Rollback caution | Do not migrate credentials or live provider config in this step; avoid external writes and provider calls. |
| Acceptance criteria | Canonical connection/job rows can be created in tests, but existing source-control flows are untouched. |

### Migration 3 — Source/evidence compatibility

| Item | Detail |
|---|---|
| Purpose | Decide whether to add `SourceRecord`/`EvidenceRef` tables or expose compatibility adapters over `ingested_events`, `source_events`, `source_documents`, and chunk/evidence JSON fields. |
| Likely files | Source/evidence model or adapter module, evidence service tests, Alembic migration only if new tables are required. |
| Tests required | Mapping tests from source events/documents/chunks to canonical refs; duplicate-prevention tests; evidence lookup tests. |
| Rollback caution | Do not rewrite raw refs, source event IDs, document IDs, or evidence refs in bulk. |
| Acceptance criteria | One documented source/evidence identity path exists for MVP features; no duplicate source-of-truth table is introduced accidentally. |

### Migration 4 — Briefing foundation

| Item | Detail |
|---|---|
| Purpose | Add `Briefing` and `BriefingItem` for founder briefing generation with evidence-backed item references. |
| Likely files | Briefing DB model module; Alembic migration; briefing service/API tests. |
| Tests required | Briefing creation, item ordering, item evidence refs, workspace scoping, and status/lifecycle tests. |
| Rollback caution | Do not convert all attention triage or digest rows into briefing items in the first migration. |
| Acceptance criteria | Manual Founder Briefing v0 can persist a briefing and evidence-backed items without changing source ingestion. |

### Migration 5 — Human-approved actions

| Item | Detail |
|---|---|
| Purpose | Add or reconcile `ActionProposal` and `ActionExecution` so AI suggestions and external writes remain human-approved. |
| Likely files | Action proposal/execution model module or adaptation of `AgentProposal`; Alembic migration; approval/action API tests. |
| Tests required | Proposal lifecycle, approval/rejection, execution status, idempotency, audit log linkage, and no-direct-AI-write guard tests. |
| Rollback caution | Do not wire live provider writes into this migration. Keep execution records local/test-only until explicit provider approval flow exists. |
| Acceptance criteria | Human-approved action persistence exists with auditability, but no live external write path is enabled by the migration itself. |

## 8. Implementation Notes for FOS-DB-02

Next task: FOS-DB-02 — Add User/Workspace/Membership models.

Use the existing SQLAlchemy/Alembic conventions:

- Use `app.db.base.Base` and async-session-compatible SQLAlchemy models.
- Put identity models in a focused DB module such as `app/db/identity_models.py`.
- Import the new module in `migrations/env.py` so Alembic metadata can see the tables.
- Prefer existing timestamp style: timezone-aware `created_at`/`updated_at`, server defaults where the codebase already uses them, and explicit update behavior.
- Use canonical UUID primary keys for `User`, `Workspace`, and `Membership` unless implementation review finds an established local helper that should be reused. Keep external/provider IDs separate from canonical IDs.
- Use `String` status/role fields with explicit constraints/tests unless the repo already has a local enum/check-constraint pattern selected during implementation.

Recommended constraints:

- `users.email` unique, normalized lower-case at the application boundary, nullable only if the auth contract explicitly allows it.
- `workspaces.slug` unique if slugs are added.
- `memberships` has foreign keys to `users` and `workspaces`.
- Unique membership per `(workspace_id, user_id)`.
- Membership role supports at least owner/admin/member or the smallest equivalent set chosen for MVP.
- Membership status supports active/invited/disabled or the smallest equivalent set chosen for MVP.
- Add indexes for `workspace_id`, `user_id`, and common auth lookup fields.

Recommended tests:

- Model metadata/import test for identity models.
- Constraint test for unique user email.
- Constraint test for unique workspace slug, if slug exists.
- Constraint test for one membership per user/workspace.
- Relationship/cascade test only if cascade semantics are explicitly chosen.
- Alembic migration smoke test if the repo has an established migration test pattern.

Commands to run for FOS-DB-02:

```bash
git status --short
UV_NO_SYNC=1 uv run ruff check .
UV_NO_SYNC=1 uv run pytest -q <focused identity/migration tests>
git diff --check
```

Run broader tests only if the implementation touches shared metadata/import paths or existing auth behavior.

## 9. Open Questions / Assumptions

- MVP starts with one owner per workspace, then expands membership roles after the identity foundation exists.
- Existing API-key auth remains temporarily for operator routes.
- Workspace-aware auth is introduced gradually in FOS-BE-01, after identity tables exist.
- Static `/ui` remains local/operator UI until the separate Next.js web shell exists.
- Existing rows are not backfilled into workspaces during FOS-DB-02.
- Existing source/evidence tables remain the source substrate until Migration 3 resolves compatibility.
- AI remains evidence-first and does not directly mutate production data.
- External writes remain blocked behind human-approved action proposals.

## 10. Final Recommendation

Ready for FOS-DB-02: YES.

Why: the current repo has no exact `User`, `Workspace`, or `Membership` equivalents, and adding identity foundation tables is the lowest-collision first migration. Existing source, evidence, graph, action, and audit areas already have partial equivalents and should not be duplicated before compatibility mapping is implemented.

What exact task should be run next: FOS-DB-02 — Add User/Workspace/Membership models.
