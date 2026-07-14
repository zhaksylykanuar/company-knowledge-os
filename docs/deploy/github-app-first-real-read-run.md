# GitHub App First Real Read Runbook

Status: **human-approved, read-only runbook**. The managed `/github` wizard is
the primary setup path. This document does not create a GitHub App, call the
provider, or authorize a read by itself; the founder performs each external
confirmation and the final scoped read explicitly.

## Boundaries

- One local workspace and one workspace-managed GitHub App.
- Private App; repository issues and pull requests are read-only. GitHub's
  implicit metadata read is accepted. No contents read, provider writes,
  webhooks, background sync, bulk sync, deploy, or LLM.
- Setup is available only to a browser-session owner/admin. Viewer is read-only;
  operator/CI cannot advance the managed wizard.
- OAuth user tokens and just-in-time installation tokens are never persisted.
- Never paste private keys, client secrets, OAuth codes, tokens, session cookies,
  installation identifiers, database URLs, or raw provider payloads into logs,
  docs, issues, or commits.

## Prerequisites

1. Run the reviewed local build with `make local` and verify it with
   `make local-smoke`. Startup performs no GitHub provider call.
2. Apply and verify the current migration before starting the new backend:

   ```bash
   UV_NO_SYNC=1 uv run alembic upgrade head
   UV_NO_SYNC=1 uv run alembic current
   UV_NO_SYNC=1 uv run alembic check
   ```

   The expected single head for this flow is `c5d6e7f8a9b0`.
3. Sign in to FounderOS as the workspace owner or admin. The existing local
   application encryption key must remain available; do not print it.
4. Be ready to choose either a personal GitHub account or the exact GitHub
   organization login that owns the intended repositories.

An offline `.local/repos.json` surface is optional historical/local evidence. It
is not required for managed setup and cannot prove live GitHub access.

## Step 1 - Complete managed setup in `/github`

Open `http://127.0.0.1:3000/github` and use **«Настроить GitHub за 2 минуты»**.

The wizard performs four visible stages:

1. **Create App.** Choose personal account or organization. FounderOS submits an
   exact private read-only manifest to GitHub in the same tab. Confirm creation
   on GitHub; GitHub returns to FounderOS.
2. **Install.** Click **«Установить и выбрать репозитории»**. On GitHub, choose
   the account and grant only the repositories FounderOS should be able to read.
3. **Verify.** GitHub returns through the setup callback and OAuth + PKCE. The
   installation ID from the callback is not trusted by itself: FounderOS checks
   it with the App and then proves the current GitHub user can see the same
   installation. The temporary user token is revoked best-effort and never
   stored.
4. **Repositories.** Review the accessible repository list, remove unnecessary
   selections, and save at least one. FounderOS keeps only this subset in the
   completed setup state. The connection is not enabled before this save.

Leaving GitHub without approval does not create a connected source. A denial
returns to a recoverable cancelled state; use **«Начать заново»**. Expired or
replayed state is rejected.

## Step 2 - Verify the receipt before reading

The connected card must show the expected GitHub account, App name, and selected
repository count. The command center must list only the saved managed subset.
To change that subset later, first adjust access through the connected card,
then refresh and save the replacement selection. The existing saved subset
continues to work until the new choice is saved; closing an unfinished draft
does not disable it.

In **«Технические детали и безопасность»**, verify the truthful boundaries:

- installation token stored: **no**;
- GitHub writes: **not enabled**;
- connection is verified and live-read available, while `is_live` remains false
  because status itself does not call GitHub.

Stop if the account, App, repository subset, or verification state is wrong.

## Step 3 - Run one scoped read

Choose one repository in the command center and click the single read-only load
button. That browser-session action is the first approved provider read.

The backend rechecks all of the following before token mint or network access:

- current workspace, connection, active credential, and active installation
  relation match;
- installation was provider- and user-verified;
- provider reads were enabled by completed setup;
- the requested `owner/repo` belongs to the saved FounderOS subset; and
- the repository is still returned by the live GitHub installation inventory.

For this managed browser-session action, the legacy
`FOUNDEROS_ENABLE_REAL_CONNECTORS` env gate is not required. Operator/CI calls
remain behind that kill switch. No background read starts after setup.

## Step 4 - Verify canonical results

- Confirm the read receipt reports `external_write_performed: false` and no
  persisted installation token.
- Confirm the selected repository's tasks and pull requests appear in the
  `/github` work pulse.
- Confirm Company Brain shows the new canonical records with evidence refs.
- Generate a deterministic Founder Briefing only if desired and confirm its
  evidence refs resolve. This is not an LLM run.

The first run is proven only after these live results are observed. Green mocked
tests or a connected status alone are not evidence of a real provider read.

## Recovery and stopping

- If GitHub returns no repositories, adjust the App installation access on
  GitHub, return to the wizard, and use **«Проверить доступ ещё раз»**.
- If verification or encryption fails, the setup remains disabled and the UI
  shows a safe retry/restart state; do not create manual database rows.
- If a read fails, no provider write needs rollback. Do not retry broadly;
  re-check the selected repository and use one explicit action again.
- To stop reading, do nothing. There is no schedule or webhook. `make local-stop`
  stops the local product without deleting its state.

## Legacy compatibility path

The following path is retained only for older operator workflows:

- env names such as `FOUNDEROS_GITHUB_APP_ID`,
  `FOUNDEROS_GITHUB_APP_SLUG`, and
  `FOUNDEROS_GITHUB_APP_PRIVATE_KEY`/`..._PATH`;
- `scripts/github_app_real_read_run_preflight.py`;
- the manual `POST .../connections/app-installation`; and
- the global `FOUNDEROS_ENABLE_REAL_CONNECTORS` gate.

The offline preflight sees only env configuration and cannot attest managed
database credentials. A new manual installation POST is deliberately recorded
as unverified/read-disabled and cannot start live reads by itself. Do not use the
legacy path as the normal founder onboarding flow.
