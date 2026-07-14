# founderOS — PROGRESS (live state / single source of truth)

> Это **живой файл состояния**. Его обновляет агент (Claude Code / Codex) после КАЖДОЙ задачи.
> Человек смотрит сюда, чтобы за 5 секунд понять: **где мы и что дальше.**
> Текущая ветка `codex/guided-onboarding-ux` связана с Draft PR #33; UX-03 и
> UX-04 пока зафиксированы только локально и не опубликованы. Активный runtime теперь
> локальный (`make local`, DEC-077); hosted deploy не является текущей целью.

---

## ▶ СЕЙЧАС

- **UX-04 GitHub Source Command Center (DEC-079): РЕАЛИЗОВАН; BROWSER VISUAL QA
  PASS.** `/github` больше не показывает статические
  backend-карточки и MVP-заглушку. Экран ведёт через роль-зависимую миссию,
  трёхшаговый путь `GitHub App → выбранный репозиторий → задачи/PR`, четыре
  честные метрики загруженной repository-выборки и одну read-only загрузку.
  Репозитории показываются компактно (8 сразу, остальные по запросу); результат
  успешной или частичной загрузки автоматически обновляет «Пульс работы» с
  доступными задачами и PR, не выдавая `partial` за полный успех,
  который также ограничивает видимый список четырьмя строками на колонку.
  Readiness, env-названия, token/write policy, provenance, warnings и
  технические причины сохранены в disclosure. Viewer не получает недоступных
  обещаний; sync требует connected GitHub App installation, `connection_id` и
  валидный явный `owner/repo`, поэтому прежнее ложное действие при error/suspended
  закрыто. Backend API, БД, миграции, RBAC, provider-read approval,
  external-write и LLM gates не менялись. Проверено 2026-07-14: frontend
  **293/293 passed**, typecheck, lint и production build (**17 routes**) ✅;
  docs navigation **2 passed**, tracked-secret и whitespace checks ✅;
  локальные backend/frontend health endpoints отвечают. Авторизованный экран
  проверен на реальных локальных данных при **1280×720** и **390×844**: mission,
  метрики, repository chooser и work pulse складываются без горизонтального
  overflow; интерактивный keyboard/console pass остаётся отдельным follow-up.
- **UX-03 post-auth Command Mode (DEC-078): РЕАЛИЗОВАН; ВИЗУАЛЬНЫЙ QA
  ЗАБЛОКИРОВАН ИНСТРУМЕНТОМ.** Пять зон после авторизации теперь ведут
  пользователя через единый паттерн «Сейчас → Нажмите → Результат».
  «Сегодня» показывает короткую миссию и компактные сигналы; Company World
  обучает первому клику и ведёт к следующему кандидату; «Решения» ставят
  очередь и следующий доступный шаг выше создания, фильтров и диагностики;
  «Источники» рекомендуют полезное подключение, показывают результат и честно
  различают active/attention/read-only состояния; «Настройки» начинаются с
  команды и понятных ролей, а безопасность отделена в самостоятельный блок.
  Формы, readiness, evidence и технические границы сохранены через progressive
  disclosure; аккаунт перенесён в компактное профильное меню. Backend API, БД,
  миграции, RBAC, evidence и provider/write/LLM gates не менялись. Проверено
  2026-07-14: frontend **283/283 passed**, typecheck, lint и production build
  (**17 routes**) ✅; tracked-secret и whitespace checks ✅. Exact UX-03 tree
  ещё не прошёл desktop/mobile browser acceptance: обновлённый in-app browser
  падает до навигации с `Cannot redefine property: process`, поэтому прежний
  LOCAL-01 QA не переиспользуется как доказательство нового интерфейса.
- **LOCAL-FIRST RUNTIME (DEC-077): ПРИНЯТ И ГОТОВ К ИСПОЛЬЗОВАНИЮ.** Канонический
  цикл `make local-doctor` → `make local` → `make local-smoke` →
  `make local-backup` → `make local-stop` полностью проверен на текущей машине.
  PostgreSQL 16 и Alembic head `b4d5e6f7a8c9` зелёные; backend/frontend доступны
  только на loopback через same-origin proxy. Возвратный login, onboarding и
  пять зон продукта прошли авторизованный browser QA при 1280 px без overflow и
  console errors; временные QA user/workspace/session удалены. Restore-proven
  backup подтвердил 31 таблицу / 7 265 строк и 51 raw-файл / 1 353 141 байт,
  включая расшифровку 1 реального credential-поля; 3 test fixtures отделены.
  Restore работал через приватный Unix socket без TCP и полностью очистился.
  `SIGHUP` корректно остановил стек, а после имитации `SIGKILL` supervisor
  `make local-stop` безопасно убрал проверенные orphan-процессы. Изолированный
  backend gate: **655 passed / 1 внешнее warning**; frontend: **269 passed**,
  production build (17 routes), typecheck и lint. Следующий продуктовый gate —
  отдельно одобренная настройка GitHub App и один scoped read-only sync.
  Provider reads, external writes и LLM не включались. Старый hosted project не
  удалён: любое stop/domain/database/volume/project removal требует отдельного
  явного approval после restore-proof. Локальный экран входа теперь принимает
  короткий login identifier без требования email-формата; credential хранится
  только как Argon2-хеш в локальной БД и не попадает в tracked-файлы.
- **UX-02 spatial Company World board (DEC-076): ЗАКРЫТ ЛОКАЛЬНО.**
  `/company-brain` теперь ведёт не в набор реестров, а в
  пространственную стратегическую доску: компания находится в центре, команда,
  подтверждённая сеть и discovery-кандидаты разведены по понятным контурам, а
  один клик открывает сфокусированный profile inspector. Люди помещаются внутрь
  подтверждённой организации только при точном durable affiliation
  (`organization_id` + `organization_key` + human-authored relationship type);
  domain/name similarity и candidate signals не рисуются как факт, остальные
  подтверждённые люди остаются отдельно. Confirmation flow задаёт по одному
  человеческому вопросу за шаг, не меняя candidate-version/idempotency/RBAC и
  server-resolved evidence contract. Evidence и технические capability/window
  границы сохранены, но убраны в раскрываемые детали; provider call, external
  write, LLM, backend API или migration не добавлены. Проверено 2026-07-13:
  frontend **272/272 tests**, typecheck, lint и production build
  (**17 routes**) ✅; backend **537 passed / 1 внешнее deprecation warning** и
  Ruff ✅; Alembic `heads/current` — `b4d5e6f7a8c9`, `alembic check` — no new
  operations. Browser QA на desktop 1024/1280 px и mobile 390×844 прошёл без
  overlap/overflow: keyboard activation и focus transfer работают, controls не
  меньше 44 px, полный organization/person wizard сохраняет durable affiliation
  и только после этого группирует человека под организацией; console — **0
  warnings/errors**. Ephemeral QA workspace/users/invite/source/profile rows
  удалены; provider calls/writes, LLM, push и deploy не выполнялись. Offline
  `make release-handoff` прошёл на чистом exact commit: local MVP scope complete,
  full MVP complete остаётся false из-за human/external gates. Exact commit
  `85b5e1f` опубликован в Draft PR #33; все шесть GitHub checks зелёные.
  Hosted rehearsal и его backup blocker теперь исторический контекст, а не
  активный release gate. DEC-077 переводит продукт на проверяемый local-first
  runtime без cloud migration/deploy.
- **UX-01 guided founder onboarding + five-zone company shell (DEC-075):
  ЗАКРЫТ ЛОКАЛЬНО.** One-time fragment-only `/start` enrollment атомарно создаёт
  founder/company/owner/session и ведёт в real-state `/onboarding`; public signup
  закрыт. Основной UI теперь состоит из «Сегодня / Компания / Решения / Источники
  / Настройки»: «Сегодня» показывает одну следующую задачу и ровно три сигнала,
  provider routes вложены в «Источники», multi-company контекст выбирается явно,
  desktop rail и mobile bottom navigation сохраняют одинаковые пять зон. RBAC
  совпадает с backend. Inviter не задаёт teammate пароль: новый аккаунт получает
  ровно одну fragment-only setup-ссылку, cross-workspace existing account
  блокируется `409`, concurrent consumption/attach закрыты row locks. Login
  защищён DB email-throttle, stable dummy Argon2, bounded inputs и production
  pre-Argon2 process-local admission; disabled sessions отзываются.
  Проверено 2026-07-13: Ruff ✅; backend **537 passed / 1 внешнее deprecation
  warning**; Alembic `heads/current` — `b4d5e6f7a8c9`, `alembic check` — no new
  operations. Frontend **268/268 tests**, typecheck, lint и production build
  **17 routes (16 static + 1 dynamic)** ✅. Browser QA прошёл founder enrollment,
  hash-backed onboarding continuity, teammate self-setup/login, explicit
  multi-company selection и 390×844 mobile без overflow; console — **0
  warnings/errors**, ephemeral QA identities/workspaces/invites удалены. Tracked
  secret scan и `git diff --check` ✅. Provider calls/writes, LLM, push и deploy
  не выполнялись. Loopback runtime соответствует текущему single-process
  admission boundary; любой будущий public/multi-worker target потребует нового
  shared limiter и отдельной security-проверки. UX-02 закрыт DEC-076; актуальный
  указатель — первый отдельно одобренный GitHub App read после принятого
  local-first runtime DEC-077.
- **Durable Company World / founder confirmation (DEC-074):** проекция DEC-073
  теперь объединяется с workspace-owned `Person`, `Organization`,
  `Affiliation`, `Interaction` и terminal `CompanyWorldResolution` receipts.
  Member+ может явно подтвердить либо отклонить server-resolved кандидата через
  `POST /api/v1/workspaces/{workspace_id}/company-map/resolutions`; viewer
  остаётся read-only, а cross-workspace доступ скрыт. Клиент передаёт только
  candidate key/version, idempotency key и введённые человеком labels; email,
  domain и evidence повторно разрешаются сервером. Подтверждение материализует
  только sanitized Gmail metadata и source-record provenance, не меняет raw
  source records, не вызывает provider, external write или LLM. UI «Мир
  компании» показывает подтверждённых людей/организации отдельно от кандидатов,
  ручную классификацию связи и стабильные confirm/dismiss состояния. Добавлен
  aggregate-only `scripts/backfill_company_world.py`: dry-run по умолчанию,
  explicit `--apply`, без автоматического принятия внешних кандидатов. Alembic
  migration `a3c4d5e6f7b8` schema-only; downgrade fail-closed для непустых
  profile-таблиц.
  Проверено 2026-07-13: `UV_NO_SYNC=1 uv run ruff check .` ✅; полный backend
  regression — **498 passed / 1 внешнее deprecation warning**; Alembic
  `heads/current` — `a3c4d5e6f7b8`, empty-table downgrade до `f2b3c4d5e6f7` и
  повторный upgrade прошли; non-empty downgrade после exclusive locks отказал
  без потери данных и сохранил head; `alembic check` — без новых операций.
  Frontend: **222/222 tests**, build (16/16 routes), typecheck и lint ✅.
  Browser QA итогового дерева прошёл owner confirm/dismiss и reload durable
  person/organization profiles, viewer read-only, viewport 390×844 без
  горизонтального overflow и focus transfer в профиль; console — **0
  warnings/errors**. Локальный deterministic backfill добавил только **6
  membership-backed people в 6 workspaces**; повторный aggregate dry-run — **0
  proposals, 0 conflicts, 0 writes**. Ephemeral QA workspace и пользователи
  удалены; staged secret scan и cached whitespace audit ✅. Provider calls,
  external writes, deploy и LLM не выполнялись.
- **Chunk:** первая продуктовая фича за логином — **Briefings**. Chunk 1
  (персистентность) **сделан**; `CHUNK 8` hardening закрыт ранее. Repository
  identity/race debt перед live sync **закрыт** (DEC-050). GitHub App
  product-connect foundation **сделан** (DEC-052). GitHub App polling-only live
  read sync backend foundation **сделан** (DEC-053). `/github` product UI со
  списком repo, per-repo read-only sync кнопкой и local repo-surface focus
  фильтрами **сделан**. Mocked synced evidence/briefing isolation verification
  **сделан**. Live-read observability/rate-limit handling **сделан**. Локальный `/github` теперь
  показывает canonical org repo rows для `qtwin-io` из `.local/repos.json`
  (25 repos), а не retained source-event/legacy fallbacks; live read-only check
  по org env keys подтвердил тот же count без вывода секретов. Следующий
  продуктовый Company World chunk с durable профилями и founder-confirm flow
  закрыт (DEC-074), а spatial board/profile inspector закрыт frontend-срезом
  DEC-076. Local runtime acceptance по DEC-077 закрыт; следующий приоритет —
  GitHub App real-provider read как отдельный human-approved внешний gate.
- **GitHub App real-read-run readiness gate (НОВОЕ, DEC-054):** добавлен
  offline, детерминированный gate перед первым approved real read run:
  чистая функция `github_app_real_read_run_readiness()` + безопасный CLI
  `scripts/github_app_real_read_run_preflight.py` (только presence-флаги, без
  значений секретов) + offline unit-тесты + human-approved read-only runbook
  `docs/deploy/github-app-first-real-read-run.md`. `/github` теперь также
  показывает display-only real-read readiness section из уже загруженных
  `connectionStatus.app` + local repository surface: env configured/missing,
  installation connection state, repo count, blockers и next human step. Сам
  real read run остаётся существующим human-triggered scoped
  `POST .../app-installation/sync` (DEC-053). **Проверено независимо:** сейчас
  real read run внешне заблокирован — GitHub App env
  (`FOUNDEROS_GITHUB_APP_ID` / `..._PRIVATE_KEY`) не задан и installation
  connection не записан; сеть до `api.github.com` теперь доступна (`HTTP 200`
  без auth), локальная поверхность репо (25 из `.local/repos.json`)
  присутствует. Preflight/UI сообщает точный next step; выполнить run должен
  человек после установки credentials.
- **Connector framework registry (DEC-056):** добавлен канонический read-only
  реестр MVP-коннекторов: `GET /workspaces/{id}/connectors` и страница
  `/connectors` показывают `github`, `jira`, `gmail`, `drive`, counts локальных
  `integration_connections`, статус `available/planned`, boundary
  (no provider calls / no sync / no external writes / no LLM / no secret reads)
  и deep-link в доступные продуктовые пути. GitHub доступен через `/github`,
  Jira через `/jira`, Gmail через `/gmail`, Google Drive через `/drive`;
  весь MVP provider set теперь имеет локальную product surface.
- **Google Drive local connector foundation (НОВОЕ, DEC-059):** добавлен
  третий non-GitHub connector slice без внешних вызовов: `GET
  /api/v1/workspaces/{workspace_id}/drive/files` показывает локально
  импортированную Drive file metadata, а admin-only `POST
  .../drive/files/import` принимает pasted/exported JSON (`[...]` или
  `{ files: [...] }`) и идемпотентно пишет sanitized canonical
  `SourceRecord(provider=drive, record_type=file)` rows с evidence refs (без
  `Task` и без raw document body). `/drive` добавлен во фронтенд и sidebar;
  `/connectors` теперь помечает Google Drive как `available`. Boundary
  сохранён: no Drive provider calls, no sync, no external writes, no LLM,
  no secret reads; invalid entries возвращаются per-entry failures, valid
  entries могут импортироваться.
- **Company Brain connector SourceRecord coverage (НОВОЕ, DEC-060):** workspace
  Company Brain payload теперь содержит additive `source_records` coverage block
  (`total`, `by_provider`, `by_record_type`) по всем canonical `SourceRecord`
  rows workspace. Dashboard `SourceCoveragePanel` показывает общий count,
  provider breakdown (GitHub/Jira/Gmail/Drive) и record-type breakdown без raw
  payloads, email/document bodies, secrets, provider calls, sync, external
  writes или LLM. GitHub-first `summary/repositories/work/evidence` контракт
  сохранён; это visibility bridge для локальных коннекторов, а не full
  cross-provider reasoning model.
- **Founder Briefing connector coverage item (НОВОЕ, DEC-061):**
  детерминированный manual Founder Briefing теперь добавляет item
  `connector-source-coverage` из Company Brain `source_records` aggregate
  (DEC-060): total + by_provider + by_record_type по GitHub/Jira/Gmail/Drive,
  так что импортированные Jira/Gmail/Drive записи видны в самом briefing flow, а
  не только на dashboard. Company Brain читается один раз за генерацию и
  используется и существующим GitHub-first `source-coverage` item, и новым
  connector item. Aggregate-only: без raw payloads, provider calls, sync,
  external writes и LLM; при отсутствии записей item становится `next_step` с
  предупреждением. Существующие briefing item ids/shape сохранены, item
  additive.
- **Jira first-class Company Brain work items (НОВОЕ, DEC-062):** локальные
  canonical `Task(source_provider=jira)` rows теперь попадают в workspace
  Company Brain `work.issues`, `work.recent`, issue summary counts and evidence.
  `CompanyBrainWorkItem` получил optional `source_provider` и `project_key`, а
  UI показывает provider + scope (GitHub repo или Jira project) вместо
  GitHub-only repository label. Boundary сохранён: no Jira provider calls, no
  sync, no external writes, no raw payload rendering, no LLM. Gmail/Drive не
  притворяются task/work items; для них используется отдельная read-section
  модель (DEC-063).
- **Gmail/Drive first-class Company Brain read sections (НОВОЕ, DEC-063):**
  workspace Company Brain теперь возвращает `communications.messages` для
  локальных Gmail `SourceRecord(provider=gmail, record_type=message)` rows и
  `documents.files` для Drive `SourceRecord(provider=drive, record_type=file)`
  rows. UI показывает отдельные секции Gmail messages и Drive files, не
  превращая их в tasks. Читаются только sanitized normalized payload fields +
  source refs; raw email bodies/document contents, secrets, provider calls,
  sync, external writes и LLM не добавлены.
