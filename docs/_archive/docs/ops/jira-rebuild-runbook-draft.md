# Jira Rebuild Runbook Draft

Status: draft. This runbook is safe to review. It does not approve or execute
Jira writes. Every write step is a future approval gate.

## Purpose

Rebuild Jira from disordered current projects/boards into a clean operating
model while preserving issue history and avoiding accidental writes. The process
has three modes:

1. Read-only evidence collection.
2. No-write dry-run planning.
3. Separately approved write migration.

## Safety Rules

- Do not run Jira write APIs during audit.
- Do not create, edit, move, delete, transition, archive, assign, comment on,
  or bulk-change Jira issues until a future write approval exists.
- Do not run live FounderOS sync/provider/bot commands for this audit.
- Do not paste Jira credentials, tokens, chat IDs, `.env` contents, raw issue
  bodies, comments, attachments, or provider payloads into chat.
- Keep old Jira projects and boards intact until post-migration sign-off.
- Treat old Jira as the rollback path; never destroy it during migration.

## Phase 0 - Freeze And Ownership

Goal: prevent audit drift.

Checklist:

- [ ] Name a founder owner for the rebuild decision.
- [ ] Name a Jira admin/operator for future approved writes.
- [ ] Agree that this runbook is read-only until explicit write approval.
- [ ] Decide the audit export storage path, for example `audit_exports/jira/`.
- [ ] Avoid changing current Jira structure while evidence is being collected.

Output:

- Audit owner.
- Export folder.
- Freeze window or note that no freeze is possible.

## Phase 1 - Read-Only Evidence Collection

Goal: collect enough evidence to map current Jira safely.

### 1.1 Repo-local safe reports

Run no-live/no-write reports:

```bash
uv run python scripts/plan_jira_creation_dry_run.py --json \
  > audit_exports/jira/founderos-jira-creation-dry-run.json

uv run python scripts/plan_jira_write_readiness.py --json --dry-run \
  > audit_exports/jira/founderos-jira-write-readiness.json

uv run python scripts/check_jira_readonly_inventory.py --synthetic --compare-portfolio --json \
  > audit_exports/jira/founderos-jira-inventory-synthetic.json
```

Optional founder-run live read-only sanitized report:

```bash
uv run python scripts/check_jira_readonly_inventory.py \
  --allow-live-readonly-apis \
  --acknowledge-live-readonly-risk "ALLOW LIVE PROVIDER EXECUTION" \
  --compare-portfolio \
  --max-results 100 \
  --json \
  > audit_exports/jira/founderos-jira-inventory-live-readonly.json
```

Expected behavior:

- No Jira writes.
- Sanitized JSON only.
- Provider payloads suppressed.
- Counts/classes are safe; raw names/text may still require manual exports.

### 1.2 Jira UI/API read-only exports

Create the folder:

```bash
mkdir -p audit_exports/jira/board-configs
```

Export projects/boards/schemes from Jira UI when possible. If using read-only
API commands locally, use environment variables and do not print secrets:

```bash
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

Export issue CSVs from Jira UI with selected fields:

- `issues-open.csv`: unresolved/open issues.
- `issues-recently-closed.csv`: resolved/closed in the last 180 days.
- `links-and-subtasks.csv`: parent, epic, issue links.
- `sprints-versions-components.csv`: active sprint, version, component data.

Export board configurations per board id:

```bash
BOARD_ID="replace-with-board-id"
curl -sS -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/agile/1.0/board/$BOARD_ID/configuration" \
  > "audit_exports/jira/board-configs/$BOARD_ID.json"
```

### 1.3 Evidence review

Populate:

- Current project list.
- Current board list.
- Current workflow/status list.
- Current issue type list.
- Custom fields and required fields.
- Active/open issue counts by project/type/status.
- Board filters and ownership.
- Known automation/permission risks.

Stop condition:

- If exports are incomplete or contradictory, stop and update open questions.
  Do not proceed to write planning.

## Phase 2 - Target Model Design

Goal: approve the desired target model before migration mapping.

Use `docs/ops/jira-rebuild-audit.md` as the design record.

Decisions:

- Target project names and keys.
- Target board names and filters.
- Target workflow/status map.
- Target issue type map.
- Component strategy.
- Required fields and governance rules.
- Permission scheme and project roles.
- Automation policy.

No writes are allowed in this phase.

## Phase 3 - Migration Mapping

Goal: create a deterministic mapping package.

Create these local files:

- `audit_exports/jira/mapping-projects.csv`
- `audit_exports/jira/mapping-boards.csv`
- `audit_exports/jira/mapping-statuses.csv`
- `audit_exports/jira/mapping-issue-types.csv`
- `audit_exports/jira/mapping-fields.csv`
- `audit_exports/jira/mapping-components.csv`
- `audit_exports/jira/mapping-issues-open.csv`
- `audit_exports/jira/mapping-issues-archive.csv`

Minimum columns for `mapping-issues-open.csv`:

```text
old_key,current_project,current_type,current_status,target_project,target_type,target_status,target_component,migrate_decision,reason,founder_decision_required
```

Rules:

- Every active issue must have a target project/type/status or
  `founder_decision_required=true`.
- Every blocked issue must have blocker context or stay in review.
- Every done/closed issue must preserve resolution semantics.
- Unknown mappings do not default to bulk migration.

## Phase 4 - No-Write Dry Run

Goal: validate the plan without changing Jira.

Run:

```bash
uv run python scripts/plan_jira_creation_dry_run.py --json \
  > audit_exports/jira/founderos-jira-creation-dry-run-final.json

