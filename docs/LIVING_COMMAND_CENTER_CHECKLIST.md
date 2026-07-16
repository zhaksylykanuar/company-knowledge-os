# Living Command Center — checklist реального продукта

Status: execution checklist for promoting the synthetic `/demo` interaction
reference into the authenticated local FounderOS product. This document is
subordinate to `founderOS_MASTER_PLAYBOOK.md`, `PROGRESS.md`, and durable
decisions in `DECISIONS.md`; it is the acceptance ledger for this product slice.

## Как использовать этот документ

- `[x]` ставится только после кода, тестов и проверяемого результата.
- `[ ]` означает, что пункт ещё не доказан, даже если рядом уже есть похожий UI.
- `🔒 GATE` требует отдельного подтверждения человека до provider read/write,
  schema/data-risk работы или публикации.
- После каждого завершённого блока обновляются `PROGRESS.md`, `TODO.md` и
  `CHANGELOG.md`.
- `/demo` остаётся синтетическим эталоном взаимодействия и никогда не считается
  доказательством готовности реального продукта.

## Что именно означает «система работает как в демо»

Основатель может запустить FounderOS локально, войти, выбрать компанию и дальше
работать только через UI:

1. увидеть честную готовность компании и закончить обязательную настройку;
2. подключить источник, выбрать точный scope и выполнить безопасное чтение;
3. увидеть один главный приоритет, три понятных pulse-метрики, следующие решения
   и последние подтверждённые сигналы;
4. открыть основания, источник, сотрудника, заказчика или историю в одном drawer;
5. задать ассистенту вопрос о текущем workspace и получить короткий ответ с
   разрешимыми citations;
6. открыть конкретную миссию и увидеть последствия; точный execution preview
   появляется только для уже локально одобренного внешнего action;
7. сначала approve/reject локальное решение и получить local receipt, а затем,
   если разрешено, отдельно проверить preview и подтвердить внешнюю запись;
8. получить durable receipt, вернуться в штаб и увидеть новый приоритет;
9. перезапустить систему и не потерять канонические данные, audit и receipts;
10. создать backup, доказать restore и безопасно остановить локальный runtime.

Текущий контракт этого checklist — desktop web при 1280×720 и 1440×900 sanity
pass. Mobile/tablet, hosted deploy и автономные агенты не входят в Definition of
Done и не должны задерживать локальный рабочий продукт.

## Непереговорные правила продукта

- Raw storage и PostgreSQL — source of truth; browser state и `/demo` fixtures —
  никогда.
- Каждый конкретный приоритет, риск, сигнал, профильный факт и proposal имеет
  workspace-scoped `evidence_refs`.
- Если подтверждения нет, API возвращает `null`, пустой список или
  `insufficient evidence`; UI не дописывает правдоподобный текст.
- Каждый снимок сообщает `as_of`, полноту, warnings и точность счётчиков:
  `exact`, `at_least` или `unavailable`.
- Connection row, mocked import, canonical local data и live provider result —
  разные состояния и не смешиваются в одном claim.
- Обычное открытие штаба не вызывает provider read, LLM run или mutation.
- Чтение не должно скрыто отмечать данные просмотренными; checkpoint создаётся
  отдельной явной локальной командой.
- UI использует backend capabilities и RBAC, а не вычисляет права самостоятельно.
- Ассистент ничего не исполняет. Он отвечает, открывает контекст или предлагает
  черновик `ActionProposal`.
- Любая внешняя запись проходит цепочку evidence → preview → human confirmation
  → idempotent execute → audit → receipt.
- Частичный сбой не превращается ни в пустую компанию, ни в полный успех.
- Raw email/document bodies, private payloads, tokens, cookies и secret-like
  значения не попадают в штаб, assistant context, UI receipts или логи.

## Бюджет внимания интерфейса

Authenticated `/dashboard` должен сохранить грамматику DEC-085:

- один главный приоритет и один основной CTA;
- ровно три компактных кликабельных pulse-метрики;
- максимум два следующих решения;
- максимум три последних сигнала на поверхности;
- одна глобальная точка входа в ассистента (`Cmd/Ctrl+K`);
- одновременно открыт не более чем один drawer или один modal;
- профили, evidence, документы, полная очередь и технические детали находятся
  только в progressive disclosure;
- никаких очков, streaks, декоративных gauges, sci-fi clutter или фиктивной
  «критичности».

## Карта текущей реальности

