# founderOS — PROGRESS (live state / single source of truth)

> Это **живой файл состояния**. Его обновляет агент (Claude Code / Codex) после КАЖДОЙ задачи.
> Человек смотрит сюда, чтобы за 5 секунд понять: **где мы и что дальше.**
> ⚠️ Перед первым запуском прогони **Prompt A (Audit)** — он перезапишет этот файл реальным состоянием репозитория.

---

## ▶ СЕЙЧАС

- **Chunk:** `CHUNK 0 — Audit & Docs`
- **Task:** `FOS-000`
- **State:** ❓ not started — запусти audit
- **Next action:** запустить Prompt A

---

## 📊 ПРОГРЕСС

```
Tasks:  0 / 23   ▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱   0%
Chunks: 0 / 9
```

**Легенда статусов задачи:** `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked

---

## 🚦 GATE HEALTH (результат последней проверки)

| Gate | Status | Last checked |
|---|---|---|
| `alembic upgrade head` | ❓ unknown | — |
| backend tests (`pytest`) | ❓ unknown | — |
| `ruff` | ❓ unknown | — |
| frontend build | ❓ unknown | — |
| **GitHub E2E (spine)** | ❓ unknown | — |
| **full main E2E** | ❓ unknown | — |
| prod smoke | ❓ unknown | — |

Статусы: ✅ pass · ❌ fail · ❓ unknown

---

## ✅ CHUNKS

### CHUNK 0 — Audit & Docs
*Gate: PROGRESS.md заполнен реальным состоянием; `docs/` создан.*
- [ ] FOS-000 — Repository baseline audit (без изменений кода)
- [ ] FOS-001 — Project docs: DECISIONS / ROADMAP / TODO / POST_MVP / CHANGELOG

### CHUNK 1 — Data Foundation
*Gate: `alembic upgrade head` ✅ · model tests ✅ · encryption roundtrip test ✅.*
- [ ] FOS-002 — Core DB models (23 модели §6) + migrations + tests
- [ ] FOS-003 — Encryption utility (encrypt/decrypt токенов, `ENCRYPTION_KEY`)

### CHUNK 2 — Connector Framework
*Gate: mock-коннектор создаёт SourceRecord + NormalizedEntity + EvidenceRef (доказано тестом).*
- [ ] FOS-004 — Base connector interface (контракт)
- [ ] FOS-005 — Sync service (raw SourceRecords)
- [ ] FOS-006 — Normalization service (+ EvidenceRef)

### CHUNK 3 — GitHub E2E (SPINE) 🎯 критический milestone
*Gate: пользователь подключает GitHub через UI → sync проходит → данные видны в Dashboard и Brain.*
- [ ] FOS-007 — GitHub OAuth
- [ ] FOS-008 — GitHub sync repositories
- [ ] FOS-009 — GitHub sync issues + PRs
- [ ] FOS-010 — Connectors UI page
- [ ] FOS-011 — Dashboard v0
- [ ] FOS-012 — Brain entity API + UI

### CHUNK 4 — Briefing MVP
*Gate: пользователь генерирует briefing с evidence drawer.*
- [ ] FOS-013 — Briefing backend (context pack + LLM + JSON validation)
- [ ] FOS-014 — Briefing UI + evidence drawer

### CHUNK 5 — Action Approval 🎯 full main E2E complete
*Gate: approved action создаёт реальный GitHub issue.*
- [ ] FOS-015 — Action proposal API (approve/reject + execution worker)
- [ ] FOS-016 — GitHub create-issue action

### CHUNK 6 — Remaining Connectors
*Gate: Jira / Gmail / Drive / Documents видны в Brain.*
- [ ] FOS-017 — Jira connector minimal
- [ ] FOS-018 — Gmail connector minimal (+ summarize)
- [ ] FOS-019 — Drive connector minimal
- [ ] FOS-020 — Documents module (CRUD + tags + search + Brain)

### CHUNK 7 — Polish + Repo Audit UI
*Gate: нет dead-end состояний; repo audit виден в UI.*
- [ ] FOS-021 — Repo Audit UI
- [ ] FOS-P — Polish: errors / retries / empty states / filters / evidence UX / action-failure UX (§Phase 5)

### CHUNK 8 — Testing Gate + Deploy
*Gate: launch gate зелёный; production URL работает; первый E2E проходит в проде.*
- [ ] FOS-022 — Smoke tests
- [ ] FOS-T — Full backend tests + frontend build + integration tests (§16)
- [ ] FOS-D — Deploy: Railway (DB/Redis/backend/worker/frontend/migrations/smoke) (§19)

---

## ⛔ BLOCKERS

*(пусто)*

<!--
Формат блокера:
- [FOS-XXX] <одна строка: что именно сломано>
  repro: <минимальные шаги/команда>
  нужно от человека: <конкретный вопрос ИЛИ "ничего, чиню сам">
-->

---

## 🧾 SESSION LOG (append-only, новое — сверху)

- `INIT` — template создан, состояние не проверено. Запусти Prompt A.
