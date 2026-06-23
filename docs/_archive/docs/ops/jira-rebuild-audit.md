# Jira Rebuild Audit

Status: read-only audit draft. No Jira writes, issue moves, board edits,
workflow edits, field edits, or live sync/provider/bot commands were executed
while preparing this document.

This report is the control document for rebuilding Jira from the current
disordered state into a clean operating model while preserving history. It is
evidence-led: items marked `observed` are backed by repository contracts or
future Jira exports; items marked `pending export` must be filled from the
read-only evidence package before any write migration is approved.

## Evidence Register

| Evidence ID | Source | Status | What It Supports |
|---|---|---:|---|
| E1 | `docs/runbooks/jira-operating-model.md` | observed | Existing safe Jira operating model, recommended project classes, issue type classes, workflow status classes, governance rules, and read-only/write boundaries. |
| E2 | `app/services/jira_operating_model.py` | observed | Machine-readable recommended classes: product-area model, components as repos/services, statuses, priorities, governance rules. |
| E3 | `app/services/jira_creation_dry_run.py` | observed | No-write dry-run model and blocked write-operation classes. |
| E4 | `scripts/check_jira_readonly_inventory.py` | observed | Guarded read-only inventory command that suppresses provider payloads and reports safe counts/classes only. |
| E5 | `scripts/plan_jira_creation_dry_run.py` | observed | No-live, no-write creation dry-run report. |
| E6 | `scripts/plan_jira_write_readiness.py` | observed | Dry-run-only write readiness report; does not execute Jira writes. |
| E7 | Jira projects/boards/workflows/issues export package | pending export | Actual current Jira inventory and content mapping. |

## Current Inventory

### Evidence-backed current facts

- FounderOS already has guarded Jira read-only diagnostics and no-write planning
  scripts; this audit does not need new application infrastructure.
- Existing repository contracts classify Jira as read-only until a separate
  write approval exists.
- The recommended target model already exists as safe classes in the repo:
  `product_area_model`, repo/service components, eight issue type classes,
  eight workflow status classes, five priority classes, and governance rules.
- Current live Jira project, board, workflow, field, status, and issue content
  was not fetched in this task. It remains `pending export` and must not be
  inferred from memory or chat.

### Required current-state inventory package

The founder should collect these read-only exports before this document is
converted from draft to final audit:

| File | Required Fields | Purpose |
|---|---|---|
| `audit_exports/jira/projects.json` | project id, key, name, type, lead/account class, category, issue type scheme, workflow scheme, field config scheme, permission scheme | Identify current project sprawl and scheme reuse. |
| `audit_exports/jira/boards.json` | board id, name, type, filter id/JQL, project keys, location | Identify board duplication and cross-project boards. |
| `audit_exports/jira/board-configs/*.json` | columns, statuses per column, estimation, ranking, subquery | Map current board behavior to target boards. |
| `audit_exports/jira/workflows.json` | workflow names, statuses, transitions, validators/post-functions if exportable | Build target workflow/status mapping. |
| `audit_exports/jira/issue-types.json` | issue type ids/names/descriptions/subtask flag | Map current issue types to target types. |
| `audit_exports/jira/fields.json` | field id/name/type/custom flag/screens/context | Identify custom-field cleanup and required migration fields. |
| `audit_exports/jira/statuses.json` | status id/name/category | Build status consolidation map. |
| `audit_exports/jira/issues-open.csv` | key, project, issue type, status, priority, assignee, reporter, component, labels, epic link/parent, sprint, fix versions, created/updated/resolved, summary | Map active work into the new model. |
| `audit_exports/jira/issues-recently-closed.csv` | same as open export plus resolution/resolved | Validate history preservation and reporting continuity. |
| `audit_exports/jira/links-and-subtasks.csv` | key, parent, issue links, blocks/is blocked by, epic/parent | Preserve hierarchy and dependencies. |
| `audit_exports/jira/sprints-versions-components.csv` | sprint names/state, versions, components | Decide what to recreate versus archive. |
| `audit_exports/jira/automation-and-permissions.md` | automation rules, project roles, permission schemes, notification schemes | Avoid recreating unsafe automation or overbroad permissions. |

