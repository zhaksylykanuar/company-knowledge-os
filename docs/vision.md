# FounderOS Vision (North Star)

Операционная память компании и AI second opinion фаундера. Этот документ —
карта направления. Закон исполнения — [`playbook.md`](playbook.md):
вертикальные срезы, usage gates, WIP=1. Фазы ниже открываются только
воротами использования, не по плану.

## Формула

```
Company Knowledge Graph + Current Status Engine + Engineering Reality Check
+ Meeting Intelligence + Jira Action Layer + Telegram Founder Copilot
= AI Second Opinion: «что реально происходит» вместо «что написано в Jira»
```

Killer-флоу: фаундер пишет в Telegram «что у нас с SSAP?» и получает
управленческий ответ — статус, изменения, блокеры, риски, расхождения
источников, рекомендации, источники, уверенность.

## Принципы

1. Evidence или молчание: каждый факт ссылается на источники
   (`evidence_refs` — инвариант репо). Нет данных → «данных не хватает».
2. Конфликты источников не скрываются — это контент ответа.
3. Источники правды ранжированы: код > Jira > чат; письма/транскрипты >
   пересказов; последняя утверждённая спека > старых документов;
   Calendar — правда о времени и участниках.
4. Pull > Push. Telegram — командная строка фаундера, не лог событий.
   Push только по правилам значимости.
5. Read свободен, write через подтверждение (guards + approval-цепочка).
6. Никакой ручной разметки шума: значимость определяют LLM-триаж и
   детерминированные правила; пометки фаундера — опциональный сигнал.
7. Уверенность всегда явная и считается формулой (свежесть, покрытие,
   конфликты), а не выбирается LLM.

Анти-принципы: не поиск по документам, не дайджест-пересказ, не
Jira-статистика, не спам, не фантазии без источников, не уверенные ответы
на неполных данных, не секреты/коды в чате.

## Карта «есть / нет» (на момент v1)

| Слой | Состояние |
|---|---|
| Source Connectors | есть: Gmail, Drive, GitHub org, Jira (read-only); нет: Calendar, транскрипты, Telegram-inbound |
| Sync | ручной backfill; нет periodic workers/webhooks |
| Normalization | есть: IngestedEvent → SourceEvent → NormalizedActivityItem |
| Extraction | есть: задачи/риски/решения с evidence; расширить: обещания, требования |
| Entity Resolution | нет — ключевой новый кирпич |
| Knowledge Graph links | нет — ключевой новый кирпич (`entity_links`) |
| Status Engine | нет — ключевой новый кирпич (`status_snapshots`) |
| Retrieval/Reasoning | есть детерминированные search/ask; нет pgvector, intent, FounderAnswer |
| Action Layer | есть approval-цепочка + audit; Jira write readiness/dry-run готовы; самого write нет |
| Telegram | есть outbound + digest v2; нет inbound bot |
| Security | guards, audit, sanitizer, маскирование кодов — реализовано |
| Dashboard | нет (Фаза F) |

Недостающее ядро — «большая четвёрка»: inbound Telegram bot,
Entity Resolution + graph links, Status Engine, Answer-пайплайн.

## Data model (расширение существующей схемы)

Новые таблицы: `entities`, `entity_aliases`, `entity_links` (relation enum по
связям из vision-промпта), `status_snapshots` (версионно, supersedes),
`contradiction_findings` (детекторы second opinion), `founder_questions`
(вопрос → intent → ответ → evidence), `document_chunks.embedding`
(pgvector). Существующие таблицы остаются source of truth; граф ссылается
на них через `entities(entity_type, attrs.source_ref)`.

## Ключевой контракт ответа

```python
class FounderAnswer(StrictModel):
    status: Literal["green", "yellow", "red"] | None
    headline: str                      # управленческий вывод, 1-3 предложения
    what_changed: list[str]
    in_progress: list[str]
    blockers: list[str]
    risks: list[str]
    owners: list[dict]                 # {name, area, activity_signal}
    second_opinion: str | None         # только если есть расхождения
    recommendations: list[str]
    confidence: Literal["high", "medium", "low"]
    confidence_reasons: list[str]
    data_gaps: list[str]
    evidence_refs: list[dict]
```

Все LLM-агенты — по образцу `AttentionTriageResult`: strict JSON,
schema-валидация, conservative fallback, evals в CI.

## Status Engine