| Контур | Статус | Что уже есть | Что ещё нужно |
|---|---|---|---|
| Synthetic reference | ✅ | `/demo`, DEC-085, state transition, assistant shell, drawer/modal | Не переносить fixtures в auth product |
| Local runtime | ✅ | `make local`, loopback, Postgres, backup/restore, safe stop | Повторять release proof после рискованных изменений |
| Auth/workspace | ✅ | First-party session, workspace selection, membership roles | Полная capability/RBAC матрица нового штаба |
| Реальный `/dashboard` | 🟡 | Один вычисляемый ход, Company Map, signals, pulse, evidence | Единый server snapshot, очередь, overlays и точный post-decision refresh |
| Onboarding | 🟡 | Computed checks по connectors/brain/map/members | Server contract, resumable UI flow и возврат в тот же штаб |
| Company World | 🟡 | Люди, компании, кандидаты, touchpoints, evidence, human resolution | Компактные profile drawers, pagination, mission ownership |
| Briefing | ✅ foundation | Persisted deterministic Briefing/Items, evidence, history | Включить в единый rank/queue и штабные details |
| Action decisions | ✅ foundation | Proposals, approve/reject, preview, audit, execute, receipts | Exact mission deep link и связка receipt → refreshed headquarters snapshot |
| GitHub radar | 🟡 | Managed setup, repository scope, bounded reads, receipts | Первый реальный founder-approved read и global health projection |
| Jira/Gmail/Drive | 🟡 | Canonical local import/list/evidence | Полный UI lifecycle setup → scope/import/read → receipt → disconnect |
| Изменения с визита | ⛔ | Только current evidence snapshot | Persisted change cursor/checkpoint/dedupe |
| Company assistant | ⛔ | Только synthetic demo resolver | Workspace-scoped read-only backend contract |
| Privacy lifecycle | ⛔ | Secret/redaction foundations | Notice, scopes, disconnect, retention, export/delete rules |
| Real command-center browser QA | ⛔ | Проверен только synthetic reference | Полный authenticated desktop pass |

## Целевой backend read model

### `GET /api/v1/workspaces/{workspace_id}/headquarters`

Первый implementation slice должен быть read-only projection поверх
существующих таблиц. Новая `Mission` table на этом этапе не нужна.

Минимальный ответ:

```text
snapshot:
  id | as_of | partial | warnings | coverage
workspace:
  id | name | role
onboarding:
  ready | steps[] | next_action
sources:
  healthy | total | items[]
priority:
  Mission | null
pulse:
  exactly_three_metrics[]
queue:
  at_most_two_Missions[]
changes:
  at_most_three_items[] | basis | cursor | since_checkpoint
capabilities:
  global + per-item backend capabilities
```

До LC-06 контракт честно возвращает `basis=current_snapshot`, `cursor=null` и
`since_checkpoint=false`. Поля не означают persisted delta и UI называет их
«сигналами текущего снимка». Настоящий cursor/checkpoint включается только после
отдельного schema/data gate LC-06.

Минимальные capability keys: `can_manage_team`, `can_manage_source`,
`can_import_source`, `can_start_source_read`, `can_generate_briefing`,
`can_create_proposal`, `can_review_proposal`, `can_execute_external`,
`can_resolve_world` и `can_acknowledge_changes`. Mission, source, profile и
suggestion также возвращают собственный enabled/disabled action с причиной;
frontend не выводит разрешение из названия роли.

Минимальный `Mission` projection:

```text
id | kind | reference_type | reference_id
title | summary | why_now | status
severity | confidence | due_at | impact | next_step
owner_person_ids[] | organization_id | primary_person_id
source_keys[] | evidence_refs[] | proposal_id
fact_provenance: owner | customer | due | impact -> evidence_refs[]
action: kind | label | target | enabled | disabled_reason
```

До появления durable mission lifecycle стабильные id строятся из канонической
ссылки: `proposal:<uuid>`, `briefing:<briefing_id>:<item_key>`,
`world:<opaque_selector>:<version>` или `setup:<kind>`. Raw Company Map key,
email и domain не входят в mission id, URL или логи. Отдельная таблица `Mission` требует
schema review только когда реально понадобятся назначения, составные решения,
cross-source closure и долговечный lifecycle.

Один server service обязан использоваться штабом, assistant endpoint и
post-decision refresh. Сейчас `/dashboard` делает несколько независимых чтений,
а приоритет выбирается в браузере; это нельзя считать финальным контрактом,
потому что ассистент и receipt могут увидеть другую очередь.

