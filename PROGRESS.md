# FounderOS — PROGRESS

> Живое состояние реализации. Продуктовый источник истины:
> `founderOS_MASTER_PLAYBOOK.md`. Проверяемый ledger:
> `docs/AI_FOUNDEROS_ACCEPTANCE.md`.

## Сейчас

**FounderOS 2.0 product reset, Lifecycle Event Ledger v1, Temporal Memory v2,
GitHub Source Reconciliation v1, universal pytest database guard и Atomic
External Execution v1, Strict Action Evidence v1 и Database Workspace
Isolation v1, Python Static Typing Gate и Frontend Biome Gate реализованы
локально в ветке `codex/living-hq-ux-reset`. Runtime Readiness,
Browser Security Baseline, Shared Public Auth Admission, Reproducible
Dependency Gate и Durable GitHub Provider Jobs также реализованы локально;
изменения не опубликованы.**

FounderOS теперь определяется как AI-партнёр и второе мнение с доказуемой
памятью компании. Основной интерфейс сокращён до четырёх зон:

- `Сейчас` — один главный вывод, не более двух следующих ситуаций и вход в
  вопрос;
- `Компания` — люди, организации, работа и подтверждающие материалы;
- `Спросить` — отдельная evidence-backed рабочая зона без сохраняемой истории;
- `Настройки` — команда, подключения, API и технические проверки.

Домашний экран различает текущие подтверждённые факты, новые/изменённые сигналы
и завершённые решения после явного персонального checkpoint. Checkpoint хранит
точный snapshot, время, opaque fingerprints и монотонный cursor lifecycle
ledger; тексты источников и evidence не копируются.

## Что изменено

- Заменён legacy playbook и удалён старый Living Command Center ledger.
- Удалены runtime `/demo`, synthetic demo code, старые Today/Living HQ модели,
  мини-карта и их тесты.
- Удалены product routes `/connectors`, `/github`, `/jira`, `/gmail`, `/drive`.
  GitHub setup перенесён в `/settings/integrations/github`; все остальные
  подключения находятся в `/settings/integrations`.
- Удалены provider-first и старые primary labels из пользовательского shell.
- Домашняя страница перестроена вокруг текущей картины и прямого вопроса к
  FounderOS; техническое состояние источников убрано из основного экрана.
- `Спросить` сделан самостоятельным экраном поверх exact workspace snapshot.
  История диалога не сохраняется, provider calls и внешние записи не
  выполняются.
- Сохранены raw storage/Postgres truth, evidence, tenancy, RBAC, human approval,
  idempotency и receipts.
- Исправлен GitHub App fallback redirect на новый settings route.
- Удалены неиспользуемые старые тексты и CSS-блоки Command Center, Today,
  provider pulse и source-health drawer.
- Добавлен `headquarters.v3` с Temporal Memory v2: `event_time`,
  `observed_at`, evidence, confidence, workspace access и source-bound
  retention.
- Добавлен snapshot-bound checkpoint endpoint и минимальная таблица
  `company_memory_checkpoints`; checkpoint персонален для membership и
  каскадно удаляется при отзыве membership.
- Добавлен append-only `company_memory_events`: он хранит только канонические
  UUID-ссылки, тип/время события, SHA-256 fingerprint, confidence, access,
  sensitivity и retention policy. Заголовки, описания, письма, provider
  payloads и UI-тексты в ledger не копируются.
- Action Proposal creation/approval/rejection и Company World
  confirmation/dismissal записываются в ledger идемпотентно и в той же
  транзакции, что каноническое изменение.
- Temporal Memory v2 объединяет fingerprint-сравнение текущих сигналов с
  последовательным ledger cursor. Headquarters показывает terminal action/world
  события как `resolved`; повторный checkpoint скрывает уже просмотренное.
- Добавлен `source-reconciliation.v1`: только успешный полностью
  пагинированный server-attested GitHub read со всеми состояниями может
  tombstone-ить отсутствующие issue/PR внутри выбранного репозитория.
- Tombstone хранит время начала provider snapshot, время записи, SyncJob и
  контролируемую причину. Более старый снимок не перезаписывает более новый;
  ручной `normalize-local` не может восстановить исчезнувший объект.
- Повторное появление в trusted GitHub read очищает tombstone и создаёт
  content-free lifecycle event. Company Brain и operational work скрывают
  tombstoned Task/PullRequest, сохраняя историю и evidence в PostgreSQL.
- Jira/Gmail/Drive остаются без disappearance detection: их текущие локальные
  импорты не являются полными provider snapshots. Исторический backfill
  автоматически не выполняется.
