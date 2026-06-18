# Jira Target Blueprint

Status: design artifact. No Jira writes, no live calls, no migration are
performed or approved by this document. It defines the **format and rules** of
the clean target Jira model that FounderOS will operate on. Specific names,
keys, and area-to-project assignments are **founder decisions filled from
discovery** (see `jira-rebuild-audit.md` and the Discovery Inputs section
below), not invented here.

This blueprint follows the agreed approach: do **not** rebuild on top of the
current disordered Jira. Design a clean model from scratch, keep the old Jira
read-only as archive/reference, do not auto-migrate, and gate every write
behind approval.

All examples use neutral placeholders only (playbook §0.2): `Project Alpha`,
`Client One`, `Person A`, `repo-alpha-api`, `ALPHA-101`. Real product areas and
keys are decided after discovery.

## 1. Why a clean rebuild

The current Jira accumulated inconsistent boards, projects-per-repo, status
proliferation, and habit-mixed issue types. Incremental cleanup inside that
disorder is slower and riskier than operating a clean model and treating the
old instance as read-only history. The target below is the operating contract
the future Jira source-agent reads and (only after approval) writes.

## 2. Project model

- Model class: `product_area_model` — one Jira project per product or operating
  area, **not** one per repository.
- Repositories and services map to **Components** inside a project (§5).
- Boards are views over work, never the source of truth (§6).

Target area slots (neutral placeholders — map real areas during discovery):

| Area slot | Holds | Founder decision |
|---|---|---|
| `area-product-core` | Core product engineering | name + key |
| `area-product-platform` | Shared platform/infra/data | name + key |
| `area-rnd` | R&D / exploratory | name + key |
| `area-corporate` | Corporate / marketing / brand | name + key |
| `area-ops-support` | Ops, support, incidents | name + key |

Rules:

- Project keys are short, stable, uppercase, and chosen once (changing keys
  later breaks external references). Decide preserved-vs-new keys in discovery.
- A new area is created only when work genuinely does not fit an existing area;
  default is to add a Component, not a project.

## 3. Issue types

Closed set (no ad-hoc types):

| Type | Use for |
|---|---|
| Epic | Product-level outcome / large initiative |
| Story | User/business behavior increment (has acceptance criteria) |
| Task | Implementation/operational work without user-story shape |
| Bug | Defect with reproduction / expected-vs-actual |
| Subtask | Breakdown under a parent |
| Incident | Production/customer-impacting interruption |
| Tech Debt | Refactor/maintenance with stated reason + payoff |
| Spike | Time-boxed investigation with a question + decision deadline |

## 4. Workflow and statuses

Single shared workflow, closed status set:

`Backlog → Ready → In Progress → Code Review → Validation → Ready for Release → Done`,
plus `Blocked` as a side state reachable from any active status.

| Status | Meaning | Exit condition |
|---|---|---|
| Backlog | Not selected for active work | Prioritized → Ready |
| Ready | Prioritized, owner assignable, DoR met (§8) | Owner starts → In Progress |
| In Progress | Owner actively working | Work submitted → Code Review |
| Code Review | PR / technical review active | Review passed → Validation |
| Validation | QA / UAT / product validation | Accepted → Ready for Release |
| Ready for Release | Accepted, awaiting deploy/release | Released → Done (DoD met, §8) |
| Done | Released/closed, no active work | terminal |
| Blocked | Cannot proceed without external decision/dependency | requires blocker reason; returns to prior active status |

Statuses are **not** flattened by name during any future migration — resolution
and release semantics are mapped explicitly (`jira-rebuild-audit.md`).

## 5. Components (repo ↔ project)

Strategy: `repo_as_component`. Each repository (and each long-lived service)
becomes a Component inside its owning area project.

Mapping schema (filled in discovery — one row per repo):

```text
repo, owning_area_project, component_name, component_lead, status(active/archived), notes
repo-alpha-api, area-product-core, repo-alpha-api, Person A, active, pilot repo
```

Rules:

- Exactly one owning project per repo; cross-area work is linked, not
  duplicated.
- A repo with no clear owner is a **manual decision**, not an auto-assignment.
- The pilot repo is wired first end-to-end before the rest (§9).

## 6. Boards

Boards are filtered views with an owned filter and documented JQL:

| Board | Scope |
|---|---|
| `product-roadmap` | Epics/stories by area (planning view) |
| `engineering-sprint` | Active implementation flow by team/sprint |
| `support-incidents` | Bugs/incidents/support |
| `infra-ops` | Infra/data/ops work |

Each board declares its included projects/components and a named filter owner.
No personal or stale JQL boards.

## 7. Labels and priorities

Priorities (closed): `p0-critical`, `p1-high`, `p2-normal`, `p3-low`,
`p4-idea`.

Labels are a **controlled vocabulary**, not free text. Namespaced
`prefix:value` so the agent can parse them deterministically:

