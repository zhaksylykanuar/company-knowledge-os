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
Dependency Gate, Durable GitHub Provider Jobs, Encrypted Off-device Recovery
Controls, Private Repository Governance и Maintainability Ratchets также
реализованы локально. Generative Second Opinion v1 реализован поверх exact
Headquarters snapshot со strict schema и evidence critic. Workspace AI/privacy
control реализован с encrypted key lifecycle, explicit synthetic check и
server kill switch. Memory Control v1 реализован для FounderOS-authored
документов с destructive correction/forgetting. Provider Credential Boundary
v1 реализован: ключи сервисов принимаются только workspace UI, а `.env.local`
оставлен только для bootstrap/deployment. Repository Intelligence RI-001
реализован как strict validation-only contract, RI-002 как canonical
workspace-scoped L0 projection, RI-003 как exact-SHA checkout manager, а RI-004
как bounded static collectors над synthetic checkouts. RI-005 строит
directional evidence-backed relationship candidates и bounded graph validation
только из synthetic RI-004 outputs. Target code не выполняется; изменения не
опубликованы.**

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

- Реализован RI-001 Repository Intelligence без migration/persistence/UI:
  `repository_intelligence.v1` отделяет trusted FounderOS envelope от
  untrusted analyzer result, требует workspace + stable repository identity,
  моделирует unavailable L0 SHA и exact L1/L2 SHA, использует object-shaped
  `evidence_ref.v1`, finite confidence, human-only resolution provenance,
  закрытые relationship/finding taxonomies, deterministic symmetric edges и
  сохранение evidence-backed contradictions. Добавлены только synthetic
  frontend/backend/infrastructure fixtures; company repositories не читались,
  не клонировались и не выполнялись (DEC-115).
- Реализован RI-002 canonical L0 без migration/API/UI/provider/checkout/LLM:
  projection читает только `Repository` и active identity-matching
  `SourceRecord` внутри exact workspace, использует SourceRecord UUID как
  evidence, честно возвращает unavailable SHA/unknown и не использует
  filesystem discovery, SourceEvent или legacy portfolio fallback. Purpose/type
  остаётся insufficient evidence без allowlisted canonical candidate; archived
  finding требует matching evidence (DEC-116).
- Реализован RI-003 safe checkout manager без provider portfolio read,
  migration/persistence/API/UI/LLM и без target execution. Он принимает только
  full exact SHA-1, требует standalone synthetic Git repository вне FounderOS,
  запрещает linked worktree/symlink/external alternates, использует minimal
  credential-free Git environment с denied protocols, bounded tree/blob reads,
  read-only materialization и verified cleanup на success/failure/cancel
  (DEC-117).
- Реализован RI-004 static collection без provider/company read,
  migration/persistence/API/UI/LLM и без target execution. Bounded deterministic
  collector читает только RI-003 exact-SHA checkout, распознаёт manifests,
  entrypoints, package dependencies, HTTP/schema interfaces, deployment,
  tests/CI, documentation и migrations/data objects, сохраняет только
  sanitized identifiers/paths и object-shaped evidence, а не file bodies или
  values. Synthetic frontend/backend/infrastructure и pathological fixtures
  покрывают determinism, bounds, evidence projection и no-execution boundary
  (DEC-118).
- Реализован RI-005 relationship analysis без provider/company read,
  migration/persistence/API/UI/LLM и без target execution. Trusted synthetic
  portfolio manifest разрешает stable identities и явные package/API/event/
  deploy selectors; RI-004 relationship-bearing facts становятся observed или
  inferred directional candidates с evidence на каждый edge. Unresolved targets
  остаются candidate references, symmetric edges нормализуются и объединяют
  evidence, inverse views не создают второй durable edge, а bounded graph pass
  находит cycles и orphans. Name similarity сама по себе не создаёт связь;
  opposing directional claims fail closed для отдельного contradiction review
  (DEC-119).