- Добавлен fail-closed pytest guard до импорта `app.db.base`: обязательны
  `APP_ENV=test` и отдельный test-marked `FOUNDEROS_TEST_DATABASE_URL`, который
  не совпадает с product endpoint из `.env`/`.env.local`.
- Backend checker передаёт тот же проверенный target в pytest и принудительно
  отключает dotenv, LLM, real connectors и external writes. CI использует
  `ckdos_test` и после upgrade выполняет `alembic check` (DEC-099).
- GitHub write execution теперь сначала блокирует proposal, создаёт и коммитит
  durable claim с workspace, реальным user, connection, обязательным
  client-idempotency key, request hash и claim timestamp. Уникальные индексы
  запрещают повтор ключа в workspace и несколько active/successful execution
  для одного proposal (DEC-100).
- Перед provider call execution переводится в `running` отдельным коммитом.
  Потерянный ответ больше не записывается как ложный failure: execution
  остаётся `uncertain`, а read-only reconciliation ищет точный скрытый marker.
  Пустой ранний read сохраняет неопределённость на consistency grace period;
  только последующая полная проверка может разрешить retry с новым ключом.
- Acceptance-тест запускает два одновременных execute request и доказывает
  ровно один provider call, один `ActionExecution` и одну внешнюю задачу.
- User-created evidence теперь проходит строгую JSON-схему до сохранения.
  Approval и execution используют один canonical resolver: каждая ссылка
  обязана существовать, быть активной, относиться к тому же workspace и
  совпадать с exact GitHub target. Проверка повторяется после committed
  execution start непосредственно перед provider call (DEC-101).
- AI/system proposal нельзя принять без exact `headquarters.v3` snapshot.
  Bulk approve/reject больше не использует legacy transition: каждый элемент
  несёт proposal version, client idempotency key и optional exact snapshot,
  проходит тот же row lock/role/evidence service и возвращает отдельную
  decision receipt.
- Repo-audit import больше не сохраняет произвольные внешние evidence-строки:
  proposal хранит только канонический repository selector, который обязан
  разрешиться внутри workspace перед approval.
- PostgreSQL теперь сам запрещает cross-workspace ссылки для
  `EvidenceRef→SourceRecord`, `PullRequest→Repository`,
  `PullRequest→SourceRecord`, `Task→SourceRecord` и
  `DocumentVersion→Document`. Ссылки используют составные
  `(workspace_id, id)` foreign keys; миграция fail-closed останавливается, если
  до её применения уже существует нарушение (DEC-102).
- GitHub operational read дополнительно ограничивает SourceRecord joins и
  загрузку Repository текущим workspace, даже несмотря на новую защиту БД.
- RLS оценена, но не включена частично: публичный multi-tenant hosting
  запрещён до отдельного полного RLS gate с least-privileged app role,
  transaction-local tenant context, `FORCE ROW LEVEL SECURITY`, pool reset и
  cross-tenant integration tests.
- Backend checker и CI теперь запускают `mypy app`; устранены все найденные
  ошибки типов, а включённая конфигурация дополнительно проверяет untyped
  functions, implicit Optional, unreachable code, лишние casts и stale ignores
  (DEC-103).
- Frontend `lint` больше не дублирует TypeScript typecheck. Закреплённый Biome
  проверяет React/Next, accessibility, correctness и security по 91
  implementation/test файлу; найденные нарушения hook dependencies, ARIA,
  list keys и unsafe text parsing исправлены (DEC-103).
- Публичный `/health` сохранён как минимальная liveness-проверка, а новый
  `/health/ready` выполняет ограниченный по времени `SELECT 1`. Operator-only
  `/health/metrics` возвращает только низкокардинальные process counters
  (DEC-104).
- Request logging переведён на structlog JSON events с server-generated
  correlation ID. Query, headers, cookies, bodies, identities и provider data
  не логируются; тот же request ID возвращается в response header.
- Backend и Next.js применяют CSP/frame/referrer/permissions/nosniff policy;
  HSTS включается вне local-like среды. Swagger, ReDoc и OpenAPI закрыты вне
  local-like среды.
- Cookie-authenticated mutations и public auth endpoints проверяют exact
  Origin/Referer. `SameSite=None` запрещён startup gate вне local-like среды;
  обычный same-origin browser flow остаётся `Lax`.
- Login, founder enrollment и setup-password используют общий pre-Argon2
  admission. Локальный single-process backend использует bounded process
  counters; atomic Redis script обеспечивает общий per-IP/global/concurrency
  budget для нескольких workers и fail-closed при недоступном Redis (DEC-105).
- Forwarded client IP учитывается только если direct peer входит в явно
  настроенный trusted proxy CIDR. В остальных случаях заголовок игнорируется.
