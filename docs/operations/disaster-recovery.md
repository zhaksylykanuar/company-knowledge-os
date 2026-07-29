# FounderOS Disaster Recovery

Status: **implemented control; first real off-device copy and drill remain an
operator gate**.

The local backup described in `local-runtime.md` protects against a bad
migration or local data operation. It is not disaster recovery because it is
stored on the same machine. Disaster recovery requires all three:

1. a locally restore-verified bundle;
2. an AES-256-GCM encrypted copy on founder-controlled storage independent from
   the FounderOS machine; and
3. a successful full restore drill from that encrypted copy.

The target can be an encrypted removable drive, a mounted private NAS in
another location, or a founder-owned encrypted cloud volume. A normal directory
on the same disk does not qualify. This repository does not upload to a named
vendor, manage cloud credentials, or claim that an external copy exists.

## Objectives and ownership

- **Owner:** FounderOS repository/company owner.
- **RPO target:** at most 24 hours after production use begins; export after
  every schema migration or risky data operation as well.
- **RTO target:** four hours to obtain the key, materialize a verified bundle,
  restore PostgreSQL into a new target, configure raw storage, and pass
  readiness checks.
- **Export cadence:** daily while canonical data changes.
- **Restore-drill cadence:** weekly during active development and before any
  destructive infrastructure retirement.
- **Retention:** 7 daily, 4 weekly, and 12 monthly recovery points. The newest
  valid artifact is always retained.

The drill receipt records its measured duration. Revisit the four-hour RTO if a
real drill cannot meet it.

## One-time setup

Choose two private paths outside the repository:

```bash
export FOUNDEROS_OFFSITE_BACKUP_DIR='<independent-mounted-storage-path>'
export FOUNDEROS_OFFSITE_BACKUP_KEY_FILE='<separate-private-key-file-path>'
```

The key must not be stored on the same device as the encrypted backup. Preserve
a second recoverable copy in a founder-owned password manager or equivalent
secure custody. Never paste the key or its value into `.env`, shell arguments,
chat, docs, tickets, or commits.

Create the key and initialize the independent target:

```bash
make offsite-recovery-key-init
make offsite-target-init
```

Initialization is fail-closed: both paths must be outside the repository,
directories and key files must be private, existing keys are never overwritten,
and target creation requires an explicit acknowledgement that storage is
independent.

## Daily export

First create a full local restore-proven bundle:

```bash
make local-stop
make local-backup
make offsite-backup
```

The exporter accepts only the exact seven-file local bundle with a successful
restore receipt, validates all checksums and raw-storage inventory, encrypts the
whole bundle with AES-256-GCM, decrypts it into a private temporary directory,
and verifies it again before writing an aggregate-only receipt. The plaintext
bundle, encryption key, raw file names, provider payloads, and database URL are
never printed or copied into the receipt.

An interrupted or failed export removes partial promoted files. A completed
pair consists of a `.fosbak` artifact and its `.receipt.json`.

## Weekly full restore drill

With the independent target mounted and the separately held key available:

```bash
make offsite-restore-drill
```

The drill selects the latest valid encrypted artifact, authenticates and
decrypts it, revalidates the entire local bundle, starts an isolated
matching-major PostgreSQL cluster with TCP disabled, restores the dump,
compares Alembic revisions and sanitized table counts, checks stored connector
credential decryptability, and removes the temporary database. Its private
receipt is written under the target's `drills/` directory.

A drill passes only when the receipt says `status: restore_verified`,
`database_restore_verified: true`, `raw_storage_archive_verified: true`, and
`temporary_database_dropped: true`. Do not treat decryption alone as a drill.

## Retention

Review the proposed deletion set without changing files:

```bash
make offsite-retention-dry-run
```

Apply the 7/4/12 policy only after confirming the target and counts:

```bash
make offsite-retention-apply
```

Retention never runs implicitly. The newest artifact is retained, future-dated
artifacts fail safe into the keep set, and an artifact plus its receipt are
removed together.

## Recovery after loss

1. Obtain a clean FounderOS checkout at a reviewed commit.
2. Provision a new PostgreSQL target and a private raw-storage destination.
3. Mount or download the independent backup target read-only if possible.
4. Recover the key through its separate custody path.
5. Run a drill first. Do not replace production data from an artifact that
   cannot pass a full isolated restore.
6. Materialize the selected encrypted bundle to a new, empty path outside the
   repository:

   ```bash
   uv run python scripts/disaster_recovery.py materialize \
     --output '<new-private-recovery-directory>'
   ```

7. Restore `database.dump` into the new database with matching PostgreSQL
   tooling. Extract `raw-storage.tar.gz` into the configured new raw-storage
   path. Never overwrite the damaged source in place.
8. Supply the separately preserved `FOUNDEROS_SECRET_ENCRYPTION_KEY`, configure
   the new database and raw-storage paths, apply only reviewed forward
   migrations, and run readiness plus authenticated workspace checks.
9. Keep the damaged source and recovery artifact unchanged until the founder
   confirms data, evidence links, integrations, and Company Brain state.

Materialization verifies authenticated encryption, exact archive membership,
all checksums, and raw inventory before returning. Its output is plaintext
private data: keep it outside git, use owner-only permissions, and remove it
through an approved secure process after recovery is accepted.

## What is not automated

- acquiring/mounting truly independent storage;
- backup-key escrow and recovery;
- scheduling on the founder's operating system;
- copying across a cloud provider boundary;
- replacing a production database or raw-storage directory; and
- deleting any old database, volume, artifact, or external resource.

Those actions depend on deployment ownership and require explicit human
approval. Record the date, artifact digest prefix, drill result, measured time,
and owner decision privately; never paste private payloads or credentials into
repository docs.
