# Guarded Operations Runbook

FounderOS keeps local review, digest, and reporting workflows separate from
live execution. The guard modules are runtime boundaries, not new execution
paths.

## Guard Layers

- Provider execution guard: live provider calls are default-denied unless a
  bounded execution path explicitly allows live provider execution. External
  APIs are raw event or interface sources, not interpreted truth.
- Production-operation guard: source-of-truth mutation, production database or
  migration-like work, delivery execution, raw-storage mutation, and Obsidian
  export are default-denied unless a bounded operator path explicitly allows
  that operation class.
- Scheduler execution guard: scheduler, outbox drain, background dispatch,
  retry worker, and automatic delivery execution are default-disabled. These
  paths are out of scope until a future approved scheduler design exists.

## Safe Local Workflows

Read-only review, digest drafting, compatibility reports, and no-marker
review/sweep tools remain no-send and no-source-of-truth mutation. Delivery
intention creation is a durable handoff artifact, not delivery execution.
Delivery results are execution outcome metadata, not source of truth.
Telegram and Slack are delivery or interface surfaces only.

## External API Connectors

The connector registry contains safe metadata only for provider onboarding:
provider keys, guard classes, execution modes, source-of-truth roles, and
readiness classes. GitHub and Jira connector foundations are guarded read-only
raw-event-source boundaries with synthetic transport support for tests. Live
read-only API verification remains a separate manual operator step and must
pass the provider execution guard; connector readiness is not production
approval, persistence, scheduling, delivery execution, or interpreted truth.
Raw provider payloads must pass through raw storage and validation boundaries
before they can become normalized activity items.

## Repository Portfolio

The repository portfolio catalog is static onboarding metadata seeded from a
provided overview. Operator-facing reports expose product-area, lifecycle,
priority, and action-class counts only. Repository maintenance actions such as
description updates, README work, topic updates, archive candidates, and
credential rotation remain safe action classes until a separate operator
execution path exists.

The seeded catalog is planning metadata only. The future canonical GitHub owner
is the `qtwin-io` organization, while the older overview remains a legacy seed
source. Organization migration is manual and currently classified as
`manual_org_migration_planned`; one organization repository is reported by the
operator, but live organization inventory is still `gated_not_verified`. This
catalog does not transfer repositories, edit repository metadata, rotate
credentials, write Jira data, persist source-of-truth rows, or call provider
APIs.

## GitHub Organization Read-Only Inventory

`scripts/check_github_org_readonly_inventory.py` prepares the target
organization inventory check for `qtwin-io`. Default mode makes no live calls
and reports that explicit acknowledgement is required. Synthetic mode uses
provider-free inventory for tests. Live read-only mode is reserved for a later
manual verification step with explicit provider guard acknowledgement.

The report distinguishes the legacy seed portfolio from target organization
inventory, compares counts/classes only, and suppresses provider payloads. It
does not print repository names, owner names, provider locations, object
identifiers, pull request identifiers, issue titles, authors, emails,
credentials, raw payloads, or response bodies. It does not transfer
repositories, create repositories, edit metadata, update topics or READMEs,
archive repositories, perform credential rotation, write raw storage, write
Postgres, run scheduler work, or execute delivery.

Live read-only organization inventory diagnostics expose only sanitized
failure classes. Common classes include invalid organization configuration,
authentication failure, permission denial, organization not found or no access,
rate limiting, server error, transport error, timeout, malformed response,
response-contract mismatch, and empty organization inventory. Fixing live
organization access remains a manual credential or permission task; the
inventory path stays read-only and target migration remains manual.

The live adapter uses the read-only organization repository list contract and
normalizes the response into counts/classes before public output. A successful
empty list is reported as an empty-inventory class, not an unknown failure.

## Connector Smoke CLI