- Фоновая задача удаляет истёкшие sessions, setup-token hashes и
  founder-invite hashes. Session `last_seen_at` обновляется не чаще одного раза
  за настроенный интервал, а не на каждый authenticated request.
- Smoke разделён на public liveness, real authenticated session,
  authenticated workspace reads и Playwright desktop/mobile E2E. Browser gate
  не сохраняет screenshots, video или traces с данными компании и проверяет
  reload, четыре primary zones, console и overflow (DEC-104).
- Активные README/runbook приведены к навигации
  «Сейчас / Компания / Спросить / Настройки»; историческая five-zone проверка
  больше не считается текущим acceptance.
- Удалены неиспользуемые OpenAI/Google SDK, Tenacity, obsolete
  Google/email/triage/Jira/Telegram settings, legacy provider placeholders и
  старый operator launcher. `cryptography`, `starlette` и `python-dotenv`
  объявлены напрямую; LLM env-контракт остаётся выключенным reservation без
  SDK/runtime path (DEC-106).
- Backend checker и CI запускают актуальный `pip-audit`; frontend CI проверяет
  также dev dependencies. Найденные advisory устранены обновлением
  `pydantic-settings` и Starlette, без ignore-исключений.
- PostgreSQL и Redis в local Compose закреплены exact manifest digest, а
  Renovate обновляет Docker Compose tag+digest вместе после release-age delay.
- GitHub App live read больше не выполняет provider network I/O внутри API
  request или открытой SQL-транзакции. API только проверяет доступ и создаёт
  durable `SyncJob`, после чего возвращает `202`; bounded worker pool забирает
  задания через PostgreSQL lease и `SKIP LOCKED` (DEC-107).
- Каждый репозиторий читается через общий HTTP connection pool и сохраняется
  отдельной короткой транзакцией. Прогресс, завершённые репозитории и агрегаты
  позволяют продолжить работу после истёкшего lease без повторной обработки.
- Transient provider failures получают ограниченные exponential retries;
  наружу и в БД записываются только контролируемые коды/сообщения. Токен
  GitHub App остаётся только в памяти, а durable cursor не содержит raw
  provider payload.
- Экран GitHub автоматически следит за queued/running job до terminal state,
  показывает накопленный результат, блокирует повторный запуск и позволяет
  owner/admin отменить задачу. Отмена отзывает lease, а поздний provider result
  отбрасывается.

## Проверено 2026-07-29

- Frontend: `npm test` — **320 passed**.
- Frontend: `npm run typecheck` — успешно.
- Frontend: `npm run lint` — успешно, **95 files**, 0 warnings.
- Frontend: `npm run build` — успешно, **16 routes**.
- Frontend dependencies: full и production audit — **0 vulnerabilities**.
- Python dependencies: `pip-audit --local` — **0 known vulnerabilities**.
- Backend: guarded `make backend-check` equivalent — успешно.
- Backend: `uv run ruff check .` — успешно.
- Backend: `uv run mypy app` — успешно, **100 source files**.
- Backend: guarded full pytest — **788 passed**, одно внешнее
  deprecation-предупреждение Starlette/httpx.
- Alembic: единственная head `c4d5e6f7a8b9`, применена к отдельной test БД;
  `alembic check` не обнаружил расхождений metadata/schema.
- Небезопасный bare pytest без explicit test environment остановлен до
  application import; локальная `ckdos_test` создана отдельно от рабочей БД.
- Local runtime перезапущен штатным supervisor: `make local-doctor` полностью
  зелёный, backend `8765` и web `3000` принадлежат текущему FounderOS;
  прежний `make local-smoke` проверил только login `200`, health `200` и ожидаемый
  unauthenticated session probe `401`.

Authenticated browser QA не засчитан: локальный URL теперь открывается во
встроенном браузере и Chrome, но обе доступные сессии корректно перенаправлены
на `/login` и не содержат авторизации. Пароли/cookies не читались. Доступный
login-screen проверен при ширине `1280` и `390`: horizontal overflow и
console warnings/errors не обнаружены. Это не заменяет QA экранов после входа.

## Следующий рекомендуемый шаг

1. Добавить внешний error-reporting/tracing sink и полный hosted topology/RLS
   gate; process counters не являются distributed telemetry.
2. Провести новые authenticated session/workspace/browser gates и один
   founder-approved read-only GitHub App read.

## Неподвижные границы

- Секреты и `.env` значения не попадают в git, UI, логи или документацию.
- Raw storage и Postgres остаются источником истины; Obsidian — только export.
- Значимые утверждения и ActionProposal требуют `evidence_refs`.
- LLM не изменяет production data и не выполняет внешние действия напрямую.