`snapshot.id` — не случайная метка ответа. Он является deterministic content
version по точным input watermarks/versions, собранным в одной согласованной DB
границе (`REPEATABLE READ` либо эквивалентный explicit-watermark read). Assistant,
preview и confirmation передают `expected_snapshot_id`; если состояние уже
изменилось и прежний snapshot нельзя воспроизвести, backend возвращает
`snapshot_changed`/`409`, а UI обновляет штаб вместо смешивания версий.

## Фазовый implementation checklist

### LC-00 — Зафиксировать честные контракты

- [ ] Добавить Pydantic/TypeScript схемы `HeadquartersSnapshot`, `Mission`,
  `PulseMetric`, `SourceHealth`, `ChangeItem` и `CapabilitySet`.
- [ ] Для каждого числа определить precision: `exact`, `at_least` или
  `unavailable`.
- [ ] Для каждого факта определить обязательные `evidence_refs` и поведение при
  их отсутствии.
- [ ] Зафиксировать ranking version и deterministic tie-breaker.
- [ ] Зафиксировать state machine миссии и решения.
- [ ] Определить `snapshot.id` как immutable/versioned state reference; preview
  получает `proposal_version` и digest точного payload/target.
- [ ] Зафиксировать consistency strategy: одна repeatable-read transaction либо
  explicit source watermarks; несколько независимых READ COMMITTED запросов не
  считаются одним snapshot.
- [ ] Перед server ranking разрешать каждый proposal/evidence/reference id в
  текущем workspace и присваивать provenance/trust class.
- [ ] Declared, missing или cross-workspace refs не считаются verified evidence
  и не участвуют в evidence-backed priority ranking.
- [ ] `created_by`, origin и system/AI trust class задаёт backend; caller не может
  повысить собственный proposal до system/AI или подложить severity из payload.
- [ ] Составить RBAC-матрицу `owner/admin/member/viewer × control`.
- [ ] Зафиксировать, какие данные считаются live, imported, local canonical,
  stale, partial и unavailable.
- [ ] Написать contract tests до замены `/dashboard`.

Готово, когда одинаковый workspace snapshot даёт одинаковый priority/queue во
всех потребителях, а unsupported fact не может попасть в payload.

### LC-01 — Собрать единый read-only штаб

- [ ] Реализовать headquarters service поверх существующих Company Brain,
  Company Map, Briefing, ActionProposal, connector и membership reads.
- [ ] Перенести deterministic ranking из browser view model на backend.
- [ ] Возвращать один приоритет и не дублировать его в очереди.
- [ ] Возвращать максимум два следующих элемента того же ranking.
- [ ] Выбрать три честные метрики из реально доступных данных; не использовать
  `critical risk` или `employees in focus`, пока для них нет канонической связи.
- [ ] Зафиксировать эти три v1 keys и формулы:
  `waiting_decisions` = evidence-eligible proposed actions;
  `sources_attention` = configured sources с failed/partial/stale/no-data;
  `pending_relationships` = unresolved evidence-backed people/organization
  candidates. Каждая метрика возвращает precision, empty behavior и точный
  drawer target.
- [ ] Возвращать source health, freshness, last success/attempt, record count,
  blocker и safe next action.
- [ ] Прикреплять несколько source keys к одной mission только через
  воспроизводимое правило корреляции по канонической сущности/work item/customer,
  времени и прямым refs; возвращать `correlation_reason` и `rule_version`.
- [ ] Не объединять сигналы только по похожему тексту, имени, email domain или
  LLM similarity.
- [ ] Сохранять полезные данные при частичном падении одного projection и
  возвращать warnings.
- [ ] Partial `200` разрешён только для typed ожидаемой недоступности независимо
  изолированного subprojection и обязан перечислить coverage/watermarks.
  Auth/tenancy mismatch, DB transaction/invariant/corruption и неизвестная
  ошибка проваливают весь request; broad catch не превращает их в правдоподобный
  partial штаб.
- [ ] Защитить endpoint от cross-workspace IDs и stale responses.
- [ ] Не добавлять provider calls, LLM или writes в headquarters GET.
- [ ] Покрыть exact/lower-bound counts, partial data, deterministic order,
  missing evidence и RBAC contract tests.

Готово, когда один API payload полностью объясняет поверхность штаба и
повторный запрос без изменения данных возвращает тот же порядок.

### LC-02 — Перенести дизайн-грамматику в authenticated `/dashboard`

- [ ] Переиспользовать данные и routes реального продукта; не импортировать
  `demo-tour` или `demo-command-center` fixtures.
- [ ] Вынести production-safe `OverlayShell` с focus trap, inert background,
  Escape close и возвратом фокуса.
