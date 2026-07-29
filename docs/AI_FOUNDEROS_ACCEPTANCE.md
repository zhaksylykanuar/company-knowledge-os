# FounderOS 2.0 Acceptance

Этот файл — единственный проверяемый ledger перехода к AI-first FounderOS.
Текущее состояние задач живёт в `PROGRESS.md`; продуктовый контракт —
`../founderOS_MASTER_PLAYBOOK.md`.

## A. Продуктовая модель

- [x] FounderOS определён как AI-партнёр с доказуемой памятью.
- [x] Зафиксированы зоны «Сейчас / Компания / Спросить / Настройки».
- [x] Зафиксированы уровни погружения от вывода до evidence.
- [x] Личный репозиторий FounderOS отделён от рабочей GitHub-организации.
- [x] Зафиксированы правила хранения, исправления и удаления памяти.
- [x] Старые Command Center решения помечены superseded в `DECISIONS.md`.

## B. Сейчас

- [x] Домашний экран использует спокойный AI-first язык.
- [x] Показывается один главный вывод и максимум две следующие ситуации.
- [x] На экране есть единый очевидный вход в вопрос к FounderOS.
- [x] Технические source-health данные скрыты в подробностях или настройках.
- [x] «Изменения» не заявляются без temporal checkpoint.
- [x] Каждый вывод открывает основания.
- [x] Empty, partial, stale, forbidden и offline состояния честные.

## C. Компания

- [x] Основная зона называется «Компания».
- [x] Люди, клиенты, проекты, работа и решения представлены как одна модель.
- [x] Provider-first и отдельная «Мир» метафора удалены.
- [x] Есть progressive drill-down до объекта и evidence.
- [x] Подтверждённые связи отделены от кандидатов.
- [x] Unknown и truncated counts не показываются как точный ноль.

## D. Спросить

- [x] «Спросить» является самостоятельной основной зоной.
- [x] Ответ разделяет факт, интерпретацию, возражение и рекомендацию.
- [x] Ответ связан с точным workspace snapshot.
- [x] Evidence и ограничения доступны из ответа.
- [x] История разговора не сохраняется по умолчанию.
- [x] Action request создаёт только draft/переход к подтверждению.
- [x] Generative LLM path использует strict schema и evidence validation.

## E. Настройки

- [x] Все подключения доступны только через настройки.
- [ ] Настройки разделены на компанию, источники, доступ, AI, память,
  автоматизацию, безопасность и advanced.
- [x] AI имеет отдельный workspace-scoped экран: encrypted key lifecycle,
  model/reasoning/budget controls, provider-policy acknowledgement, synthetic
  read-only check и server kill switch.
- [x] У подключения есть save, read check, write readiness и disconnect.
- [x] Отключение объясняет, какие canonical данные сохраняются или удаляются.
- [x] Секреты никогда не возвращаются в браузер.
- [x] Рабочая GitHub-организация и repositories выбираются явно.
- [x] GitHub live read создаёт durable job; UI автоматически показывает
  queued/running progress, terminal receipt и owner/admin cancel.
- [ ] Пользователь может управлять memory retention и удалением.

## F. Память и reasoning

- [ ] Canonical model покрывает people, organizations, customers, projects,
  commitments, decisions, risks and events.
- [ ] У сохраняемой памяти есть event time, observed time, evidence,
  confidence, access and retention.
- [x] Есть Temporal Memory v2: явный персональный checkpoint объединяет
  fingerprint comparison с монотонным lifecycle cursor.
- [x] Append-only ledger транзакционно фиксирует creation/terminal lifecycle
  Action Proposal и terminal resolutions Company World без копирования
  source/UI text.
- [x] Исчезнувшие GitHub issue/PR фиксируются через reconciliation/tombstones
  только после полного server-attested repository snapshot.
- [ ] Jira/Gmail/Drive получают полные live provider snapshots и подключаются к
  reconciliation; локальные/частичные импорты не объявляют исчезновение.
- [ ] Есть contradiction detection между источниками.
- [ ] Есть пользовательское исправление и забывание памяти.
- [x] Retrieval scoped к workspace и текущим правам.
- [x] AI critic не принимает unsupported claim.

## G. Действия

- [x] Существует ActionProposal foundation.
- [x] Существуют approval, idempotency и persisted receipt foundations.
- [x] Durable execution claim коммитится до provider call и содержит workspace,
  реального пользователя, connection, обязательный client key, request hash и
  claim timestamp.
