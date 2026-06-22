# FounderOS Post-MVP Parking Lot

Status: useful ideas and existing surfaces that should not expand until the
GitHub-first MVP E2E is complete.

This file is not a deletion list. Items here can remain in the repository when
they are already useful, but they should be frozen unless explicitly pulled
into a scoped task after MVP.

## Frozen Until GitHub-First MVP E2E

### Telegram/manual pilot

Current posture: keep existing guarded/manual pilot work, but do not expand
scheduler, webhook, or auto-delivery behavior before MVP.

Reason: master MVP focuses on UI-driven GitHub E2E first.

### Share packs and investor view

Current posture: keep existing surfaces as post-MVP. Do not expand them before
Dashboard, Company Brain, Briefing, and Actions are productized.

Reason: they are useful output formats, but not part of the first E2E.

### Jira write planning

Current posture: keep read-only planning and dry-run artifacts. Do not execute
Jira writes before canonical ActionProposal approval and MVP GitHub flow exist.

Reason: Jira writes are high-risk and not the first approved write in the
master playbook.

### Scheduler/outbox expansion

Current posture: keep default-deny guards. Do not add production scheduler or
outbox execution before manual MVP flows are stable.

Reason: automated delivery before trusted manual use increases duplicate and
side-effect risk.

### Role agents

Current posture: defer QA/TL/UX/PM or other role agents until after MVP usage
shows concrete demand.

Reason: master playbook prioritizes main founder flow first.

### Multi-model council

Current posture: defer.

Reason: explicitly outside MVP.

### Natural language rule compiler

Current posture: defer.

Reason: explicitly outside MVP.

### Sandbox workflow execution

Current posture: defer.

Reason: explicitly outside MVP and security-sensitive.

### Advanced diagnostics

Current posture: freeze new diagnostics unless tied to a current MVP blocker.

Reason: diagnostics should serve real usage, not become a parallel product.

### Compliance hardening beyond MVP

Current posture: keep baseline security and secret hygiene; defer enterprise
RBAC, SOC2-style programs, and advanced compliance.

Reason: baseline is required, advanced compliance should not block MVP.

### Marketplace/plugins

Current posture: defer.

Reason: explicitly outside MVP.

### Mobile app

Current posture: defer.

Reason: explicitly outside MVP.

## Parking Lot Rules

- Do not delete working code just because it is post-MVP.
- Mark existing post-MVP code as FREEZE or POST_MVP.
- Do not expand frozen surfaces without a new task and explicit approval.
- Any future expansion must preserve evidence_refs, human approval for writes,
  no raw secrets, and source-of-truth boundaries.