uv run python scripts/plan_jira_write_readiness.py --json --dry-run \
  > audit_exports/jira/founderos-jira-write-readiness-final.json
```

Manual dry-run checks:

- Target project count matches approved project list.
- Target board count matches approved board list.
- All blocked write-operation classes are understood.
- Migration mapping CSVs have no missing required target fields for active
  issues.
- Sample issues are selected for future sandbox or test migration.

Stop condition:

- Any missing mapping, unknown workflow/status, or unresolved permission risk
  blocks write approval.

## Phase 5 - Approval Gate For Write Migration

This phase is a decision gate only. It must produce a separate approved prompt
or ticket before any write command exists.

Founder must approve:

- Target model.
- Mapping CSVs.
- Batch size.
- Migration window.
- Communication plan.
- Rollback plan.
- Jira admin/operator.
- Exact write operation classes.

The approved write plan must explicitly say which of these are allowed:

- Create projects.
- Create components.
- Create issue types/schemes.
- Create workflows/schemes.
- Create boards/filters.
- Create fields/contexts.
- Move or bulk-change issues.
- Update links/parents/components/versions.
- Disable/adjust automation.
- Archive or restrict old projects.

Everything not explicitly allowed remains forbidden.

## Phase 6 - Approved Write Migration

This phase is intentionally not executable from this draft.

Recommended future sequence after approval:

1. Create target projects and schemes.
2. Create target components.
3. Create target boards/filters.
4. Create target workflow and status mapping.
5. Migrate a small approved sample batch.
6. Validate sample history, comments, links, parents, attachments, watchers,
   status, type, component, labels, and reporting.
7. Migrate active/open issues in small batches.
8. Validate counts after every batch.
9. Move recently closed issues only if approved.
10. Keep old projects read-only until stabilization is complete.

## Phase 7 - Validation

Validate after every write batch:

- Old issue count versus migrated issue count.
- Active issues by target project/type/status.
- Parent/epic/subtask relationships.
- Issue links.
- Comments/attachments/history samples.
- Components/versions/sprints.
- Board visibility and filter correctness.
- Permissions for founder and team.
- Automation and notifications did not fire unexpectedly.
- FounderOS Jira sync can still read required issues after approval to run sync
  in a later separate step.

No FounderOS live sync is part of this runbook unless separately approved.

## Phase 8 - Rollback And Stabilization

Rollback policy:

- Default rollback is operational: stop using the new boards and return to old
  read-only boards.
- Data rollback by moving issues back is a write migration and requires a
  separate approval.
- Keep export snapshots and mapping CSVs immutable.
- Do not delete old projects until the stabilization period ends.

Stabilization checklist:

- [ ] Team confirms target boards are usable.
- [ ] Founder confirms reporting/status needs are met.
- [ ] No missing active issues.
- [ ] No broken critical links or parent relationships.
- [ ] Permissions are correct.
- [ ] Old boards are marked read-only or clearly deprecated.
- [ ] Archive/delete decisions are deferred to a later approved cleanup.

## Approval Matrix

| Action | Allowed In This Draft? | Requires Separate Approval? |
|---|---:|---:|
| Review docs | yes | no |
| Run no-live dry-run scripts | yes | no |
| Founder runs live read-only inventory | yes, manually | provider acknowledgement |
| Export Jira CSV/JSON read-only data | yes, manually | no write approval |
| Create projects/boards/workflows/fields | no | yes |
| Move/bulk-change issues | no | yes |
| Archive/delete old Jira data | no | yes |
| Run FounderOS live Jira sync | no | yes |
| Run Telegram bot/provider commands | no | yes |

## Next Minimal Step

Founder runs the read-only export package in Phase 1 and stores the outputs
locally. Then update `docs/ops/jira-rebuild-audit.md` with actual inventory and
mapping tables before any write dry-run becomes actionable.
