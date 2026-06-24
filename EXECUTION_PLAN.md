# founderOS — EXECUTION PLAN (orchestration layer)

**Назначение:** превратить большой `founderOS_MASTER_PLAYBOOK.md` в исполняемую последовательность.
Playbook отвечает на вопрос **«что и как строить»**. Этот файл отвечает на **«в каком порядке и где мы сейчас»**.

## Система из 3 файлов

| Файл | Роль | Кто меняет |
|---|---|---|
| `founderOS_MASTER_PLAYBOOK.md` | Reference: спеки, модели, API, prompts. Источник истины по содержанию. | Человек (редко) |
| `EXECUTION_PLAN.md` (этот файл) | Порядок: 9 чанков, gate'ы, правила, driver-промпты. | Человек (редко) |
| `PROGRESS.md` | Live state: где мы, что готово, что сломано. | **Агент после каждой задачи** |

**Рабочий цикл человека:**
1. Один раз: запустить **Prompt A (Audit)** → `PROGRESS.md` заполняется реальным состоянием.
2. Дальше по кругу: запускать **Prompt B (Execute)** → агент берёт текущий чанк, доводит до gate, обновляет `PROGRESS.md`.
3. Чанк закрыт → снова **Prompt B** → следующий чанк. И так до CHUNK 8.

---

## ЖЕЛЕЗНЫЕ ПРАВИЛА (агент обязан соблюдать)

1. **Один чанк за сессию.** Не начинать следующий чанк, пока текущий gate не зелёный.
2. **Внутри чанка — по задачам FOS-XXX по порядку.** После каждой задачи: обновить `PROGRESS.md` + commit.
3. **Plan-first для каждой задачи:** сначала список файлов и «что НЕ трогаю», потом код.
4. **Минимальная реализация под acceptance criteria.** Никакого «заодно улучшил».
5. **Никакого рефакторинга до зелёного GitHub E2E (CHUNK 3).** (§21.4)
6. **Никаких новых фич вне текущего чанка.** Новая идея → строка в `docs/POST_MVP.md`, не в код. (§23.2)
7. **Каждый AI-claim имеет evidence. AI не делает external write без approval.** (§2.4)
8. **Зелёное состояние перед выходом.** Репозиторий и `PROGRESS.md` всегда консистентны на конце сессии.
9. **Self-heal, но не молотить.** Ошибка по пути — чинится здесь же (до ~3 сфокусированных попыток). Не вышло → блокер в `PROGRESS.md` + один конкретный вопрос, и стоп.
10. **Commit-формат:** `feat(scope): ...` / `fix(scope): ...` / `test(scope): ...` / `docs(scope): ...`. Checkpoint перед миграциями, после зелёных тестов, после E2E. (§15)

---

## CHUNK MAP (9 больших шагов)

Порядок неизменен — он повторяет fixed first E2E из playbook (§Phase 4):
`GitHub OAuth → Sync → SourceRecords → Entities → Dashboard → Brain → Briefing → Action → Approved Issue`.

### CHUNK 0 — Audit & Docs
- **Tasks:** FOS-000, FOS-001
- **Playbook:** §11 Phase 0–1, §12, §22 Этап 1
- **GATE:** `PROGRESS.md` отражает реальность; `docs/{DECISIONS,ROADMAP,TODO,POST_MVP,CHANGELOG}.md` существуют и совпадают с playbook.

### CHUNK 1 — Data Foundation
- **Tasks:** FOS-002, FOS-003
- **Playbook:** §6 (все модели), §12, §22 Этап 2
- **GATE:** `alembic upgrade head` ✅ · model tests ✅ · encryption roundtrip test ✅.

### CHUNK 2 — Connector Framework
- **Tasks:** FOS-004, FOS-005, FOS-006
- **Playbook:** §6.7–6.9, §9.2–9.3, §12, §22 Этап 3
- **GATE:** mock-коннектор в тесте создаёт SourceRecord + NormalizedEntity + EvidenceRef.

### CHUNK 3 — GitHub E2E (SPINE) 🎯
- **Tasks:** FOS-007, FOS-008, FOS-009, FOS-010, FOS-011, FOS-012
- **Playbook:** §7.5/7.7, §8 (`/connectors`,`/github`,`/dashboard`,`/brain`), §9.1–9.3, §Phase 4, §22 Этап 4
- **GATE (критический milestone):** пользователь подключает GitHub через UI → sync проходит → данные видны в Dashboard и Brain. **После этого разрешён рефакторинг.**