- [x] Proposal lock и PostgreSQL uniqueness не допускают несколько
  active/successful execution; concurrent test доказывает один provider call.
- [x] Потерянный provider response сохраняется как `uncertain`, а read-only
  reconciliation разрешает его только по точному execution marker или после
  полного повторного доказательства отсутствия.
- [x] Approval и execution используют одну strict `evidence_ref.v1` schema и
  canonical same-workspace resolver; fabricated, deleted, unrelated,
  unsupported и foreign evidence fail closed.
- [x] Evidence повторно проверяется после committed execution start
  непосредственно перед provider call.
- [x] Bulk decisions проходят тот же versioned/idempotent row-locked service,
  что одиночные решения, и возвращают receipt для каждого успешного элемента.
- [x] AI/system proposal нельзя принять без exact Headquarters snapshot и
  exact proposal version.
- [ ] Draft из AI связывается с evidence и exact snapshot.
- [x] Preview показывает последствия и provider target.
- [x] Ни один LLM path не вызывает external write напрямую.
- [x] После выполнения read-back нормализует результат в canonical
  `SourceRecord` + `Task`, доступные Company Brain и текущей картине.

## H. Удаление старого продукта

- [x] Удалены primary labels «Штаб / Мир / Миссии / Радары».
- [x] Удалены provider-first product routes.
- [x] Удалена дублирующая briefing/dashboard/action навигация.
- [x] Удалён runtime `/demo` и synthetic Command Center код.
- [x] Удалены неиспользуемые компоненты и стили.
- [x] Удалены tests, проверяющие superseded UX.
- [x] Удалена или переписана superseded документация.
- [x] Поиск не находит активных ссылок на удалённые маршруты и термины.

## I. Проверка

- [x] `uv run ruff check .`
- [x] `uv run mypy app` проверяет все application modules локально и в CI.
- [x] Guarded `make backend-check` runs the full pytest suite only against an
  explicit dedicated test database.
- [x] Bare pytest fails closed before application import without explicit test
  mode and a test-marked database.
- [x] `npm test`
- [x] `npm run typecheck`
- [x] `npm run lint` является отдельным zero-warning Biome gate, а не alias на
  typecheck.
- [x] `npm run build`
- [x] `npm audit --audit-level=moderate`
- [x] `uv run pip-audit --local --progress-spinner off`
- [x] Local PostgreSQL/Redis Compose images and CI service images are pinned by
  immutable digest and automated updates preserve tag+digest.
- [x] Public liveness and database readiness are separate probes; readiness
  fails with 503 when PostgreSQL is unavailable.
- [x] Browser mutations enforce exact Origin/Referer, hosted security headers
  are present, and OpenAPI/Swagger/ReDoc are local-only.
- [x] Login, enrollment and setup-password share pre-Argon2 admission with an
  atomic Redis option and trusted-proxy address policy.
- [x] Expired auth artifacts are cleaned and session activity writes are
  interval-bounded.
- [x] Smoke commands are separated into liveness, session, workspace and
  desktop/mobile browser E2E contracts.
- [x] Provider network I/O не удерживает SQL transaction; GitHub jobs имеют
  bounded workers, PostgreSQL lease, retry, resume, progress и cancel.
- [x] Workspace-owned canonical/document relations use composite PostgreSQL
  foreign keys; negative tests reject every covered cross-workspace commit.
- [x] Exact local backup bundle can be encrypted for independent storage,
  decrypt-verified, fully restore-drilled and managed by explicit 7/4/12
  retention without persisting the key beside it.
- [x] Private license notice, SECURITY/CONTRIBUTING policy, owner CODEOWNERS and
  repository pre-commit gates are present and contract-tested.
- [x] Audited large modules have line-budget ratchets; Headquarters query count
  does not scale per SourceRecord, durable job claiming has a two-worker
  concurrency test, and the first bounded API extraction is complete.
- [x] Superseded synchronous selected-issue/PR provider routes are removed; one
  durable `202` GitHub App job remains the live repository-read path.
- [ ] First real encrypted copy and full restore drill from physically
  independent storage with separately recovered key.
- [ ] Public multi-tenant mode enforces the full RLS gate from DEC-102.
- [ ] Desktop browser QA.
- [ ] Mobile browser QA.
- [ ] Нет horizontal overflow.
- [ ] Нет console errors/warnings.
- [x] Нет секретов, provider payloads или лишней памяти в UI/log/docs.