- [ ] Сделать header: компания, честный source health, assistant launcher,
  профиль; технические настройки оставить backstage.
- [ ] Сделать real priority card из `HeadquartersSnapshot.priority`.
- [ ] CTA выводить только из `Mission.action` и capabilities.
- [ ] `Почему это №1?` открывает exact ranking/evidence drawer.
- [ ] Pulse открывает релевантный detail, а не общий текстовый dump.
- [ ] Каждая строка queue передаёт точный mission id/reference.
- [ ] После решения refetch показывает новый snapshot без full page reload.
- [ ] Смена workspace отменяет старые requests и закрывает чужой overlay.
- [ ] Loading, empty, partial, stale, forbidden, offline/error и retry состояния
  остаются на той же понятной поверхности.

Готово, когда authenticated экран визуально работает как `/demo`, но каждый
показанный факт приходит из текущего workspace и имеет честный статус.

### LC-03 — Встроить вычисляемый onboarding

- [ ] Добавить `GET .../onboarding` с server-computed steps, evidence,
  capabilities и `next_action`.
- [x] Сохранить private-beta pre-workspace boundary DEC-075: `/start` по
  одноразовому invite атомарно создаёт User, Workspace, owner Membership и
  Session до входа в workspace-scoped onboarding.
- [ ] Не вызывать workspace endpoints для zero-workspace account; показывать
  честный recovery. Будущий public self-service create требует отдельного
  security/product decision и не подменяется bootstrap route.
- [ ] Оставить пять пользовательских шагов: компания, первый источник, первое
  canonical чтение/снимок, контекст карты/команды и вход в штаб.
- [ ] Команду оставить optional для single-founder readiness.
- [ ] Required step со state `unknown` не считается complete.
- [ ] Required: workspace/company, хотя бы один canonical source record и
  успешно вычисленный headquarters snapshot. Team, дополнительный map context и
  первое решение — recommended; `priority=null` является допустимым calm state и
  не блокирует доступ к штабу.
- [ ] Compact onboarding внутри headquarters и detailed onboarding endpoint
  используют один service/version; второго source of truth нет.
- [ ] Открывать один компактный modal поверх штаба, а не отдельную админку.
- [ ] Onboarding modal имеет приоритет над остальными overlays и не создаёт
  drawer/modal stack.
- [ ] Для каждого шага показывать одно действие, «что это даст», status и
  disclosure «Подробнее».
- [ ] Галочки вычисляет backend; пользователь не отмечает их вручную.
- [ ] Resume после reload возвращает на первый реальный blocker.
- [ ] После завершения modal закрывается и refetch’ит тот же штаб.
- [ ] Owner/admin получает setup controls; member/viewer — результат и понятный
  путь обратиться к администратору.
- [ ] Добавление команды использует one-time self-setup/invite flow и не
  показывает пароль или bearer secret в общем UI.

Готово, когда после получения private invite новый founder проходит обязательную
настройку из UI и не редактирует env/JSON/терминал, кроме запуска локального
runtime оператором.

### LC-04 — Довести радары по одному источнику

- [ ] Не использовать один взаимоисключающий source enum. Контракт имеет четыре
  независимые оси: `configuration=disconnected|configured`,
  `read=idle|running|succeeded|failed`, `data=empty|available|partial`,
  `freshness=fresh|stale|unknown`, плюс derived `attention_reason`.
- [ ] Зафиксировать precedence для primary UI state:
  failed → partial → stale → no-data → healthy → setup, а thresholds freshness
  задаёт backend по provider/contract version.
- [ ] Global label отдельно показывает `data_ready_count` и
  `configured_count`; «N из M» не использует registry total как будто все
  providers уже настроены.
- [ ] Backend возвращает точный `next_action`/disabled reason для роли и каждого
  состояния; frontend не строит CTA из enum.
- [ ] Показать exact configured scope и реальные provider permissions.
- [ ] Показать last successful read, last attempt, freshness, records,
  warnings и safe debug id.
- [ ] Сохранить GitHub как эталон setup → repository scope → one read →
  canonical records → evidence → receipt.
- [ ] 🔒 GATE: выполнить первый реальный GitHub read только после отдельного
  подтверждения founder по существующему runbook.
- [ ] Не считать connection enabled до сохранения непустого repository subset.
- [ ] Не сохранять installation/provider tokens в tracked files или frontend.
- [ ] Не запускать background/bulk reads в первом доказательстве.
- [ ] Backend защищает read через per-workspace/provider single-flight lock,
  idempotency/replay key, cooldown и rate limit; двойной клик или прямой replay
  не создают второй provider request, а throttling возвращает safe `Retry-After`.