- **Founder Briefing non-GitHub read-model items (НОВОЕ, DEC-064):**
  детерминированный manual Founder Briefing теперь добавляет evidence-backed
  items из first-class Company Brain read sections: `jira-work-items` для
  локальных Jira issue work, `gmail-message-signals` для Gmail messages и
  `drive-file-signals` для Drive file metadata. Это additive briefing polish:
  данные берутся только из локального Company Brain + `source_refs`; Gmail/Drive
  не превращаются в tasks; provider calls, sync, external writes, raw
  email/document content, secret reads и LLM не добавлены. Точность под
  truncation: read-секции Company Brain обрезаются до display-limit, поэтому
  imported total берётся из unlimited `source_records` aggregate ("N shown of M
  imported"), а visible-only unread/shared помечены "in view" — обрезанный slice
  не выдаётся за workspace-wide total. Проверено (независимый прогон):
  `UV_NO_SYNC=1 uv run ruff check .` ✅, full backend
  `UV_NO_SYNC=1 uv run pytest -q` ✅ 436 passed / 1 warning,
  `UV_NO_SYNC=1 uv run alembic check` ✅ (no new ops), `npm test` ✅ 179,
  `npm run build` ✅, `npm run lint`/typecheck ✅,
  `bash scripts/check_no_secrets.sh --tracked` ✅.
- **Briefing → local non-GitHub ActionProposals (НОВОЕ, DEC-065):**
  persisted Founder Briefing теперь имеет local-only backend bridge
  `POST /api/v1/workspaces/{workspace_id}/briefings/{briefing_id}/action-proposals`
  и UI bulk control в BriefingPanel. Member+ user может сгенерировать локальные
  `internal_todo` `ActionProposal` rows из evidence-backed Jira/Gmail/Drive
  briefing items (`jira-work-items`, `gmail-message-signals`,
  `drive-file-signals`) и теперь также из `internal-document-context` (DEC-069).
  Missing-evidence items skip’аются, existing open actions по тому же
  `briefing_id + briefing_item_key` skip’аются (включая старые per-item UI
  actions), чтобы не создавать blind duplicates. Всё local DB only: no provider
  calls, no sync, no external writes, no secret reads, no LLM.
  Проверено: focused backend `tests/test_founder_briefing_api.py` ✅ 25 passed,
  frontend `npm test` ✅ 181 passed (после UI/API helper), plus ruff/imports.
- **Action review readiness summary (НОВОЕ):** `/actions` теперь показывает
  локальную сводку готовности review/execution по уже загруженным
  `ActionProposal` rows: сколько предложений ждёт решения, сколько одобренных
  GitHub issue proposals можно открыть в execution preview, сколько local-only
  internal follow-ups, сколько предложений без `evidence_refs`, и сколько
  предложений уже имеют reported execution receipt. Сводка даёт
  детерминированный next-step hint и не запускает execute, sync, provider call,
  external write, secret read или LLM.
- **Founder Briefing internal document context (НОВОЕ, DEC-067):**
  deterministic manual Founder Briefing теперь добавляет item
  `internal-document-context` из Company Brain `documents.notes` (DEC-066), так
  что внутренние документы не только видны в Brain, но и используются как
  founder-facing briefing context. Item показывает bounded metadata (count, top
  titles, statuses, tags) + internal document evidence refs; raw
  `body_markdown`/body text не копируются. Local-only: no provider calls, sync,
  external writes, secret reads или LLM. Проверено: focused
  `tests/test_founder_briefing_api.py` ✅ 26 passed.
- **Internal DocumentVersion history (НОВОЕ, DEC-068):** internal Documents
  теперь сохраняют immutable local history snapshots: version 1 на create и
  новая version на каждый effective successful update; пустой или
  идемпотентный PATCH остаётся no-op и не создаёт лишнюю revision. Добавлены
  `document_versions` + migration `f2b3c4d5e6f7`, read-only endpoint
  `GET /api/v1/workspaces/{workspace_id}/documents/{document_id}/versions`, и
  selectable version snapshots в `/documents` detail: founder может выбрать
  version и увидеть её markdown snapshot + metadata. Local-only: no provider
  calls, external writes, secret reads или LLM.
  `/documents` detail также поддерживает in-product edit (title/body/tags/
  status) и guarded delete через существующие PATCH/DELETE routes, поэтому CRUD
  внутренних документов доступен end-to-end и version history реально растёт
  выше version 1 через UI.
- **Gmail local connector foundation (НОВОЕ, DEC-058):** добавлен второй
  non-GitHub connector slice без внешних вызовов: `GET
  /api/v1/workspaces/{workspace_id}/gmail/messages` показывает локально
  импортированные Gmail messages, а admin-only `POST .../gmail/messages/import`
  принимает pasted/exported JSON (`[...]` или `{ messages: [...] }`) и
  идемпотентно пишет sanitized canonical `SourceRecord(provider=gmail,
  record_type=message)` rows с evidence refs (без `Task` и без raw body).
  `/gmail` добавлен во фронтенд и sidebar; `/connectors` теперь помечает Gmail
  как `available`. Boundary сохранён: no Gmail provider calls, no sync, no
  external writes, no LLM, no secret reads; invalid entries возвращаются
  per-entry failures, valid entries могут импортироваться.
- **Jira local connector foundation (НОВОЕ, DEC-057):** добавлен первый
  non-GitHub connector slice без внешних вызовов: `GET
  /api/v1/workspaces/{workspace_id}/jira/issues` показывает локально
  импортированные Jira issues, а admin-only `POST .../jira/issues/import`
  принимает pasted/exported JSON (`[...]` или `{ issues: [...] }`) и
  идемпотентно пишет sanitized canonical `SourceRecord(provider=jira,
  record_type=issue)` + `Task(source_provider=jira)` rows с evidence refs.
  `/jira` добавлен во фронтенд и sidebar; `/connectors` теперь помечает Jira
  как `available`. Boundary сохранён: no Jira provider calls, no sync, no
  external writes, no LLM, no secret reads; invalid issue entries возвращаются
  per-entry failures, valid entries могут импортироваться.
- **Teammate provisioning foundation (НОВОЕ, DEC-055):** добавлен первый
  multi-user slice без внешних сервисов: `GET /workspaces/{id}/members`
  возвращает local workspace members, а `POST /workspaces/{id}/members`
  позволяет owner/admin создать local `User` + `Membership` с ролью
  `admin|member|viewer`. `owner` остаётся bootstrap-only; duplicate membership,
  disabled users и viewer/member self-provisioning отклоняются. Endpoint явно
  возвращает `external_invite_sent=false` и `provider_write_performed=false`.
  Inviter больше не задаёт teammate пароль: для каждого нового локального
  аккаунта endpoint автоматически возвращает ровно одну fragment-only
  `/setup-password#token=...` ссылку для ручной передачи по доверенному каналу.
  `account_setup_tokens` хранит только SHA-256 digest; teammate сам задаёт пароль
  и входит, а concurrent/repeated consumption создаёт не более одной сессии.
  Existing account с membership в другом workspace не прикрепляется молча:
  endpoint блокирует такой запрос через `409` до будущего self-accepted invite
  flow; user-row lock закрывает конкурентное A/B workspace attach. Email
  delivery, recipient verification, password reset и SSO остаются отдельными
  последующими slices.
  `/settings` теперь показывает участников workspace и форму локального
  добавления teammate для owner/admin с тем же no-email/no-provider-write
  boundary; viewer/member видят read-only состояние.
- **Dashboard Source Coverage (НОВОЕ):** добавлен `SourceCoveragePanel` на
  `/dashboard`, который использует существующий Company Brain endpoint и
  показывает, что уже известно рабочему пространству: canonical repo count,
  open issue/PR count, evidence refs, local/live mode, live-provider deferred
  status и LLM off status. Панель не делает provider calls, не запускает LLM и
  не обещает live sync; copy централизован в `web/lib/messages.ts`, тесты
  проверяют states and no live/AI overclaim. Панель дополнительно показывает
  локальную разбивку по уже загруженному Company Brain payload: закрытая работа
  (closed issues / merged PRs), счётчик недавней активности, repo с source refs
  vs без них и evidence-разбивку по типу (kind). Разбивка не добавляет новых
  endpoints/provider calls/LLM и остаётся детерминированной read-only. Теперь
  там же есть блок deterministic next steps: canonical data readiness, evidence
  gaps, open-work review, live-provider boundary и AI boundary — всё вычисляется
  из уже загруженного payload и ничего не запускает.
- **Local runtime readiness (DEC-077):** текущий операционный путь —
  `make local-doctor`, `make local`, `make local-smoke`, `make local-backup`,
  `make local-stop` и `docs/operations/local-runtime.md`. Устаревший hosted
  checklist удалён из Dashboard; provider/write/LLM boundaries остаются в
  соответствующих продуктовых поверхностях и human-approved runbooks.
- **GitHub repo-surface focus (НОВОЕ):** `/github` теперь показывает локальный
  фокус/фильтры поверх уже загруженного списка репозиториев: все repo,
  активные, архивные, private и с evidence refs, плюс summary counts. Фильтр
  работает только client-side по уже полученному backend payload, не делает
  provider calls, не запускает bulk sync и сохраняет per-repo explicit
  read-only sync boundary.
- **Repository Audit surface + audit→local-action loop (ИСТОРИЯ; RETIRED
  DEC-073):** глобальная product page `/audit` и dashboard overview удалены,
  потому что filesystem-проекция не workspace-scoped. Preview API сохранён
  только для оператора с API key и отвергает browser session. Уже созданные
  `ActionProposal(source=repo_audit|repo_audit_import)` и workspace-scoped
  action-review/audit endpoints не удалены.
- **External repo-audit import (backend сохранён):** историческая форма `/audit`
  удалена из product UI; endpoint `POST .../actions/proposals/import-repo-audit`
  по-прежнему принимает JSON
  findings от внешнего/другого аудита (массив или `{ findings: [...] }`) и
  детерминированно превращает валидные entries в локальные `internal_todo`
  `ActionProposal` rows с `source=repo_audit_import` and per-finding partial
  failures. Импорт требует
  `repository_full_name` в формате `owner/repo` и `evidence_refs`, редактирует
  secret-like fragments в известных текстовых полях, пишет только локальные
  proposals и не вызывает provider APIs, external writes или LLM.
- **Repo-audit import UX hardening (ИСТОРИЯ; UI RETIRED DEC-073):** удалённая
  форма импорта показывала локальный предпросмотр разобранных findings: каждый
  finding помечается валидным/невалидным по тем же правилам, что и backend
  (`repository_full_name` в формате `owner/repo` + непустые `evidence_refs`), с
  описанием проблем по каждому пункту. Появились контролы «выбрать все валидные»
  и «снять выбор»; импортируются только выбранные валидные findings. После
  частичного импорта per-finding backend-ошибки показываются inline на
  соответствующих строках предпросмотра (включая случай, когда импортировалось
  только выбранное подмножество findings), выбранными остаются только упавшие
  findings (для повторной попытки), а вставленный JSON сохраняется. Предпросмотр
  редактирует secret-like fragments и не делает provider calls, external writes
  или LLM; импорт по-прежнему пишет только локальные `internal_todo` proposals.
- **Audit-origin action review polish (НОВОЕ):** `/actions` теперь различает
  локальные предложения из детерминированного repo audit (`source=repo_audit`) и
  импортированного внешнего аудита (`source=repo_audit_import`). Внутри origin
  filter «Из аудита репо» появился client-side подфильтр «Тип аудита»:
  все audit findings / детерминированный аудит / импортированный аудит. Карточки
  audit proposals получили отдельные badges для local deterministic vs external
  import, а payload details теперь показывают тип аудита вместе с repository,
  severity, area, recommended next step и risk/related entities без raw payload
  dump. `audit_source` query param поддержан на `/actions`, bulk selection and
  default evidence drawer follow the final visible subset. Всё local-only:
  backend/provider calls, external writes и LLM не добавлены.
- **Dashboard ↔ audit overview (ИСТОРИЯ; RETIRED DEC-073):** глобальная
  `RepositoryAuditOverviewPanel` больше не монтируется в workspace dashboard и
  ссылки на удалённый `/audit` отсутствуют в продуктовой навигации.
- **Briefing coverage signals (НОВОЕ):** manual deterministic Founder Briefing
  теперь добавляет `signals.coverage` и item `source-coverage` из локального
  Company Brain state: canonical repositories, open issues/PRs, evidence refs,
  local/live mode, live-provider sync flag and LLM flag. Persisted briefings
  остаются backward-compatible через default coverage model; UI cards теперь
  показывают coverage/work/evidence/mode вместо sync-job-centric summary.
  Никаких provider calls, external writes или LLM calls не добавлено.
- **Briefing → local Action bridge (НОВОЕ):** в `BriefingPanel` у каждого item
  появилась кнопка “Создать локальное действие”, которая создаёт `internal_todo`
  `ActionProposal` с summary/evidence refs из briefing item. Это local DB-only:
  не создаёт GitHub issue, не запускает external execution и не пишет во внешние
  сервисы; proposal далее проверяется/одобряется в блоке “Действия”.
- **Briefing item focus + evidence defaults (НОВОЕ):** `BriefingPanel` теперь
  умеет локально фильтровать пункты сводки по категории в уже загруженной
  deterministic briefing, показывает counts по категориям и не запускает
  provider calls/LLM. `EvidenceDrawer` для сводки по умолчанию показывает первый
  evidence ref из видимых пунктов, с briefing-specific default/manual context и
  evidence-ref count; ручной выбор evidence сохраняет приоритет над default.
- **Briefing history comparison (НОВОЕ):** карточки истории сводок теперь
  показывают persisted coverage summary (repos/open work/evidence/mode) and
  item/evidence deltas against the currently open briefing when available. Это
  local-only comparison over already loaded briefing summaries; no provider
  calls, external writes, or LLM.
- **Briefing ↔ Action cross-links (НОВОЕ):** `BriefingPanel` теперь
  дополнительно читает локальные `ActionProposal` rows и связывает уже созданные
  briefing-derived действия обратно с пунктами текущей сводки по
  `briefing_item_key`/`briefing_item_id`. В сводке видны counts по статусам
  действий, кнопка создания блокируется для пунктов с открытым локальным
  действием, а переход «Открыть действия» ведёт в `/actions` с фокусом
  `origin=briefing&status=proposed`. Всё local/read-only кроме уже существующей
  кнопки создания `internal_todo`: без provider calls, external writes и LLM.
- **Action review polish (НОВОЕ):** в `ActionProposalsPanel` добавлен локальный
  status filter (“Нужно решение” / “Одобрено” / “Отклонено” / “Все”) с counts.
  Фильтр работает только по уже загруженным local proposals, не делает provider
  calls, не меняет backend state и помогает разбирать `internal_todo` proposals,
  созданные из briefing evidence.
- **Action execution audit readability (НОВОЕ):** `ActionExecutionControls`
  теперь показывает audit events как структурированный локальный timeline
  (status/event/message/provider/action/external write) вместо плотной строки.
  No-write boundary отображается на уровне audit event; provider writes по-прежнему
  не запускаются без отдельного live execution path/confirmation.
- **Action evidence drawer defaults (НОВОЕ):** в `ActionProposalsPanel`
  evidence drawer теперь автоматически показывает первый evidence ref из текущего
  локального фильтра proposals, если пользователь ещё не выбрал источник вручную.
  Для фильтров без evidence остаётся безопасный placeholder; raw payloads/secrets
  не рендерятся, provider calls не запускаются.
- **Action proposal grouping + drawer/detail polish (НОВОЕ):** в
  `ActionProposalsPanel` отфильтрованные proposals теперь группируются по
  источнику (из пунктов сводки / задачи GitHub / внутренние) с counts и
  описаниями; briefing-derived proposals помечаются бейджем «Из сводки»
  (определяется по `briefing_item_id` или payload-маркеру `source=briefing_item`).
  `EvidenceDrawer` получил необязательные контекст-подсказку (default vs manual)
  и счётчик evidence refs, а evidence-по-умолчанию берётся из первого видимого
  proposal в порядке групп. Payload-рендерер для `internal_todo` из сводки теперь
  показывает ключ пункта сводки, категорию, важность, рекомендуемый следующий
  шаг и связанные сущности; raw payload dumps и secret-like ключи не выводятся.
  Всё local-only: без provider calls, external writes и LLM.
- **Action proposal origin filter (НОВОЕ):** `ActionProposalsPanel` теперь
  добавляет второй локальный фильтр «Источник предложения» поверх status-фильтра:
  все источники / из сводки / GitHub задачи / internal todo. Counts считаются
  внутри текущего status-фокуса, список и группы показывают только пересечение
  фильтров, а default evidence drawer берёт первый evidence ref из финальной
  видимой выборки. Фильтр работает только на уже загруженном local list, не
  делает backend provider calls, не мутирует state и не запускает external
  execution/LLM.
- **Action proposal bulk local review (НОВОЕ):** добавлены массовые локальные
  действия в `ActionProposalsPanel`: выбрать все видимые `proposed` предложения
  в текущем пересечении status/origin фильтров, снять выбор, локально одобрить
  выбранные или локально отклонить выбранные. Selection intentionally pruned to
  visible `proposed` proposals so hidden/approved/rejected карточки не
  затрагиваются случайно. Bulk approve/reject использует существующие локальные
  ActionProposal endpoints, меняет только local DB state and never starts
  provider execution, external writes, or LLM.
  Теперь bulk review backed by admin-only backend endpoints
  `POST .../actions/proposals/bulk-approve` and `bulk-reject`, которые dedupe
  requested IDs and return per-proposal successes/failures with counts.
  Bulk approve/reject устойчив к частичным сбоям: каждый переход settle-ится
  независимо на backend, успешные локальные изменения всегда сохраняются и
  мержатся, неуспешные остаются выбранными для повторной попытки, а частичный/
  полный сбой показывается inline без скрытия загруженного списка
  (`summarizeBulkResponse`).
  Single and bulk successful local approve/reject decisions now append sanitized
  no-write audit events to the existing per-proposal audit timeline
  (`action_proposal_approved_locally` / `action_proposal_rejected_locally`);
  no `ActionExecution` rows, provider calls, external writes, or LLM calls are
  created.
  UI: `ActionExecutionControls` can load that recorded decision history for any
  decided proposal (approved or rejected, GitHub or internal) via a read-only
  «Показать историю решений» control, so the persisted trail is reachable
  without going through the approved-GitHub-issue execution preview.
- **Local `/github` org repo inventory fix (НОВОЕ):**
  `scripts/ingest_local_org_repositories.py` продвигает локальный org snapshot
  в canonical `Repository` rows для workspace, чтобы `/github` брал список repo
  из highest-precedence canonical inventory. Скрипт idempotent/offline-only,
  читает non-secret `FOS_GITHUB_TARGET_ORG` из env/`.env.local`/`.env`, не
  читает/печатает GitHub tokens и не делает provider calls. Локально выполнено
  для `founder@example.com`: 25 `qtwin-io` repos visible через frontend proxy,
  token leak check false. После этого локально удалены stale non-org GitHub
  `source_events`/derived activity rows (`company-knowledge-os`, `example-org`);
  `qtwin-io` source events and canonical repo rows сохранены.
- **GitHub App live read sync backend/UI foundation (НОВОЕ):** DEC-053 фиксирует
  polling-only v0 (webhooks deferred до raw-body signature verification +
  delivery dedupe). Добавлены JIT installation token minting, read-only
  installation repository client, endpoint
  `POST .../github/connections/app-installation/sync`, explicit repository
  scope, issues/PRs provider reads into existing canonical
  normalization/upsert path, and `/github` per-repository explicit sync
  controls.
  Installation access token не сохраняется, provider writes не выполняются,
  tests/mock UI keep provider calls mocked. Company Brain and persisted
  deterministic Briefings are verified over mocked synced data with workspace
  isolation. Safe provider HTTP status/message/rate-limit metadata propagates to
  API errors without leaking authorization headers, tokens, or provider payloads.
- **GitHub App product-connect foundation (НОВОЕ):** DEC-052 выбирает GitHub App
  installation как product path (не OAuth/PAT в браузере). Добавлены backend
  config/status contract (`FOUNDEROS_GITHUB_APP_*`), workspace-scoped
  app-installation connection endpoint
  `POST .../github/connections/app-installation`, safe status payload без
  секретов, no provider calls, no persisted installation access tokens, no
  external writes. `/github` теперь показывает GitHub App readiness, local repo
  surface count, token persistence boundary, and writes disabled.
- **GitHub local repository surface (НОВОЕ):** `.local/repos.json` (25 repos,
  owner `qtwin-io`, offline/local only) теперь поддержан как fallback GitHub
  discovery snapshot for repo audit / repository inventory. Добавлен скрипт
  `scripts/prepare_github_local_snapshot.py`, который нормализует этот файл в
  `.local/discovery/github/<snapshot>/raw/repos.json` и пишет безопасный
  `.local/github-repositories.env` allowlist snippet без provider calls,
  токенов/секретов или write enablement. Локально подготовлен snapshot
  `.local/discovery/github/local-repos-current/raw/repos.json`. Решение — DEC-051.
- **Repository identity guard:** добавлена миграция `e8f9a0b1c2d3` и уникальный
  guard `uq_repositories_workspace_provider_full_name` (`workspace_id, provider,
  full_name`). `_upsert_repository` теперь race-safe across `external_id` and
  `full_name` paths and не понижает стабильный GitHub id обратно до full_name.
  Это закрывает near-term backlog item перед GitHub App live read sync.
  Решение — DEC-050.
- **Briefings Chunk 1 — персистентные сводки (бэкенд+фронтенд, гейты зелёные):**
  ручная Founder-сводка теперь **сохраняется**. Детерминированная генерация не
  менялась и по-прежнему без LLM — сохраняется только её вывод. Новые модели
  `Briefing` / `BriefingItem` + миграция `e7f8a9b0c1d2` (Briefings head на момент chunk),
  workspace-scoped, `ON DELETE CASCADE`, элементы упорядочены по `position` и
  повторяют форму генератора. `POST .../briefings/manual` запускает генерацию,
  **сохраняет** сводку + элементы и возвращает её с `id`
  (`persistence:"persisted"`); плюс история: `GET .../briefings` (новые сверху)
  и `GET .../briefings/{id}`, обе session/operator-auth и строго workspace-scoped
  (чужой workspace → 404). Фронтенд: «Сформировать сводку» сохраняет и показывает
  сводку, есть список истории с переоткрытием прошлых сводок (русские строки в
  `web/lib/messages.ts`). Бэкенд: `pytest 368 passed`, `ruff` чисто,
  `alembic check` чисто. Фронтенд: `npm test` 90, build/lint/typecheck зелёные.
  Без LLM и без GitHub OAuth/connect. Решение — DEC-048.
- **Что сделано ранее (sync-hardening/auth/русский UI series перед Briefings):**
  - **Sync-layer hardening (FOS-027B2 → далее):** в канонические `tasks` добавлен
    partial unique index `uq_tasks_workspace_provider_external_id`
    (`workspace_id, source_provider, external_id` при `external_id IS NOT NULL`;
    ручные задачи с NULL `external_id` не ограничиваются), дедуп существующих
    дублей в миграции `f7b8c9d0e1a2`, и идемпотентный `ON CONFLICT` upsert для
    `Task` / `PullRequest` / `SourceRecord` / `Repository` в
    `github_normalization_service`. Дрейф alembic по `ingested_events` сведён
    отдельной миграцией `a8c9d0e1f2b3` (только индексы/ограничения, без данных).
    `Task.updated_at` задокументирован как маркер «последней синхронизации»
    (bump на каждый sync), а пользовательская свежесть берётся из
    `source_updated_at`. Усилено шифрование секретов:
    `FOUNDEROS_SECRET_ENCRYPTION_KEY` обязателен вне local — иначе fail-closed,
    без переиспользования API-ключа как материала шифрования. Публичный health
    разделён: `GET /health` — минимальный liveness без auth, `GET /health/detail`
    (флаги app/env/write/llm) — за операторским ключом.
  - **Auth-фаза (email+password, серверные сессии; invite-only founder и
    локальный teammate setup, архитектура многопользовательская):**
    `password_service` (Argon2id),
    `session_service` + таблица `sessions` (в БД хранится только sha256-хэш
    токена, сырой токен только в cookie), эндпоинты
    `/api/v1/auth/login|logout|me|change-password`, зависимость `require_session`
    и резолвер `get_current_actor` (сессия-ИЛИ-операторский ключ; сессия в
    приоритете), DB-throttle логина от перебора (`login_attempts`, по умолчанию
    5 попыток / блок 15 мин, generic 401 без раскрытия существования email),
    стабильная dummy Argon2 verification для unknown/disabled/passwordless
    аккаунтов и process-local pre-Argon2 admission по client/global/concurrent
    limits в production. Верный пароль не позволяет злоумышленнику заблокировать
    владельца через email-throttle, disabled session отзывается при следующей
    проверке, а публичные password inputs ограничены до Argon2. Admission требует
    один Uvicorn process и отдельную deploy-проверку trusted client IP за proxy;
    до масштабирования нужен shared edge/Redis limiter.
    same-origin Next.js-прокси для first-party cookie
    (`FOUNDEROS_API_PROXY_TARGET`), фронтенд полностью переведён с
    operator-key/owner-email на сессию (`web/lib/config.ts` удалён, workspace
    берётся из сессии), страница Settings → аккаунт/смена пароля, админ
    создаётся идемпотентно через `scripts/create_admin_user.py`.
  - **Русский UI:** вся пользовательская копия вынесена в центральный каталог
    сообщений `web/lib/messages.ts` (без i18n-фреймворка).
- **Текущее состояние:** детерминированный evidence-first спайн + продуктовый
  логин (email+password, серверные сессии) + **персистентные briefings** поверх
  него + GitHub App product-connect + polling-only live read sync backend/UI
  foundation + synced-evidence isolation tests + safe rate-limit/error
  observability; операторский API-ключ остаётся для server/CI/админ-скриптов.
  Один alembic head — `b4d5e6f7a8c9`.
- **Дальше:** канонический DEC-077 lifecycle принят на текущей машине. Настроить
  founder-owned GitHub App, записать installation connection и после отдельного
  human approval выполнить один scoped read-only sync. External write и
  LLM-нарратив остаются последующими отдельными approval; future public/
  multi-worker hosting потребует нового решения и shared limiter/trusted-proxy
  проверки.
- **Примечание:** Briefings Chunk 1 — это реальный код (модели / миграция /
  эндпоинты / фронтенд) с зелёными гейтами; бэкенд и фронтенд закоммичены
  отдельно, push не делался.

---

## 📊 ПРОГРЕСС

```
Tasks: 23 / 29   ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▱▱▱▱▱   79%   (строго DONE)
Chunks: 2 / 9
```

Разбивка: **DONE = 23** · **PARTIAL = 5** · **MISSING = 1**.
FOS-002 закрыт по DEC-028 (spine-subset §6: SourceRecord/EvidenceRef/Repository/PullRequest/Task; остальные §6-модели отложены по чанкам — не «не сделано», а scoped-out).
DONE строго = есть код + проходящий тест/рабочий эндпоинт под acceptance criteria.
`docs/TODO.md` теперь содержит только near-term backlog; завершённые детали
живут в этом файле, `docs/CHANGELOG.md` и git history.

**Легенда статусов задачи:** `[ ]` todo · `[~]` in progress/partial · `[x]` done · `[!]` blocked

---

## 🚦 GATE HEALTH (актуальная последняя проверка по каждому gate)

| Gate | Status | Last checked | Evidence |
|---|---|---|---|
| `alembic upgrade head` | ✅ pass | 2026-07-14 | Isolated PostgreSQL 16 migrated from empty to the single head `b4d5e6f7a8c9`; product `heads/current/check` are green with no new operations |
| **Lineage-2 purge** (DEC-029) | ✅ done | 2026-06-24 | ~139 модулей + 27 таблиц + ~150 тестов + 55 скриптов + non-canon доки удалены; leftover static UI artifact/test removed by FOS-PURGE-01; tag `pre-purge-20260624` |
| **CHUNK 1 gate** (model tests + encryption roundtrip) | ✅ pass | 2026-06-24 | `tests/test_canonical_models.py` (9) + `test_integration_models.py` + encryption roundtrip — зелёные |
| backend tests (`pytest`) | ✅ pass | 2026-07-14 | Dedicated temporary loopback test database through `make backend-check`: **655 passed / 0 failed / 1 external warning** |
| `ruff` | ✅ pass | 2026-07-14 | Isolated backend gate: `uv run ruff check .` → `All checks passed!` |
| API namespace `/api/v1` (DEC-023) | ✅ done | 2026-06-24 | 660 `/v1`→`/api/v1`; нет stray `/v1` |
| frontend build | ✅ pass | 2026-07-14 | `npm test` **293 passed**; production build **17 routes**, typecheck and lint passed |
| UX-03 authenticated browser QA | ❓ unknown | 2026-07-14 | Exact UX-03 tree was not visually inspected: the in-app browser failed before navigation with `Cannot redefine property: process`; prior LOCAL-01 QA predates UX-03 and is not reused as proof |
| UX-04 `/github` browser visual QA | ✅ pass | 2026-07-14 | Authenticated real-local-data pass at **1280×720** and **390×844**; mission, metrics, compact repository chooser and work pulse render without horizontal overflow. Keyboard/console interaction audit remains separate |
| docs navigation | ✅ pass | 2026-07-14 | `test_local_runtime_docs.py`, `test_external_action_result_runbook.py`, and `test_docs_navigation_integrity.py` — **12 passed** |
| local runtime live acceptance | ✅ pass | 2026-07-14 | Doctor/start/smoke, authenticated onboarding + five zones, verified DB/raw restore, graceful signal stop and crash-orphan cleanup passed; ephemeral QA rows removed |
| `alembic check` (retained substrate) | ✅ reconciled | 2026-07-01 | Прежний дрейф (7 операций на `ingested_events`) сведён миграцией `a8c9d0e1f2b3`; GitHub App live read-sync foundation pass: `alembic upgrade head` + `alembic check` зелёные |
| **GitHub E2E (spine)** | ✅ selected-sync pass | 2026-06-26 | FOS-019B created exactly one real GitHub issue; FOS-020 read it back; FOS-021 closed it; FOS-022 selected repo issue sync read the approved smoke repo only; FOS-023 selected PR sync covered with read-only mocks |
| **full main E2E** | ✅ pass | 2026-06-26 | «approved action → real GitHub issue → canonical sync → cleanup close → closed-state sync → selected repository issue sync → selected PR sync» verified locally/mocked where provider reads are not live; execution count stayed single and no extra issues were created |
| historical hosted smoke | ✅ pass | 2026-06-27 | FOS-026C rehearsal evidence retained; it is not the active DEC-077 runtime gate |

Статусы: ✅ pass · ❌ fail · ❓ unknown

---

## ✅ CHUNKS

### CHUNK 0 — Audit & Docs ✅
*Gate: PROGRESS.md заполнен реальным состоянием; `docs/` создан.*
- [x] FOS-000 — Repository baseline audit — этот аудит, код не менялся; PROGRESS/DECISIONS/_audit обновлены
- [x] FOS-001 — Project docs — `docs/{DECISIONS,ROADMAP,TODO,POST_MVP,CHANGELOG}.md` существуют (⚠ 4 doc-contract теста красные — см. BLOCKERS)

### CHUNK 1 — Data Foundation ✅
*Gate: `alembic upgrade head` ✅ · model tests ✅ · encryption roundtrip test ✅.*
- [x] FOS-002 — Core DB models (spine-subset §6, DEC-028) — `app/db/canonical_models.py`: `SourceRecord`/`EvidenceRef`/`Repository`/`PullRequest`/`Task` (uuid, workspace-scoped) + миграция `f6b7c8d9e0a1` + `tests/test_canonical_models.py` (9 зелёных). `NormalizedEntity`/`Project`/`Briefing`/… отложены по чанкам; `Person` post-MVP.
- [x] FOS-003 — Encryption utility — `app/services/secret_encryption.py` (Fernet `encrypt_secret`/`decrypt_secret`); roundtrip доказан в `tests/test_github_provider_token_connection.py` (plaintext/`fernet:v1:` не утекают)

### CHUNK 2 — Connector Framework — ОТЛОЖЕН по DEC-028
*Не строим generic-абстракцию вперёд; выделим при 2-м коннекторе (Jira/Gmail). Общая §6-подложка делает это дёшево потом.*
- [ ] FOS-004 — Base connector interface — отложено (DEC-028): no speculative framework
- [ ] FOS-005 — Sync service — отложено (DEC-028); канонический `SourceRecord` теперь существует для будущего generic sync
- [ ] FOS-006 — Normalization service (+EvidenceRef) — отложено (DEC-028); `SourceRecord`/`EvidenceRef` существуют, `NormalizedEntity` deferred до FOS-012

### CHUNK 3 — GitHub E2E (SPINE) 🎯 критический milestone
*Gate: пользователь подключает GitHub через UI → sync → данные в Dashboard и Brain.*
- [~] FOS-007 — GitHub product connect — GitHub App installation выбран и
  foundation реализован (DEC-052): backend config/status, workspace-scoped
  app-installation connection record, `/github` readiness UI. Live provider read
  sync ещё не реализован; PAT bridge остаётся operator/admin bridge.
- [x] FOS-008 — GitHub sync repositories — `normalize-local` при `persist_if_supported=true` пишет canonical `source_records`/`repositories` idempotent-upsert; `persist_if_supported=false` остаётся projection-only. Доказано `tests/test_github_normalization_api.py` + `tests/test_github_first_backend_e2e.py`
- [x] FOS-009 — GitHub sync issues + PRs — local normalization reads local `cursor_before.local_github` issue/PR records, persists issues as canonical `Task`, PRs as canonical `PullRequest` linked to `Repository`, exposes `/api/v1/workspaces/{workspace_id}/github/operational-work`, and repoints repository inventory to canonical `repositories` before retained `source_events` fallback. No live provider execution.
- [x] FOS-010 — Connectors UI page — `web/app/dashboard` has product GitHub local-sync controls over existing backend contracts, and `/github` shows GitHub App product-connect readiness. UI reads connection status, runs canonical local normalization through `/api/v1/workspaces/{workspace_id}/github/local-sync`, reports counts/warnings, refreshes operational work, and keeps live provider execution out of the UI.
- [x] FOS-011 — Dashboard v0 — `web/app/dashboard/page.tsx` fetches canonical GitHub operational work via typed frontend API client, renders issue/task and PR sections, repository labels where present, open/all/closed/merged filters, and loading/empty/error states. No `source_events` direct read and no hardcoded current GitHub work.
- [x] FOS-012 — Brain entity API + UI — workspace-scoped canonical Company Brain read API `GET /api/v1/workspaces/{workspace_id}/company-brain` reads canonical `repositories`/GitHub `tasks`/`pull_requests` + `SourceRecord` refs, and `web/app/dashboard` renders deterministic evidence-backed GitHub state. Legacy founder preview routes remain unchanged; no live provider/AI execution.

### CHUNK 4 — Briefing MVP
*Gate: пользователь генерирует briefing с evidence drawer.*
- [x] FOS-013 — Briefing backend — `app/services/founder_briefing_service.py` детерминированный и без LLM; Chunk 1 добавил `Briefing`/`BriefingItem` persistence + history поверх той же генерации. `tests/test_founder_briefing_api.py` зелёный
- [x] FOS-014 — Briefing UI + evidence drawer — `web/components/BriefingPanel.tsx` + `EvidenceDrawer.tsx`; `web/app/dashboard` and `web/app/briefings` call the deterministic manual briefing endpoint, persist/show the briefing, list/reopen history, render returned briefing items/signals/warnings, and show provided evidence refs without inventing facts

### CHUNK 5 — Action Approval 🎯 full main E2E
*Gate: approved action создаёт реальный GitHub issue.*
- [x] FOS-015 — Action proposal API + UI — `app/api/actions.py` (create/list/get/approve/reject/execute) + модели ActionProposal/ActionExecution + миграция `f5a6b7c8d9e0`; `web/components/ActionProposalsPanel.tsx` wires product list/create/approve/reject, evidence drawer, local audit timestamps, and explicit no-external-execution copy. UI does **not** call execute.
- [x] FOS-016 — GitHub create-issue execution preview/audit — `app/api/actions.py` exposes `/execution-preview` for local approved GitHub issue proposals, preserves evidence refs without inventing them, reports eligibility/capabilities/audit fallback, and blocks `/execute` when `enable_write_actions=false`. `web/components/ActionExecutionControls.tsx` surfaces preview-only state, external-write disabled copy, confirmation UI only when backend says live writes are enabled, and no raw provider payload dumps. GitHub client remains mocked in tests; real external-write proof is still human-gated.
- [x] FOS-017 — Execution audit/receipt hardening — new proposal-scoped `ActionExecutionEvent` model/table + migration `a2b3c4d5e6f7`, idempotent audit append/list service, `/audit` read endpoint, persisted preview/blocked-execute events, and local execution receipt. `web/components/ActionExecutionControls.tsx` reads durable audit events, keeps timestamp fallback when empty, refreshes audit after preview/blocked execute, and continues to state that no external write occurred.
- [x] FOS-018 — Human-gated GitHub issue write path — existing `github_issue_execution_service` can call the GitHub issue client only after `enable_write_actions=true`, approved proposal, supported GitHub issue action, valid payload/connection, non-empty evidence refs, explicit confirmation, target repository in the explicit GitHub write allowlist (`FOS_GITHUB_WRITE_ALLOWED_REPOS` / `FOS_GITHUB_SMOKE_REPO`), and no existing successful receipt. Success/failure/duplicate/block paths persist `ActionExecution` receipts and `ActionExecutionEvent` audit events; duplicate execute returns the existing receipt without another provider call. `web/components/ActionExecutionControls.tsx` shows live execution controls only when backend capabilities allow them, requires explicit confirmation, and renders external issue receipt/link only after backend success. Automated tests still mock provider calls; FOS-019B proved the manual live smoke with exactly one issue against an approved private smoke repository.
- [x] FOS-020 — Post-execution sync verification — `POST /api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/sync-execution-result` validates the executed/succeeded GitHub issue receipt, uses an encrypted GitHub connection for read-only issue fetch, creates a local manual SyncJob, and reuses canonical GitHub normalization to upsert `SourceRecord` + `Task`. Verified against the smoke issue: operational work and Company Brain see the synced issue; deterministic briefing reflects the normalization item; execution rows remain single and no provider write is called.
- [x] FOS-021 — Smoke issue closeout / closed-state sync — after explicit human approval, closed exactly the existing approved smoke issue and nothing else. Closed state was read back and synced through the FOS-020 path; canonical `Task` is closed, operational open work no longer includes it, closed operational work does include it, Company Brain open issues=0/closed issues=1, deterministic briefing remains evidence-backed, and ActionExecution receipt count stayed single.
- [x] FOS-022 — Selected repository issue sync — `POST /api/v1/workspaces/{workspace_id}/github/repositories/issues/sync` reads issues only from explicit read-sync allowlisted repositories, uses encrypted GitHub connection access for provider reads, creates a manual SyncJob, normalizes selected issues into canonical `SourceRecord`/`Task` + repository records, skips PR-shaped issue API records, preserves open/closed state, and keeps external writes disabled. Verified live against the approved smoke repository only; no `/execute` call and no new GitHub issue/write.
- [x] FOS-023 — Selected repository PR sync — `POST /api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync` reads PRs only from explicit read-sync allowlisted repositories, validates allowlist before token decrypt/provider reads, creates a manual SyncJob, normalizes selected PRs into canonical `SourceRecord`/`PullRequest` + repository records, preserves open/closed/merged state, avoids duplicate repository rows after selected issue sync, de-dupes PR read models by repository+number, and keeps external writes disabled. Verified with read-only provider mocks for the approved repository scope; no `/execute` call and no GitHub write.

### CHUNK 6 — Remaining Connectors ✅ (local-only slices)
*Gate: Jira / Gmail / Drive / Documents видны в Brain — выполнено локально
(DEC-057/058/059/066). Live provider OAuth/sync для Jira/Gmail/Drive остаётся
отложенным.*
- [x] FOS-JIRA-01 — Jira connector minimal (local-only) — DONE via DEC-057. Local read-only issue import/list at `/jira` and `app/services/jira_connector_service.py` / `app/api/jira.py`. Live Jira OAuth/API-token provider sync remains deferred.
- [x] FOS-GMAIL-01 — Gmail connector minimal (local-only) — DONE via DEC-058. Local read-only message import/list at `/gmail` and `app/services/gmail_connector_service.py` / `app/api/gmail.py`. Live Gmail OAuth/API-token provider sync remains deferred.
- [x] FOS-019 — Drive connector minimal (local-only) — DONE via DEC-059. Local read-only file metadata import/list at `/drive` and `app/services/drive_connector_service.py` / `app/api/drive.py`. Live Drive OAuth/API-token provider sync remains deferred.
- [x] FOS-DOC-01 — Documents module — DONE via DEC-066. Canonical workspace-scoped
  `Document` model (`app/db/document_models.py`) + migrations `f1a2b3c4d5e6`
  and `f2b3c4d5e6f7`, member-gated CRUD + search service/API
  (`app/services/document_service.py`, `app/api/documents.py`: `GET/POST
  /workspaces/{id}/documents`, `GET/PATCH/DELETE /documents/{id}`,
  `GET /documents/{id}/versions`), `body_markdown` + deterministic `body_text`
  projection, immutable local `DocumentVersion` history (DEC-068), and
  `/documents` frontend page (list/search/create/detail/version history) +
  sidebar. Non-archived documents appear in Company Brain `documents.notes` with
  evidence. Manual Founder Briefing consumes `documents.notes` as
  `internal-document-context` (DEC-067). NormalizedEntity linkage deferred.
  Local-only: no provider calls, external writes, secret reads, or LLM.

### CHUNK 7 — Polish + Repo Audit UI (история; superseded DEC-073)
*Gate был закрыт исторически; глобальная UI-поверхность позднее выведена из
product routes из-за несовпадения tenant scope.*
- [x] FOS-RA-01 — Repo Audit UI — RETIRED FROM PRODUCT. Operator-only backend
  preview сохранён; `/audit` удалён, Company World заменил его в MVP completion
  contract. Workspace-scoped action audit/import APIs сохранены.
- [ ] FOS-P — Polish (errors/retries/empty/filters/evidence UX) — UI на уровне scaffold, не сделано

### CHUNK 8 — Testing Gate + Deploy
*Gate: launch gate зелёный; production URL работает; первый E2E в проде.*
- [x] FOS-025B — Deploy/smoke foundation — explicit backend CORS config, placeholder-only env contract, read-only private-beta smoke script, `make smoke`, local full-stack/private-beta smoke docs, and focused smoke/config/docs tests. No deploy and no external writes.
- [x] FOS-025C — Frontend/full-stack deploy-readiness CI gates — `.github/workflows/ci.yml` now has separate backend and frontend jobs; backend gates are preserved and add explicit docs/smoke/CORS/CI contract tests; frontend gates run `npm ci`, `npm test`, `npm run build`, `npm run typecheck`, and `npm run lint`; CI contains no provider secrets, live smoke command, selected sync, or execute calls.
- [x] FOS-025D — Private-beta deploy runbook/config path — `docs/deploy/private-beta.md` documents the manual split backend/frontend deploy model, managed Postgres/Redis, backend/frontend runtime commands, migration verification, backup/rollback, env names, CORS/API-base setup, GitHub connection limits, and read-only post-deploy smoke procedure. No deploy config that auto-deploys, no cloud secrets, and no deployment was added.
- [x] FOS-025E — Railway hosting target dry-run plan — `docs/deploy/railway-private-beta.md` maps the concrete Railway-only split-service target (backend API, frontend web, managed Postgres, managed/deferred Redis), commands, env names, domain/CORS/API-base, migration, smoke, rollback, operator checklist, and later live-provider-smoke approval boundaries; placeholder-only backend/frontend/smoke env templates and hosting-doc safety tests were added. No provisioning or deploy.
- [x] FOS-026B — Railway private-beta rehearsal — Railway project/backend/frontend/Postgres were provisioned; backend/frontend deployments reached success; Alembic migrated Postgres to head; deployed health/auth-only read-only smoke passed. No provider writes, LLM calls, selected sync, or ActionProposal execute.
- [x] FOS-026C — Private-beta workspace context + full deployed smoke — minimal workspace/owner context was bootstrapped through the supported operator API, then full read-only deployed smoke passed across workspace, GitHub connection status, Company Brain, operational work, and deterministic transient briefing checks. No provider writes, selected repo live sync, ActionProposal execute, or LLM calls.
- [x] FOS-SMOKE-01 — Smoke tests — backend `tests/test_github_first_backend_e2e.py` + `tests/test_external_connector_readonly_smoke.py` зелёные; FOS-025B added `make smoke` + read-only private-beta smoke script; FOS-026C proved the deployed Railway read-only smoke path with minimal private-beta workspace context.
- [x] FOS-T — Full tests + frontend build — FOS-025C local gate: backend full pytest 297 passed / 1 warning; frontend `npm test`, build, typecheck, and lint passed; CI now enforces both backend and frontend gates
- [x] FOS-027B1 — Private-beta blocker hardening pass 1 — API auth is fail-closed outside local via a startup guard; untrusted server-provided URLs render through `safeHref`/`SourceLink` (http(s)-only); stale `app/agents` bytecode and deleted-LLM/agent/boundary-doc references were reconciled. Backend pytest/ruff and frontend test/build/typecheck/lint green. No deploy, push, or provider writes.
- [x] FOS-027B2 — Task uniqueness + idempotent task upsert — partial unique index `uq_tasks_workspace_provider_external_id` (`workspace_id, source_provider, external_id` where `external_id IS NOT NULL`) + dedupe migration `f7b8c9d0e1a2`; the GitHub-issue→`Task` upsert in `github_normalization_service` is now `ON CONFLICT DO UPDATE` (index-matched), bumping `updated_at` per "last synced" semantics. Closes the duplicate-Task-rows blocker.
- [x] Sync-layer idempotency + hardening (post-FOS-027B2) — idempotent `ON CONFLICT` upserts for `PullRequest`/`SourceRecord`/`Repository`; `ingested_events` alembic drift reconciled (migration `a8c9d0e1f2b3`, indexes/constraints only); secret-encryption fail-closed outside local (`FOUNDEROS_SECRET_ENCRYPTION_KEY` required); public health split (`/health` liveness public, `/health/detail` behind operator key).
- [x] Auth phase (email+password, server-side sessions) — `password_service` (Argon2id), `session_service` + `sessions` table (stores only the sha256 token hash), `/api/v1/auth/login|logout|me|change-password`, `require_session` + `get_current_actor` (session-or-operator resolver), DB login brute-force throttle (`login_attempts`), same-origin Next.js proxy for a first-party cookie (`FOUNDEROS_API_PROXY_TARGET`), frontend migrated off operator-key/owner-email to the session (`web/lib/config.ts` removed), Settings→account page, invite-only founder enrollment and protected teammate setup. Multi-workspace/multi-user capable; browser users choose an explicit company when ambiguous. See DEC-041…DEC-047 and DEC-075.
- [x] UX-01 guided onboarding/company shell — fragment-only founder enrollment,
  computed five-step onboarding, five product zones, one-move/three-signal Today,
  nested source navigation, explicit workspace selector, role-accurate controls,
  automatic teammate self-setup links, concurrency/identity hardening, desktop and
  390 px browser acceptance. See DEC-075.
- [x] UX-02 spatial Company World board — company-centered strategic board,
  separate team/confirmed/discovery contours, affiliation-safe placement,
  focused profile inspector, exact-key touchpoint history, progressive
  evidence/technical disclosure, and one-question confirmation flow over the
  existing Company Map contract. Frontend **272 tests** plus
  typecheck/lint/build, full backend **537 tests**, Ruff/Alembic and desktop /
  390×844 browser acceptance are verified. See DEC-076.
- [x] Russian UI localization — all user-facing copy centralized in `web/lib/messages.ts` (no i18n framework; second language is a small addition). See DEC-045.
- [x] FOS-D — Local operation (DEC-077) — canonical loopback
  doctor/start/smoke/backup/stop acceptance, authenticated founder browser pass,
  restore proof, graceful signal shutdown and verified orphan cleanup completed.
  Historical hosted rehearsal evidence is retained; cloud/public-hosting scope
  was not expanded.

---

## ⛔ BLOCKERS

- ~~**[LOCAL-RUNTIME-P1] Full canonical local acceptance was pending.**~~
  **RESOLVED 2026-07-14:** doctor/start/authenticated browser/smoke/restore-proven
  backup/graceful stop/crash-orphan cleanup all passed on the current machine.
- **[EXTERNAL-RETIREMENT-GATE] No deletion is authorized.** Any older hosted
  database/service remains untouched until a matching-major logical archive has
  passed checksum and isolated restore verification. Stopping services, removing
  domains, deleting a database/volume, or deleting a project each requires a
  separate explicit human approval. Local-first operation alone is not approval.
- **[FUTURE-PUBLIC-HOSTING] Deferred, not blocking local use.** A future public
  or multi-worker topology needs a new hosting decision, shared edge/Redis login
  limiting, trusted-proxy verification, backups, monitoring, and restore drills.

- ~~[CHUNK 0] 4 doc-contract теста красные~~ — **РЕШЕНО (ШАГ A, 2026-06-24).** Починено doc-side (тесты не ослаблялись): вернул CI-секцию в README, lean `docs/playbook.md`, восстановил `docs/ops/jira-target-blueprint.md`, прилинковал guarded-operations, убрал legacy static-UI путь. pytest 1809/0. Коммит `394df7b`.

- ~~[CHUNK 1] Фундамент «вбок» — ОЖИДАЕТ РЕШЕНИЯ A/B~~ — **РЕШЕНО (DEC-028):** ветка A — §6 расширяет спайн (spine-subset готов, FOS-002), knowledge-graph lineage → frozen legacy и удалён (DEC-029). `source_events` repointed to compatibility fallback in FOS-009 (DEC-030); physical drop remains a later migration/cleanup task, not this feature path.

- ~~[SPINE] GitHub App live sync productization~~ — **FOUNDATION RESOLVED.**
  Product UI, polling-only backend read sync, observability, and mocked
  briefing/evidence isolation are present (DEC-052/053). The first real-provider
  read remains a separate human-approved external gate, not the next local UX
  implementation task.

---

## 🧾 SESSION LOG (append-only, новое — сверху)

- `2026-07-14` — **UX-04 GitHub Source Command Center (DEC-079).** Replaced
  `/github` backend scaffolding with one role-aware mission, a three-step visual
  data path, four bounded repository metrics, a compact selected-repository
  workbench and a refreshed operational task/PR pulse. Technical readiness,
  env names, provenance, token/write policy, warnings and causes remain behind
  disclosures. Counts are explicitly scoped to the loaded API sample; no CI,
  velocity, trend or organization-total metric is invented. Viewer guidance is
  read-only; admin sync remains one explicit repository and now fails closed
  unless the installation is connected with a connection id. Frontend-only:
  no API, persistence, migration, provider write/read authorization, or LLM
  change. Checks: frontend **293/293 passed**, production build (**17 routes**),
  typecheck, lint, docs navigation **2 passed**, tracked-secret scan and
  `git diff --check` ✅; local health endpoints respond. Authenticated browser
  visual QA passed with real local data at **1280×720** and **390×844** without
  horizontal overflow; keyboard/console interaction remains a separate pass.
- `2026-07-14` — **UX-03 post-auth Command Mode (DEC-078).** Reworked the five
  authenticated zones around one mission-first grammar: «Сейчас → Нажмите →
  Результат». Today now keeps one compact move; Company World teaches the first
  click and offers the next unresolved candidate; Actions leads with the queue,
  role-aware decision/preview step and explicit failed execution state;
  Connectors recommends the next useful source while distinguishing connected,
  attention and role-limited states; Settings leads with the human roster and
  separates account security. Secondary creation, filters, readiness, evidence
  and technical boundaries remain available through disclosures. The profile
  control keeps both name and account email visible. Frontend-only: no API,
  persistence, migration, provider, external-write or LLM change. Checks:
  frontend **283/283 passed**, production build (**17 routes**), typecheck,
  lint, tracked-secret scan and `git diff --check` ✅. Exact desktop/mobile
  visual acceptance remains unknown because the in-app browser bootstrap fails
  before navigation with `Cannot redefine property: process`; older browser QA
  is not counted for this tree.
- `2026-07-14` — **LOCAL-01 full local acceptance completed.** The canonical
  local lifecycle passed on PostgreSQL 16: doctor, start, same-origin smoke,
  returning-user authentication, guided onboarding and all five founder zones.
  Browser QA at 1280 px found no horizontal overflow or console errors;
  the ephemeral user, workspace, membership and session were removed. The
  verified private backup restored 31 tables / 7 265 aggregate rows and checked
  51 raw files / 72 directories / 1 353 141 bytes; 1 real encrypted credential
  field decrypted successfully, 3 explicit fixtures were excluded, restore used
  a private Unix socket with TCP disabled, and no temporary cluster remained.
  Graceful `SIGHUP` cleanup and simulated supervisor `SIGKILL` followed by
  `make local-stop` both cleared state and app listeners without touching data.
  Final gates: isolated test PostgreSQL migration/schema/Ruff/pytest/secret scan
  **655 passed / 1 external warning**; frontend **269 passed** plus build
  (17 routes), typecheck and lint; product Alembic head/current/check, Compose
  config, tracked-secret scan and whitespace check all green. Railway was removed
  from the active repo path, but no external hosted resource was stopped or
  deleted. Next: founder-approved GitHub App credentials/installation and one
  explicit scoped read-only sync; writes and LLM remain separate approvals.
- `2026-07-14` — **Local-first runtime becomes the active product path
  (DEC-077).** Replaced the active hosted/private-beta operating guidance with
  `make local-doctor`, `make local`, `make local-smoke`, `make local-backup`, and
  `make local-stop`; added `docs/operations/local-runtime.md`; retired the
  Railway/private-beta runbooks and placeholder hosting templates; kept prior
  rehearsal history intact. The supervisor reuses healthy loopback PostgreSQL or
  starts a safe Compose fallback, preserves `.local/`/volumes, runs backend and
  frontend on loopback with the same-origin proxy, and opens returning login or
  private first-founder enrollment without printing the bearer. Redis is
  optional. Provider reads/writes and LLM remain separate approvals. No hosted
  resource was stopped or deleted; final archive/restore proof and a separate
  explicit approval are required before every external retirement phase.
- `2026-07-14` — **Private-beta publication passed; production deploy stopped at
  backup gate.** Published exact product commit `85b5e1f` on
  `codex/guided-onboarding-ux`, opened Draft PR #33, and received six green
  GitHub checks (backend, frontend, dependency review and CodeQL). Re-ran local
  release gates: backend **537 passed / 1 external warning**, Ruff, frontend
  **272 passed** plus build/typecheck/lint, tracked-secret and whitespace checks
  all green. Read-only Railway inspection confirmed production auth/database
  presence and write-actions/LLM/real-connectors disabled. Production Alembic
  current is `a2b3c4d5e6f7`; reviewed head is `b4d5e6f7a8c9` (11 pending
  migrations). No managed backup exists and the Railway Trial plan exposes zero
  backup entitlement, so backup creation was rejected. The running CLI-uploaded
  backend also exposes no source SHA and is outside Trial image retention.
  Compatible rollback source `541a0df` was therefore verified locally against
  its matching Alembic head: backend 316 tests/Ruff and frontend 80 tests/build/
  typecheck/lint are green (two moderate old frontend dependency findings remain
  bounded to emergency rollback). No service was scaled, no migration/deploy/
  smoke/provider call/external write/LLM was started. Next: establish and verify
  the data backup boundary, then resume the documented maintenance/deploy
  sequence.
- `2026-07-13` — **UX-02 spatial Company World board (DEC-076).** Replaced the
  registry-like Company World surface with a company-centered strategy board,
  distinct team/confirmed-network/discovery zones, focused inspector and
  profile-local touchpoint history. Confirmed people are nested under an
  organization only from exact durable affiliation fields plus a human-authored
  relationship; domain/name/candidate similarity never creates a visual fact.
  Candidate resolution now asks one plain-language question per step, while
  evidence and capability/window boundaries remain available through collapsed
  disclosures. Existing API, durable rows, RBAC, candidate versions,
  idempotency and server-resolved evidence remain unchanged; no migration,
  provider call/write or LLM. Checks: frontend **272 passed** plus
  typecheck/lint/build (**17 routes**) ✅; backend **537 passed / 1 external
  warning**, Ruff and Alembic head/current/check ✅; desktop 1024/1280 px и
  mobile 390×844 browser QA passed without overlap/overflow, with
  keyboard/focus/44 px
  controls, complete organization/person resolution and **0 console
  warnings/errors**. Ephemeral QA data was removed. Offline
  `make release-handoff` then passed on a clean exact commit with local MVP scope
  complete and no deploy/provider/external write. Next: explicit human approval
  for push → deploy/read-only smoke, not another UX expansion.
- `2026-07-13` — **UX-01 guided founder onboarding + company-management shell
  (DEC-075).** Replaced the technical panel wall with five primary zones,
  deterministic Today, contextual source/company navigation, explicit workspace
  choice, guided computed onboarding, and bold responsive public/auth surfaces.
  Added one-time hash-only founder enrollment and automatic teammate self-setup;
  removed inviter-selected credentials; added row-lock concurrency, cross-
  workspace `409`, disabled-session revocation, stable dummy verification,
  bounded passwords, durable DB throttle cleanup, and production pre-Argon2
  admission. Checks: backend **537 passed / 1 external warning**, Ruff ✅,
  Alembic head/current/check ✅; frontend **268 passed**, typecheck/lint/build
  **17 routes** ✅; founder/team/multi-workspace/mobile browser QA ✅ with **0
  warnings/errors**; QA rows cleaned; tracked secrets/whitespace checks ✅. No
  provider call/write, LLM, push, or deploy. P1 deploy gate remains distinct
  client-IP/shared-limiter verification; next local chunk is UX-02.
- `2026-07-13` — **Durable Company World profiles + founder confirmation
  (DEC-074).** Добавлены workspace-owned people, organizations, affiliations,
  sanitized interactions и terminal resolution receipts; server-revalidated
  member+ confirm/dismiss API, viewer/cross-tenant boundaries, отдельные
  person/organization decisions, snapshot locks, idempotency и безопасный
  dry-run/apply backfill. «Мир компании» теперь разделяет подтверждённые
  профили и кандидатов, показывает роль, должность, заказчика и историю
  соприкосновений. Concurrent confirmation, stale UI completion, membership
  provenance и locked fail-closed rollback покрыты regression tests. Checks:
  backend **498 passed / 1 external warning**, ruff ✅, Alembic empty
  downgrade/upgrade + non-empty refusal + no-drift check ✅, frontend **222
  passed** + build/typecheck/lint ✅, owner/viewer/mobile browser QA ✅, console
  clean, staged secret scan ✅, post-apply backfill dry-run **0
  proposals/conflicts/writes**. Следующий шаг — private-beta release
  handoff/deploy на этом reviewed commit; push, deploy и provider gates требуют
  отдельного человеческого действия.

- `2026-07-07` — **Private-beta release handoff report.**
  Added a sanitized offline release handoff packet for the human push/deploy
  boundary: `scripts/private_beta_release_handoff.py` plus `make
  release-handoff`. It combines local git state, the deterministic MVP
  completion audit, GitHub App real-read preflight, and ordered human-gated next
  steps (push, deploy, read-only smoke, GitHub App setup/read, one external
  action result smoke) without starting deploy, provider calls, provider writes,
  external writes, database access, secret reads, or LLM. Linked from
  `README.md` and `docs/README.md`; covered by
  `tests/test_private_beta_release_handoff.py`. Files: `Makefile`,
  `scripts/private_beta_release_handoff.py`,
  `tests/test_private_beta_release_handoff.py`, `README.md`, `docs/README.md`,
  `docs/CHANGELOG.md`, `docs/TODO.md`, `PROGRESS.md`. Checks: focused
  `UV_NO_SYNC=1 uv run pytest -q tests/test_private_beta_release_handoff.py
  tests/test_mvp_completion_audit.py tests/test_docs_navigation_integrity.py` ✅
  **11 passed**, `make release-handoff` ✅, full backend
  `UV_NO_SYNC=1 uv run pytest -q` ✅ **469 passed / 1 warning**,
  `UV_NO_SYNC=1 uv run ruff check .` ✅, `UV_NO_SYNC=1 uv run alembic check` ✅
  (no drift), frontend `npm test` ✅ **205 passed**, `npm run build` ✅,
  `npm run lint` ✅, tracked secret scan ✅, `git diff --check` ✅. Commit
  local-only; push не делался.

- `2026-07-07` — **External action result smoke runbook.**
  Added the missing manual runbook for the final human-gated MVP flow step:
  `docs/deploy/external-action-result-smoke.md` documents a one-action,
  explicitly approved write smoke for `Approve Action Proposal -> See External
  Action Result` after deploy/read-only smoke/first provider read proof. It
  covers preconditions, preferred `/actions` UI path, API fallback placeholders,
  evidence/approval requirements, `execution-preview`, `/execute`,
  `sync-execution-result`, idempotency/duplicate behavior, sanitized reporting,
  cleanup/rollback boundaries, and disabling `ENABLE_WRITE_ACTIONS` after the
  smoke. The runbook is linked from `README.md` and `docs/README.md`, and the
  MVP completion audit now treats it as evidence for the human-gated external
  result path. No live provider call, external write, deploy, migration, secret
  read, or LLM was run. Files: `docs/deploy/external-action-result-smoke.md`,
  `tests/test_external_action_result_runbook.py`,
  `app/services/mvp_completion_audit.py`, `README.md`, `docs/README.md`,
  `docs/CHANGELOG.md`, `docs/TODO.md`, `PROGRESS.md`. Checks: focused
  `UV_NO_SYNC=1 uv run pytest -q tests/test_external_action_result_runbook.py
  tests/test_mvp_completion_audit.py tests/test_docs_navigation_integrity.py`
  ✅ **12 passed**, MVP audit CLI ✅ (`local_scope_complete=True`,
  `fully_complete=False`), full backend `UV_NO_SYNC=1 uv run pytest -q` ✅
  **465 passed / 1 warning**, `UV_NO_SYNC=1 uv run ruff check .` ✅,
  `UV_NO_SYNC=1 uv run alembic check` ✅ (no drift), tracked secret scan ✅,
  `git diff --check` ✅. Commit local-only; push не делался.

- `2026-07-07` — **Deterministic MVP completion audit.**
  Independently re-derived the playbook MVP contract and added a pure, offline
  audit that maps every §1.5 requirement and §1.4 main-flow step to
  authoritative in-repo evidence: `app/services/mvp_completion_audit.py`
  (evidence checks + summary), CLI `scripts/mvp_completion_audit.py`
  (`--json`), and offline tests `tests/test_mvp_completion_audit.py`. The audit
  reports `local_scope_complete = True` (29/29 local items present) but
  `fully_complete = False`, honestly keeping staging/prod deployment and the
  first real external action result as human/external-gated. Read-only/offline:
  no provider calls, network, database, deploy, external write, secret read, or
  LLM. Files: `app/services/mvp_completion_audit.py`,
  `scripts/mvp_completion_audit.py`, `tests/test_mvp_completion_audit.py`,
  `docs/CHANGELOG.md`, `docs/TODO.md`, `PROGRESS.md`. Checks: focused
  `UV_NO_SYNC=1 uv run pytest -q tests/test_mvp_completion_audit.py` ✅ **5
  passed**, full backend `UV_NO_SYNC=1 uv run pytest -q` ✅ **460 passed / 1
  warning**, `UV_NO_SYNC=1 uv run ruff check .` ✅, `UV_NO_SYNC=1 uv run alembic
  check` ✅ (no drift), frontend `npm test` ✅ **205 passed**, `npm run build`
  ✅, `npm run lint` ✅, tracked secret scan ✅, `git diff --check` ✅. Commit
  local-only; push не делался.

- `2026-07-07` — **Control docs current-state alignment.**
  Reconciled stale high-level status text in `README.md`,
  `founderOS_MASTER_PLAYBOOK.md`, and `docs/ROADMAP.md` so completion audits no
  longer treat already-built local surfaces as missing. The docs now mark
  local Jira/Gmail/Drive import/list connectors, internal Documents,
  normalized entities, teammate provisioning/setup links, sanitized request
  logging, the prior guarded GitHub issue live smoke, and `/github` real-read
  readiness as implemented where appropriate, while keeping the true remaining
  gaps explicit: first human-approved GitHub App real read, first production
  deploy of the current auth/session build, LLM narrative, live non-GitHub
  provider sync, email/SSO delivery, webhooks/rate limiting, custom domain, and
  broader beta hardening. Docs-only: no code path, provider call, external
  write, deploy, push, secret read, or LLM. Files: `README.md`,
  `founderOS_MASTER_PLAYBOOK.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`,
  `PROGRESS.md`. Checks: targeted docs/private-beta contract tests
  `UV_NO_SYNC=1 uv run pytest -q tests/test_docs_navigation_integrity.py
  tests/test_private_beta_deploy_docs.py tests/test_private_beta_hosting_docs.py
  tests/test_private_beta_smoke.py` ✅ **22 passed**, tracked secret scan ✅,
  `git diff --check` ✅. Commit local-only; push не делался.

- `2026-07-07` — **GitHub App real-read readiness on `/github`.**
  Added a display-only readiness section to `GitHubProductConnectPanel` that
  mirrors the existing offline first-real-read preflight from already-loaded UI
  state: GitHub App env configured/missing, workspace-scoped installation
  connection state, local repository surface count, blockers, and next human
  step. This makes the critical external blocker visible in the product before
  any live provider run. The real read remains the existing explicit
  per-repository GitHub App sync control after human approval; the new section
  starts no sync, provider read, provider write, secret read, external write, or
  LLM. Files: `web/components/GitHubProductConnectPanel.tsx`,
  `web/lib/messages.ts`, `web/tests/github-product-connect.test.tsx`,
  `docs/CHANGELOG.md`, `docs/TODO.md`, `PROGRESS.md`. Checks: frontend
  `npm test` ✅ **205 passed**, `npm run build` ✅, `npm run lint` ✅, backend
  `UV_NO_SYNC=1 uv run ruff check .` ✅, full backend
  `UV_NO_SYNC=1 uv run pytest -q` ✅ **455 passed / 1 warning**,
  `UV_NO_SYNC=1 uv run alembic check` ✅ (no drift), tracked secret scan ✅,
  `git diff --check` ✅. Commit local-only; push не делался.

- `2026-07-07` — **Action review readiness summary.**
  Added a founder-facing readiness section to `/actions` over the already
  loaded local `ActionProposal` list: needs-decision proposals, approved GitHub
  issue proposals ready for execution preview, local-only internal follow-ups,
  proposals missing `evidence_refs`, and proposals with reported execution
  receipts. The panel also returns a deterministic next-step hint so generated
  briefing/audit/document proposals are easier to triage before any live
  execution path. Frontend-only/local-only: no execute call, sync, provider
  call, external write, secret read, or LLM. Files:
  `web/components/ActionProposalsPanel.tsx`, `web/lib/messages.ts`,
  `web/tests/action-proposals.test.tsx`, `docs/CHANGELOG.md`, `docs/TODO.md`,
  `PROGRESS.md`. Checks: frontend `npm test` ✅ **203 passed**, `npm run build`
  ✅, `npm run lint` ✅, backend `UV_NO_SYNC=1 uv run ruff check .` ✅, full
  backend `UV_NO_SYNC=1 uv run pytest -q` ✅ **455 passed / 1 warning**,
  `UV_NO_SYNC=1 uv run alembic check` ✅ (no drift), tracked secret scan ✅,
  `git diff --check` ✅. Commit local-only; push не делался.

- `2026-07-07` — **Basic request logging (DEC-072).**
  Independent MVP-scope audit (§1.5) found "basic logging" was unimplemented:
  the app had no `getLogger`, no logging config, and no request logging — only
  domain audit rows. Added `app/core/logging.py` (`configure_logging` +
  `RequestLoggingMiddleware`) and wired it in `app/main.py`. It logs one
  sanitized line per HTTP request (method, path, status, duration_ms) at
  `FOUNDEROS_LOG_LEVEL`/`LOG_LEVEL` (default INFO), never logging query values,
  headers, cookies, bodies, tokens, or provider payloads. Local/in-process
  only: no new dependency, table, migration, provider call, external write, or
  LLM. Checks: `uv run ruff check .` ✅, focused `tests/test_basic_logging.py`
  ✅ 3 passed, full backend `uv run pytest -q` ✅ **455 passed / 1 warning**,
  `uv run alembic check` ✅ (no drift), tracked secret scan ✅,
  `git diff --check` ✅. Commit local-only; push не делался.

- `2026-07-07` — **Normalized entities type focus filter (DEC-071 polish).**
  Added a client-side `entity_type` focus filter to `NormalizedEntitiesPanel` so
  the dedicated `/company-brain` view can scale beyond a flat all-entities list.
  Founder can switch between all entities and each projected type using the
  already-loaded local response; no backend call, provider call, sync, external
  write, secret read, or LLM is started. Checks: focused frontend
  test/typecheck (`npm test -- --test-name-pattern=normalized entities`) ✅ 201
  passed, `uv run ruff check .` ✅, focused entities API tests ✅ 3 passed, full
  backend `uv run pytest -q` ✅ **452 passed / 1 warning**, `uv run alembic
  check` ✅ (no drift), tracked secret scan ✅, `git diff --check` ✅,
  frontend `npm test` ✅ **201 passed**, `npm run build` ✅ (`/company-brain`
  route present), `npm run lint` ✅. Commit local-only; push не делался.

- `2026-07-07` — **Dedicated Company Brain view (DEC-071).**
  Independent MVP-flow audit (§1.4 "See Company Brain entities" / §1.5
  "Company Brain view") found Company Brain + normalized entities existed only
  as dashboard panels with no navigable route. Added a first-class
  `/company-brain` page + sidebar entry that composes the existing read-only
  `CompanyBrainPanel` and `NormalizedEntitiesPanel` with a manual refresh; no
  new data path. `Sidebar` now exports `NAV_LINKS` for nav unit tests.
  Read-only/local-only: no provider calls, sync, external writes, secret
  reads, or LLM. Checks: frontend `npm test` ✅ **200 passed**, `npm run build`
  ✅ (`/company-brain` route present), `npm run lint` ✅, `uv run ruff check .`
  ✅, full backend `uv run pytest -q` ✅ **452 passed / 1 warning**, tracked
  secret scan ✅, `git diff --check` ✅. Commit local-only; push не делался.

- `2026-07-07` — **Normalized entities dashboard surface (DEC-070).**
  Added frontend access to the normalized-entities projection: new
  `NormalizedEntitiesPanel`, API helper/types for
  `GET /api/v1/workspaces/{workspace_id}/company-brain/entities`, dashboard
  wiring, copy, and frontend tests. The dashboard now shows normalized entity
  summary cards, type/provider breakdowns, entity cards, source refs, evidence,
  and explicit read-only/no-provider/no-LLM boundary copy. This makes the MVP
  "See Company Brain entities" path reachable from the UI, not only the API.
  Checks: focused frontend test/typecheck ✅ (current harness ran **198
  passed**), `uv run ruff check .` ✅, focused entities API tests ✅ 3 passed,
  full backend `uv run pytest -q` ✅ **452 passed / 1 warning**,
  `uv run alembic check` ✅ (no drift), tracked secret scan ✅,
  `git diff --check` ✅, frontend `npm test` ✅ **198 passed**,
  `npm run build` ✅, `npm run lint` ✅. Commit local-only; push не делался.

- `2026-07-07` — **Normalized entities read projection (DEC-070).**
  Independent MVP-scope audit (§1.5) found "normalized entities" was the last
  locally-buildable must-have surface with no API. Added a deterministic
  read-only projection: `app/services/company_brain_entities_read_service.py`
  plus `GET /api/v1/workspaces/{workspace_id}/company-brain/entities`, which
  flattens canonical Company Brain rows (repositories, issues, pull requests,
  Gmail messages, Drive files, internal documents) into one evidence-backed
  `entities` list + by-type/by-provider summary. No new table/migration (avoids
  the open ASK-1 `Person` design), no provider calls, sync, external writes,
  secret reads, or LLM; this satisfies the DEC-028 trigger to build the
  canonical `/brain/entities` API. Checks: focused
  `tests/test_company_brain_entities_api.py` ✅ 3 passed and scoped ruff ✅;
  full gates: `uv run ruff check .` ✅, full backend `uv run pytest -q` ✅
  **452 passed / 1 warning**, `uv run alembic upgrade head` + `uv run alembic
  check` ✅ (no drift, no new migration), tracked secret scan ✅,
  `git diff --check` ✅. Backend-only change (no frontend files touched). Commit
  local-only; push не делался.

- `2026-07-07` — **Internal document context → local ActionProposals (DEC-069).**
  Extended persisted Founder Briefing action generation so
  `internal-document-context` joins the existing Jira/Gmail/Drive actionable
  briefing items. The existing local-only endpoint
  `POST /api/v1/workspaces/{workspace_id}/briefings/{briefing_id}/action-proposals`
  can now create an evidence-backed `internal_todo` ActionProposal from
  persisted internal-document context, while missing evidence and existing open
  actions for the same `briefing_id + briefing_item_key` are still skipped.
  This closes the local document→briefing→action-review loop without provider
  calls, sync, external writes, raw document body copying, secret reads, or LLM.
  Checks: focused action-generation test ✅, focused briefing suite
  `tests/test_founder_briefing_api.py` ✅ 26 passed, full backend
  `uv run pytest -q` ✅ **449 passed / 1 warning**, `uv run ruff check .` ✅,
  `uv run alembic upgrade head` + `uv run alembic check` ✅ (no drift),
  frontend `npm test` ✅ **194 passed**, `npm run build` ✅, `npm run lint` ✅,
  tracked secret scan ✅, `git diff --check` ✅. Commit local-only; push не
  делался.

- `2026-07-07` — **Documents in-product edit/delete wiring (DEC-066/DEC-068).**
  Independent completion audit against playbook §1.5 ("internal documents")
  found a real end-to-end gap: `updateDocument`/`deleteDocument` API clients and
  backend `PATCH`/`DELETE` routes existed, but `/documents` UI had no edit or
  delete affordance, so document CRUD was not reachable in-product and
  DocumentVersion history could never exceed version 1 through the UI. Wired an
  inline edit form (title/body/tags/status) and a guarded delete into the
  `/documents` detail view over the existing routes; a successful edit refreshes
  the document and its version history. Frontend-only; no provider calls,
  external writes, secret reads, migrations, or LLM. Checks: `npm test` ✅ 194
  passed (4 new), `npm run build` ✅, `npm run lint` ✅, `uv run ruff check .`
  ✅, focused `tests/test_documents_api.py` ✅ 10 passed, tracked secret scan ✅,
  `git diff --check` ✅. Commit local-only; push не делался.

- `2026-07-07` — **Documents version snapshot UI polish (DEC-068).**
  `/documents` detail now turns compact version history into selectable local
  snapshots: each version row can be selected, and the detail pane renders that
  version's markdown body, status, tags, and recorded timestamp. This is
  frontend-only over the existing read-only versions API; no provider calls,
  external writes, secret reads, migrations, or LLM were added. Checks: `npm
  test -- --test-name-pattern=document` ✅ (current harness ran 190 tests, all
  passed), full backend `uv run pytest -q` ✅ **449 passed / 1 warning**,
  `uv run ruff check .` ✅, `uv run alembic upgrade head` + `uv run alembic
  check` ✅, frontend `npm test` ✅ **190 passed**, `npm run build` ✅,
  `npm run lint` ✅, tracked secret scan ✅, `git diff --check` ✅. Commit
  local-only; push не делался.

- `2026-07-07` — **DocumentVersion no-op PATCH hardening (DEC-068).**
  Hardened the version-history semantics after the initial DEC-068 slice: empty
  or idempotent PATCH requests now remain successful no-ops and do not append
  duplicate `DocumentVersion` revisions or rewrite update metadata. Effective
  updates still append the next immutable version. Docs were reconciled to make
  the no-op behavior explicit. Local-only: no provider calls, external writes,
  secret reads, or LLM. Checks: focused backend `tests/test_documents_api.py` ✅
  10 passed; full backend `uv run pytest -q` ✅ **449 passed / 1 warning**;
  `uv run ruff check .` ✅; `uv run alembic upgrade head` +
  `uv run alembic check` ✅ (single head `f2b3c4d5e6f7`, no drift); frontend
  `npm test` ✅ **190 passed**, `npm run build` ✅, `npm run lint` ✅; tracked
  secret scan ✅; `git diff --check` ✅. Commit local-only; push не делался.

- `2026-07-07` — **Internal DocumentVersion history (DEC-068).**
  Continued the Documents module after DEC-066/067: added immutable local
  `DocumentVersion` snapshots with migration `f2b3c4d5e6f7`; create writes v1,
  every successful update appends the next version. Added read-only
  `/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions` and a
  compact version list in `/documents` detail. Viewer can read history; writes
  stay member-gated. Local-only: no provider calls, external writes, secret
  reads, or LLM. Checks: focused backend `tests/test_documents_api.py` ✅
  9 passed; full backend `uv run pytest -q` ✅ **448 passed / 1 warning**;
  `uv run ruff check .` ✅; `uv run alembic upgrade head` + `uv run alembic
  check` ✅ (single head `f2b3c4d5e6f7`, no drift); frontend `npm test` ✅
  **190 passed**, `npm run build` ✅ (`/documents` present), tracked secret scan
  ✅. Commit local-only; push не делался.

- `2026-07-06` — **Founder Briefing internal document context (DEC-067).**
  Continued after the internal Documents module: Company Brain already exposed
  `documents.notes`, but deterministic Founder Briefing did not yet consume that
  context. Added `internal-document-context` briefing item from Company Brain
  document notes with internal-document evidence refs, bounded title/status/tag
  metadata, and no raw `body_markdown`/body text copying. This closes the local
  §4.7 loop "Briefing can use document as context" without LLM/provider calls/
  sync/external writes/secret reads. Checks: focused briefing API **26 passed**,
  full backend `uv run pytest -q` **447 passed / 1 warning**, `uv run ruff check
  .` green, `uv run alembic check` no drift, frontend `npm test` **189 passed**,
  `npm run build` green (`/documents` still present), tracked secret scan green.
  Commit local-only; push не делался.

- `2026-07-06` — **Internal Documents module (FOS-DOC-01 / DEC-066).**
  Independently re-derived the MVP scope and found that internal documents were
  the one §1.5 "must have" connector/module with no model, endpoint, or UI (every
  other connector was done). Implemented the full vertical: `Document` model +
  migration `f1a2b3c4d5e6`, member-gated CRUD + search service/API, deterministic
  `markdown_to_text` projection, Company Brain `documents.notes` integration with
  evidence, and a `/documents` frontend page + sidebar entry. Company Brain
  `documents` block is additive (`files` + new `notes`), so existing consumers
  keep working. Local-only: no provider calls, external writes, secret reads, or
  LLM. Verified independently: `uv run ruff check .` ✅, full backend
  `uv run pytest -q` ✅ **446 passed / 1 warning** (added
  `tests/test_documents_api.py` 8 tests; updated one Company Brain empty-state
  assertion for the additive `notes` field), `uv run alembic upgrade head` +
  `uv run alembic check` ✅ (single head `f1a2b3c4d5e6`, no drift), frontend
  `npm test` ✅ **189 passed** (+10 documents), `npm run build` ✅ (`/documents`
  route present), `npm run lint`/typecheck ✅, `check_no_secrets.sh --tracked` ✅.
  Commit local-only; push не делался.

- `2026-07-02` — **Founder Briefing history coverage comparison.** Added richer
  local history cards for persisted Founder Briefings: each saved briefing
  summary now shows coverage (repo count, open issues/PRs, evidence refs, local/
  live mode) and, when a briefing is open, item/evidence deltas against that
  open briefing. If no briefing is open, the history card shows a safe
  comparison fallback. This reads only already loaded `BriefingSummary.signals`
  from the history endpoint and starts no provider calls, external writes, or
  LLM. Changed `web/components/BriefingPanel.tsx`, `web/lib/messages.ts`,
  `web/tests/briefing.test.tsx`, docs. Checks: `npm test` **128 passed**,
  `npm run typecheck`, `npm run lint`, `npm run build`, `uv run ruff check .`,
  docs tests **16 passed**, `uv run pytest -q` **403 passed / 1 warning**,
  `git diff --check`, tracked/staged secret scans green. Commit local-only;
  push не делался.

- `2026-07-02` — **Verification + coverage: briefing category filter empty
  state.** Independently re-derived the objective requirements and audited the
  prior "briefing item focus + evidence defaults" chunk against the real
  worktree. Confirmed correctness: `categoryFilter` resets to `all` on
  generate/open so a stale category cannot hide a newly loaded briefing; default
  evidence follows the filtered items; manual selection overrides default; the
  shared `EvidenceDrawer` changes are additive/optional so `ActionProposalsPanel`
  is unaffected; no provider calls, external writes, or LLM. Found one shipped
  but untested branch — the `noItemsForFilter` empty state (category filter
  matches zero items while the briefing has items) — and added a focused test
  proving the filter-specific empty message renders, item titles are hidden, and
  the evidence drawer falls back to its safe placeholder. Changed
  `web/tests/briefing.test.tsx` only. Checks: `npm test` **127 passed**,
  `npm run typecheck`, `npm run lint`, `npm run build`, `uv run ruff check .`,
  docs tests **16 passed**, `uv run pytest -q` **403 passed / 1 warning**,
  `git diff --check`, tracked/staged secret scans green. Commit local-only;
  push не делался.

- `2026-07-02` — **Founder Briefing item focus + evidence defaults.**
  Continued the local-only Founder-facing coverage/briefing polish. Added a
  category filter to `BriefingPanel` that works only on the currently loaded
  deterministic briefing items, with counts for all categories and no provider
  calls/LLM. The briefing evidence drawer now defaults to the first evidence ref
  from the visible filtered items, shows briefing-specific default/manual
  context copy and an evidence-ref count, and still lets manual evidence
  selection override the default. Empty filter intersections show a safe
  placeholder/no-items message and no unsupported claims. Changed
  `web/components/BriefingPanel.tsx`, `web/components/EvidenceDrawer.tsx`,
  `web/lib/messages.ts`, `web/tests/briefing.test.tsx`, docs. Checks:
  `npm test` **126 passed**, `npm run typecheck`, `npm run lint`,
  `npm run build`, `uv run ruff check .`, docs tests **16 passed**,
  `uv run pytest -q` **403 passed / 1 warning**, `git diff --check`,
  tracked/staged secret scans green. Commit local-only; push не делался.

- `2026-07-02` — **Surface local decision history in the UI (verification +
  gap fix).** Independently re-derived the objective requirements and audited the
  prior "local ActionProposal review audit events" chunk against the real
  worktree. Backend event recording and receipt logic were correct
  (`_receipt_from_events` ignores the no-write decision events, so receipts stay
  `provider_result="none"`, `external_write_performed=false`). Found a real
  end-to-end scope gap: the persisted decision trail was only fetched in the UI
  via the approved-GitHub-issue execution preview, so recorded decisions were
  unreachable for rejected or internal/briefing proposals. Fix: added a
  read-only "Показать историю решений" control in `ActionExecutionControls` that
  loads the per-proposal audit trail via the existing audit endpoint for any
  proposal with a recorded decision (`approved_at` or `rejected_at`), independent
  of approvable/GitHub gating. Read-only: no provider calls, external writes, or
  LLM. Changed `web/components/ActionExecutionControls.tsx`, `web/lib/messages.ts`,
  `web/tests/action-execution.test.tsx`, `docs/CHANGELOG.md`, `docs/TODO.md`,
  `PROGRESS.md`. Checks: `npm test` **123 passed**, `npm run typecheck`,
  `npm run lint`, `npm run build`, `uv run ruff check .`, docs tests
  **16 passed**, `uv run pytest -q` **403 passed / 1 warning**, `git diff --check`,
  tracked/staged secret scans green. Commit local-only; push не делался.

- `2026-07-02` — **Local ActionProposal review audit events.** Added local
  decision audit events for successful single and bulk ActionProposal
  approve/reject transitions. Events reuse the existing append-only
  `ActionExecutionEvent` timeline with event types
  `action_proposal_approved_locally` and `action_proposal_rejected_locally`,
  actor `workspace_admin`, `status=recorded`, sanitized metadata
  (`decision`, `bulk`, `proposal_status`, `external_execution_enabled=false`),
  and message “No external write occurred.” Failed bulk items get no event
  because they do not mutate. Updated event ordering so local review decisions
  appear before execution preview/execution events; audit UI copy now says
  “Локальный аудит решений и выполнения”. No `ActionExecution` rows are
  created, provider execution is not started, external writes are not performed,
  and LLM is not used. Added backend assertions for single approve audit,
  bulk approve partial success audit, bulk reject audit, and updated execution
  audit expectations. Checks: targeted action/execution audit tests
  **63 passed**, `npm test` **119 passed**, `npm run typecheck`,
  `npm run lint`, `npm run build`, `uv run ruff check .`, docs tests
  **16 passed**, `uv run pytest -q` **403 passed / 1 warning**,
  `git diff --check`, tracked/staged secret scans green. Commit local-only;
  push не делался.

- `2026-07-02` — **Independent verification of bulk ActionProposal API chunk.**
  Re-derived requirements from objective (large local-only chunk, no external
  writes, reads allowed, docs + green gates) and audited the just-committed bulk
  review work against the real worktree instead of trusting the summary.
  Confirmed: FastAPI route ordering is correct (`/proposals/bulk-approve` and
  `/bulk-reject` are declared before the dynamic `/proposals/{proposal_id}`, so
  `bulk-*` is never parsed as a UUID); `approve_action_proposal`/
  `reject_action_proposal` raise not-found/transition errors before any DB
  mutation, so a failed item in the bulk loop never corrupts the shared session
  and the single final `commit()` persists only succeeded transitions; endpoints
  keep `is_live=false`/`execution_started=false` and never call providers/LLM;
  `summarizeBulkOutcome`→`summarizeBulkResponse` rename has no stale references;
  `mergeUpdatedProposals` (array) powers the bulk path while singular per-card
  approve/reject stay intact. Test boundary is intentional: harness uses
  `renderToStaticMarkup` with no jsdom, so container handlers are covered
  indirectly via the pure `summarizeBulkResponse`, the API client tests, and the
  backend endpoint tests; adding a stateful container test would require new
  jsdom/testing-library infra (flagged, intentionally not added to avoid scope
  creep). Independently re-ran gates: `npm test` **119 passed**,
  `npm run typecheck`, `npm run lint`, `npm run build`, `uv run ruff check .`,
  docs tests **16 passed**, `uv run pytest -q` **403 passed / 1 warning**,
  `git diff --check`, tracked/staged secret scans green; working tree clean,
  branch ahead 11, nothing pushed. No external writes performed.

- `2026-07-02` — **Bulk ActionProposal backend endpoints.** Добавлен local-only
  backend contract for bulk review:
  `POST /api/v1/workspaces/{workspace_id}/actions/proposals/bulk-approve` and
  `/bulk-reject`. Endpoints admin-only, dedupe requested proposal IDs, process
  each local transition independently, and return `proposals` successes,
  per-proposal `failures`, `succeeded_count`, `failed_count`, `is_live=false`,
  `execution_started=false`, and warnings. Web bulk controls now call these
  endpoints once per bulk action instead of orchestrating one request per card;
  `summarizeBulkResponse` preserves partial-success UI semantics. Added backend
  tests for partial approve with 409/404 failures, bulk reject with duplicate ID
  dedupe, RBAC rejection for member, plus web API client tests for paths/bodies.
  Provider execution, external writes and LLM are not started. Изменены
  `app/api/actions.py`, `tests/test_action_proposals_api.py`, `web/lib/api.ts`,
  `web/lib/types.ts`, `web/components/ActionProposalsPanel.tsx`,
  `web/tests/action-proposals.test.tsx`, `PROGRESS.md`, `docs/CHANGELOG.md`,
  `docs/TODO.md`. Checks: targeted action API tests **25 passed**, `npm test`
  **119 passed**, `npm run typecheck`, `npm run lint`, `npm run build`,
  `uv run ruff check .`, docs tests **16 passed**, `uv run pytest -q`
  **403 passed / 1 warning**, `git diff --check`, tracked/staged secret scans
  green. Commit local-only; push не делался.

- `2026-07-02` — **Bulk local review hardening (partial-failure safety).**
  Проверка предыдущего bulk-review куска выявила data-loss баг: массовое
  approve/reject использовало fail-fast `Promise.all`, и при частичном сбое
  (например, одно предложение уже переведено в другом табе → 409) catch-ветка
  сбрасывала уже применённые бэкендом локальные изменения и прятала весь список
  через `status="error"`. Исправлено: каждый approve/reject теперь settle-ится
  независимо, успешные локальные переходы всегда мержатся в state, из выбора
  снимаются только успешные (неуспешные остаются выбранными для повторной
  попытки), а частичный/полный сбой показывается inline без скрытия списка.
  Добавлен чистый экспортируемый bulk summary helper + behavioral тесты и
  inline-alert рендер-тест. Provider execution, external writes и LLM
  по-прежнему не запускаются. Изменены
  `web/components/ActionProposalsPanel.tsx`, `web/lib/messages.ts`,
  `web/tests/action-proposals.test.tsx`, `PROGRESS.md`, `docs/CHANGELOG.md`.
  Checks: `npm test` **118 passed**, `npm run typecheck`, `npm run lint`,
  `npm run build`, `uv run ruff check .`, `uv run pytest -q`, docs tests,
  `git diff --check`, tracked/staged secret scans green. Commit local-only;
  push не делался.

- `2026-07-02` — **Action review polish: bulk local review.** Добавлены
  массовые локальные действия в `ActionProposalsPanel`: выбрать все видимые
  `proposed` предложения в текущем пересечении status/origin фильтров, снять
  выбор, локально одобрить выбранные или локально отклонить выбранные. Selection
  автоматически ограничен видимыми `proposed` proposals, поэтому скрытые,
  approved/rejected карточки не мутируются случайно. Bulk approve/reject
  вызывает только существующие local ActionProposal approve/reject endpoints,
  не запускает provider execution, external writes или LLM; success copy явно
  сообщает, что внешнее выполнение не запускалось. Изменены
  `web/components/ActionProposalsPanel.tsx`, `web/lib/messages.ts`,
  `web/app/globals.css`, `web/tests/action-proposals.test.tsx`, `PROGRESS.md`,
  `docs/CHANGELOG.md`, `docs/TODO.md`. Checks: `npm test` **115 passed**,
  `npm run typecheck`, `npm run lint`, `npm run build`,
  `uv run ruff check .`, `uv run pytest -q`, docs tests, `git diff --check`,
  tracked/staged secret scans green. Commit local-only; push не делался.

- `2026-07-02` — **Action review polish: local origin filter.** Добавлен второй
  фильтр в `ActionProposalsPanel`: «Источник предложения» (все источники / из
  сводки / GitHub задачи / internal todo), который применяется поверх текущего
  status-фильтра. Counts считаются внутри выбранного status-фокуса, список и
  origin-группы показывают только пересечение фильтров, а default
  `EvidenceDrawer` берёт первый evidence ref из финальной видимой выборки.
  Это client-side local-only ergonomics поверх уже загруженного списка:
  provider calls, backend state mutations, external execution и LLM не
  запускаются. Изменены `web/components/ActionProposalsPanel.tsx`,
  `web/lib/messages.ts`, `web/tests/action-proposals.test.tsx`,
  `PROGRESS.md`, `docs/CHANGELOG.md`, `docs/TODO.md`. Checks:
  `npm test` **112 passed**, `npm run typecheck`, `npm run lint`,
  `npm run build`, `uv run ruff check .`, `uv run pytest -q`, `git diff --check`,
  and tracked/staged secret scans green. Commit local-only; push не делался.

- `2026-07-02` — **Action review polish: origin grouping + evidence drawer UX +
  briefing payload detail.** Продолжение local-only action review ergonomics.
  `ActionProposalsPanel` теперь группирует отфильтрованные proposals по
  источнику (из пунктов сводки / задачи GitHub / внутренние) с counts и
  описаниями, помечает briefing-derived proposals бейджем «Из сводки»
  (по `briefing_item_id` или payload-маркеру `source=briefing_item`), а
  evidence-по-умолчанию берётся из первого видимого proposal в порядке групп.
  `EvidenceDrawer` получил необязательные context-подсказку (default vs manual)
  и счётчик evidence refs (backward-compatible, `BriefingPanel` не менялся).
  Payload-рендерер для `internal_todo` из сводки теперь показывает ключ пункта
  сводки, категорию, важность, рекомендуемый следующий шаг и связанные сущности;
  raw payload dumps и secret-like ключи не выводятся. Всё local-only: без
  provider calls, external writes и LLM. Изменены `web/lib/messages.ts`,
  `web/components/EvidenceDrawer.tsx`, `web/components/ActionProposalsPanel.tsx`,
  `web/app/globals.css`, `web/tests/action-proposals.test.tsx`. Checks:
  `npm test` **109 passed**, `npm run typecheck`, `npm run lint`,
  `npm run build`, `uv run ruff check .`, и `uv run pytest -q` зелёные.
  Push не делался (branch ahead; внешние записи запрещены текущим objective).

- `2026-07-01` — **Local admin provisioning script import fix.**
  Fixed `scripts/create_admin_user.py` direct execution from repo root by adding
  the same project-root `sys.path` bootstrap pattern used by `start_local.py`.
  This resolves `ModuleNotFoundError: No module named 'app'` when running
  `uv run python scripts/create_admin_user.py` to set/reset the founder login.
  Added regression coverage in `tests/test_auth_provision.py`. Checks:
  `uv run ruff check scripts/create_admin_user.py tests/test_auth_provision.py`
  and `uv run pytest -q tests/test_auth_provision.py` **4 passed**. No password,
  secrets, raw storage, provider calls, deploys, or push.

- `2026-07-01` — **Per-repository GitHub App sync buttons in UI.**
  По подтверждённому плану refinеd `/github`: теперь UI выводит каждый known
  repository из repository surface отдельной карточкой/строкой с соседней
  кнопкой `Синхронизировать read-only`. Каждая кнопка вызывает existing GitHub
  App polling endpoint for exactly that one repo and keeps independent per-repo
  `syncing/success/error` state. No bulk sync control, no browser secrets, no
  provider writes. Frontend API/types/tests updated; docs updated (CHANGELOG,
  TODO, ROADMAP, README, master playbook, PROGRESS). Проверки: frontend
  `npm test` **98 passed**, `npm run build`, `npm run typecheck`, `npm run lint`
  — зелёные; docs contracts **16 passed**, `git diff --check`, tracked secret
  scan — зелёные. No real provider calls, deploys, production DB/cloud writes,
  raw storage/Obsidian edits, or push.

- `2026-07-01` — **GitHub App live-read error/rate-limit observability.**
  Added shared safe GitHub provider error formatting for repository/issue/PR
  read clients. Live read sync now propagates sanitized provider read details to
  API `502` errors: HTTP status, bounded GitHub message, and safe rate-limit
  headers (`retry-after`, `x-ratelimit-*`) when present. Tests prove rate-limit
  metadata surfaces while authorization headers/JIT tokens/provider payload dumps
  do not leak, and provider read failures stop before canonical persistence.
  Docs updated (TODO, ROADMAP, CHANGELOG, README, master playbook, PROGRESS).
  Проверки: provider error + app live sync tests **10 passed**, full backend
  `pytest` **394 passed / 1 warning**, `uv run ruff check .`, `alembic
  heads/current/upgrade/check` — зелёные. No real provider calls, deploys,
  production DB/cloud writes, raw storage/Obsidian edits, or push.

- `2026-07-01` — **GitHub App synced evidence isolation verification.**
  Добавлен backend test over mocked GitHub App live sync proving synced canonical
  data feeds Company Brain and persisted deterministic Briefings with evidence,
  while workspace B cannot see workspace A's synced canonical state/evidence and
  wrong-owner workspace access returns 404. Test also verifies no JIT
  installation token leakage in brain/briefing payloads. Docs updated
  (TODO, ROADMAP, CHANGELOG, README, master playbook, PROGRESS). Проверки:
  focused `tests/test_github_app_live_sync.py` **7 passed**, full backend
  `pytest` **391 passed / 1 warning**, `uv run ruff check .`, `alembic
  heads/current/upgrade/check`, docs contracts **16 passed**, `git diff --check`,
  tracked secret scan — зелёные. No real provider calls, deploys, production
  DB/cloud writes, raw storage/Obsidian edits, or push.

- `2026-07-01` — **GitHub App live sync explicit repo UI.**
  Productized the backend polling-only live read-sync foundation on `/github`:
  typed frontend API for
  `POST .../github/connections/app-installation/sync`, explicit owner/repo input
  (prefilled from repository surface when available), read-only sync action,
  invalid-repo/missing-app/error/success states, synced counts, and visible
  no-write/no-token-persistence copy. No browser secrets/operator key/PAT. Tests
  added for endpoint URL/body, render states, result/warning rendering, and
  no-write boundary. Docs updated (TODO, ROADMAP, CHANGELOG, README, master
  playbook, PROGRESS). Проверки: frontend `npm test` **98 passed**, `npm run
  build`, `npm run typecheck`, `npm run lint`, docs contracts **16 passed**,
  `git diff --check`, tracked secret scan — зелёные. Backend code not changed in
  this UI chunk after previous backend **390 passed**. No real provider calls,
  deploys, production DB/cloud writes, raw storage/Obsidian edits, or push.

- `2026-07-01` — **GitHub App polling-only live read sync backend foundation.**
  Продолжили по плану после GitHub App product-connect foundation. Добавлен
  DEC-053: v0 live read sync is polling-only/admin-triggered/explicit repo
  scoped; webhooks deferred until raw-body signature verification + delivery
  dedupe. Backend: новый `github_app_token_service` builds GitHub App JWT and
  mints short-lived installation tokens just-in-time; `github_repository_client`
  reads installation repositories; `github_app_live_sync_service` validates
  workspace-scoped app-installation connection, requires explicit repositories,
  reads installation repos/issues/PRs, creates manual SyncJob, and persists via
  existing idempotent `normalize_github_sync_job_local`; new endpoint
  `POST .../github/connections/app-installation/sync`. Tests mock all provider
  calls and prove token not persisted, no provider writes, workspace isolation
  before provider read, member/viewer RBAC, repo-not-installed rejection, invalid
  state rejection, and JWT shape without private-key leakage. Docs updated
  (DECISIONS, TODO, ROADMAP, CHANGELOG, README, master playbook, PROGRESS).
  Проверки: focused **46 passed / 1 warning**, full backend `pytest`
  **390 passed / 1 warning**, `uv run ruff check .`, `alembic
  heads/current/upgrade/check` — зелёные. Frontend not touched. No real provider
  calls, deploys, production DB/cloud writes, raw storage/Obsidian edits, or
  push.

- `2026-07-01` — **GitHub App foundation independent verification + test hardening.**
  Независимо перепроверен предыдущий foundation commit (`31566e9`) на ветке
  `feat/github-app-connect-foundation`: backend/frontend gates подтверждены
  зелёными до изменений (**380 / 95**). Найдены и закрыты три реальных test-gap
  на новом admin-gated endpoint `POST .../github/connections/app-installation`
  (сравнение с sibling `provider-token` контрактом): member/viewer RBAC → 403
  `insufficient workspace role`; идемпотентный update того же installation
  in place (одна строка, обновлённые metadata); невалидный
  `repository_selection` → 400. Только тесты, без изменения продакшн-поведения.
  Проверки: `uv run ruff check .` (тест-файл), full backend `pytest`
  **384 passed / 1 warning**, `git diff --check` — зелёные. No provider calls,
  deploys, production writes, or push.

- `2026-07-01` — **GitHub App product-connect foundation.**
  Создана branch `feat/github-app-connect-foundation` от local `main`
  (содержит предыдущий local GitHub repository-surface commit). Добавлен DEC-052:
  product connect uses GitHub App installation, not browser PAT/OAuth; GitHub
  App private key/webhook secret are backend-only; short-lived installation
  tokens are minted just-in-time and not persisted. Backend: new
  `FOUNDEROS_GITHUB_APP_*` config/status contract; redacted
  `/github/connection-status` app block; admin endpoint
  `POST .../github/connections/app-installation` records/updates a
  workspace-scoped installation connection without provider calls, SyncJob
  execution, persisted tokens, or external writes; service rejects binding the
  same installation to another workspace. Frontend: `/github` renders GitHub App
  readiness, local repository-surface count, token persistence boundary, and
  writes disabled via a new product-connect panel. Env templates/runbooks,
  TODO/ROADMAP/CHANGELOG/PROGRESS/master playbook updated. Checks:
  `uv run ruff check .`, `uv run alembic heads/current/upgrade/check`, full
  backend `pytest` **380 passed / 1 warning**, frontend `npm test` **95 passed**
  + build + typecheck + lint, `git diff --check`, and tracked secret scan —
  зелёные. No provider calls, deploys, production DB/cloud writes, raw
  storage/Obsidian edits, or push.

- `2026-06-30` — **GitHub local repository surface prep.**
  Подготовлен offline/local GitHub repository surface из `.local/repos.json`: 25
  repo records (owner `qtwin-io`, mostly private) без provider calls. Repo audit
  и repository inventory теперь принимают `.local/repos.json` как fallback
  discovery snapshot when canonical `.local/discovery/github/<snapshot>/raw/repos.json`
  absent. Добавлен `scripts/prepare_github_local_snapshot.py`: normalizes owner
  string → `owner.login`, adds `visibility`, refuses sensitive-looking keys,
  writes canonical discovery snapshot and safe `.local/github-repositories.env`
  allowlist snippet. Локально создан ignored snapshot
  `.local/discovery/github/local-repos-current/raw/repos.json` + ignored
  `.local/github-repositories.env`. Обновлены DEC-051, README, TODO/ROADMAP,
  CHANGELOG, PROGRESS. Проверки: focused tests **17 passed**, full backend
  **375 passed / 1 warning**, `ruff`, `alembic heads/current/upgrade/check`,
  tracked secret scan, frontend `npm test` **90 passed** + build + typecheck +
  lint — зелёные. No provider calls, deploys, production DB/cloud
  writes, raw storage/Obsidian or secrets edits.

- `2026-06-30` — **Repository identity guard before GitHub live sync.**
  Рабочая ветка `fix/repository-identity-guard`. Закрыт near-term blocker перед
  GitHub product connect/live sync: в `repositories` добавлен DB-level unique
  guard `uq_repositories_workspace_provider_full_name` (`workspace_id, provider,
  full_name`) миграцией `e8f9a0b1c2d3` (новый single head). Миграция
  детерминированно дедупит существующие duplicate rows по full_name, re-points
  `pull_requests.repository_id` на keeper и удаляет loser rows. `_upsert_repository`
  переведён на race-safe `ON CONFLICT DO NOTHING` + select/update by either
  identity; work-item paths no longer downgrade stable GitHub numeric ids back to
  full_name. Добавлены concurrent cross-path, stable-id preservation,
  workspace-isolation and schema-constraint tests. Обновлены DEC-050,
  `docs/TODO.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`, `PROGRESS.md`.
  Проверки: focused sync/model tests **19 passed**, full backend **371 passed / 1
  warning**, `ruff`, `alembic heads/current/upgrade/check`, tracked secret scan,
  frontend `npm test` **90 passed** + build + typecheck + lint — зелёные. No push,
  provider calls, deploys, production DB/cloud writes, raw storage/Obsidian or
  secrets edits.

- `2026-06-30` — **Project actualization / continuation checkpoint.**
  Сверены required docs (`docs/README.md`, `AGENTS.md`, `CLAUDE.md`), live
  status, near-term backlog, git state and targeted repository/GitHub sync debt.
  Remote checked with `git fetch origin`: `main` чистый, локальная ветка
  **ahead `origin/main`** (`origin/main` на `016c7e7`), push не делался. Текущий следующий
  инженерный шаг не меняется: перед GitHub product connect/live sync закрыть
  Repository identity/race debt — DB-level guard for workspace-scoped GitHub
  repository `full_name`/identity, then continue GitHub App/product connect
  design. Проверки actualized: `uv run ruff check .`, `uv run alembic heads`,
  `uv run alembic current`, `uv run alembic upgrade head`, `uv run alembic
  check`, `uv run pytest -q` (**368 passed / 1 warning**), tracked secret scan,
  frontend `npm test` (**90 passed**) + build + typecheck + lint — зелёные. No
  provider calls, deploys, production DB/cloud writes, raw storage/Obsidian or
  secrets edits.

- `2026-06-29` — **Project-wide audit / cleanup / docs refresh.**
  Проведена полная инвентаризация tracked/untracked структуры без чтения
  секретов. Удалены 3 obsolete grouped-lifecycle operator scripts
  (`doctor_no_marker_grouped_lifecycle_review.py`,
  `manual_no_marker_grouped_lifecycle_review.py`,
  `manual_no_marker_grouped_lifecycle_review_sweep.py`): они не имели ссылок из
  активного пути и не импортировались из-за уже удалённого report-модуля.
  `docs/TODO.md` сжат из completed-work ledger в near-term backlog; active docs
  обновлены под persisted Briefings и следующий шаг GitHub product connect/live
  sync перед LLM-нарративом. Добавлены doc-maintenance правила в
  `docs/README.md`/`AGENTS.md`, Make check targets, расширен `.gitignore`,
  убран неиспользуемый `session_cookie_secure` config field, а secret scan
  теперь тихо пропускает deleted-but-not-yet-staged files. Проверки: `uv sync
  --frozen`, `ruff`, `alembic upgrade head`, `alembic check`, full pytest
  **368 passed / 1 warning**, frontend `npm test` **90 passed** + build +
  typecheck + lint, docs contract tests **22 passed**, tracked secret scan,
  markdown link sanity, `git diff --check` — зелёные. No push, deploy, provider
  calls, production DB/cloud writes, raw storage/Obsidian/secrets edits.

- `2026-06-29` — **Briefings Chunk 1: персистентные сводки (бэкенд+фронтенд).**
  Ручная Founder-сводка теперь сохраняется. Генерация
  (`founder_briefing_service`) не менялась и без LLM — сохраняется только вывод.
  Бэкенд: новые модели `Briefing`/`BriefingItem` (`app/db/briefing_models.py`),
  миграция `e7f8a9b0c1d2` (новый head; workspace-scoped, `ON DELETE CASCADE`,
  `position`-порядок, форма элементов = форма генератора),
  `briefing_persistence_service`, `POST .../briefings/manual` сохраняет и
  возвращает сводку с `id` (`persistence:"persisted"`), история
  `GET .../briefings` (новые сверху) + `GET .../briefings/{id}` (workspace-scoped,
  чужой → 404). Обновлены transient-ассерты в briefing/e2e/selected-sync тестах.
  Гейты: `pytest 368 passed`, `ruff` чисто, `alembic upgrade head`/`current`/`check`
  зелёные. Фронтенд: api `listBriefings`/`getBriefing`, `BriefingPanel` грузит
  историю, показывает сохранённую сводку и переоткрывает прошлые; русские строки
  в `web/lib/messages.ts`; `npm test` 90, build/lint/typecheck зелёные. Два
  отдельных коммита (бэкенд, фронтенд), затем docs. Без LLM, без GitHub
  OAuth/connect; workspace-изоляция проверена тестом. Решение — DEC-048.
- `2026-06-28` — **Docs reconciliation (docs-only).** Сверил канонические доки с
  реальным кодом/git после auth-фазы: 18 локальных коммитов поверх `82fb52f`
  (последний в `origin/main`) не были отражены в трекинг-доках, т.к. промпты
  фазы запрещали трогать доки. Обновлены `PROGRESS.md`, `docs/TODO.md`,
  `docs/DECISIONS.md` (DEC-041…DEC-047), `docs/ROADMAP.md`, `docs/CHANGELOG.md`,
  `founderOS_MASTER_PLAYBOOK.md` (status-блок), `README.md`, `.env.example`
  (+`FOUNDEROS_API_PROXY_TARGET`), `SECURITY_BASELINE.md`. Никакого кода:
  `app/` / `web/` / `migrations/` не тронуты; факты проверены по коду
  (эндпоинты, таблицы, миграции, env-переменные) и git-истории, ничего не
  выдумано. Тесты в этом проходе заново не прогонялись. Стейл-claim, который
  чинили: ROADMAP «Missing: Login page» и «Missing: Production auth/session
  decision» — логин/сессии теперь построены.
- `2026-06-28` — **Auth-фаза + русский UI (feat(auth)/feat(web)).** Реализован
  продуктовый логин email+password на серверных сессиях: `password_service`
  (Argon2id), `session_service` + таблица `sessions` (в БД только sha256-хэш
  токена), эндпоинты `/api/v1/auth/login|logout|me|change-password`,
  `require_session` + `get_current_actor` (сессия-ИЛИ-операторский ключ),
  DB-throttle логина (`login_attempts`, по умолчанию 5/15 мин), same-origin
  Next.js-прокси для first-party cookie (`FOUNDEROS_API_PROXY_TARGET`).
  Фронтенд переведён с operator-key/owner-email на сессию (`web/lib/config.ts`
  удалён, workspace из сессии), Settings → аккаунт/смена пароля, админ —
  `scripts/create_admin_user.py` (идемпотентно). Вся UI-копия вынесена в
  `web/lib/messages.ts` (русский, без i18n-фреймворка). Один основатель сейчас,
  архитектура многопользовательская. Решения зафиксированы в DEC-041…DEC-047.
- `2026-06-28` — **Sync-layer hardening (FOS-027B2 + далее).** Канонические
  `tasks` получили partial unique index
  `uq_tasks_workspace_provider_external_id` + дедуп-миграцию `f7b8c9d0e1a2`;
  upsert issue→`Task` стал идемпотентным `ON CONFLICT`, как и
  `PullRequest`/`SourceRecord`/`Repository`. Дрейф `ingested_events` сведён
  миграцией `a8c9d0e1f2b3` (индексы/ограничения, без данных). `Task.updated_at`
  задокументирован как «последняя синхронизация». Шифрование секретов
  fail-closed вне local (`FOUNDEROS_SECRET_ENCRYPTION_KEY`). Health разделён на
  публичный liveness и операторский `/health/detail`. Один alembic head —
  `c0e1f2a3b4d5`.
- `2026-06-27` — **FOS-027B1 private-beta blocker hardening pass 1.** Made API
  auth fail-closed outside local: `enforce_fail_closed_auth` (FastAPI lifespan)
  aborts startup when a non-local `APP_ENV` runs with auth disabled or without a
  configured key; the `api_auth_enabled=false` default is kept for local dev.
  Added a shared frontend `safeHref` helper + `SourceLink` component so
  untrusted server-provided URLs (evidence/source URLs, `external_result_url`)
  are clickable only for http(s); `javascript:`/`data:`/`vbscript:`/malformed
  render as non-clickable text. Removed stale `app/agents` bytecode and
  reconciled CLAUDE.md / SECURITY_BASELINE.md / README.md references to deleted
  LLM/agent code and a deleted boundary doc. Checks: backend `pytest`/`ruff`
  green, frontend `npm test` (86) / build / typecheck / lint green. No deploy,
  no push, no Railway change, no provider writes; secrets not printed.

- `2026-06-27` — **FOS-026C private-beta workspace context + full read-only deployed smoke.**
  Bootstrapped the minimal private-beta workspace/owner context in the deployed
  Railway database through the supported operator workspace bootstrap API. Full
  read-only deployed smoke passed across health/auth, workspace read, GitHub
  connection status read, Company Brain read, operational work read, and
  deterministic transient briefing generation. Provider writes, selected repo
  live sync, ActionProposal execute, LLM, and real connectors remained disabled
  or uncalled. Secret values and operational IDs are intentionally omitted.
- `2026-06-27` — **FOS-026B authenticated Railway private-beta setup/rehearsal.**
  Created the Railway rehearsal project with backend, frontend, and managed
  Postgres services; Redis was skipped. Configured backend/frontend env through
  Railway only, with provider writes, LLM, and real connectors disabled. Current
  Railway Railpack required `RAILPACK_BUILD_CMD`/`RAILPACK_START_CMD`, and the
  backend `DATABASE_URL` needed the `postgresql+asyncpg` driver form. Alembic
  migrated Railway Postgres to head. Backend health, frontend load, CORS
  preflight, and API auth behavior were verified. Read-only deployed smoke passed
  in health/auth-only mode; workspace-scoped smoke is blocked until a
  private-beta workspace/owner context is approved. Secret values, DB URLs, API
  keys, Railway IDs, and provider payloads are intentionally omitted. No push,
  GitHub provider write, selected repo live sync, ActionProposal execute, OpenAI
  call, or custom domain setup occurred.

- `2026-06-26` — **FOS-025E Railway private-beta hosting dry-run plan.**
  Added `docs/deploy/railway-private-beta.md` plus placeholder-only backend,
  frontend, and smoke env templates under `docs/deploy/templates/`. The plan
  selects the Railway-only split-service target implied by the master playbook,
  mapping backend API, frontend web, managed Postgres, managed/deferred Redis,
  domain/CORS/API-base, env names, migration, smoke, rollback, and operator
  checklist steps without provisioning anything. Added hosting-doc tests for
  required sections, commands, env names, placeholder-only templates, no
  secret-shaped values, no auto-deploy workflows, and no provider-write/sync
  commands. No deploy, provisioning, external writes, provider calls, GitHub
  issue/PR changes, or push were performed.

- `2026-06-26` — **FOS-025D private-beta deploy runbook/config path.**
  Added `docs/deploy/private-beta.md` and linked it from README/docs/web docs.
  The runbook chooses a manual split deployment baseline (backend API process,
  frontend web process, managed Postgres, managed/deferred Redis), documents
  backend/frontend install/build/start commands, migration head/current
  verification, database backup and restore-as-rollback policy, exact env names,
  CORS/API-base setup, GitHub connection boundaries, and read-only post-deploy
  `make smoke`. Added deploy-doc safety tests that verify required env names,
  smoke/read-only boundaries, no secret-shaped values, and no auto-deploy
  workflow. No deploy, external writes, provider calls, GitHub issue/PR changes,
  or push were performed.

- `2026-06-26` — **FOS-025C frontend/full-stack deploy-readiness CI gates.**
  Extended `.github/workflows/ci.yml` into separate backend and frontend jobs.
  Backend CI keeps the secret scan, `uv sync --frozen`, ruff, Alembic upgrade,
  and full pytest, plus explicit docs/smoke/CORS/CI contract tests. Frontend CI
  runs `npm ci`, `npm test`, `npm run build`, `npm run typecheck`, and
  `npm run lint` from `web/` using pinned actions and no provider secrets. Added
  CI deploy-readiness contract tests proving frontend gates exist and forbidden
  execute/selected-sync/live-smoke/provider-secret strings are absent. No deploy,
  external writes, GitHub issue/PR changes, or push were performed.

- `2026-06-26` — **FOS-025B private-beta deploy/smoke foundation.** Added
  explicit backend CORS settings with local-safe defaults, a read-only
  private-beta smoke script, `make smoke`, placeholder-only `.env.example`,
  local full-stack/private-beta docs, and smoke/config/docs tests. The smoke
  policy forbids ActionProposal execute, selected repository sync, provider-token
  setup, local-sync, normalize-local, post-execution-result sync, provider write
  endpoints, raw response dumps, and secret/env value printing. No deploy, no
  external writes, no GitHub issue/PR changes, and no push were performed.

- `2026-06-26` — **FOS-024 selected repository sync UI controls.** Exposed the
  existing read-only selected repository issue and PR sync backends in the
  product frontend. Added typed API helpers (`syncSelectedRepositoryIssues`,
  `syncSelectedRepositoryPullRequests`, optional combined
  `syncSelectedRepositoryGitHubWork`) plus request/response types, and a new
  `SelectedRepositorySyncControls` dashboard panel near the existing GitHub
  sync/Company Brain/operational-work panels. The panel discovers the GitHub
  `connection_id` from the existing connection-status endpoint (never
  hardcoded), validates explicit `owner/repo` input client-side (non-empty, one
  slash, no spaces), syncs one explicit allowlisted repository at a time, and
  never offers "sync all org repos". It covers missing-settings,
  missing-connection, invalid-input, per-action loading (issues / PRs / both),
  success summaries (repositories synced; issues synced/open/closed; PRs
  synced/open/closed/merged; skipped PR-shaped issue records), allowlist
  (`Repository is not allowlisted for selected sync.`), permission, generic
  error, and empty/no-records states. The UI states read-only / no external
  writes, renders no raw JSON or private IDs/secrets, and refreshes Company
  Brain plus operational work after a successful sync via the existing dashboard
  refresh counter. No backend contract change was needed. No external GitHub
  write was performed. Checks: `git diff --check` passed, selected-sync tests
  **6 passed**, GitHub normalization/inventory **23 passed**, action/execution
  regression **60 passed**, Company Brain + briefing + backend E2E **15
  passed**, docs navigation **2 passed**, full pytest **287 passed / 1
  warning**, `ruff` clean, tracked secret scan clean; frontend `npm test` **79
  passed**, `npm run build` passed, `npm run typecheck` passed, `npm run lint`
  passed. Next: multi-repo selected sync from the UI (after the human approves
  additional repositories) or production/deploy readiness.

- `2026-06-26` — **FOS-023 selected repository PR sync.** Added a
  read-only selected repository PR sync endpoint:
  `POST /api/v1/workspaces/{workspace_id}/github/repositories/pull-requests/sync`.
  The path requires an explicit read-sync allowlist (`FOS_GITHUB_SYNC_ALLOWED_REPOS`
  or existing selected GitHub repo config), validates selected repositories
  before token decrypt/provider calls, fetches GitHub pull requests read-only,
  creates a local manual SyncJob, and reuses canonical GitHub normalization to
  upsert repository `SourceRecord`/`Repository` plus PR `SourceRecord`/
  `PullRequest` rows. Selected PR sync preserves open/closed/merged state, uses
  repository+number identities for PR read-model de-dupe, keeps repository
  identity stable after selected issue sync so duplicate repository rows are not
  created, and performs no issue/PR/comment/merge/close/provider write. Verified
  with read-only provider mocks for the approved repository scope. Checks:
  focused selected PR sync tests **3 passed**, GitHub normalization/inventory/
  selected-sync tests **29 passed**, Company Brain + briefing + backend E2E
  tests **15 passed**, action/proposal tests **60 passed**, docs navigation
  **2 passed**, full pytest **287 passed / 1 warning**, `ruff` clean, tracked
  secret scan clean. Next: FOS-024 selected repository sync UI controls, or
  broader selected issue+PR sync only after the human approves additional
  repositories.

- `2026-06-26` — **FOS-022 selected repository issue sync.** Added a
  read-only selected repository issue sync endpoint:
  `POST /api/v1/workspaces/{workspace_id}/github/repositories/issues/sync`.
  The path requires an explicit read-sync allowlist (`FOS_GITHUB_SYNC_ALLOWED_REPOS`
  or existing selected GitHub repo config), validates selected repositories
  before token decrypt/provider calls, fetches GitHub issues read-only, skips
  PR-shaped issue API records, creates a local manual SyncJob, and reuses
  canonical GitHub normalization to upsert repository `SourceRecord`/`Repository`
  plus issue `SourceRecord`/`Task` rows. Product read models de-dupe GitHub
  issue rows by repository+number so alternate historical identifiers do not
  double-count a real issue. Live verification was limited to the approved
  smoke repository: one closed issue synced, open issue count stayed 0,
  operational work and Company Brain report the issue as closed, deterministic
  briefing remains evidence-backed, and ActionExecution receipt counts stayed
  unchanged. No GitHub issue/comment/PR/release/settings write occurred, and
  private issue URL plus local IDs are intentionally omitted from public docs.
  Checks: `git diff --check` passed, focused selected-sync tests **3 passed**,
  GitHub normalization/inventory/selected-sync tests **26 passed**,
  action/proposal tests **60 passed**, Company Brain + briefing + backend E2E
  tests **15 passed**, docs navigation **2 passed**, full pytest **284 passed /
  1 warning**, `ruff` clean, tracked secret scan clean. Next: FOS-023 selected
  repository PR sync, or broader selected issue sync only after the human
  approves additional repositories.

- `2026-06-26` — **FOS-021 smoke issue closeout / closed-state sync.** After explicit human approval, closed exactly the existing approved smoke issue and performed no other GitHub write. No new issue, comment, PR, release, repo setting change, label/assignee/title/body update, or additional repository modification occurred. Closed state was read back and synced through the post-execution sync path: canonical `Task.status=closed`, operational open work no longer contains the smoke issue, closed/all operational work does contain it, Company Brain reports open_issues=0 and closed_issues=1, deterministic briefing remains evidence-backed, and ActionExecution receipt count stayed single. Private issue URL and local workspace/proposal/connection/evidence/source IDs are intentionally omitted from public docs. Checks: `git diff --check` passed, action/proposal tests **60 passed**, GitHub normalization/inventory **23 passed**, Company Brain **2 passed**, briefing **12 passed**, docs navigation **2 passed**, full pytest **281 passed / 1 warning**, `ruff` clean, tracked secret scan clean. Next: FOS-022 selected repository issue sync.

- `2026-06-26` — **FOS-020 post-execution sync verification.** Added a read-only post-execution sync path for executed GitHub issue `ActionProposal` receipts: `POST /api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/sync-execution-result`. The route validates executed/succeeded receipt state, reads exactly the provider issue through the encrypted GitHub connection, writes no GitHub content, creates a local manual SyncJob, and reuses canonical GitHub normalization to upsert `SourceRecord` + `Task`. Live verification read the approved smoke issue back into canonical records; operational work and Company Brain see it, deterministic briefing reflects the normalization evidence, and execution count stayed single. Private issue URL and local workspace/proposal/connection/evidence IDs are intentionally omitted from public docs. Checks: `git diff --check` passed, targeted backend suite **98 passed**, full pytest **281 passed / 1 warning**, docs navigation **2 passed**, `ruff` clean, tracked secret scan clean. Next: explicit smoke issue closeout/cleanup approval, then broader selected-repository issue sync.

- `2026-06-26` — **FOS-019B manual live GitHub issue smoke proof.** Manual live GitHub issue smoke succeeded against an approved private smoke repository. Exactly one GitHub issue was created through the gated `ActionProposal` execution path after runtime capability, explicit confirmation, evidence, allowlist, and idempotency gates. Receipt and durable audit are stored locally (`execution_preview_generated`, `execution_confirmation_received`, `execution_started`, `execution_succeeded`). External issue URL/id and local workspace/proposal/connection/evidence IDs are intentionally omitted from public docs. No other repositories were modified and no push was performed. Next: FOS-020 post-execution sync verification.

- `2026-06-25` — **FOS-019A.2 live-write repository allowlist gate.** Added an explicit non-secret GitHub write repository allowlist (`FOS_GITHUB_WRITE_ALLOWED_REPOS`, with `FOS_GITHUB_SMOKE_REPO` as a single-repo alias) to the approved GitHub issue executor. No allowlist or a non-matching repository blocks before token decrypt/provider calls, records durable `execution_repository_not_allowed` audit, and returns a clear 409. Broad token scope and variable names such as `READONLY` are not trusted as safety boundaries. An earlier bounded setup against an approved private smoke repository target was blocked by GitHub permissions, so no local smoke candidate was prepared in that run and no live issue was created then.

- `2026-06-25` — **FOS-018 gated live GitHub issue execution path.** Hardened the existing approved GitHub issue executor behind strict gates: `enable_write_actions=true`, explicit confirmation, approved GitHub issue proposal, valid issue payload/connection, non-empty evidence refs for live execution, and no existing successful receipt. Duplicate execute returns the existing `ActionExecution` receipt and records `execution_duplicate_returned_existing_receipt` without calling the provider again. Success/failure/block paths now persist durable `ActionExecutionEvent` audit events (`execution_confirmation_received`, `execution_started`, `execution_succeeded`, `execution_failed`, `execution_blocked`) and frontend-safe receipt fields. `web/app/actions` shows live execution controls only when backend capabilities allow them, requires confirmation, and renders external issue id/url only from backend success. Automated tests mock the GitHub issue client; **no real live GitHub write smoke was run**. Checks: `git diff --check` passed, action/proposal execution backend tests **52 passed**, GitHub-first backend E2E **1 passed**, full pytest **273 passed / 1 warning**, `alembic heads/current/upgrade` passed at `a2b3c4d5e6f7`, `alembic check` expected drift only **7 operations on `ingested_events`**, `ruff` clean, `npm test` **60 passed**, `npm run build` passed, `npm run typecheck` passed, `npm run lint` passed, docs navigation **2 passed**, tracked secret scan clean.
- `2026-06-25` — **FOS-017 persistent execution audit trail.** Added proposal-scoped `action_execution_events` with sanitized metadata, deterministic idempotency keys, and indexes for workspace/proposal/created order. Preview now records/reuses `execution_preview_generated` or blocked/unsupported preview events; blocked execute records/reuses `execution_confirmation_missing` or `execution_confirmation_received_but_disabled`; neither path calls GitHub/provider. Added `GET /api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/audit` with a local execution receipt/readiness view. `web/app/actions` now renders persisted audit events, receipt status, local "audit event recorded" copy, and keeps timestamp fallback when no audit rows exist. No live provider call, OAuth, AI/LLM, `source_events` read, ActionExecution overload, legacy audit_logs overload, or raw provider payload dump was added. Checks: `git diff --check` passed, action/proposal execution backend tests **51 passed**, migration metadata tests **2 passed**, GitHub-first backend E2E **1 passed**, full pytest **272 passed / 1 warning**, `alembic heads/current/upgrade` passed at `a2b3c4d5e6f7`, `alembic check` expected drift only **7 operations on `ingested_events`**, `ruff` clean, `npm test` **59 passed**, `npm run build` passed, `npm run typecheck` passed, `npm run lint` passed, docs navigation **2 passed**, tracked secret scan clean.
- `2026-06-25` — **FOS-016 guarded execution preview/audit surface.** Added `GET /api/v1/workspaces/{workspace_id}/actions/proposals/{proposal_id}/execution-preview` for dry-run GitHub issue execution readiness over approved local `ActionProposal` records. The preview validates proposal state/action/payload, returns provider/action/repository/title/body/labels/assignees, preserves backend evidence refs, exposes capabilities, and never calls GitHub. `/execute` now rejects with `external execution is disabled` when `enable_write_actions=false`; mocked execution tests explicitly opt into write capability. `web/app/actions` and dashboard action panels now show `ActionExecutionControls` with preview-only copy, external-write disabled state, no-evidence warnings, audit/status events, and explicit connection+confirmation UI only if backend capabilities enable live writes. No live provider call, OAuth, AI/LLM, source_events UI read, or raw provider payload dump was added. Checks: `git diff --check` passed, action/proposal execution backend tests **50 passed**, full pytest **271 passed / 1 warning**, `ruff` clean, `npm test` **56 passed**, `npm run build` passed, `npm run typecheck` passed after build-generated Next types, `npm run lint` passed after build-generated Next types, docs navigation **2 passed**, tracked secret scan clean.
- `2026-06-25` — **FOS-015 local ActionProposal approval UI.** `web/app/dashboard` and `web/app/actions` now surface the existing local ActionProposal backend contracts: list/create local proposals, approve locally, reject locally, show status counts, proposal target details, audit timestamps, backend warnings, and evidence refs through `EvidenceDrawer`. Added typed frontend API helpers for `/api/v1/workspaces/{workspace_id}/actions/proposals` list/create/approve/reject. The UI intentionally does not call `/execute`, does not claim GitHub writes occurred, and does not read retained `source_events`. Checks: `git diff --check` passed, ActionProposal backend tests **22 passed**, Founder Briefing backend tests **12 passed**, Company Brain backend tests **2 passed**, GitHub normalization/inventory tests **23 passed**, docs navigation **2 passed**, `ruff` clean, tracked secret scan clean, full pytest **268 passed / 1 warning**, `npm test` **48 passed**, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed.
- `2026-06-24` — **FOS-014 briefing UI + evidence drawer.** `web/app/dashboard` and `web/app/briefings` now surface the existing deterministic manual Founder Briefing backend through `POST /api/v1/workspaces/{workspace_id}/briefings/manual`. Added typed frontend API helpers, `BriefingPanel`, and `EvidenceDrawer` for loading/missing/empty/unsupported/error/success states, returned item/signals/warnings rendering, evidence ref inspection, source links only when provided, and explicit no-live-provider/no-AI/no-action-execution copy. No backend route/schema change; retained `source_events` is not a primary UI path. Checks: `git diff --check` passed, Founder Briefing backend tests **12 passed**, Company Brain backend tests **2 passed**, GitHub normalization/inventory tests **23 passed**, docs navigation **2 passed**, `ruff` clean, tracked secret scan clean, full pytest **268 passed / 1 warning**, `npm test` **38 passed**, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed.
- `2026-06-24` — **FOS-012 Company Brain GitHub evidence state.** Added workspace-scoped `GET /api/v1/workspaces/{workspace_id}/company-brain` over canonical GitHub `Repository`/`Task`/`PullRequest` rows and `SourceRecord` source refs. It returns deterministic summary counts, repositories, open issue/task highlights, open PRs, recent work, evidence/source refs, and explicit capabilities (`local_sync=true`, live OAuth/provider sync/AI briefing false). `web/app/dashboard` now shows a Company Brain panel between local sync controls and operational work details, with loading/missing/empty/error states and evidence/source rendering. Retained `source_events` is not a primary read path. Checks: `git diff --check` passed, new Company Brain backend tests **2 passed**, GitHub normalization/inventory tests **23 passed**, docs navigation **2 passed**, `ruff` clean, tracked secret scan clean, full pytest **268 passed / 1 warning**, `npm test` **26 passed**, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed.
- `2026-06-24` — **FOS-010 product GitHub local-sync controls.** Added `POST /api/v1/workspaces/{workspace_id}/github/local-sync` as an explicit local-normalization wrapper over existing manual SyncJob + `normalize-local` behavior; it does not start live provider execution and returns compact status/counts/warnings. `web/app/dashboard` now shows connection/local-sync state, honest no-live-OAuth copy, missing/unsupported/error/success states, and refreshes the canonical operational-work panel after successful local sync. Tests added for backend route success/no-connection/idempotence/no-live path and frontend URL/action/render states. Checks: `git diff --check` passed, GitHub normalization/inventory tests **23 passed**, docs navigation **2 passed**, `ruff` clean, tracked secret scan clean, full pytest **266 passed / 1 warning**, `npm test` **17 passed**, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed.
- `2026-06-24` — **FOS-011 dashboard GitHub operational work wiring.** `web/app/dashboard` now reads `GET /api/v1/workspaces/{workspace_id}/github/operational-work` through the existing browser-local API base/key/workspace settings. Added typed frontend operational-work API helper, dashboard panel with open/all/closed/merged filters, separate issue/task and PR sections, repository labels, source links, and loading/empty/error states. Frontend tests cover URL building, response parsing, render success/empty/error/loading/filter states, and absence of old `source_events`/placeholder current truth. Checks: `npm test` 8 passed, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed, FOS-009 backend tests 20 passed, docs navigation 2 passed, `ruff` clean, tracked secret scan clean, full pytest **263 passed / 1 warning**.
- `2026-06-24` — **FOS-009 canonical GitHub issues/PRs + substrate repoint.** `normalize-local` can persist local GitHub issue records into canonical `Task` rows and PR records into canonical `PullRequest` rows linked to `Repository`, with sanitized `SourceRecord` payloads and idempotent counters. Added backend read model `GET /api/v1/workspaces/{workspace_id}/github/operational-work` for open/all/closed/merged issues+PRs. `repository_source_inventory` now prefers canonical `repositories` for workspace reads; retained `source_events` remains read-only compatibility fallback, not dropped in this feature commit. Checks: focused GitHub/inventory tests 28 passed, docs navigation 2 passed, GitHub-first backend E2E 1 passed, `ruff` clean, tracked secret scan clean, full pytest **263 passed / 1 warning**.
- `2026-06-24` — **Post-merge main order check + docs alignment.** `feat/platform-part2-computed-repo-brain` fast-forward merged into local `main` (`ef22360`); worktree clean; `main` ahead `origin/main` by 43 commits, push intentionally not done without explicit human command. Rechecked gates on `main`: docs navigation ✅, local markdown links ✅, `ruff` ✅, `pytest 259/0` ✅, web `typecheck/lint/build` ✅, `alembic head/current/upgrade` ✅, `alembic check` expected drift **7 ops on `ingested_events`**. Docs-control cleanup completed in canonical set only: PLAYBOOK(what)+PROGRESS(where)+DECISIONS(why), plus ROADMAP/TODO/POST_MVP/CHANGELOG as planning layer.
- `2026-06-24` — **Read-only чекап + doc-гигиена (новая сессия).** Ветка `feat/platform-part2` (purge влит, 40 ahead of main / 0 behind), app/ 39 модулей, `canonical_models` + `/api/v1` на месте. Гейт перепрогнан на дереве с FOS-008: alembic head чист, ruff ✅, **pytest 259/0**, drift 6 (`ingested_events`), github-first E2E зелёный → FOS-008 закоммичен (`fc6b55d`). Установлено правило гигиены доков (DEC-031); `EXECUTION_PLAN.md` свёрнут (дубль chunk-map + неиспользуемые driver-промпты, частично устарел vs DEC-028). Канон управления = PLAYBOOK(что)+PROGRESS(где)+DECISIONS(почему). Аномалий нет; substrate `source_events` удержан до FOS-009.
- `2026-06-24` — **FOS-008 canonical GitHub repository persistence.** `POST /api/v1/workspaces/{workspace_id}/github/sync-jobs/{sync_job_id}/normalize-local` сохраняет projection-only режим при `persist_if_supported=false`, а при `true` пишет GitHub repositories в canonical `SourceRecord`/`Repository` с idempotent upsert, sanitized payload, SyncJob counters/logs. `EvidenceRef`/issues/PRs не пишутся; retained substrate не тронут.
- `2026-06-24` — **FOS-PURGE-01 final purge consistency cleanup.** Удалены leftover static UI HTML artifact и dedicated static UI test; local starter теперь открывает backend root, не `/ui`. Удержанный substrate `source_events`/`normalized_activity_items`/`ingested_events` остаётся до FOS-009. Актуальный `alembic check` drift: 7 operations, all on `ingested_events`; не чинить в этой задаче. Runtime namespace остаётся `/api/v1`.
- `2026-06-24` — **Lineage-2 retired (purge, DEC-029).** Удалены entities-граф + identity-слой + knowledge-graph/RAG + digest/inbox/telegram/gmail/drive/extraction/share-packs/second-opinion/attention/jira/obsidian/source-control + legacy-коннекторы (`connectors.github`, `source_control`) + статичный `/ui` + их тесты/скрипты + non-canon доки. Дропнуто 27 таблиц (миграция `e1a2b3c4d5f6`, необратима). Удержан substrate `source_events`/`normalized_activity_items`/`ingested_events` (DEC-030, retire в FOS-009). Гейт: app boots, alembic head чист, drift now 7 operations on `ingested_events`, ruff ✅, pytest green, web build ✅, github-first E2E зелёный (спайн цел). Recovery tag `pre-purge-20260624`. Коммиты: eadd7d8 (код), 1d281e3 (таблицы), e83e5d2 (доки).
- `2026-06-24` — **FOS-002 готов (spine-subset §6, ветка A / DEC-028).** Добавлены канонические `source_records`/`evidence_refs`/`repositories`/`pull_requests`/`tasks` (`app/db/canonical_models.py`, uuid+workspace-scoped) + миграция `f6b7c8d9e0a1` + `tests/test_canonical_models.py` (9). `NormalizedEntity` отложен (решено по коду: нет GitHub-only читателя обобщённой сущности). CHUNK 1 gate зелёный: alembic upgrade head ✅, model tests ✅, encryption roundtrip ✅. pytest 1818/0, ruff ✅. `alembic check` ругается на pre-existing legacy drift (Линия 2), не на канон-таблицы. DONE 5/23, chunks 2/9.
- `2026-06-24` — **FOS-002 диагностика (read-only): две параллельные линии.** Спайн (github sync/normalize/action/briefing/brain) НЕ читает/пишет `entities`-граф и `source_events` — идёт мимо, на `integration_models`+`action_models`+проекциях. Граф+identity-слой+`source_events` нагружают ТОЛЬКО старую Graphiti/knowledge-graph генерацию + frozen founder-views/digest/inbox (DEC-026). Карта «что чем нагружено» — `docs/_audit/DOCS_AUDIT.md` → «Load-Bearing Map». Случай «две генерации» → СТОП, вопрос человеку (ветка A: §6 расширяет спайн, граф→legacy / ветка B). Схема не менялась.
- `2026-06-24` — **FOS-002 ШАГ A+B + namespace.** ШАГ A: 4 doc-contract теста починены doc-side → pytest 1809/0 (`394df7b`). Namespace `/v1`→`/api/v1` (DEC-023) выполнен: 660 замен в 65 файлах, ruff/pytest/tsc зелёные (`fix(api)` коммит). ШАГ B (shape-equivalence) gate: `source_events`/`entities` **НЕ эквивалентны** §6 по форме → СТОП перед rename, finding в DECISIONS/DOCS_AUDIT (`d757835`). Канонизация данных ждёт решения A/B (диагностика «что чем нагружено» → ветка). Код-модель пока не менялась.
- `2026-06-24` — **Audit (Prompt A) выполнен.** Сверено с реальным кодом: строго DONE 4/23 (FOS-000/001/003/008), PARTIAL 16, MISSING 3. Gate: alembic ✅, ruff ✅, frontend build ✅, pytest 1805✅/4❌ (doc-contract), GitHub-E2E ❌ (mocked/`is_live=false`), prod ❓. Дрейф зафиксирован в DECISIONS.md (DEC-023..026) и `docs/_audit/DOCS_AUDIT.md`. Канонический namespace = `/api/v1` (код везде `/v1`), канон. имя = `SourceRecord` (код — `source_events`/`entities`), продуктовый фронт = Next.js `web/` (`/ui` — legacy). ASK-1 (23-я модель / Person), ASK-2 (rename vs add-alongside) — человеку.
- `INIT` — template создан, состояние не проверено. Запусти Prompt A.
