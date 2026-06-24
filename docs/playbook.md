# FounderOS Dev & CI Playbook

Operational playbook for local development and CI parity. This is **not** the
product playbook — product scope, MVP order, and Definition of Done live in the
root [`founderOS_MASTER_PLAYBOOK.md`](../founderOS_MASTER_PLAYBOOK.md),
[`EXECUTION_PLAN.md`](../EXECUTION_PLAN.md), and [`PROGRESS.md`](../PROGRESS.md).
Agent rules live in [`../AGENTS.md`](../AGENTS.md) and [`../CLAUDE.md`](../CLAUDE.md).

## Gates

Every change must keep these green (same gates as CI):

```bash
uv sync --frozen
uv run ruff check .
uv run alembic upgrade head
uv run pytest -q
```

The exact commands and dependency-automation details are in the root
[`README.md`](../README.md) under "Development & CI".

## Secret Hygiene

A tracked-secret scan runs in CI and can be run locally:

```bash
bash scripts/check_no_secrets.sh --tracked
```

No secrets, tokens, or provider payloads belong in tracked files, logs, or API
responses. See [`runbooks/guarded-operations.md`](runbooks/guarded-operations.md)
for the default-deny execution boundaries.

## Supply Chain

GitHub Actions are pinned by full commit SHA; bumps come through Renovate or
manual SHA rotation. Dependency Review, OpenSSF Scorecard, and uv Dependency
Submission (`uv.lock` transitive coverage) run in CI.
