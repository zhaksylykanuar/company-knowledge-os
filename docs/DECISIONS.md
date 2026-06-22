# FounderOS Decisions

Status: current project-level decisions after the alignment audit against
`founderOS_MASTER_PLAYBOOK.md`.

These decisions are durable until explicitly superseded by a later decision
record.

## DEC-001 - Master Playbook Is The Primary Product Source

Decision: `founderOS_MASTER_PLAYBOOK.md` is the main source of truth for product
scope, MVP order, architecture direction, and Definition of Done.

Implication: repo-local docs may describe current implementation, but when
current docs conflict with the master playbook, treat that conflict as an
alignment gap to resolve explicitly.

## DEC-002 - Continue From Current Base

Decision: continue from the current repository base. Do not rewrite from
scratch.

Reason: the backend, evidence model, guards, source tooling, and tests are
valuable. Rewriting would risk losing working logic and safety contracts.

## DEC-003 - Backend Stack Remains Python/FastAPI/Postgres

Decision: keep Python, FastAPI, SQLAlchemy, Alembic, and PostgreSQL as the
backend foundation.

Reason: this matches the master playbook and the existing repository.

## DEC-004 - Current Static `/ui` Remains Local/Operator UI

Decision: keep the current static `/ui` as a local/operator interface.

Implication: do not delete it and do not treat it as the final product frontend.
It is useful for local evidence review, source diagnostics, Company Brain
preview, and guarded operator flows.

## DEC-005 - Next.js Web App Comes Later As A Separate Slice

Decision: add the master-playbook Next.js frontend separately later.

Implication: do not scaffold or partially implement `web/` during audit/docs
tasks. Plan it under FOS-FE-01 after data-model and GitHub path decisions are
clear.

## DEC-006 - Freeze Post-MVP/Operator Expansion Until GitHub-First E2E

Decision: do not expand post-MVP/operator surfaces until the GitHub-first MVP
E2E is working.

Frozen areas include Telegram/manual pilot, share packs, investor view, Jira
write planning, scheduler/outbox expansion, role agents, advanced diagnostics,
and compliance hardening beyond the baseline.

## DEC-007 - Preserve Evidence-First Product Semantics

Decision: keep evidence-first behavior as a core invariant.

Rules:

- Every extracted task, risk, or decision must have `evidence_refs`.
- Missing evidence returns `null`, an empty array, or insufficient evidence.
- Computed or preview surfaces must show provenance.
- Repositories are components/evidence, not Jira projects by default.

## DEC-008 - AI Does Not Directly Perform External Actions

Decision: AI may draft, classify, summarize, or recommend, but it must not
directly mutate external systems.

Implication: LLM outputs must remain strict JSON and validated before
persistence. Source text is untrusted data.

## DEC-009 - External Writes Require Human Approval

Decision: external writes only happen through human-approved action proposals.

Implication: future GitHub/Jira write paths must pass a human approval boundary
before execution. A live-provider ack alone is not enough to authorize a write.

## DEC-010 - Security Baseline Remains Required, Advanced Compliance Is Later

Decision: maintain the existing security baseline, secret hygiene, auth
boundary, and default-deny guards, but do not let advanced compliance work block
the MVP.

Implication: do not expand compliance programs, enterprise RBAC, SOC2-style
processes, or marketplace security before the GitHub-first MVP E2E.

## DEC-011 - Cleanup Waits For Checkpoint And Scope Split

Decision: no cleanup, deletion, or refactor before the current dirty tree is
checkpointed and split by scope.

Implication: useful but out-of-scope code is marked POST_MVP or FREEZE, not
deleted. Delete candidates are limited to clearly generated/local artifacts.

## DEC-012 - Workspace Auth Starts As Operator-Compatible Contract

Decision: keep the current API-key/operator auth boundary while adding
workspace-aware backend helpers on top of `User`, `Workspace`, and
`Membership`.

Implication: there is no public password login or session UI in the MVP
contract yet. The workspace bootstrap route is operator-protected and MVP-only.
New workspace-aware routes must check `Membership` for access; operator access
requires explicit owner context until session-based user auth is introduced.