### CHUNK 4 — Briefing MVP
- **Tasks:** FOS-013, FOS-014
- **Playbook:** §7.13, §8 `/briefings`, §9.5, §10.3, §12, §22 Этап 5
- **GATE:** пользователь генерирует briefing; evidence drawer открывается и показывает источники.

### CHUNK 5 — Action Approval 🎯
- **Tasks:** FOS-015, FOS-016
- **Playbook:** §7.14, §8 `/actions`, §9.6, §10.6, §12, §22 Этап 6
- **GATE (full main E2E):** approved action создаёт реальный GitHub issue; результат виден в UI; всё в audit log.

### CHUNK 6 — Remaining Connectors
- **Tasks:** FOS-017, FOS-018, FOS-019, FOS-020
- **Playbook:** §7.8–7.11, §8 (`/jira`,`/gmail`,`/drive`,`/documents`), §10.4, §12, §22 Этап 7–10
- **GATE:** Jira/Gmail/Drive/Documents видны в Brain (минимально).

### CHUNK 7 — Polish + Repo Audit UI
- **Tasks:** FOS-021, FOS-P (polish)
- **Playbook:** §7.15, §8 `/repo-audit`, §17, §Phase 5, §22 Этап 11
- **GATE:** нет dead-end состояний (везде loading/empty/error); repo audit виден.

### CHUNK 8 — Testing Gate + Deploy
- **Tasks:** FOS-022, FOS-T (full tests), FOS-D (deploy)
- **Playbook:** §16, §19, §20, §12, §22 Этап 12–13
- **GATE:** launch checklist (§20) зелёный; production URL работает; первый E2E проходит в проде.

---

## ЦИКЛ ВЫПОЛНЕНИЯ ОДНОЙ ЗАДАЧИ (что агент делает на каждом FOS-XXX)

```
1. plan        — файлы, что НЕ трогаю
2. implement   — минимально под acceptance criteria
3. verify      — targeted tests / migration / build (по типу задачи)
   └─ red? → fix (до ~3 попыток) → verify снова
4. update      — PROGRESS.md: [x] задача, прогресс-бар, gate table, +строка в SESSION LOG
5. commit      — feat(scope): ...
6. report      — одна строка: «✅ FOS-XXX done — N/23 · gate: … · next: FOS-YYY»
```
После последней задачи чанка → прогнать **GATE чанка** → если ✅: пометить чанк, сделать checkpoint, напечатать `🎯 CHUNK N COMPLETE`.

---

## PROMPT A — AUDIT (запустить ОДИН раз в начале)

> Скопируй целиком в Claude Code / Codex. Этот промпт ничего не ломает: только читает и пишет `PROGRESS.md`.

```text
Ты — инженер-аудитор проекта founderOS. Задача: понять реальное состояние репозитория и записать его в PROGRESS.md. КОД НЕ МЕНЯТЬ.

Контекст (прочитай перед работой):
1. founderOS_MASTER_PLAYBOOK.md — особенно §6 (Data Model), §7 (API), §8 (Frontend), §11 (Phases), §12 (FOS-000..FOS-022), §22 (Этапы).
2. EXECUTION_PLAN.md — CHUNK MAP и gate'ы (9 чанков).
3. PROGRESS.md — формат файла состояния.

Сделай инвентаризацию (read-only):
- стек, структура папок, существующие модули;
- модели в коде vs 23 модели из §6 (каких нет);
- backend services / API routes vs §7 (что реализовано);
- frontend pages vs §8 (какие страницы есть);
- статус проверок: запусти безопасно и зафиксируй РЕЗУЛЬТАТ (не чини):
    - alembic current / alembic heads / попытка alembic upgrade head на dev,
    - pytest (кратко: passed/failed),
    - ruff,
    - сборка фронтенда (если есть).

Затем для каждой задачи FOS-000 … FOS-022 присвой статус:
  DONE / PARTIAL / MISSING — и ОДНУ строку доказательства (путь к файлу или имя теста).
Маппинг задача→чанк бери из EXECUTION_PLAN.md.

Перезапиши PROGRESS.md реальными данными:
- блок «▶ СЕЙЧАС»: Chunk = первый чанк, который НЕ полностью DONE; Task = первая невыполненная FOS в нём; State; Next action;
- «📊 ПРОГРЕСС»: посчитай X/23 задач и нарисуй прогресс-бар; X/9 чанков;
- «🚦 GATE HEALTH»: проставь ✅/❌/❓ и дату по фактическим прогонам;
- «✅ CHUNKS»: проставь [x]/[~]/[ ]/[!] по каждой FOS;
- «⛔ BLOCKERS»: если что-то мешает двигаться — впиши;
- «🧾 SESSION LOG»: добавь строку с датой и итогом аудита.

Ограничения: НЕ менять код приложения и миграции. Разрешено только создать/перезаписать PROGRESS.md. Если для проверок надо что-то установить — ставь во временное окружение, репозиторий не трогай.

В конце напечатай человеку короткое резюме (5 строк максимум):
  «Вы на: CHUNK N / FOS-XXX. Готово: A/23. Gate-проблемы: …. Следующий шаг (Prompt B): сделать FOS-XXX».
```