- [ ] Только после успешного bounded manual read добавить scheduled refresh и
  scheduler-specific backoff, переиспользуя уже обязательные single-flight,
  idempotency, cooldown и rate limits; автоматизация не должна скрывать scope,
  partial failure или последнюю успешную квитанцию.
- [ ] После GitHub последовательно дать Jira, Gmail и Drive такой же UI lifecycle;
  local import может быть первым честным шагом, а live OAuth/read — отдельным.
- [ ] Спрятать JSON/manual import в technical disclosure, не выдавая его за
  основной пользовательский сценарий.
- [ ] Для каждого радара реализовать disconnect/revoke и объяснить судьбу уже
  сохранённых canonical/raw/audit данных.
- [ ] Disconnect/revoke доступен только разрешённой роли, требует consequence
  preview и confirmation, идемпотентен и создаёт receipt.
- [ ] Provider revoke failure не стирает локальную connection state и предлагает
  safe retry/recovery; canonical retention не меняется скрыто.

Готово, когда source health в штабе объясняется receipts и каноническими
данными, а не наличием connection row.

### LC-05 — Сделать exact mission, people и customer drill-down

- [ ] Конкретная mission row открывает карточку именно этой миссии.
- [ ] Показывать title, why now, impact, due, owner, customer, source set и
  evidence только если они подтверждены.
- [ ] Owner, customer, due и impact имеют field-level provenance; общий список
  mission evidence не считается доказательством каждого из этих полей.
- [ ] Неподтверждённое поле показывает `Не определено`, а не synthetic copy.
- [ ] Добавить exact `proposal_id` deep link в `/actions`.
- [ ] Вынести компактный mission decision flow из `/actions`, не дублируя API,
  status logic и execution safety.
- [ ] Переиспользовать Company Map selectors для person/company drawer.
- [ ] Customer drawer: `Обзор / Люди / История` только по durable relations.
- [ ] Employee profile разделяет RBAC role и business role.
- [ ] 🔒 GATE: перед добавлением durable employee business profile провести
  schema review; связать membership/internal Person без дублирования identity.
- [ ] Owner/admin через UI может задать подтверждённые title/function/focus;
  system не угадывает должность, загрузку или mission ownership.
- [ ] Customer profile связывает только human-confirmed relationship kind,
  внутреннего account owner, key people, commitments и evidence-backed history.
- [ ] Commitment/health не выводятся из tone письма; сначала нужен явный
  structured fact или human confirmation с receipt.
- [ ] Не писать «в текущей миссии» без канонической mission-person связи.
- [ ] Candidate resolution остаётся отдельным human action с idempotent receipt.
- [ ] Profiles/timeline поддерживают pagination или честно показывают window и
  truncation.

Готово, когда любой CTA, citation и queue item открывает ту же сущность, которую
пользователь видел на поверхности, без generic fallback.

### LC-06 — Добавить настоящие изменения «с прошлого визита»

- [ ] До реализации продолжать писать «сигналы текущего снимка», не
  «изменилось с прошлого визита».
- [ ] 🔒 GATE: провести schema/data review и verified backup до миграции.
- [ ] Добавить workspace-scoped snapshot/change contract с server timestamp,
  source watermarks, coverage и evidence.
- [ ] Добавить stable dedupe/idempotency key и deterministic order.
- [ ] Ввести per-user server checkpoint; не использовать localStorage timestamp.
- [ ] GET остаётся read-only; acknowledge checkpoint — отдельная команда.
- [ ] Различать `new`, `changed`, `resolved`, `stale` и `current`.
- [ ] Не выдавать delta за полную, если один source partial/stale.
- [ ] Закрытие mission создаёт receipt и change event, не удаляя evidence.
- [ ] Повторная обработка события не создаёт второй сигнал.
- [ ] Timezone влияет только на отображение, не на server ordering.

Готово, когда feed воспроизводим после restart и каждый change можно проследить
до snapshot и evidence.

### LC-07 — Подключить реального read-only ассистента компании

- [ ] Реализовать `POST /api/v1/workspaces/{workspace_id}/assistant/query`.
- [ ] Первая версия — deterministic allowlisted intents без LLM.
- [ ] Intents: current priority, why now, owners, company/person, sources,
  briefing, waiting decisions, evidence и decision status.
- [ ] Читать тот же headquarters service/snapshot, что и экран.
- [ ] Ответ: `intent`, короткий `text`, normalized citations, `suggestions`,
  optional safe UI action, `snapshot_id`, `as_of`, `partial`, `warnings`,
  `is_live`, `llm_used=false`.
