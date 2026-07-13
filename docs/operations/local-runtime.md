# FounderOS Local Runtime

Status: **active operational path** (DEC-077). FounderOS runs on the founder's
machine until a future hosting decision is explicitly approved. This runbook
does not authorize provider reads, external writes, cloud changes, or deletion
of any external resource.

## Runtime shape

- `make local` is the canonical start command for the full local product.
- FounderOS first reuses a reachable loopback PostgreSQL. If none is reachable
  and the database port is free, Compose PostgreSQL 16 is the managed fallback
  with a named volume.
- FastAPI listens on `127.0.0.1:8765`.
- Next.js listens on `127.0.0.1:3000` and proxies `/api/*` plus `/health` to the
  backend, keeping the session cookie first-party.
- Redis is available in Compose for future/background-job work, but it is not a
  prerequisite for the current synchronous product path.
- Canonical application state lives in PostgreSQL. Raw evidence lives at the
  configured `RAW_STORAGE_DIR`: an existing gitignored `raw_storage/` is
  preserved, while a fresh installation uses `.local/raw_storage/`. Other
  local evidence stays under gitignored `.local/`; the Obsidian vault is
  export-only.
- LLM, real connectors, and provider writes remain disabled unless a later,
  separately approved runbook explicitly enables a bounded action.

## Safety rules

1. Never delete or recreate `.local/`; it may contain discovery snapshots,
   repository review material, exports, and the local Obsidian vault.
2. Never remove a Docker volume before a verified full local backup exists.
3. Never commit `.env.local`, `web/.env.local`, `.local/`, database archives,
   credentials, provider payloads, or raw source bodies.
4. Do not copy database files between PostgreSQL major versions. Use a logical
   dump created by a `pg_dump` client at least as new as the source server, then
   prove restore in an isolated matching-major database.
5. A successful local runtime does not authorize a GitHub/provider read or an
   external action. Those remain separate human-approved gates.
6. The stable `FOUNDEROS_SECRET_ENCRYPTION_KEY` in owner-only `.env.local` is
   required to decrypt future stored provider tokens. Preserve it separately in
   a founder-owned password manager; the database/raw bundle intentionally does
   not duplicate that key beside encrypted data.

## 1. Diagnose prerequisites

`uv`, Python, Node.js, and npm must be available. A reachable loopback
PostgreSQL satisfies the database prerequisite; Docker is required only when
the supervisor must start the Compose fallback. From the repository root, run
the sanitized doctor:

```bash
make local-doctor
```

The doctor reports readiness and blocker categories without printing secret or
environment values. Resolve every required blocker before starting. If an
existing loopback PostgreSQL is healthy, Docker may remain unavailable. Redis
may be reported as optional; it does not block the current product runtime.

## 2. Start FounderOS

From the repository root:

```bash
make local
```

The command prepares the gitignored local workspace, reuses a reachable
loopback PostgreSQL or starts the Compose fallback when safe, applies Alembic
migrations, and starts the backend and frontend with the correct same-origin
proxy. It must not clear `.local/`, recreate an existing database volume, call
providers, enable external writes, or invoke an LLM.

Before migrating a non-empty database that is behind or whose revision cannot
be proven current, the supervisor creates the same full restore-proven bundle
described below. A normal restart at the current Alembic head does not create an
unbounded series of duplicate backups. If the required backup boundary cannot
be created, startup stops before migration.

Open `http://127.0.0.1:3000`. By default the supervisor opens `/login` for an
existing founder. For an empty database it creates a private founder invite and
opens the fragment URL without printing the bearer. Keep the command running
while using FounderOS.

## 3. First-founder fallback

Normally `make local` performs the private browser handoff. Only when automatic
opening was disabled or failed, issue a short-lived one-time founder link from a
separate terminal:

```bash
UV_NO_SYNC=1 uv run python scripts/create_founder_invite.py \
  --base-url http://127.0.0.1:3000 \
  --ttl-hours 72
```

The command prints the bearer URL once. Treat it like a password: open it
locally, but do not paste it into chat, docs, tickets, shell history, or commits.
Complete `/start`, then the guided `/onboarding` flow. Existing local founders
return through `/login`.

## 4. Verify the local stack

Run the bounded local smoke:

```bash
make local-smoke
```

The local stack is accepted only when all of the following are true:

- the doctor and smoke finish successfully;
- PostgreSQL is healthy and Alembic `heads` equals `current`;
- `/health` succeeds through the local frontend proxy;
- `/login` loads and a founder session survives reload;
- the founder sees the intended company, resumes onboarding, and can open
  «Сегодня», «Компания», «Решения», «Источники» and «Настройки»;
