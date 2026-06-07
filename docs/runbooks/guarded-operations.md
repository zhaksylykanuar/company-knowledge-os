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