- Подготовлен proposal/handoff
  `docs/REPOSITORY_INTELLIGENCE_IMPLEMENTATION_PLAN.md` для будущего
  Repository Intelligence: назначение и обязанности каждого репозитория,
  directional evidence-backed связи между репозиториями, L0/L1/L2 аудит,
  durable runs/facts/findings, reconciliation, cross-source интеграция и
  безопасный staged rollout. Это план, а не реализованное поведение; следующий
  рекомендуемый slice в нём — strict contract/fixtures без миграции.
- Добавлен полный русскоязычный operational handoff
  `docs/REPOSITORY_INTELLIGENCE_FULL_GUIDE_RU.md`: какие папки создать, какие
  существующие FounderOS contracts переиспользовать, как пройти RI-001–RI-009
  только на synthetic fixtures, доказать readiness без чтения company repos и
  затем отдельно запустить read-only portfolio run по 20+ репозиториям.
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
  История диалога не сохраняется, внешние записи не выполняются. По умолчанию
  работает локальный детерминированный ответ; optional AI path требует server
  kill switch и проверенную workspace-настройку.
- Добавлен `/settings/ai`: owner/admin может сохранить зашифрованный OpenAI
  key, выбрать allowlisted model/reasoning/output budget, подтвердить текущую
  provider policy, включить AI, отдельно проверить соединение и удалить ключ.
  Viewer видит только безопасный статус.
- OpenAI и GitHub App больше не читают credentials/model/policy из env.
  GitHub token mint требует managed workspace credential; статус не показывает
  имена deployment variables.
- `.env.local` стал единственным dotenv-файлом runtime. `.env.example` содержит
  только bootstrap/deployment placeholders; provider secrets вводятся в
  `/settings/ai` и `/settings/integrations`.
- Удалены manual GitHub installation-record endpoint, offline env-preflight,
  password-through-env admin recovery и legacy local-org promotion script.
  Founder enrollment и GitHub App setup остаются product-managed.
- Добавлен `/settings/memory`: content-free preview показывает exact
  `updated_at` и число версий. Owner/admin может исправить внутренний документ
  с удалением всех прежних версий или забыть документ вместе со всей историей.
  Старый direct DELETE route удалён.
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
  объявлены напрямую. OpenAI SDK не возвращался: `assistant.v2` использует
  существующий audited HTTP client только после трёх явных gates (DEC-111
  supersedes reservation-часть DEC-106).
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
- Local restore-proven bundle теперь можно экспортировать только целиком в
  AES-256-GCM artifact на явно инициализированное независимое хранилище.
  Экспорт повторно decrypt-верифицируется; full drill восстанавливает PostgreSQL
  в private isolated cluster и пишет только sanitized receipt (DEC-108).
- Retention 7 daily / 4 weekly / 12 monthly имеет безопасный dry-run по
  умолчанию; destructive apply всегда отдельный. Реальный off-device target и
  отдельно восстановленный key ещё не предоставлены, поэтому operational DR
  не объявлен готовым.
- Добавлены private-source LICENSE, SECURITY, CONTRIBUTING, owner CODEOWNERS и
  repository-owned pre-commit secret/type/lint gates (DEC-109). Hosted branch
  protection и private reporting channel остаются настройками владельца.
- Удалены два superseded synchronous GitHub issue/PR sync endpoint и их
  дублирующие services: продукт их не использовал, а provider I/O всё ещё шёл
  внутри API SQL session. Unified GitHub App durable `202` job теперь
  единственный live repository-read route; historical normalized records
  остаются читаемыми (DEC-110).
- Action request/response contracts вынесены в отдельный schema module;
  `app/api/actions.py` уменьшен с 1 527 до 1 225 строк. Для audited больших
  модулей установлен line-budget ratchet.
- Headquarters query-budget сравнивает 1 и 100 SourceRecord и запрещает
  per-row N+1 SQL growth. Дальнейшее уменьшение Headquarters, большого
  ActionProposalsPanel и global CSS остаётся incremental work с
  characterization каждого slice, а не broad rewrite.
