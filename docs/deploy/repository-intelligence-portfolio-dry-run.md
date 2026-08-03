# Repository Intelligence Portfolio Dry Run

Status: **approved preparation-only boundary**. This runbook validates a private
L0/L1 portfolio manifest and emits a content-free receipt. It does not call
GitHub, open a target repository, clone source, enqueue analysis, write to
PostgreSQL/raw storage, execute repository code, or authorize the real run.

## Scope

The dry-run manifest must name every intended repository with:

- canonical `workspace_id` and `repository_id`;
- provider `github`, stable provider `external_id`, and exact `owner/repository`;
- one full lowercase SHA-1 commit;
- exactly `L0` and `L1`; `L2` is rejected;
- one approved profile, policy SHA-256, and engine version;
- either `provider_exact_sha` or an opaque relative
  `operator_managed_local_mirror` reference.

The dry run returns only counts and controlled status fields. It never returns
repository names, provider IDs, SHA values, local mirror references, source
bodies, credentials, DB URLs, paths, workspace IDs, or an offline-verifiable
digest of the private manifest.

## Private manifest handling

Store the manifest outside the FounderOS repository and target repositories. It
must be an owner-owned regular file with mode `0600`; symlinks, group/world
permissions, repository-contained paths, traversal, absolute mirror paths,
unknown fields, duplicates, and files over 64 KiB fail closed.
Repository entries must be sorted case-insensitively by `full_name` so the
canonical receipt hash is stable.

Template:

```json
{
  "schema_version": "repository_portfolio_dry_run.v1",
  "workspace_id": "<workspace-uuid>",
  "l2_enabled": false,
  "provider_calls_authorized": false,
  "target_reads_authorized": false,
  "target_execution_authorized": false,
  "persistence_authorized": false,
  "repositories": [
    {
      "repository_id": "<canonical-repository-uuid>",
      "provider": "github",
      "external_id": "<stable-provider-id>",
      "full_name": "<owner/repository>",
      "commit_algorithm": "sha1",
      "commit_sha": "<40-lowercase-hex>",
      "audit_levels": ["L0", "L1"],
      "profile": "repository-static-v1",
      "policy_hash": "<64-lowercase-hex>",
      "engine_version": "ri-engine-1.0.0",
      "source_mode": "provider_exact_sha",
      "local_mirror_ref": null,
      "enabled": true
    }
  ]
}
```

For an operator-managed mirror, set `source_mode` to
`operator_managed_local_mirror` and use an opaque relative reference such as
`approved-mirrors/repository-one`. The dry run does not resolve or open it.

## Run the validation-only command

```bash
uv run python scripts/repository_intelligence_portfolio_dry_run.py \
  --manifest /absolute/private/path/repository-portfolio.json
```

Expected receipt shape:

```json
{
  "schema_version": "repository_portfolio_dry_run_receipt.v1",
  "status": "ready_for_separate_run_approval",
  "l2_enabled": false,
  "provider_calls_performed": 0,
  "target_paths_opened": 0,
  "target_repositories_read": 0,
  "target_repositories_cloned": 0,
  "target_code_executed": 0,
  "analysis_jobs_enqueued": 0,
  "persistence_writes": 0,
  "external_writes": 0,
  "next_gate": "explicit_founder_approval_required"
}
```

The exact receipt also includes only aggregate repository/source counts and the
fixed evidence, output, restart, retention, failure-isolation, and rollback
contracts. Any manifest change requires a new dry run and a new explicit
approval; the owner-private manifest itself remains the approval object.

## Planned real-run boundaries

The receipt freezes these rules for the later separately approved run:

- **Output:** central audit workspace only; no report in a target repository.
- **Evidence:** import only strict schema-valid and evidence-valid results.
- **Failure isolation:** one repository per durable job; a failure does not stop
  other repositories; failed/partial runs cannot reconcile absence.
- **Restart:** resume or retry by exact repository + SHA + profile + policy hash
  + engine version; do not silently move to a newer commit.
- **Retention:** checkout deleted on exit; sanitized artifact references expire
  after 30 days; canonical results remain until explicit repository/workspace
  deletion.
- **Rollback:** this dry run has no runtime mutation. A later run is stopped by
  cancelling queued/leased jobs, allowing owned cleanup, and refusing import of
  failed/partial or mismatched results. Provider data is read-only and requires
  no write rollback.
- **L2:** disabled. No repository command execution is authorized.

## Stop conditions

Do not start the real portfolio run if any repository lacks an exact canonical
identity/SHA, if the receipt is not successful, if repository coverage differs
from the approved private manifest, if backup/migration/runtime prerequisites
are unresolved, or if the founder has not issued a new explicit instruction to
start the L0/L1 read.