Триггеры: значимое событие, вопрос фаундера (snapshot старше N часов),
ежедневный worker. Алгоритм: окно событий проекта с прошлого snapshot →
детекторы противоречий → LLM-синтез snapshot → `what_changed` = diff с
предыдущим → confidence по формуле (high: источники свежее 48ч и нет
конфликтов; medium: один стар или 1 конфликт; low: ключевой источник
молчит или конфликтов ≥2).

## Second opinion = детерминированные детекторы + LLM-нарратив

15 проверок (Jira активна/GitHub молчит; GitHub активен/Jira нет; письмо
клиента без backlog; решение встречи без задачи; просрочка при зелёном
статусе; stale review; merged-но-in-progress; «готово» в чате при открытом
PR; документ обновлён/задачи нет; встреча без agenda; обещание без
milestone; конфликт версий статуса; устаревший документ в ссылках; клиент
ждёт без задачи; bottleneck по review) — это SQL-правила над графом с
evidence и severity. LLM только формулирует оценку. Каждый детектор имеет
ключ, пишет в `contradiction_findings`, попадает в snapshot, `/risks` и
push (severity high).

## Q&A-пайплайн

```
update (polling) → allowlist chat_id → intent (LLM, strict JSON)
→ entity resolution (алиасы: SSAP/ССАП → project:ssap)
→ context: snapshot + graph + детекторы + pgvector + свежие события
→ FounderAnswer (schema-validated, fallback «данных не хватает»)
→ рендер по шаблону + кнопки → audit
```

Решения: polling (getUpdates) в MVP, webhook в Фазе E; кнопки — inline
callbacks, маппятся на команды. Команды: /status /changes /risks /dev
/blocked /reviews /stale /calendar /prep /followups /create-task /sources
/decisions /people /client + свободный язык через intent-агента.

## Sync

Periodic pull workers за существующими guard'ами (Jira/GitHub/Gmail/
Calendar 15 мин, Drive 1 ч), идемпотентность через ingestion boundary.
`source_health`: алерт при молчании источника > 2 интервалов. Webhooks —
Фаза E.

## Security

Реализовано: default-deny guards (provider/production/scheduler), audit
log, sanitizer, маскирование verification-кодов, approval-цепочка для
write. Добавить: chat_id allowlist (inbound), project-level permissions —
Фаза G. Trace «что агент видел» = evidence_refs + persisted ответы.

## Фазы с usage gates

| Фаза | Содержание | Gate выхода |
|---|---|---|
| A. Telegram Q&A read-only | inbound bot, алиасы 3 проектов, Jira+GitHub sync, Status Engine v1, /status /followups /calendar | «что у нас с SSAP?» полезен 5 дней подряд |
| B. Engineering Intelligence | Jira↔GitHub линковка, детекторы, /dev /reviews /stale | /dev находит подтверждённый bottleneck |
| C. Meeting Intelligence | Calendar deep, briefing за 30–60 мин, транскрипты | брифинг полезен перед 5 звонками подряд |
| D. Jira Action Layer | задачи из писем/встреч через [Создать][Изменить][Отмена] | 10 задач создано через подтверждение |
| E. Proactive Second Opinion | push по правилам значимости, webhooks | неделя push без «зря отвлёк» |
| F. Dashboard | web-карта компании | открывается чаще 2 раз в неделю |
| G. Multi-agent OS | команда, RBAC, recurring reports | командное использование |

Дневной digest-пилот не выбрасывается: он становится вечерним кратким
дайджестом (режим 2 доставки) и донором push-канала Фазы E.

Бэклог Фазы A: A1 inbound bot + allowlist + /status на текущих данных →
A2 entities/aliases/links + резолюция SSAP/qTwin/Интегра → A3 Jira sync →
A4 GitHub sync → A5 Status Engine v1 (snapshot SSAP) → A6 intent +
FounderAnswer + evals → A7 Calendar read + /calendar /followups.

## Риски и tradeoffs

1. Главный риск — сам этот документ (история репо: большой план без
   usage gate = леса). Лекарство: фазы открываются только воротами.
2. Entity resolution: мусор на входе — мусор везде; старт со словаря
   алиасов руками.
3. Push-спам: правила значимости как детекторы с evals; Фаза E последняя.
4. Privacy: письма идут в OpenAI (уже принятое решение), sanitizer на
   выходе обязателен.
5. Polling delay до 15 мин в MVP — осознанный trade-off против публичного
   эндпоинта.
6. Jira write — самый опасный слой, поэтому Фаза D после доверия к read.
