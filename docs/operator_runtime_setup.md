# Operator Runtime Setup

FounderOS uses `.env.operator` as the local runtime environment for operator
sessions. It is ignored by git and should contain only local secrets, local
credential locations, and local runtime switches needed to launch Codex safely.

Do not commit `.env.operator`. Do not paste its values into issues, chats,
logs, docs, or test output.

## Create The Local File

Start from the tracked placeholder template:

```bash
cp .env.operator.example .env.operator
```

Then edit `.env.operator` locally. Keep the file shell-compatible:

```bash
KEY=value
QUOTED_KEY="value with spaces"
```

Avoid shell commands, command substitutions, and unquoted values containing
spaces.

## Fill It Safely

Use placeholders only in `.env.operator.example`; put real local values only in
`.env.operator`.

Generate `API_AUTH_KEY` locally with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Paste the generated value into `.env.operator` only. It can be any strong local
random secret.

Minimum FOS-036 Gmail validation keys:

```text
API_BASE_URL
API_AUTH_ENABLED
API_AUTH_KEY
API_AUTH_HEADER_NAME
GOOGLE_GMAIL_BACKFILL_ENABLED
GOOGLE_GMAIL_BACKFILL_QUERY
```

For persisted count validation, also configure the local database and raw
storage keys. For practical Gmail/Drive ingestion, configure Google client
secrets, token files, the Gmail bounded query, Drive folder boundary, and the
Google enable flags. For digest generation, configure the database/raw storage
runtime and enable LLM settings only when needed. For Telegram delivery,
configure the Telegram bot and chat keys.

Optional email thread-state key:

```text
EMAIL_ME_ADDRESSES
```

Use this only to help deterministic Gmail thread state classify whether the
last message was from the operator or from an external participant. It is
optional and must not block Google health checks; when it is missing, thread
state still builds but direction may remain `unknown` and status may be
`informational`.

## Health Check

Run the safe local FOS-036 check without launching Codex:

```bash
./scripts/launch_codex_operator.sh --check-only
```

The check prints JSON metadata only: key presence, boolean parse status, path
existence booleans by key name, missing required keys, and final status. It does
not call Gmail, Drive, OpenAI, Telegram, OAuth, or smoke tests.

You can also run broader local checks directly:

```bash
python3 scripts/operator_env_health.py --mode google
python3 scripts/operator_env_health.py --mode full
```

## Launch Codex

After the FOS-036 health status is `ready`, launch Codex through the wrapper:

```bash
./scripts/launch_codex_operator.sh
```

The launcher starts at the repo root, loads `.env.operator` into the
environment, runs the FOS-036 health check, and then executes:

```bash
exec codex "$@"
```

## If Health Says Blocked

Open `.env.operator` locally and fill the missing key names reported in
`missing_required_keys`. If a boolean key is invalid, use `true` or `false`.
If a required file path reports `exists: false`, create or point to the local
file before doing Google work. If a placeholder key is reported, replace the
placeholder with a real local value.

Run `./scripts/launch_codex_operator.sh --check-only` again. Keep iterating
until status is `ready`.
