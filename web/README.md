# founderOS Web

Guided Next.js product for the FounderOS company-management flow.

## Run locally

From the repository root, use the canonical full-stack supervisor:

```bash
make local-doctor
make local
```

Open `http://127.0.0.1:3000`. `make local` starts/reuses local PostgreSQL,
applies migrations, and launches FastAPI plus Next.js with the required
same-origin proxy. Use `make local-liveness-smoke`, `make local-backup`, and
`make local-stop` for acceptance, backup, and shutdown. See
[`../docs/operations/local-runtime.md`](../docs/operations/local-runtime.md).

Direct `npm run dev` is a troubleshooting fallback only. When used, bind it to
the same exact IPv4 loopback origin as the canonical supervisor:

```bash
FOUNDEROS_API_PROXY_TARGET=http://127.0.0.1:8765 \
  npm run dev -- --hostname 127.0.0.1 --port 3000
```

The browser talks to the
backend **same-origin**: `web/next.config.mjs` proxies `/api/*` and `/health`, so
the session cookie stays first-party and no browser CORS is needed for normal
local operation.

## Local quality and CI checks

```bash
npm test
npm run build
npm run typecheck
npm run lint
```

These commands are enforced by repository CI. They do not require provider
credentials or live backend/provider calls.

Authenticated browser smoke is a separate operator gate:

```bash
npm run e2e:install
FOUNDEROS_E2E_LOGIN_EMAIL='<test-account-email>' \
FOUNDEROS_E2E_LOGIN_PASSWORD='<test-account-password>' \
npm run e2e
```

It uses desktop and mobile Chromium against the running loopback product,
persists no screenshots/video/traces, and fails on console warnings/errors or
horizontal overflow.

## Environment

The frontend proxies `/api/*` and `/health` to the backend so the session cookie
is first-party. Configure the proxy target (server-only):

```bash
FOUNDEROS_API_PROXY_TARGET=http://127.0.0.1:8765
```

The local runtime injects that value. If it is absent, the code falls back to
`NEXT_PUBLIC_API_BASE_URL`, then to the same loopback backend on port `8765`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8765
```

## Authentication

The app uses invite-only founder enrollment and email+password server sessions:

- A one-time `/start#token=...` link calls `POST /api/v1/auth/enroll` and then
  opens `/onboarding`. For a session with a workspace, that route enters the real
  `/dashboard` and opens one five-step server-computed setup modal; an account
  without a workspace stays on the explicit recovery screen and makes no
  workspace read. The bearer is accepted from the URL fragment only; query
  fallback is forbidden, and the address is cleared after capture. Public signup
  stays closed.
- A `/login` page calls `POST /api/v1/auth/login`; an `AuthGate` redirects
  unauthenticated users to `/login`.
- The session is an httpOnly first-party cookie (set by the backend); the
  company list is derived from memberships, not entered in the browser. One
  membership is selected automatically; several require an explicit choice.
- The Settings page is an account / change-password page
  (`POST /api/v1/auth/change-password`), not an operator-key/owner-email config
  page. `make local` opens returning login or performs the private first-founder
  browser handoff. `scripts/create_founder_invite.py` is a manual fallback and
  there is no password-through-env recovery path.
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
- The backend admits login, founder enrollment, and password setup through
  per-IP/global request windows and a concurrency cap before Argon2, in addition
  to the durable per-email DB lockout. The process backend matches the
  single-process loopback runtime; an atomic Redis backend is available for an
  approved multi-worker topology. Forwarded client IPs are ignored unless the
  direct proxy belongs to an explicit trusted CIDR. Disabled users' existing
  sessions are revoked when next validated.

The browser sends no operator API key and no owner email; the operator API key is
for server/CI/admin tooling only. The frontend never calls GitHub, Jira, Gmail,
Drive, or other providers directly. Do not commit secrets, API keys, provider
tokens, or local environment files.

Primary navigation is «Сейчас / Компания / Спросить / Настройки».
`/dashboard` shows one evidence-backed current priority and only a bounded
number of signals; deeper details open on demand. Company memory and profiles
live under «Компания», the deterministic snapshot-bound assistant lives under
«Спросить», and every provider/API diagnostic remains under «Настройки».
Provider-first routes and the old «Штаб / Мир / Миссии / Радары» shell are
removed and must not return. Shared shell/status copy is in
`web/lib/messages.ts`; the UI is Russian. Source setup/import/sync and action
review/execution require
owner/admin; briefing generation, local action creation, and Company World
resolution require member+; viewer keeps evidence-backed read access only.

## Local product boundary

The frontend is the local FounderOS product surface (DEC-077/DEC-088). Session
auth, invite-only founder enrollment, computed onboarding inside Headquarters,
and the spatial durable Company World are in place. Onboarding readiness and its
next action come from the unified server snapshot, not browser fan-out. The first
real GitHub App read and any external action remain separate, human-approved
operations after the explicit workspace/browser gates; email delivery and
password reset remain deferred.