- `client:<slug>` — links work to a client entity.
- `risk:<type>` — `risk:timeline`, `risk:dependency`, `risk:security`.
- `source:<system>` — provenance when an issue was created from another source
  (`source:email`, `source:meeting`, `source:second-opinion`).
- `needs:<thing>` — `needs:owner`, `needs:acceptance-criteria`, `needs:repro`.

Free-form labels are allowed only as `tmp:<x>` and are never used for
reporting. The agent proposes label normalization; it does not silently relabel.

## 8. Governance — Definition of Ready / Done

Governance rules (enforced as review gates, not silent automation):
`require_component`, `require_owner`, `require_acceptance_criteria` (story/task),
`require_blocker_reason`, `done_requires_validation`,
`bugs_require_reproduction_context`, `incidents_require_impact_resolution`.

**Definition of Ready** (to enter `Ready`):

- Component set; owner assignable; priority set.
- Story/Task: acceptance criteria present.
- Bug: reproduction / expected-vs-actual present.
- Spike: question + decision deadline + expected output.
- Linked source evidence where the issue came from a source event.

**Definition of Done** (to enter `Done`):

- Validation passed (`done_requires_validation`).
- Linked PR(s) merged for code work; or explicit no-code rationale.
- Acceptance criteria checked off.
- Release/fix version set when applicable.
- No open blocking links.

## 9. Rollout sequence

Strict order, each step gated by verification before the next:

1. Create the clean target structure (projects, components, workflow, boards,
   schemes) — **write step, requires approval** (FOS-007E + dry-run first).
2. Wire the pilot: one current frontend repo as a Component; verify the
   repo ↔ project ↔ task linkage and the second-opinion engineering checks read
   it correctly.
3. Validate the pilot end-to-end (status snapshots, Jira↔GitHub reality check)
   before scaling.
4. Onboard the remaining repos (≈19) into the org and map each to a
   Component (§5) in small batches, validating counts each batch.
5. Only then build/enable the Jira **source-agent** on the clean structure.

Old Jira stays read-only as archive/reference throughout; nothing is
auto-migrated. The "do-not-migrate" list and per-issue migration decisions live
in the discovery package, not here.

## 10. Agent operating rules

The future Jira source-agent operates under the platform's read/propose/approve
model:

- **May, automatically (read-only):** read issues/boards/components; build
  status snapshots; run second-opinion checks (Jira-in-progress-without-code,
  PR-without-Jira, stale issue, missing owner, stale review); propose label
  normalization, owner gaps, and acceptance-criteria gaps as `AgentProposal`s;
  draft rich issue payloads.
- **May only after founder approval (write):** create projects/components,
  create/update/transition/comment issues, bulk changes, migration moves.
- **Enforcement:** every write goes through `write_action_guard`
  (`require_approved_write_action`, FOS-007E) — feature flag + an accepted
  `AgentProposal` (`kind="external_write_action"`, payload `write_boundary`) +
  live-provider ack. LLM output can draft and file proposals; it can never
  approve or execute a write.
- **Never:** invent issues without evidence; relabel/move silently; expose
  secrets; act outside the configured project/repo scope.

## 11. Discovery inputs (founder-run, read-only)

The specifics this blueprint leaves open are filled from a read-only discovery
package the founder runs locally. Reuse the existing safe paths — see
`jira-rebuild-runbook-draft.md` Phase 1 for exact commands:

- Jira legacy inventory: `scripts/check_jira_readonly_inventory.py` (sanitized)
  plus founder-run Jira UI/API exports (`projects.json`, `boards.json`,
  `issue-types.json`, `fields.json`, `statuses.json`, issue CSVs).
- GitHub repo discovery: `scripts/check_github_org_readonly_inventory.py` for
  org counts; then per-repo domains from README/structure/package files to
  decide area ownership.

Discovery must produce (stored locally, summarized as safe classes):

1. Legacy Jira inventory (projects/boards/workflows/statuses/fields/labels).
2. Repo inventory + proposed area/component ownership (§5 schema).
3. `area-*` → real project name/key decisions (§2).
4. Current → target mapping (projects, statuses, issue types, components).
5. Migration plan + per-issue decisions (active / archive-only).
6. **Do-not-migrate list** (legacy noise to leave in read-only archive).
7. Dry-run write plan (`plan_jira_creation_dry_run.py` output).
8. Manual-decisions list for the founder.

Nothing in discovery writes to Jira; credentials and raw issue text stay local
and out of chat.

## 12. Founder decision checklist

- [ ] Real area names + project keys for each `area-*` slot (§2).
- [ ] Preserve-keys vs new-keys policy.
- [ ] Repo → area/component ownership for the pilot repo and the rest (§5).
- [ ] Board filter ownership (§6).
- [ ] Client/risk label slugs (§7).
- [ ] Which legacy issues are migrated vs archived (do-not-migrate list).
- [ ] Approval to create the clean structure (separate write-enabled step).