## Detected Problems

The following are known from task context and repo planning docs:

1. Current boards were created and maintained inconsistently.
2. The target should be a clean Jira structure, not incremental cleanup inside
   the current disorder.
3. Jira writes and bulk changes must be separated from audit and require a
   separate approved prompt.
4. Existing scripts intentionally suppress raw Jira names/text in sanitized
   reports, so a full operational audit requires founder-held export files.

The following problems are likely but must be confirmed from `E7`:

- Duplicate boards for the same product or repository.
- Projects used for repositories instead of product/operating areas.
- Status proliferation that cannot support consistent reporting.
- Issue types used inconsistently, for example task/story/epic mixed by habit.
- Missing components, owners, acceptance criteria, blocker reasons, and done
  validation.
- Filters/boards based on personal or stale JQL.
- Legacy closed issues mixed with active migration candidates.
- Custom fields created for one-off needs without governance.

## Target Jira Model

The target model is the existing repository operating model, not a new
architecture:

- Model class: `product_area_model`.
- Jira projects represent product or operating areas.
- Repositories and services map to Components, not separate Jira projects.
- Boards are views over product/engineering/support work, not sources of truth.
- History remains in Jira issues; old projects can stay read-only during
  transition.

### Target project classes

Use these classes from `E1/E2` as the starting point:

- `ssap_digital_twin`
- `kazscan_corporate`
- `infrastructure_data`
- `rd_3d_ar`
- `marketing_corporate`
- `ops_support`

Final project names and keys are decision items and must be approved after the
current inventory package is reviewed.

### Target boards

Use the dry-run board classes from `E3`:

- `product_roadmap_board`: epics/stories/features by product area.
- `engineering_sprint_board`: implementation flow by team or active sprint.
- `support_bugs_kanban`: bugs/incidents/support work.
- `infrastructure_ops_kanban`: infra/data/ops work.

Each board must have an owned filter, documented JQL, and explicit included
project/component scope.

### Target issue type mapping

| Target Type | Use For | Migration Rule |
|---|---|---|
| Epic | Product-level outcomes and large initiatives | Preserve existing epics where useful; otherwise create a migration parent epic only after approval. |
| Story | User/business behavior increments | Map feature-like tasks with acceptance criteria. |
| Task | Operational or implementation work without user-story shape | Default fallback for active work that is not bug/incident/spike/tech debt. |
| Bug | Defects with reproduction or expected/actual behavior | Require reproduction context. |
| Subtask | Breakdown under a parent issue | Preserve hierarchy when parent is in migration scope. |
| Incident | Production/customer-impacting interruptions | Require impact, timeline, resolution owner. |
| Tech Debt | Refactoring/maintenance with risk or cost evidence | Require reason and expected payoff. |
| Spike | Time-boxed investigation | Require question, decision deadline, and output. |

### Target workflow/status mapping

| Target Status | Meaning | Current Status Mapping Rule |
|---|---|---|
| Backlog | Not selected for active work | Map To Do/Idea/New/Open items not ready for execution. |
| Ready | Prioritized and ready to start | Map selected Todo/Ready/Selected for Development. |
| In Progress | Owner actively working | Map In Progress/Doing/Implementation. |
| Code Review | PR/review or technical review is active | Map Review/Code Review/PR Review. |
| Validation | QA/UAT/product validation | Map QA/Testing/Validation/UAT. |
| Ready for Release | Accepted but not released | Map Done-like statuses that still await deploy/release. |
| Done | Released/closed and no active work remains | Map Done/Closed/Resolved only when resolution is valid. |
| Blocked | Work cannot proceed without external decision/dependency | Map Blocked/On Hold/Waiting only with blocker reason. |

Status mapping must be validated against issue history: do not flatten
`Resolved`, `Closed`, and `Done` until resolution and release semantics are
known.

### Target fields and governance