`scripts/check_external_connectors_readonly.py` is a read-only, no-send,
source-of-truth-mutation-free connector smoke report for GitHub and Jira.
Default mode makes no live calls and reports that explicit acknowledgement is
required. Synthetic mode uses synthetic transports only. Live read-only mode is
reserved for a separate manual operator step with explicit provider guard
acknowledgement and configuration presence checks. GitHub portfolio comparison
is a seed-portfolio count comparison only; target organization inventory is a
separate gated manual read-only check through
`check_github_org_readonly_inventory.py`. Jira mapping status is reported as
counts/classes only. The CLI does not update repository metadata, transfer
repositories, write Jira data, persist rows, schedule work, or execute delivery.

Jira live-read-only smoke diagnostics expose only sanitized failure classes.
Common safe classes include invalid site configuration, authentication failure,
permission denial, wrong site or not-found, rate limiting, server error,
transport error, timeout, malformed response, and response-contract mismatch.
The smoke report never prints the configured Jira site, credentials, project
names, project keys, issue keys, object identifiers, raw provider payloads, or
response bodies. Fixing live Jira access remains a manual credential,
permission, and provider-configuration task; the smoke path stays read-only and
does not persist or mutate data.

## Jira Read-Only Inventory

`scripts/check_jira_readonly_inventory.py` is a read-only, no-send,
source-of-truth-mutation-free inventory and portfolio-mapping report for Jira.
Default mode makes no live calls and reports that explicit acknowledgement is
required. Synthetic mode uses synthetic inventory only. Live read-only mode is
reserved for a separate manual operator step with explicit provider guard
acknowledgement and configuration presence checks. Inventory output exposes
project and issue counts/classes only, suppresses provider payloads, and never
prints Jira project details, issue details, provider locations, credentials,
object identifiers, raw provider payloads, or response bodies. Portfolio
mapping is planning metadata against repository product-area counts; it is not
source of truth and does not ingest issues, write Jira, persist raw storage,
write Postgres, run scheduler work, or execute delivery.

Inventory diagnostics explain zero or incomplete results as safe classes:
empty inventory, zero accessible projects, permission-limited inventory,
issue inventory not observed, malformed response, response-contract mismatch,
and mapping not configured. The report also includes a safe operating-model
summary with a `product_area_model` recommendation, a repo-as-component
strategy, and a next-action class such as access review, mapping configuration,
issue-count inventory, operating-model review, or response-contract
investigation. The detailed operating model is in `jira-operating-model.md`.

## Jira Creation Dry-Run

`scripts/plan_jira_creation_dry_run.py` converts the safe Jira operating model
and repository portfolio summary into a non-executing creation plan. It makes
no provider calls, performs no Jira writes, mutates no source of truth, and
keeps scheduler execution disabled. The output is strict sanitized JSON with
project, component, issue type, workflow, board, governance, migration, blocked
write, and follow-up classes only.

The dry-run is the review artifact before any future Jira write prompt. It
records current project visibility as confirmed, keeps issue-search inventory
as a follow-up, and requires separate manual approval before project,
component, workflow, board, field, or issue operations can be considered.

## Jira Write-Readiness Dry-Run

`scripts/plan_jira_write_readiness.py` checks Atlassian/Jira credential profile
readiness without live calls or writes. It distinguishes the read-only Jira
data API profile, the future Jira write-site profile, and Atlassian Admin
profile classes. Values, provider locations, Org ID, and credentials remain
hidden; the report exposes only configured/missing classes and counts.

Write-readiness stays `dry_run_only`: Jira project, component, board, workflow,
issue-type, and migration operations are blocked until a future manual
write-enabled prompt. Atlassian Admin APIs are not called in this flow and are
not required for Jira project creation unless a later org-level diagnostic is
explicitly approved.

## Connector Config Doctor

