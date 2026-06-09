# Jira Operating Model

FounderOS treats Jira as a guarded read-only planning surface until a future
approved write path exists. Live Jira inventory is for access diagnostics and
mapping preparation only.

## Recommended Structure

Use product or operating areas for Jira projects, not one project per
repository. Repositories should normally map to Components so issues can stay
organized by codebase without multiplying Jira projects.

GitHub repository ownership is moving to the `qtwin-io` organization. The
older 19-entry overview remains seed/planning metadata only; Jira should map to
portfolio product areas and future organization repositories/services, not the
legacy seed owner. Repository migration to the organization is manual and
separate from Jira creation.

Recommended project-area classes:

- `ssap_digital_twin`
- `kazscan_corporate`
- `infrastructure_data`
- `rd_3d_ar`
- `marketing_corporate`
- `ops_support`

Recommended starting model: `product_area_model`.

Alternative model classes:

- `compact_model`: one compact project with Components for early operations.
- `product_area_model`: one project per product or operating area.
- `portfolio_program_model`: program-level Jira structure for a larger
  portfolio.

## Components

Recommended component strategy: `repo_as_component`.

Other safe strategy classes:

- `service_as_component`
- `product_area_component_group`

Component mapping remains manual review metadata. Components can represent
migrated organization repositories or services after the operator migration is
complete. The GitHub organization inventory CLI is the separate gated
read-only path for checking target organization counts/classes; one frontend
repository is reported by the operator, but no Jira runbook step transfers or
edits repositories. The mapping flow does not update Jira, transfer
repositories, write repository metadata, or persist provider inventory.

## Creation Dry-Run

`scripts/plan_jira_creation_dry_run.py` produces the review artifact for a
future Jira structure change. It is no-live, no-send, source-of-truth-mutation
free, and write-disabled. The report uses safe classes/counts only for the
proposed product-area model, project classes, component strategy, issue type
classes, workflow status classes, board classes, governance rule classes, and
migration step classes.

The dry-run confirms that existing Jira project visibility has been observed,
but keeps issue-search inventory as a separate follow-up class. It does not
create or modify Jira projects, components, issue types, workflows, boards,
fields, or issues. Any later Jira creation requires a separate manual approval
and a separate write-enabled prompt.

The Jira creation dry-run is independent of GitHub repository migration.
GitHub writes, transfers, edits, topic updates, README updates, archive
operations, and secret-rotation execution remain disabled until a separate
manual approval path exists.

## Credential Profiles And Write Readiness

Jira read-only diagnostics use a `jira_readonly_data_api` profile with a
`basic_email_api_token` auth class and `jira_site_rest_api` endpoint class.
That profile remains read-only and write-disabled.

Future Jira structure creation is represented by a separate
`jira_write_site_api` profile with the same endpoint class. It is classified as
`dry_run_only` until a future operator prompt explicitly enables write
execution. Atlassian Admin diagnostics use separate admin profile classes with
`bearer_admin_api_key` and `atlassian_admin_api`; Org ID is reported only as a
presence class. Admin live calls are disabled in this workflow.

`scripts/plan_jira_write_readiness.py` reports which future write/admin profile
classes are configured, which write operations remain blocked, and which manual
approval class is required. It makes no live provider calls and performs no
Jira or Atlassian Admin writes.

## Issue Types

Recommended issue type classes:

- `epic`
- `story`
- `task`
- `bug`
- `subtask`
- `incident`
- `tech_debt`
- `spike`

## Workflow

Recommended workflow status classes:

- `backlog`
- `ready`
- `in_progress`
- `code_review`
- `validation`
- `ready_for_release`
- `done`
- `blocked`

## Priorities

Recommended priority classes:

- `p0_critical`
- `p1_high`
- `p2_normal`
- `p3_low`
- `p4_idea`

## Governance Rules

Recommended governance rule classes:

- `require_component`
- `require_owner`
- `require_acceptance_criteria`
- `require_blocker_reason`
- `done_requires_validation`
- `bugs_require_reproduction_context`
- `incidents_require_impact_resolution`

## Read-Only Inventory Diagnostics

`scripts/check_jira_readonly_inventory.py` reports access and mapping readiness
as safe classes only. It can distinguish empty project inventory, zero
accessible projects, permission-limited inventory, issue counts not observed,
malformed responses, response-contract mismatch, and mapping not configured.

The report suppresses provider payloads and does not print Jira locations,
project identifiers, issue identifiers, issue text, object identifiers, users,
emails, or response bodies. Live inventory remains gated by explicit provider
acknowledgement and is a separate manual verification step.

## Boundaries

This runbook does not approve Jira writes, project edits, issue ingestion, raw
storage writes, database writes, scheduler execution, delivery execution, or
LLM routing. Jira details become source data only after a future approved raw
storage and validation path exists.