---

## PROMPT B — EXECUTE (запускать по кругу, по одному на чанк)

> Скопируй целиком. Запускай повторно: после закрытия чанка тот же промпт возьмёт следующий.

```text
Ты — исполнитель проекта founderOS. Работай строго по EXECUTION_PLAN.md и founderOS_MASTER_PLAYBOOK.md. Прогресс — в PROGRESS.md.

ШАГ 0 — определи позицию:
- Прочитай PROGRESS.md → возьми текущий Chunk и текущую Task.
- Если PROGRESS.md пустой/неактуальный — сначала выполни аудит (как в Prompt A), потом продолжай.
- Прочитай в playbook секции, указанные для текущего чанка в EXECUTION_PLAN.md (§12 спека задачи + §6/§7/§8/§9/§10 по ссылкам).

ЖЕЛЕЗНЫЕ ПРАВИЛА:
- Работай ТОЛЬКО внутри текущего чанка. Следующий чанк не начинать.
- Внутри чанка иди по задачам FOS-XXX по порядку.
- Plan-first: перед кодом — список файлов и «что НЕ трогаю».
- Минимально под acceptance criteria. Никаких улучшений «заодно».
- Рефакторинг запрещён до зелёного GitHub E2E (CHUNK 3).
- Новые идеи → строкой в docs/POST_MVP.md, НЕ в код.
- Каждый AI-claim с evidence; внешние write только после approval.

ЦИКЛ НА КАЖДУЮ ЗАДАЧУ:
1) plan (файлы + что не трогаю)
2) implement (минимально)
3) verify: targeted tests / alembic / build по типу задачи.
   Если red → чини здесь же (до 3 сфокусированных попыток) → verify снова.
4) update PROGRESS.md: пометь задачу [x], пересчитай прогресс-бар (N/23), обнови GATE HEALTH, добавь строку в SESSION LOG.
5) commit: feat(scope): ... (или fix/test/docs). Checkpoint перед миграциями и после зелёных тестов.
6) report ОДНОЙ строкой: «✅ FOS-XXX done — N/23 · gate: … · next: FOS-YYY».

ПОСЛЕ ПОСЛЕДНЕЙ ЗАДАЧИ ЧАНКА:
- Прогони GATE чанка (см. EXECUTION_PLAN.md).
- Если ✅: пометь чанк готовым в PROGRESS.md, сделай git checkpoint, напечатай «🎯 CHUNK N COMPLETE — gate passed». Подскажи: запусти Prompt B снова для следующего чанка.
- Если ❌: чини. Не вышло за разумное число попыток → впиши блокер в PROGRESS.md (что сломано + repro + один конкретный вопрос) и остановись.

ЕСЛИ ЗАСТРЯЛ на любой задаче:
- Stop. Минимальный repro. Один вопрос по одному багу. Блокер — в PROGRESS.md. Не молотить вслепую.

НА ВЫХОДЕ: репозиторий зелёный, PROGRESS.md точный, последний commit сделан. Напечатай текущий прогресс-бар.
```

---

## Шпаргалка запуска

```
1) Prompt A  → один раз. Узнали, где мы. PROGRESS.md заполнен.
2) Prompt B  → довели текущий чанк до gate.
3) Prompt B  → следующий чанк.
   ... повтор до CHUNK 8.
В любой момент: открыл PROGRESS.md → видно где мы, % готовности, что сломано.
```

> Работает одинаково в **Claude Code** и **Codex** — промпты ссылаются только на файлы и shell-проверки, ничего агент-специфичного.