`scripts/doctor_external_connector_config.py` is a read-only, no-send,
source-of-truth-mutation-free configuration doctor for GitHub/Jira onboarding.
It reports expected environment variable names and presence/missing classes
only, never prints values, and never calls providers. Direct shell environment
variables still work. For local operator setup, copy `.env.example` to `.env`
and fill values locally; `.env` is ignored and must never be committed or
pasted into chat. The doctor and connector smoke CLI can load allowlisted keys
from project-root `.env`, then fall back to the older user-config connector
file for compatibility, or use an explicit `--connector-env-file`; shell values
take precedence over file values when they are configured. Blank and
placeholder-like values are treated as missing, and placeholders belong only in
`.env.example`. The loader skips non-allowlisted keys and reports only
env-file status/count diagnostics. `FOS_GITHUB_TARGET_ORG` is optional future
organization-planning metadata and is never required for current read-only
smoke checks. When all required variables are present, the next safe action
class is a separate manually acknowledged live-read-only smoke check through
the guarded connector smoke CLI.

## Ignored-File Cleanup Planner

`scripts/report_ignored_file_cleanup_plan.py` is a read-only, no-delete,
metadata-only cleanup planner for ignored local files. It asks git for ignored
paths while excluding raw storage and Obsidian vault trees, never reads file
contents, never prints ignored paths by default, and reports safe classes,
counts, and action classes only. The report is planning metadata only; deletion
or cleanup execution remains a separate manual operator action.

## Guarded-Execution Doctor

`scripts/doctor_guarded_execution.py` is a read-only, provider-free,
source-of-truth-mutation-free, no-send doctor. It verifies that provider,
production-operation, and scheduler guards are still default-denied or
default-disabled, that blocked synthetic callbacks are not called, and that
operator-output sanitizer diagnostics expose safe classes and counts only. The
doctor does not approve, schedule, dispatch, send, run migrations, or execute
production operations.

## Audit-Event Metadata

Guard decisions can be converted into sanitized guarded-execution audit-event
metadata for logging or review. The metadata envelope is JSON-serializable and
contains safe guard names, operation classes, decisions, reason codes, safety
flags, and unsafe-content classes/counts only. This contract is metadata only:
it does not persist audit events, write source-of-truth stores, approve
execution, schedule work, dispatch delivery, or call providers.

## Audit Sinks

Guarded-execution audit sinks are non-persistent in this baseline. The no-op
sink accepts sanitized metadata without retaining it, and the in-memory sink is
for tests and doctor preflight checks only. Sink summaries expose safe
counts/classes only. Persistent logging, queue routing, outbox routing, file
output, or database storage remains a future separately gated production-ops
decision.

## Readiness Report

`scripts/report_guarded_execution_readiness.py` is a read-only, no-send,
provider-free, source-of-truth-mutation-free readiness report. It consolidates
the current guard, doctor, sanitizer, audit metadata, audit sink, docs, and
remaining-risk status into strict sanitized JSON. The report is not a full
audit, not a production approval, and not an execution mechanism. Remaining
risks are listed as safe classes only.

## JSON Contracts

Guarded-execution audit events, audit sink summaries, doctor output, readiness
report output, and connector smoke output use strict sanitized JSON contract
validation. Contract validation reports safe field names, reason codes,
classes, and counts only. It does not persist reports, approve operations,
route logs, run providers, dispatch delivery, schedule work, run migrations, or
mutate source-of-truth stores.

## Future Execution Requirements

Any future scheduler or outbox execution must pass all applicable gates before
it can execute: human approval, scheduler non-execution policy replacement,
provider execution guard, production-operation guard, and duplicate-success
protection. It must record only sanitized diagnostics and execution metadata.

## Diagnostic Rules

Guard diagnostics may include guard names, safe reason codes, safe operation
classes, safe provider classes, and safe boundary classes. Diagnostics must not
include credentials, network locations, database connection details, raw
payloads, rendered message text, grouped previews, source object identifiers,
raw hashes, local artifact contents, or person-identifying contact details.
Operator-facing outputs, artifacts, and guarded-execution audit metadata should
expose unsafe-content classes and counts only. Raw data remains in
source-of-truth stores; review artifacts, manual diagnostics, audit metadata,
and CLI summaries are sanitized views.