- Добавлен `assistant.v2`: UI явно разделяет факт, интерпретацию, возражение и
  рекомендацию. Optional OpenAI Responses path получает максимум 16 bounded
  normalized фактов exact snapshot, использует `store=false`, current-turn
  reasoning, strict JSON schema и fixed HTTPS endpoint. Локальный critic
  отклоняет неизвестные fact/evidence IDs и факт, не совпадающий с retrieval.
- LLM вопрос, prompt, response, response ID и история не сохраняются. Ошибка,
  refusal, timeout, invalid schema или critic rejection возвращают
  детерминированный fallback без provider detail. `store=false` не объявлен
  Zero Data Retention: отдельное data-policy acknowledgement обязательно.
- «Применить» в AI settings не вызывает провайдера. Проверка закрывает SQL
  session до сети и отправляет только synthetic fact без данных компании;
  сохраняется только status/code/model. Configuration version отклоняет
  устаревшую квитанцию, если во время проверки изменились key/model/policy.
- Workspace AI row является authoritative: при его наличии нет скрытого
  fallback на environment credential. Удаление ключа выключает AI и очищает
  policy/check state, не удаляя canonical memory или evidence.
- Memory correction/forgetting блокирует строку и сверяет exact preview:
  конкурентное изменение возвращает conflict, cross-workspace доступ закрыт.
  Операция не хранит reason/old body/receipt и не вызывает provider/LLM.
- Удаление доказано только для active PostgreSQL rows. Dead tuples/WAL и
  encrypted backups остаются до штатной retention rotation. Provider-backed
  records не имеют ложной кнопки удаления: evidence-safe cascade ещё предстоит.

## Проверено 2026-07-30

- Repository Intelligence RI-003 focused checkout suite — **28 passed**:
  exact historical SHA, external path, no hooks/target execution, symlink,
  linked-worktree, gitlink, alternates, portable collision, file/disk/path/output
  bounds, sanitized timeout/failure и cleanup после success/exception/cancel.
- Backend после RI-003: guarded `make backend-check` — **867 passed**;
  `uv run ruff check .`, `uv run mypy app` (**107 source files**), frozen sync,
  `pip-audit`, Alembic upgrade/check и tracked secret scan успешно; одно внешнее
  Starlette/httpx deprecation-предупреждение.
- Repository Intelligence RI-001 + RI-002 focused suites — **47 passed**:
  canonical synthetic frontend/backend/infrastructure L0, cross-workspace
  isolation, missing/tombstoned/mismatched evidence, unsafe URL removal,
  deterministic read-only execution и отсутствие filesystem/provider
  зависимости.
- Backend после RI-002: guarded `make backend-check` — **839 passed**;
  `uv run ruff check .`, `uv run mypy app` (**106 source files**), frozen sync,
  `pip-audit`, Alembic upgrade/check и tracked secret scan успешно; одно внешнее
  Starlette/httpx deprecation-предупреждение.
- Repository Intelligence RI-001: focused contract suite — **38 passed**;
  synthetic L0/L1/L2, strict evidence, SHA/workspace/status/relationship bounds,
  contradiction preservation, finite confidence и sanitized raw-JSON error
  покрыты без company data, provider/LLM calls, checkout или execution.
- Backend после RI-001: guarded `make backend-check` — **830 passed**;
  `uv run ruff check .`, `uv run mypy app` (**105 source files**), frozen sync,
  `pip-audit`, Alembic upgrade/check и tracked secret scan успешно; одно внешнее
  Starlette/httpx deprecation-предупреждение.
- Frontend: `npm test` — **325 passed**.
- Frontend: `npm run typecheck` — успешно.
- Frontend: `npm run lint` — успешно, **99 files**, 0 warnings.
- Frontend: `npm run build` — успешно, **18 routes**, включая
  `/settings/ai` и `/settings/memory`.