- [ ] Query передаёт экранный `expected_snapshot_id`; если snapshot изменился,
  assistant возвращает `snapshot_changed` вместо ответа из другой версии.
- [ ] Не сохранять conversation history в первой версии.
- [ ] Не вызывать providers и ничего не мутировать.
- [ ] Suggestion может открыть drawer/mission или вернуть неперсистентный UI
  prefill draft, но не создаёт, approve или execute proposal.
- [ ] `ActionProposal` создаёт только отдельный явный пользовательский POST после
  просмотра prefill и повторной backend validation.
- [ ] При отсутствии evidence отвечать `Недостаточно подтверждённых данных`.
- [ ] Фильтровать ответ и suggestions по backend capabilities/RBAC.
- [ ] Ограничить query length, evidence count, response size и execution time.
- [ ] Добавить backend per-user/workspace rate limit и single-flight для
  одинакового assistant query/snapshot, а не полагаться на disabled UI button.
- [ ] Не логировать полный вопрос, raw bodies или private citation content.
- [ ] Покрыть unsupported intent, prompt injection, cross-workspace, viewer,
  stale snapshot и missing-evidence tests.
- [ ] Подключить один launcher во всех authenticated product zones и сохранить
  `Cmd/Ctrl+K`, focus и citations navigation.

Будущий LLM-режим — отдельный gate: bounded retrieval, strict JSON schema,
validation до persistence, evidence validation, prompt/model versioning,
budgets/rate limits, privacy/retention decision и запрет direct mutation.

Готово, когда ассистент и штаб всегда называют один priority, а просьба
«сделай сам» неизменно переводит человека в confirmation flow.

### LC-08 — Замкнуть decision → receipt → новый штаб

Обязательная derived headquarters state machine (она не заменяет persisted DB
enums без отдельной миграции):

| Derived state | Mapping на текущие rows | Что видит человек | Что завершает этот шаг |
|---|---|---|---|
| `proposed` | `ActionProposal.status=proposed` | why, consequence, evidence, proposed payload; без execution preview | approve/reject + local decision receipt |
| `approved_internal` | proposal `approved` + internal action type + нет execution | локальный результат | persisted audit/receipt, `external_write=false` |
| `approved_external` | proposal `approved` + supported external type + нет running/success execution | exact provider execution preview | отдельное confirmation перед execute |
| `executing` | latest `ActionExecution.status=running` | locked pending state | persisted execution result |
| `succeeded` / `failed` | latest execution `succeeded/failed`, proposal `executed/failed` | receipt и safe next action | terminal result; failed может стать новой attention mission |
| setup/world resolution | domain-specific canonical/audit receipt | consequence + confirmation | idempotent local receipt; без provider preview |

- [ ] Зафиксировать и протестировать mapping derived states на proposal,
  execution и audit rows; не добавлять новые persisted status strings случайно.
- [ ] `unknown_result`/reconcile требует отдельного schema/data gate либо
  доказуемого durable audit representation; до этого состояние не симулируется.

`proposed` перестаёт быть waiting decision после approve/reject. Если approve
создал готовое внешнее действие, оно может вернуться в ranking как отдельная
`approved_external` mission; это не тот же незавершённый decision claim.

- [ ] Открывать точный ActionProposal по mission/proposal id.
- [ ] В одном modal показывать why now, последствия и evidence; exact execution
  preview показывать только на `approved_external` этапе.
- [ ] Сохранить разделение local approve/reject и external execute.
- [ ] Owner/admin/member/viewer видят только разрешённые controls.
- [ ] Pending mutation блокирует смену workspace, mission и повторный submit.
- [ ] External execute требует отдельного checkbox/command и backend capability.
- [ ] Confirmation отправляет `expected_snapshot_id`, `proposal_version` и
  immutable preview digest; stale context возвращает `409` и требует новый
  preview/confirmation.
- [ ] Непосредственно перед provider call backend повторно проверяет actor,
  membership/RBAC, evidence, target/payload, capability, allowlist и write gate.
- [ ] Idempotency key обязателен; повтор возвращает существующий receipt.
- [ ] Audit фиксирует actor, workspace, preview, confirmation, start и result.
- [ ] Receipt сообщает local/external effect и provider result только по факту.
- [ ] Ambiguous result блокирует retry до reconcile.
- [ ] Для `unknown_result` owner/admin получает отдельное «Проверить результат»:
  read-only reconcile по точному target/idempotency key, отдельный audit/receipt
  и без повторного write. Retry разрешается только после доказанного
  `not_performed` либо через новый proposal и новое confirmation.
