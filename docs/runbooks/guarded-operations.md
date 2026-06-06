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