Required core fields:

- Summary
- Description
- Issue type
- Status
- Priority
- Assignee or owner
- Reporter
- Component
- Labels
- Parent/Epic
- Sprint or Kanban class when applicable
- Fix version/release when applicable
- Due date only when there is a real deadline

Governance rules from `E1/E2`:

- Require component.
- Require owner.
- Require acceptance criteria for story/task.
- Require blocker reason for blocked work.
- Done requires validation.
- Bugs require reproduction context.
- Incidents require impact and resolution context.

## Mapping Plan

### Project and board mapping

Build a mapping table after `E7` is available:

| Current Project/Board | Evidence File | Target Project Class | Target Board Class | Action |
|---|---|---|---|---|
| pending export | `projects.json`, `boards.json` | pending decision | pending decision | keep read-only until mapped |

Allowed actions during audit:

- Read and classify exports.
- Propose target mapping.
- Mark unknowns as `needs founder decision`.

Forbidden actions during audit:

- Creating projects/boards/fields/workflows.
- Editing filters, schemes, permissions, automation, or issue data.
- Moving issues or bulk-changing statuses/types/components.

### Issue content mapping

Use this sequence:

1. Classify issues into active/open, recently closed, archive-only.
2. Map each current project to a target product area.
3. Map each issue type to the target type table.
4. Map each status to the target workflow table.
5. Map components/repos/services; create component proposal rows for missing
   components.
6. Preserve parent/epic/subtask/link relationships where both endpoints are in
   migration scope.
7. Preserve labels, versions, sprint metadata, and comments/history by using
   Jira move/bulk-change operations only after separate approval.
8. Do not migrate unknown/low-evidence issues automatically; park them in a
   founder review queue.

## Content Migration Strategy

Recommended strategy:

1. Keep existing Jira projects read-only during transition.
2. Create clean target projects/boards/workflows in a separate approved write
   step.
3. Migrate active/open work first.
4. Migrate recently closed work only if it is needed for reports or roadmap
   continuity.
5. Leave old closed/archive work in old projects unless there is a concrete
   reporting need to move it.
6. Maintain an issue mapping CSV with old key, new key if key changes, target
   project, target type, target status, and migration decision.
7. Validate counts before and after every dry-run/import batch.

If Jira move operations preserve issue keys within the same site only under
specific project-key conditions, treat key preservation as a risk until tested
in dry-run. Comments, attachments, history, links, watchers, and sprints must be
verified on sampled issues before bulk migration.

## Dry-Run Plan

Run these locally/manually; the agent did not run them in this task.

### Existing sanitized repo reports

No live calls:

```bash
uv run python scripts/plan_jira_creation_dry_run.py --json
uv run python scripts/plan_jira_write_readiness.py --json --dry-run
```

Synthetic read-only inventory:

```bash
uv run python scripts/check_jira_readonly_inventory.py --synthetic --compare-portfolio --json
```

Founder-run live read-only inventory, only if Jira credentials are configured:

```bash
uv run python scripts/check_jira_readonly_inventory.py \
  --allow-live-readonly-apis \
  --acknowledge-live-readonly-risk "ALLOW LIVE PROVIDER EXECUTION" \
  --compare-portfolio \
  --max-results 100 \
  --json
```

### Manual read-only Jira export commands

These commands are examples for the founder/operator to run locally. They must
not be run by an agent in this audit slice. They use environment variables and
write local files; do not paste secrets or raw issue bodies into chat.

```bash
mkdir -p audit_exports/jira/board-configs

curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/project/search?maxResults=100" \
  > audit_exports/jira/projects.json

curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/agile/1.0/board?maxResults=100" \
  > audit_exports/jira/boards.json

curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/issuetype" \
  > audit_exports/jira/issue-types.json

curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/field" \
  > audit_exports/jira/fields.json

curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/status" \
  > audit_exports/jira/statuses.json
```

For issues, prefer Jira UI CSV exports with selected fields rather than dumping
full raw JSON. Export:

- `issues-open.csv`: all unresolved/open work.
- `issues-recently-closed.csv`: resolved/closed in the last 180 days.
- `links-and-subtasks.csv`: issue key, parent, epic, linked issues.
- `sprints-versions-components.csv`: current project sprint/version/component
  metadata.

If board configurations are needed, collect board ids from `boards.json` and
run a read-only config export per board:

```bash
BOARD_ID="replace-with-board-id"
curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/agile/1.0/board/$BOARD_ID/configuration" \
  > "audit_exports/jira/board-configs/$BOARD_ID.json"
```

## Rollback Plan

Rollback must be designed before any write migration:

1. Old projects stay accessible and read-only until the founder signs off.
2. Do not delete old projects, boards, fields, workflows, filters, or schemes
   during migration.
3. Keep pre-migration exports and mapping CSV immutable.
4. For each batch, record old issue key, target issue key, target project,
   timestamp, operator, and operation class.
5. If a batch produces incorrect mappings, stop immediately; do not run a
   corrective bulk change until a separate fix plan is approved.
6. Rollback default is operational rollback: restore use of old boards and stop
   using target boards. Data rollback by moving issues back is a separate
   high-risk write operation and requires explicit approval.

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Current inventory incomplete | Wrong target model or missing boards/projects | Require `E7` before write approval. |
| Issue history/key behavior differs during moves | Loss of traceability or broken references | Test representative issues in dry-run/sandbox before bulk move. |
| Custom fields carry hidden reporting dependencies | Reports break after cleanup | Export fields/screens/reports before field decisions. |
| Automation rules fire during migration | Unexpected notifications or issue changes | Inventory and disable/adjust automation only in approved write step. |
| Permissions/schemes differ by project | Users lose access or gain overbroad access | Export permission schemes and validate with founder. |
| Status flattening loses meaning | Metrics become unreliable | Map statuses with resolution/release semantics, not only names. |
| Old boards continue to be used | Split-brain operations | Announce cutover, freeze old boards, keep old read-only for audit. |
| Raw exports contain private issue text/users | Sensitive data leakage in chat/reports | Store exports locally; summarize only evidence classes unless audit report explicitly allows names. |

## Open Questions

1. Which Jira site/cloud instance is the source of truth?
2. Which current projects are still active?
3. Which boards are actively used by the team versus abandoned?
4. Which project keys must be preserved for external references?
5. Is the goal to preserve issue keys, or is an old-key to new-key mapping
   acceptable?
6. Which closed issues must move for reporting continuity?
7. Which users/roles must retain access after rebuild?
8. Which automations, notifications, and integrations currently depend on Jira?
9. Should old Jira projects be archived after a stabilization period, or kept
   permanently read-only?
10. What is the acceptable migration window and freeze period?

## Founder Decision Checklist

Before any write migration, the founder must approve:

- [ ] Current inventory package `E7` is complete enough.
- [ ] Target project list and project keys.
- [ ] Target board list and JQL/filter ownership.
- [ ] Workflow/status map.
- [ ] Issue type map.
- [ ] Required fields and governance rules.
- [ ] Active/open issue migration scope.
- [ ] Closed/archive issue migration scope.
- [ ] Key preservation versus key mapping policy.
- [ ] Permission/role model.
- [ ] Automation handling plan.
- [ ] Dry-run batch size and sample issues.
- [ ] Rollback plan.
- [ ] Separate approved write prompt for creation/migration.

## Actions Requiring Separate Approval

The following actions are explicitly out of scope for this audit:

- Create Jira projects.
- Create or edit boards, filters, columns, or swimlanes.
- Create or edit workflows, workflow schemes, screens, fields, field contexts,
  issue type schemes, permission schemes, notification schemes, or automation.
- Create, move, clone, bulk-change, delete, archive, transition, assign, link,
  comment on, or otherwise mutate Jira issues.
- Run live Jira sync or FounderOS provider commands that write source events or
  raw storage.
- Enable scheduler, bot, or provider execution for this migration.