- [ ] После persisted result refetch’ить headquarters snapshot и поднимать новый
  priority; ошибка refetch не превращает успешный receipt в failure.
- [ ] 🔒 GATE: реальный provider write выполняется только отдельным разрешением и
  никогда не входит в обычный smoke/CI.

Готово, когда решение нельзя повторить случайно, receipt переживает restart, а
новый приоритет появляется из канонического состояния.

### LC-09 — Privacy, observability и operational safety

- [ ] Добавить понятный privacy notice: что читается, зачем и где хранится.
- [ ] Показывать реальные scopes каждого источника.
- [ ] Зафиксировать retention для raw, canonical, audit, assistant и backups.
- [ ] Описать export/delete и disconnect/revoke последствия.
- [ ] Проверить httpOnly session, expiry/revocation/logout и login throttle.
- [ ] Проверить workspace isolation и negative RBAC matrix для всех controls.
- [ ] Логи содержат request/correlation id, method/path/status/duration, safe
  workspace/provider/action ids и error class.
- [ ] Не логировать query values, headers, cookies, bodies, credentials и raw
  provider payloads.
- [ ] Добавить метрики sync success/failure/duration/records, assistant failures,
  actions и frontend errors.
- [ ] UI показывает last success/failure и safe debug id.
- [ ] `/health` остаётся liveness-only; детальная диагностика защищена.
- [ ] Перед schema/data-risk работой создавать новый verified backup и доказывать
  restore на совместимом изолированном Postgres.
- [ ] `make local-stop` сохраняет `.local/`, volume и backups.

Готово, когда проблему можно расследовать без private payloads, а rollback
опирается на проверенный restore, а не просто timestamped dump.

## Обязательная UI state matrix

| State | Сообщение на поверхности | Primary action | Retry/поведение |
|---|---|---|---|
| loading | «Собираем подтверждённый снимок компании» | нет | skeleton не показывает старые claims как live |
| no workspace | «Компания не выбрана» | открыть `/start` или recovery | workspace endpoints не вызываются |
| onboarding required | «Нужно закончить обязательную настройку» | продолжить конкретный blocker | modal один, recommended steps можно отложить |
| calm/empty | «Подтверждённых приоритетов сейчас нет» | backend `next_action` к source/briefing/world | не придумывать mission |
| partial | «Часть данных недоступна» + список contours | повторить недоступные reads | подтверждённые данные остаются видимы |
| stale source | «Источник давно не обновлялся» + `as_of` | открыть радар/обновить, если разрешено | freshness не маскируется цветом |
| offline/backend unavailable | «Локальный сервер недоступен» | повторить | не заявлять live/empty state |
| forbidden/read-only | «Недостаточно прав для действия» | посмотреть контекст/обратиться к admin | mutation controls отсутствуют |
| mutation pending | «Сохраняем решение…» | disabled | блокируются workspace/mission switch и replay |
| safe error | «Штаб не удалось обновить» + safe debug id | повторить | raw traceback/payload не показывается |
| receipt | фактический local/external result | вернуться в обновлённый штаб | status объявляется screen reader, затем refetch |

### LC-10 — Desktop acceptance и release proof

- [ ] Проверить real authenticated штаб при 1280×720 и 1440×900.
- [ ] Нет horizontal overflow, перекрытий, обрезанных CTA и blank screens.
- [ ] Проверить loading, empty, partial, stale, offline, forbidden и error.
- [ ] Полный keyboard flow: Tab/Shift+Tab, Enter/Space, Escape, `Cmd/Ctrl+K`.
- [ ] Drawer/modal удерживают и возвращают focus.
- [ ] Async status и receipt объявляются screen reader.
- [ ] Contrast AA; смысл не передаётся только цветом.
- [ ] При text zoom 200% критические действия остаются доступны.
- [ ] `prefers-reduced-motion` убирает необязательное движение.
- [ ] Back/refresh/deep link не повторяют mutation.
- [ ] Быстрая смена workspace/profile не показывает stale response.
- [ ] Browser console без свежих warnings/errors.
- [ ] Backend gates выполняются только через `make backend-check` с явным
  `FOUNDEROS_TEST_DATABASE_URL` на отдельный loopback PostgreSQL, имя которого
  содержит standalone test marker вроде `founderos_test`; product DB не
  используется для тестов.