- Company World renders only durable confirmed relationships and keeps
  unresolved candidates separate;
- no operator key is stored in the browser; and
- no provider call, external write, selected-repository sync, or LLM run occurs
  during smoke.

Latest verified acceptance (2026-07-14): doctor/start/same-origin smoke passed;
a returning founder session opened onboarding and all five zones without
horizontal overflow or console errors; ephemeral QA data was removed. Backup
restore, signal shutdown and simulated supervisor-crash recovery also passed as
recorded in `PROGRESS.md`. This evidence does not authorize a provider call or
hosted-resource change.

For an exact release candidate, also run the repository gates. Backend checks
must use an explicit dedicated loopback PostgreSQL test target whose name has a
standalone test marker such as `founderos_test`. The marker does not prove that
the target is empty or disposable; provisioning the dedicated target remains
an operator responsibility. The wrapper refuses to run against the product
endpoint from ambient `DATABASE_URL`, `.env`, or `.env.local`, and forces test
mode with provider, write, and LLM gates off:

```bash
FOUNDEROS_TEST_DATABASE_URL='<loopback-postgresql-test-url>' make backend-check
make frontend-check
bash scripts/check_no_secrets.sh --tracked
git diff --check
```

## 5. Back up local state

Before a schema migration, risky data operation, or Docker-volume change:

```bash
make local-stop
make local-backup
```

The command refuses to run while FounderOS app ports are occupied. It creates a
private `0700` bundle under `.local/backups/` containing:

- a custom-format PostgreSQL dump plus SHA-256;
- a configured raw-storage archive plus SHA-256;
- a private aggregate-only manifest; and
- a `0600` verification receipt.

The helper validates every checksum and raw-file content digest, rescans the raw
source after archiving to reject added/deleted/changed files, then starts an
isolated same-major PostgreSQL cluster on a private `0700` Unix socket with TCP
disabled. It restores the dump, compares Alembic revisions and sanitized table
counts, and proves that real stored connector credentials remain decryptable by
the separately preserved local key (explicit test fixtures are reported
separately). Finally it proves the temporary cluster, socket and files were
removed. Only a bundle whose receipt says `status: verified` is a rollback
boundary. If any step fails, the source database/raw storage remain untouched
and no partial bundle is promoted; do not use Alembic downgrade as a substitute
for a restorable backup.

## 6. Stop the local processes safely

```bash
make local-stop
```

This stops FounderOS processes without deleting `.local/`, PostgreSQL data or
volumes, or logical backups. The supervisor handles `SIGINT`, `SIGTERM`, and
`SIGHUP`; after a supervisor crash, `make local-stop` removes child processes
only when their recorded launch signatures still match and otherwise refuses
unsafe cleanup. Never append `-v` to a Compose shutdown as part of normal
operation.

## 7. Troubleshooting fallback

Use the manual commands below only to diagnose a failed canonical command. They
are not a second normal startup path.

Inspect local services:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8765/health
UV_NO_SYNC=1 uv run alembic heads
UV_NO_SYNC=1 uv run alembic current
```

Start only the required database and backend manually:

```bash
docker compose up -d postgres
UV_NO_SYNC=1 uv run python scripts/start_local.py backend
```

In another terminal, start the frontend with the canonical proxy target:

```bash
cd web
npm ci
FOUNDEROS_API_PROXY_TARGET=http://127.0.0.1:8765 \
  npm run dev -- --hostname 127.0.0.1 --port 3000
```

If only the frontend fails, keep the backend/database intact and diagnose the
proxy or Node process. If a new application build fails before migration, return
to the previously reviewed code snapshot and restart processes without altering
database data. If a migration or local data operation fails, stop writers and
restore the last verified archive into a new database/volume; preserve the
failed database for comparison.

## 8. External-resource deletion boundary

Moving FounderOS to local operation does not authorize stopping or deleting an
older hosted environment. Before any external database or volume can be removed:

1. pass the local acceptance gate;
2. create a final logical archive with a matching-or-newer PostgreSQL client;
3. verify its checksum and restore it into an isolated matching-major database;
4. compare only sanitized schema revision and aggregate row counts; and
5. keep the archive and source database through an agreed observation window.

Stopping hosted services, removing domains, deleting a database/volume, and
deleting a project are external state changes. Each retirement phase requires a
separate explicit human approval after restore proof. A general instruction to
"work locally" is not deletion approval.