- Frontend dependencies: full и production audit — **0 vulnerabilities**.
- Python dependencies: `pip-audit --local` — **0 known vulnerabilities**.
- Backend: guarded `make backend-check` equivalent — успешно.
- Backend: `uv run ruff check .` — успешно.
- Backend: `uv run mypy app` — успешно, **102 source files**.
- Backend: guarded full pytest — **792 passed**, одно внешнее
  deprecation-предупреждение Starlette/httpx.
- Assistant v2: strict provider/evidence, fallback, privacy-gate и UI contract
  входят в полный backend/frontend gate; настоящий OpenAI call не выполнялся.
- AI settings: encrypted-at-rest secret, no-secret response, RBAC/isolation,
  DB readiness constraint, no-company-data check, stale-result rejection и
  отсутствие env-fallback даже без workspace row покрыты тестами; настоящий
  OpenAI call не выполнялся.
- GitHub App: environment/manual setup path удалён; тесты доказывают, что
  live read требует verified managed workspace credential и installation
  relation.
- Memory Control: exact preview, correction purge, full active document/version
  deletion, concurrency conflict, RBAC, workspace isolation и private/no-store
  response покрыты тестами; product data не использовались.
- Disaster recovery/governance: focused Ruff + **7 tests passed**; encrypted
  round-trip, tamper/path rejection, sanitized drill proof, retention и
  repository contracts подтверждены без product data.
- Alembic: единственная head `c6f41d8e29ab`, применена к отдельной test БД;
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

1. После отдельного approval начать RI-006 persistence ADR и reviewed migration
   в отдельной branch/PR workflow; до approval не создавать таблицы или jobs.
2. Заново внести OpenAI и нужные connector credentials через
   `/settings/ai` и `/settings/integrations`, затем выполнить отдельные
   read-only проверки.
3. Провести один явно разрешённый credentialed AI smoke из `/settings/ai`
   после проверки provider retention policy и оценить latency/cost.
4. Провести новые authenticated session/workspace/browser gates и один
   founder-approved read-only GitHub App read.
5. Настроить физически независимое storage и отдельное хранение recovery key,
   затем выполнить первый настоящий encrypted export и full restore drill.
6. Добавить внешний error-reporting/tracing sink и полный hosted topology/RLS
   gate; process counters не являются distributed telemetry.
7. Расширить Memory Control на provider-backed records только после exact
   dependency preview, evidence-safe cascade и provider-side deletion contract.

Последняя проверка RI-005 (2026-07-31):

- Security review for parent PR #35 (2026-08-02) hardened fixed-origin GitHub
  requests, keyed one-time setup-state verification, status-only bootstrap CLI
  output and exact frontend error matching (DEC-121); focused security suite —
  **44 backend + 326 frontend passed**.
- CI harness backport (2026-08-02) фиксирует canonical
  `http://127.0.0.1:3000` с non-credentialed CORS одинаково для direct pytest
  и `make backend-check`; production CORS defaults не изменены.
- focused RI contract/checkout/collector/relationship suite — **80 passed**;
- `uv run ruff check .` — успешно;
- guarded `make backend-check` — **884 passed**, Ruff, mypy (**109 source
  files**), frozen sync, `pip-audit`, Alembic upgrade/check и tracked secret
  scan успешно; одно внешнее Starlette/httpx deprecation-предупреждение.
- `make frontend-check` — **326 passed**, production build, typecheck и lint
  успешно.

## Неподвижные границы

- Provider secrets вводятся в UI один раз, шифруются до persistence и не
  возвращаются; `.env.local` values не попадают в git, UI, логи или документацию.
- Raw storage и Postgres остаются источником истины; Obsidian — только export.
- Значимые утверждения и ActionProposal требуют `evidence_refs`.
- LLM не изменяет production data и не выполняет внешние действия напрямую.