- [ ] Backend wrapper подтверждает full pytest, Ruff и migrations/current/heads/check.
- [ ] Frontend: tests, typecheck, lint, production build.
- [ ] Tracked/staged secret scan и `git diff --check`.
- [ ] `uv run python scripts/mvp_completion_audit.py` и `make local-readiness`.
- [ ] `make local-doctor`, `make local-smoke`, verified backup/restore и safe stop.
- [ ] Зафиксировать sanitized provider-read receipt отдельно от mocked/local
  evidence; write receipt — отдельно и только если write входит в release.
- [ ] Release manifest содержит commit, migration head, feature flags, source
  scopes, contract versions, backup id и known limitations.

Готово, когда полный сценарий ниже проходит на чистой сессии и после restart.

## Уровни готовности

### A — Полезный локальный штаб

LC-00…LC-03, local/import + honest source-health часть LC-04, LC-05, local-only
часть LC-08, LC-09 и desktop LC-10 завершены. Основатель может настроить
компанию, импортировать данные, увидеть реальный штаб, проверить миссию и принять
локальное решение. Assistant, true delta и provider read/write ещё могут быть
выключены и честно обозначены.

### B — Полное соответствие показанному сценарию

Дополнительно завершены LC-06 и LC-07: есть доказуемые изменения с checkpoint,
реальный read-only assistant, exact profiles и post-receipt state transition.
Хотя бы один provider read доказан отдельной квитанцией.

### C — Полная parity радаров

GitHub, Jira, Gmail и Drive каждый прошли собственный setup/scope/read-or-import/
receipt/disconnect contract, source health показывает реальные оси состояния, а
scheduled refresh допускается только после bounded manual proof конкретного
provider. Невключённый live connector честно остаётся local/import mode.

### D — Управляемое внешнее действие

External часть LC-08 открывается только после read proof и отдельного human gate.
Один allowlisted action проходит exact preview, confirmation, idempotent execute,
read-back/reconcile и receipt. Это не превращает assistant в autonomous agent.

## Финальный end-to-end сценарий

- [ ] Founder входит и видит только свой workspace.
- [ ] Незавершённая настройка открывает компактный computed onboarding.
- [ ] Founder добавляет/проверяет компанию и роли команды через UI.
- [ ] Founder подключает или импортирует первый источник через UI.
- [ ] Явное первое чтение создаёт canonical records, evidence и no-write receipt.
- [ ] Штаб показывает один реальный priority, три metrics, queue и signals.
- [ ] `Почему это №1?` открывает exact evidence и freshness.
- [ ] Person/customer/source controls открывают точные drawers.
- [ ] Ассистент отвечает из того же snapshot и открывает citation target.
- [ ] Конкретная queue row открывает конкретную mission.
- [ ] Founder approve/reject proposal и получает local receipt без внешней записи.
- [ ] Для approved external action founder отдельно видит exact preview и
  подтверждает execute.
- [ ] Receipt честно различает local result и external write.
- [ ] Штаб refetch’ится и показывает новый priority.
- [ ] Logout удаляет session; другой workspace не видит данные.
- [ ] Restart сохраняет records, decisions, audit и receipts.
- [ ] Backup восстанавливается и даёт те же безопасные aggregate counts.

## Порядок реализации без расползания scope

1. **LC-00/LC-01:** headquarters schema, service, endpoint и contract tests — без
   миграции и без нового UI.
2. **LC-02:** заменить реальный `/dashboard` на минимальный command center,
   используя только новый snapshot.
3. **LC-03:** встроить computed onboarding и возврат в штаб.
4. **LC-05/LC-08:** exact mission/profile drawers и существующий decision modal.
5. **LC-07:** deterministic read-only assistant поверх того же service.
6. **LC-04:** доказать GitHub read, затем доводить остальные радары по одному.
7. **LC-06:** только после schema review добавить durable change boundary.
8. **LC-09/LC-10:** privacy, observability и полный release proof.

Первый следующий implementation ticket: **LC-00/LC-01 — единый read-only
`HeadquartersSnapshot` поверх существующих данных, без миграции, provider calls,
LLM и writes.**

## Что не делать до завершения checklist

- не переносить synthetic fixtures в authenticated routes;
- не строить отдельное приложение внутри drawer;
- не начинать с LLM, background sync или autonomous actions;
- не подключать несколько новых providers одновременно;
- не вводить durable `Mission` table до доказанной потребности;
- не называть current snapshot изменениями «с прошлого визита»;
- не считать presence env/connection доказательством live readiness;
- не делать hosted deploy, mobile app, marketplace, billing или visual polish
  вместо первого целого локального E2E.
