# Security Policy

FounderOS is private, pre-release software. Do not open a public issue or
discussion for a suspected vulnerability.

## Report privately

Send the report to the repository owner through a private, verified channel.
Include:

- the affected version or commit;
- a minimal reproduction;
- the expected and observed result;
- the likely impact; and
- whether any credential, private source, or production data may be exposed.

Do not include live secrets, raw provider payloads, customer data, database
exports, or exploit output in GitHub issues, pull requests, or chat. Agree on a
private transfer method with the owner first.

The owner will acknowledge the report, assess severity, coordinate a fix, and
decide when disclosure is safe. There is no public vulnerability disclosure
timeline while the product remains private.

## Supported version

Only the current reviewed `main` revision is supported. Historical revisions
and unmerged branches receive no security fixes.

## Security boundaries

- LLM output never directly mutates production data.
- External writes require a validated proposal, fresh human approval, and
  repository/provider scope checks.
- Raw storage plus PostgreSQL are canonical; Obsidian is export-only.
- Secrets and raw private source bodies must never be committed.
- A local backup is not disaster recovery until an encrypted copy exists on
  independent storage and a restore drill has passed.

See `SECURITY_BASELINE.md`, `AGENTS.md`, and
`docs/operations/disaster-recovery.md` for the enforceable repository rules.
