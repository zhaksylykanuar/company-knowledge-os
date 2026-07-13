# founderOS Web

Guided Next.js product for the FounderOS company-management flow.

## Install

```bash
npm install
```

## Run locally

Start the backend first from the repository root, then run the frontend:

```bash
FOUNDEROS_API_PROXY_TARGET=http://127.0.0.1:8765 npm run dev
```

The app starts on the Next.js default port unless you pass a port to `next dev`.
The browser talks to the backend **same-origin**: `web/next.config.mjs` proxies
`/api/*` and `/health` to the backend (see Environment below), so the session
cookie stays first-party and no browser CORS is needed for the normal path.
(`FOUNDEROS_CORS_ALLOWED_ORIGINS` only matters if the browser is pointed at a
separately hosted API instead of the proxy.)

Port `8765` matches the repository-root `scripts/start_local.py` runner. If you
start Uvicorn manually on `8000`, plain `npm run dev` uses the documented
fallback.

## Build and deploy-readiness checks

```bash
npm test
npm run build
npm run typecheck
npm run lint
```

These commands are enforced by the repository CI deploy-readiness workflow. They
do not require provider credentials or live backend/provider calls.

## Environment

The frontend proxies `/api/*` and `/health` to the backend so the session cookie
is first-party. Configure the proxy target (server-only):

```bash
FOUNDEROS_API_PROXY_TARGET=<backend-internal-base-url>
```

It falls back to `NEXT_PUBLIC_API_BASE_URL`, then to `http://localhost:8000` if
neither is set:

```bash
NEXT_PUBLIC_API_BASE_URL=<backend-public-base-url>
```

## Authentication

The app uses invite-only founder enrollment and email+password server sessions:

- A one-time `/start#token=...` link calls `POST /api/v1/auth/enroll` and then
  opens the focused `/onboarding` journey. The bearer is accepted from the URL
  fragment only; query fallback is forbidden, and the address is cleared after
  capture. Public signup stays closed.
- A `/login` page calls `POST /api/v1/auth/login`; an `AuthGate` redirects
  unauthenticated users to `/login`.
- The session is an httpOnly first-party cookie (set by the backend); the
  company list is derived from memberships, not entered in the browser. One
  membership is selected automatically; several require an explicit choice.
- The Settings page is an account / change-password page
  (`POST /api/v1/auth/change-password`), not an operator-key/owner-email config
  page. Create the normal founder link from the repository root with
  `scripts/create_founder_invite.py`; `scripts/create_admin_user.py` remains a
  local/operator recovery path (see the root README).
- Teammate setup uses the same fragment-only `/setup-password#token=...`
  contract. An owner/admin never chooses the teammate's password: a brand-new
  account gets one setup link in the response, while `initial_password` is
  rejected. No email is sent and this slice does not verify the recipient, so
  the inviter must transfer the link manually over a trusted direct channel.
  The link is one-time, cleared from the address immediately, and invalid/reused
  requests do not run password hashing. An existing account that already has a
  membership in another company is rejected with 409 rather than attached
  silently; the future self-accepted invitation flow owns that case.
- Public password fields are bounded before hashing: login accepts 1–256
  characters; founder enrollment, setup-password, and change-password require
  8–256 characters.
- In production the backend admits login work by per-IP/global request windows
  and a concurrency cap before Argon2, in addition to the durable per-email DB
  lockout. This admission state is process-local and supports the documented
  single-Uvicorn-process private beta only; multiple workers/replicas require a
  shared edge/Redis limiter first. The per-IP key uses the ASGI client address;
  distinct external clients behind the production proxy remain a mandatory
  deploy smoke. Disabled users' existing sessions are revoked when next
  validated.

The browser sends no operator API key and no owner email; the operator API key is
for server/CI/admin tooling only. The frontend never calls GitHub, Jira, Gmail,
Drive, or other providers directly. Do not commit secrets, API keys, provider
tokens, or local environment files.

Primary navigation is «Сегодня / Компания / Решения / Источники / Настройки».
Provider routes are nested under «Источники»; `/dashboard` shows one
deterministic next move and three signals. Shared shell/status copy is in
`web/lib/messages.ts`; focused journey copy is colocated with its page. The UI
is Russian. Source setup/import/sync and action review/execution require
owner/admin; briefing generation, local action creation, and Company World
resolution require member+; viewer keeps evidence-backed read access only.

## Private-beta notes

See [`../docs/deploy/private-beta.md`](../docs/deploy/private-beta.md) for the manual split-service deploy runbook and [`../docs/deploy/railway-private-beta.md`](../docs/deploy/railway-private-beta.md) for the current Railway dry-run target map.

The frontend is a private-beta product surface. Production auth/session,
invite-only founder onboarding, and durable Company World confirmation are in
place. The next interface chunk is the spatial Company World board. Remaining
external gaps include the first real GitHub App installation/read, the first
production deploy of the auth phase, and email delivery/password reset.
