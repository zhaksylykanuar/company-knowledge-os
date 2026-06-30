# founderOS MASTER PLAYBOOK / GUIDE

**Версия:** 1.0  
**Назначение:** единый главный документ для разработки founderOS через Claude Code / Codex / Cursor / AI-агентов.  
**Правило:** этот файл является главным источником решений по MVP. Если агент, новая идея или внешний пример противоречит этому документу, сначала обновляется `DECISIONS.md`, потом код.  
**Статус:** scope lock для MVP.

---

## Текущий статус реализации (видение vs. реальность)

Этот документ — **целевое product-видение и scope-lock MVP**, а не отчёт о
текущем состоянии кода. Каноничный статус «что уже сделано» живёт в
`PROGRESS.md` и `docs/TODO.md`; при расхождении доверять им, а не этому файлу.

Сегодня в коде реализован детерминированный, evidence-first спайн:

- единый backend FastAPI на канонических путях `/api/v1`; `web/` (Next.js) —
  единственный фронтенд (статический `/ui` удалён), с русским UI через
  центральный каталог сообщений `web/lib/messages.ts`;
- продуктовый логин **email+password на серверных сессиях** (Argon2id, httpOnly
  first-party cookie через same-origin прокси, DB-throttle перебора): эндпоинты
  `/api/v1/auth/login|logout|me|change-password`, страница `/login`, аккаунт в
  Settings; операторская аутентификация по API-ключу сохраняется для
  server/CI/админ-скриптов и сосуществует с сессией (fail-closed вне local/dev);
- GitHub через provider-token connection: read-only нормализация
  репозиториев / issues / PR в канонические таблицы (идемпотентный `ON CONFLICT`
  upsert), Company Brain и ручной evidence-брифинг, плюс human-approved guarded
  write-back одного GitHub issue;
- детерминированные проекции без LLM: Company Brain и Founder Briefing считаются
  из локальных данных и несут `evidence_refs`; ручные Founder Briefings уже
  сохраняются в `Briefing` / `BriefingItem` с историей.

Ещё **не** реализовано (остаётся видением этого плана, а не текущим кодом):

- GitHub OAuth/App start/callback/connect и живая продуктовая синхронизация;
- LLM-брифинг-пайплайн поверх уже персистентной модели;
- продуктовые пути Jira / Gmail / Drive / Documents;
- мультиюзер/онбординг (сейчас один основатель, заводится через
  `scripts/create_admin_user.py`);
- остальные страницы (`/connectors`, `/jira`, `/gmail`, ...), rate limiting,
  webhook-подписи.

---

## Краткая реконструкция проекта из контекста чата

Ты строишь **founderOS** - AI-native операционную систему для основателя и маленькой команды. Пользователь должен работать с компанией через один UI: видеть задачи, репозитории, pull requests, письма, документы, аудит репозитория, Company Brain, брифинги и предлагаемые действия. Пользователь не хочет работать через терминал, код, ручные команды или набор разрозненных вкладок.

Главная проблема: у founder / operator данные компании живут в Jira, GitHub, Google Drive, Gmail, документах, коде и переписках. Чтобы понять состояние компании, приходится открывать 5-10 инструментов и вручную собирать картину. founderOS должен убрать этот налог на управление.

Из переписки зафиксированы основные идеи:

- система должна быть **много-модульной**;
- модули должны быть независимыми по логике, но работать в одном UI;
- основные коннекторы: **Jira, GitHub, Google Drive, Gmail, Documents**;
- уже обсуждены модули **company_brain, repo_audit, repository_source_inventory**;
- уже была локальная проверка текущего WIP: тесты, ruff, migrations, secret scan, compileall были зелёными по предоставленному отчёту Claude;
- цель смещена с “строить новое без оглядки” на “быстро собрать рабочую платформу, не утонув в security/compliance”; 
- безопасность не должна блокировать MVP, но архитектура не должна быть опасной и непоправимой;
- вдохновение из статьи `From Company Brain to an AI Operating System`: собрать сигналы, нормализовать, строить Company Brain, выводить insights, оценивать goals, делать role briefings и позже выполнять workflow в sandbox;
- MVP не должен сразу копировать всю сложность AI Operating System;
- сначала нужен один end-to-end flow, потом расширение.

**Главное зафиксированное решение для MVP:** founderOS строится как **модульный монолит** с единым backend, единым frontend, общей базой данных, connector framework, Company Brain, briefing engine и human-approved action flow.

---

# 1. Executive Summary

## 1.1 Что мы строим

Мы строим **founderOS** - веб-платформу для основателя, которая объединяет рабочие источники компании в один управляемый интерфейс.

MVP founderOS должен позволять:

1. войти в систему;
2. создать workspace компании;
3. подключить GitHub, Jira, Gmail, Google Drive;
4. синхронизировать данные;
5. видеть данные в едином UI;
6. открыть Company Brain;
7. получить Founder Briefing;
8. увидеть evidence для каждого AI-вывода;
9. получить action proposal;
10. подтвердить действие вручную;
11. увидеть результат выполнения действия.

## 1.2 Зачем это нужно

founderOS нужен, чтобы заменить хаотичный набор вкладок на один операционный центр.

Пользователь больше не должен вручную спрашивать:

- какие PR застряли;
- какие Jira задачи просрочены;
- какие письма требуют ответа;
- где лежит важный документ;
- что изменилось со вчера;
- что требует моего внимания сейчас;
- какие действия надо сделать.

Система должна сама собрать данные, показать статус, объяснить важное и предложить следующий шаг.

## 1.3 Кто пользователь

### MVP пользователь

- founder;
- solo founder;
- technical founder;
- CTO-founder;
- operator в маленькой команде;
- человек, который управляет продуктом, задачами, кодом, письмами и документами.

### После MVP

- product lead;
- engineering manager;
- operations lead;
- investor relations;
- маленькая команда 3-20 человек.

## 1.4 Успешный результат MVP

MVP успешен, если пользователь может пройти этот путь:

```txt
Login
-> Create Workspace
-> Connect GitHub
-> Sync GitHub
-> See Dashboard
-> See Company Brain entities
-> Generate Founder Briefing
-> Open Evidence
-> Approve Action Proposal
-> See External Action Result
```

Это главный end-to-end flow. Всё остальное вторично.

## 1.5 Что входит в MVP

Обязательно:

- auth;
- workspace;
- UI shell;
- connector framework;
- GitHub connector;
- Jira connector минимально;
- Gmail connector минимально;
- Google Drive connector минимально;
- internal documents;
- raw source records;
- normalized entities;
- evidence refs;
- Company Brain view;
- Founder Dashboard;
- Repo Audit view;
- manual Founder Briefing;
- action proposals;
- human approval before execution;
- basic logging;
- basic tests;
- staging/prod deployment.

## 1.6 Что НЕ входит в MVP

Не входит:

- автономные агенты без подтверждения;
- multi-model council;
- natural language rule compiler;
- sandbox execution для LLM-generated code;
- полный workflow builder;
- marketplace integrations;
- billing/payments;
- mobile app;
- enterprise RBAC;
- SOC2/compliance program;
- Slack connector;
- Stripe connector;
- HubSpot/Salesforce connector;
- полноценный graph database;
- vector-only architecture;
- отправка писем без human review.

## 1.7 Главные ограничения

- пользователь работает через UI;
- никакой обязательной работы через терминал для пользователя;
- AI не имеет права делать external write без approval;
- каждый AI claim должен иметь evidence;
- сначала GitHub E2E, потом остальные коннекторы;
- не начинать новую большую идею, пока главный flow не работает;
- security baseline обязателен, но advanced compliance после launch.

---

# 2. North Star Vision

## 2.1 Финальное видение продукта

founderOS должен стать **AI Operating System для компании**.

В идеале пользователь утром открывает один экран и видит:

- что изменилось с последнего открытия;
- что застряло;
- где риск;
- какие PR требуют внимания;
- какие задачи просрочены;
- какие письма требуют ответа;
- какие документы важны;
- какие цели под угрозой;
- какие действия система предлагает;
- почему система так считает;
- откуда взят каждый факт.

Система должна развиться от dashboard к Company Brain, потом к AI Briefing, потом к human-approved execution, потом к controlled automation.

## 2.2 Ценность для пользователя

founderOS даёт:

- единый рабочий центр;
- меньше вкладок;
- меньше ручного мониторинга;
- меньше хаоса;
- больше операционной ясности;
- быстрое понимание состояния компании;
- AI, который опирается на факты;
- действия, а не просто summary.

## 2.3 Главный пользовательский путь

```txt
Connect sources
-> Sync data
-> Normalize into Company Brain
-> Show Dashboard
-> Generate Briefing
-> Explain with Evidence
-> Propose Action
-> Human Approves
-> Execute through Connector
-> Log Result
```

Это продуктовая ось. Все модули должны обслуживать эту ось.

## 2.4 Принципы продукта

1. **Сначала рабочий end-to-end flow, потом улучшения.**
2. **Один source of truth для каждой категории данных.**
3. **Raw records immutable, normalized entities updatable.**
4. **Каждый модуль имеет явный контракт.**
5. **Каждый AI claim имеет evidence.**
6. **AI не выполняет внешние действия без approval.**
7. **UI должен показывать источник, статус и ошибку.**
8. **Не делать магические функции без понятной логики.**
9. **Не начинать новый модуль, пока старый не usable.**
10. **Любая сложность должна сокращать путь пользователя, а не украшать архитектуру.**

## 2.5 Продуктовые запреты

Нельзя:

- строить красивую AI-фантазию до рабочего sync;
- превращать MVP в security/compliance-проект;
- превращать MVP в no-code builder;
- добавлять новый connector до usable GitHub flow;
- делать autonomous agents до audit trail;
- делать workflow execution до human approval;
- прятать ошибки provider API;
- показывать AI-брифинг без evidence.

---

# 3. Scope Lock: что именно делаем

## 3.1 MVP - обязательно

### Core platform

- user auth;
- workspace;
- membership;
- app shell;
- settings;
- connector settings;
- background jobs;
- sync status;
- audit log.

### Data layer

- integration connections;
- encrypted tokens;
- source records;
- normalized entities;
- evidence refs;
- sync jobs;
- documents;
- briefings;
- action proposals.

### Connectors

- GitHub read + one approved write;
- Jira read minimal;
- Gmail read minimal;
- Drive read minimal;
- Documents internal CRUD.

### Intelligence

- deterministic insights v0;
- manual Founder Briefing;
- evidence validation;
- action proposal generation;
- human approval;
- execution log.

### UI

- Dashboard;
- Connectors;
- GitHub;
- Jira;
- Gmail;
- Drive;
- Documents;
- Company Brain;
- Briefings;
- Actions;
- Repo Audit;
- Settings.

## 3.2 После MVP - можно позже

- scheduled daily briefing;
- role-specific briefings;
- goals tracking;
- natural language rules;
- rule compiler;
- multi-model council;
- sandbox workflows;
- Slack;
- Stripe;
- HubSpot;
- Salesforce;
- analytics connectors;
- vector search;
- graph visualization;
- team roles;
- billing;
- marketplace.

## 3.3 Не делать сейчас

- микросервисы;
- отдельные frontend apps под каждый модуль;
- custom workflow DSL;
- самостоятельный email client full replacement;
- самостоятельная Jira replacement;
- собственный GitHub UI replacement;
- enterprise compliance;
- сложная role matrix;
- “полностью автономный CEO-agent”.

## 3.4 Запрещённые отвлечения

Идеи, которые надо записать в `POST_MVP.md`, но не делать в MVP:

- “подключим сразу 20 сервисов”;
- “сделаем свой no-code builder”;
- “сделаем agent marketplace”;
- “пусть AI сам пишет код в repo”;
- “пусть AI сам отвечает клиентам”;
- “пусть AI сам закрывает Jira tasks”;
- “сразу делаем DecidrOS/Wave/Taskade целиком”;
- “сразу делаем multi-agent council”;
- “сразу делаем sandbox architecture”.

## 3.5 Зафиксированные MVP решения при противоречиях

| Вопрос | Решение MVP |
|---|---|
| Архитектура | Модульный монолит |
| UI | Один Next.js frontend |
| Backend | FastAPI |
| DB | PostgreSQL |
| Jobs | Redis + RQ |
| AI | Один provider через abstraction |
| Actions | Только human-approved |
| Security | Baseline now, hardening later |
| Первый flow | GitHub E2E |
| Search | Postgres full-text first |

---

# 4. Пользовательские сценарии

## 4.1 Flow: первый вход и workspace

### Пользователь

Founder.

### Цель

Создать рабочее пространство компании.

### Шаги

1. Открывает founderOS.
2. Видит login.
3. Входит.
4. Видит onboarding.
5. Создаёт workspace.
6. Видит checklist подключения источников.
7. Переходит к Connectors.

### Экраны

- Login;
- Create Workspace;
- Onboarding;
- Connectors;
- Dashboard empty state.

### Данные

Создаются:

- User;
- Workspace;
- Membership;
- AuditLog.

### Успех

Пользователь видит Dashboard с понятным next step: “Connect GitHub”.

### Edge cases

- email уже занят;
- session expired;
- workspace уже создан;
- ошибка DB;
- пользователь открыл app без workspace.

---

## 4.2 Flow: подключение GitHub

### Пользователь

Founder / CTO.

### Цель

Подключить GitHub и увидеть репозитории, issues, PRs.

### Шаги

1. Открывает Connectors.
2. Нажимает Connect GitHub.
3. Проходит OAuth.
4. Возвращается в founderOS.
5. Видит connected status.
6. Нажимает Sync now.
7. Видит sync job status.
8. Открывает GitHub page.
9. Видит repositories, PRs, issues.

### Экраны

- Connectors;
- GitHub connection detail;
- Sync status;
- GitHub repositories;
- GitHub pull requests;
- GitHub issues.

### Данные

Создаются:

- IntegrationConnection;
- SyncJob;
- SourceRecord;
- Repository;
- Task;
- PullRequest;
- EvidenceRef;
- AuditLog.

### Успех

GitHub данные появились в Dashboard и Company Brain.

### Edge cases

- OAuth denied;
- token expired;
- rate limit;
- private repo no access;
- archived repo;
- duplicate issue;
- partial sync;
- provider API changed.

---

## 4.3 Flow: Founder Dashboard

### Пользователь

Founder.

### Цель

Понять состояние компании за 1-2 минуты.

### Шаги

1. Открывает Dashboard.
2. Видит status подключений.
3. Видит last sync.
4. Видит active risks.
5. Видит stale PRs/tasks.
6. Видит recent important emails.
7. Видит кнопку Generate Briefing.
8. Переходит в briefing.

### Экраны

- Dashboard;
- Evidence Drawer;
- Briefing Button;
- Action Proposal Preview.

### Данные

Читаются:

- SyncJob;
- NormalizedEntity;
- Insight;
- Briefing;
- ActionProposal.

### Успех

Пользователь понимает, что требует внимания.

### Edge cases

- нет данных;
- один connector failed;
- sync stale;
- AI unavailable;
- contradictory source data.

---

## 4.4 Flow: Company Brain

### Пользователь

Founder.

### Цель

Найти и проверить факты компании.

### Шаги

1. Открывает Company Brain.
2. Видит entities.
3. Фильтрует по типу.
4. Открывает entity.
5. Видит source records.
6. Видит evidence refs.
7. Переходит во внешний источник.

### Экраны

- Brain entity list;
- Entity detail;
- Source records;
- Evidence drawer;
- Related entities.

### Данные

Читаются:

- NormalizedEntity;
- SourceRecord;
- EvidenceRef;
- EntityLink.

### Успех

Пользователь может проверить любой факт.

### Edge cases

- source deleted;
- evidence missing;
- duplicate entity;
- stale data.

---

## 4.5 Flow: Founder Briefing

### Пользователь

Founder.

### Цель

Получить AI-брифинг с важными событиями и предложенными действиями.

### Шаги

1. Нажимает Generate Briefing.
2. Backend собирает context pack.
3. LLM получает structured input.
4. LLM возвращает JSON.
5. Backend валидирует JSON.
6. Backend отбрасывает claims без evidence.
7. UI показывает briefing.
8. Пользователь открывает evidence.
9. Пользователь выбирает action proposal.

### Экраны

- Briefing loading;
- Briefing list;
- Briefing detail;
- Evidence drawer;
- Action proposal modal.

### Данные

Создаются:

- Briefing;
- BriefingItem;
- LLMCallLog;
- ActionProposal;
- AuditLog.

### Успех

Briefing содержит только проверяемые пункты.

### Edge cases

- LLM timeout;
- invalid JSON;
- no evidence;
- too much context;
- no important events;
- duplicate proposal.

---

## 4.6 Flow: Action Proposal approval

### Пользователь

Founder.

### Цель

Превратить рекомендацию в действие.

### Пример

AI предлагает: “Create Jira issue to follow up on PR stuck for 5 days.”

### Шаги

1. Открывает proposal.
2. Видит target provider.
3. Видит payload.
4. Проверяет evidence.
5. Нажимает Approve или Reject.
6. Если Approve - backend выполняет action.
7. UI показывает result.
8. AuditLog фиксирует действие.

### Экраны

- Action proposal list;
- Action detail;
- Approval modal;
- Execution status.

### Данные

Обновляются:

- ActionProposal;
- ActionExecution;
- AuditLog;
- SourceRecord after provider response.

### Успех

Внешнее действие выполнено только после approval.

### Edge cases

- token expired;
- permission denied;
- duplicate approval;
- provider timeout;
- created externally but response failed;
- user rejects.

---

## 4.7 Flow: Documents

### Пользователь

Founder.

### Цель

Создать внутренний документ и использовать его в Company Brain.

### Шаги

1. Открывает Documents.
2. Нажимает New Document.
3. Пишет title и body.
4. Добавляет tags.
5. Сохраняет.
6. Документ появляется в Brain.
7. Briefing может использовать документ как context.

### Экраны

- Documents list;
- Document editor;
- Document detail;
- Related entities.

### Данные

Создаются:

- Document;
- DocumentVersion;
- NormalizedEntity;
- EvidenceRef.

### Успех

Документ доступен в Brain и search.

### Edge cases

- autosave fail;
- empty title;
- huge body;
- conflict;
- deleted linked entity.

---

# 5. Архитектура системы

## 5.1 Зафиксированный стек

### Backend

**Python + FastAPI + SQLAlchemy + Alembic + PostgreSQL**

Причины:

- текущий проект уже похож на Python/FastAPI;
- уже есть Alembic migrations;
- уже есть pytest/ruff;
- уже есть WIP вокруг company_brain, repo_audit, drive/gmail;
- переписывать стек сейчас опасно.

### Frontend

**Next.js + TypeScript + Tailwind + shadcn/ui**

Причины:

- быстрый production UI;
- хорошие таблицы, forms, drawers;
- удобно работать AI-агентам;
- легко держать app shell и modules.

### Database

**PostgreSQL**

Причины:

- связи;
- JSONB для raw payload;
- индексы;
- full-text search;
- later pgvector.

### Background jobs

**Redis + RQ**

Причины:

- проще Celery;
- достаточно для sync jobs;
- проще debugging;
- подходит MVP.

### Storage

MVP:

- documents в PostgreSQL;
- Drive files не копируются полностью;
- храним metadata, source_url, extracted_text;
- binary storage после MVP.

### AI

- один provider через `LLMService`;
- strict JSON;
- schema validation;
- evidence required;
- no direct external writes.

### Deployment

**Railway** для MVP.

Причины:

- быстрый deploy;
- Postgres + Redis;
- несколько services;
- GitHub deploy;
- подходит для early launch.

---

## 5.2 Backend layers

```txt
API Routes
-> Services
-> Connectors / Repositories
-> Database
-> Jobs
```

### API Routes

Отвечают за:

- request validation;
- auth dependency;
- workspace access;
- calling services;
- response schemas.

Не делают:

- provider API calls напрямую;
- normalization logic;
- AI prompt assembly.

### Services

Отвечают за:

- business logic;
- sync orchestration;
- action approval;
- briefing generation;
- audit logging.

### Connectors

Отвечают за:

- provider clients;
- provider pagination;
- provider auth refresh;
- provider-specific mapping.

Не отвечают за:

- UI;
- database transactions outside sync contract;
- AI logic.

### Jobs

Отвечают за:

- async sync;
- action execution;
- long LLM runs later;
- retries.

---

## 5.3 Frontend layers

```txt
Pages
-> Feature Components
-> Shared Components
-> API Client
-> Types
```

### Pages

- route-level UI;
- data fetching;
- loading/error/empty state.

### Feature components

- connector cards;
- entity table;
- briefing item;
- evidence drawer;
- action modal.

### Shared components

- buttons;
- tables;
- badges;
- forms;
- layout.

### API client

- typed fetch wrapper;
- error normalization;
- no direct provider API calls.

---

## 5.4 Suggested folder structure

```txt
repo/
  app/
    api/
      routes/
        auth.py
        workspaces.py
        connectors.py
        sync.py
        github.py
        jira.py
        gmail.py
        drive.py
        documents.py
        brain.py
        briefings.py
        actions.py
        repo_audit.py
      deps.py
      schemas/
    core/
      config.py
      security.py
      encryption.py
      logging.py
      errors.py
    db/
      session.py
      base.py
      migrations/
    models/
      user.py
      workspace.py
      integration.py
      sync_job.py
      source_record.py
      entity.py
      document.py
      briefing.py
      action.py
      audit_log.py
    services/
      auth_service.py
      workspace_service.py
      connector_service.py
      sync_service.py
      normalization_service.py
      brain_service.py
      briefing_service.py
      action_service.py
      llm_service.py
      repo_audit_service.py
    connectors/
      base.py
      github/
        client.py
        mapper.py
        sync.py
        actions.py
      jira/
        client.py
        mapper.py
        sync.py
        actions.py
      gmail/
        client.py
        mapper.py
        sync.py
      drive/
        client.py
        mapper.py
        sync.py
    jobs/
      worker.py
      sync_jobs.py
      action_jobs.py
      briefing_jobs.py
    tests/
  web/
    app/
      layout.tsx
      page.tsx
      login/
      dashboard/
      connectors/
      github/
      jira/
      gmail/
      drive/
      documents/
      brain/
      briefings/
      actions/
      settings/
    components/
      layout/
      ui/
      connectors/
      tables/
      evidence/
      briefing/
      actions/
    lib/
      api.ts
      errors.ts
      types.ts
    tests/
  docs/
    PLAYBOOK.md
    ROADMAP.md
    DECISIONS.md
    TODO.md
    POST_MVP.md
    CHANGELOG.md
```

## 5.5 Что нельзя смешивать

Нельзя:

- frontend -> provider API directly;
- connector -> UI logic;
- AI service -> direct provider writes;
- normalization -> OAuth;
- action execution -> bypass approval;
- source records -> overwrite raw payload silently;
- logs -> include tokens;
- routes -> hold business logic.

---

# 6. Data Model

## 6.1 Source of truth rules

| Data | Source |
|---|---|
| GitHub repo/issue/PR | GitHub |
| Jira issue | Jira |
| Gmail thread/message | Gmail |
| Drive file | Google Drive |
| Internal doc | founderOS |
| Briefing | founderOS |
| Action proposal | founderOS |
| Raw snapshot | founderOS copy |

Rules:

- external providers remain source of truth for their own objects;
- founderOS stores snapshots and normalized views;
- raw source records are append/update-by-observation, not rewritten manually;
- normalized entities can be updated;
- AI output is never source of truth for external facts;
- evidence refs connect claims to source records.

---

## 6.2 User

### Зачем

Пользователь founderOS.

### Fields

```txt
id: uuid required
email: string required unique
name: string optional
password_hash: string optional
status: active | disabled
created_at: datetime
updated_at: datetime
last_login_at: datetime optional
```

### Relations

- has many Memberships.

### Indexes

- unique email.

### Lifecycle

created -> active -> disabled.

---

## 6.3 Workspace

### Зачем

Компания / рабочее пространство.

### Fields

```txt
id: uuid required
name: string required
slug: string required unique
created_by_user_id: uuid required
status: active | archived
created_at: datetime
updated_at: datetime
```

### Relations

- users through memberships;
- integrations;
- source records;
- entities;
- documents;
- briefings.

---

## 6.4 Membership

### Зачем

Доступ пользователя к workspace.

### Fields

```txt
id: uuid
workspace_id: uuid required
user_id: uuid required
role: owner | admin | member | viewer
created_at: datetime
```

### MVP decision

MVP использует `owner` и basic membership check. Полная RBAC после MVP.

---

## 6.5 IntegrationConnection

### Зачем

Подключение внешнего сервиса.

### Fields

```txt
id: uuid
workspace_id: uuid required
provider: github | jira | gmail | drive
status: connected | error | revoked | disabled
display_name: string optional
external_account_id: string optional
scopes: string[]
encrypted_access_token: text optional
encrypted_refresh_token: text optional
token_expires_at: datetime optional
metadata: jsonb
last_sync_at: datetime optional
last_error: text optional
created_at: datetime
updated_at: datetime
```

### Indexes

```txt
(workspace_id, provider)
(provider, external_account_id)
```

### Lifecycle

created -> connected -> syncing -> connected/error -> revoked.

### Rules

- tokens encrypted;
- no plain tokens;
- frontend never receives token;
- scopes visible to user.

---

## 6.6 SyncJob

### Зачем

Отслеживание sync execution.

### Fields

```txt
id: uuid
workspace_id: uuid
connection_id: uuid
provider: github | jira | gmail | drive
status: queued | running | succeeded | failed | partial
sync_type: initial | incremental | manual
started_at: datetime optional
finished_at: datetime optional
cursor_before: jsonb optional
cursor_after: jsonb optional
records_seen: int
records_created: int
records_updated: int
error_message: text optional
logs: jsonb optional
```

### Indexes

```txt
(workspace_id, status)
(connection_id, started_at)
```

---

## 6.7 SourceRecord

### Зачем

Raw record from external provider.

### Fields

```txt
id: uuid
workspace_id: uuid
provider: github | jira | gmail | drive | internal
connection_id: uuid optional
external_id: string required
record_type: string required
source_url: string optional
payload: jsonb required
payload_hash: string required
observed_at: datetime required
source_updated_at: datetime optional
sync_job_id: uuid optional
is_deleted: bool default false
created_at: datetime
```

### Indexes

```txt
(workspace_id, provider, external_id) unique
(workspace_id, record_type)
payload_hash
source_updated_at
```

### Lifecycle

observed -> normalized -> retained.

### Rules

- never store provider token in payload;
- raw payload can be replaced only by newer observation from provider;
- source record is evidence base.

---

## 6.8 EvidenceRef

### Зачем

Доказательство для entity, insight, briefing, action.

### Fields

```txt
id: uuid
workspace_id: uuid
source_record_id: uuid required
entity_id: uuid optional
quote: text optional
field_path: string optional
source_url: string optional
confidence: float default 1.0
created_at: datetime
```

### Rules

- every AI briefing item must have at least one evidence ref;
- evidence must belong to same workspace;
- no evidence -> no factual claim.

---

## 6.9 NormalizedEntity

### Зачем

Общее представление разных provider objects.

### Fields

```txt
id: uuid
workspace_id: uuid
entity_type: project | task | repository | pull_request | document | message_thread | person | goal
canonical_key: string required
title: string required
status: string optional
summary: text optional
metadata: jsonb
first_seen_at: datetime
last_seen_at: datetime
created_at: datetime
updated_at: datetime
```

### Indexes

```txt
(workspace_id, entity_type)
(workspace_id, canonical_key) unique
full-text(title, summary)
```

---

## 6.10 Project

```txt
id: uuid
workspace_id: uuid
name: string
description: text optional
status: string optional
source: internal | jira | github | mixed
external_refs: jsonb
created_at: datetime
updated_at: datetime
```

---

## 6.11 Task

```txt
id: uuid
workspace_id: uuid
source_provider: github | jira | internal
source_record_id: uuid optional
external_id: string optional
project_id: uuid optional
title: string required
description: text optional
status: string optional
priority: string optional
assignee_person_id: uuid optional
due_date: date optional
source_url: string optional
metadata: jsonb
created_at: datetime
updated_at: datetime
source_updated_at: datetime optional
```

### Indexes

```txt
(workspace_id, status)
(workspace_id, assignee_person_id)
(source_provider, external_id)
```

---

## 6.12 Repository

```txt
id: uuid
workspace_id: uuid
provider: github
external_id: string
name: string
full_name: string
default_branch: string optional
visibility: public | private | internal
archived: bool
source_url: string optional
metadata: jsonb
last_activity_at: datetime optional
```

---

## 6.13 PullRequest

```txt
id: uuid
workspace_id: uuid
repository_id: uuid
external_id: string
number: int
title: string
state: open | closed | merged
author_person_id: uuid optional
source_url: string
created_at_source: datetime optional
updated_at_source: datetime optional
merged_at_source: datetime optional
metadata: jsonb
```

---

## 6.14 MessageThread

```txt
id: uuid
workspace_id: uuid
provider: gmail
external_id: string
subject: string
participants: jsonb
last_message_at: datetime
snippet: text optional
labels: string[]
summary: text optional
metadata: jsonb
```

---

## 6.15 DriveFile

```txt
id: uuid
workspace_id: uuid
external_id: string
name: string
mime_type: string
web_url: string optional
modified_at_source: datetime optional
owners: jsonb optional
size_bytes: int optional
extracted_text: text optional
metadata: jsonb
```

---

## 6.16 Document

```txt
id: uuid
workspace_id: uuid
title: string required
body_markdown: text required
body_text: text required
status: draft | published | archived
tags: string[]
created_by_user_id: uuid
updated_by_user_id: uuid optional
created_at: datetime
updated_at: datetime
```

---

## 6.17 Goal

```txt
id: uuid
workspace_id: uuid
title: string required
description: text optional
metric_name: string optional
target_value: numeric optional
current_value: numeric optional
period_start: date optional
period_end: date optional
owner_user_id: uuid optional
status: active | paused | achieved | missed
created_at: datetime
updated_at: datetime
```

### MVP decision

Goal is stored and used as briefing context. Goal compiler is post-MVP.

---

## 6.18 Insight

```txt
id: uuid
workspace_id: uuid
type: stale_pr | stale_task | email_risk | missing_docs | repo_activity | custom
title: string
summary: text
severity: low | medium | high
status: open | dismissed | resolved
evidence_refs: uuid[]
created_by: system | ai
created_at: datetime
resolved_at: datetime optional
```

---

## 6.19 Briefing

```txt
id: uuid
workspace_id: uuid
title: string
period_start: datetime
period_end: datetime
status: generated | failed | stale
model: string optional
input_hash: string
summary: text
created_at: datetime
```

---

## 6.20 BriefingItem

```txt
id: uuid
briefing_id: uuid
category: risk | opportunity | update | action
title: string
summary: text
severity: low | medium | high
confidence: float
evidence_refs: uuid[]
recommended_action: jsonb optional
created_at: datetime
```

---

## 6.21 ActionProposal

```txt
id: uuid
workspace_id: uuid
briefing_item_id: uuid optional
target_provider: github | jira | gmail | drive | internal
action_type: string
title: string
description: text
payload: jsonb
status: proposed | approved | rejected | executing | executed | failed
evidence_refs: uuid[]
created_by: ai | user | system
approved_by_user_id: uuid optional
approved_at: datetime optional
created_at: datetime
updated_at: datetime
```

---

## 6.22 ActionExecution

```txt
id: uuid
action_proposal_id: uuid
status: running | succeeded | failed
provider_response: jsonb optional
external_id: string optional
error_message: text optional
started_at: datetime
finished_at: datetime optional
```

---

## 6.23 AuditLog

```txt
id: uuid
workspace_id: uuid
actor_user_id: uuid optional
actor_type: user | system | ai
action: string
target_type: string
target_id: uuid optional
metadata: jsonb
created_at: datetime
```

---

## 6.24 Cache rules

Можно кэшировать:

- dashboard counts;
- sync cursors;
- provider metadata;
- Drive extracted text;
- AI context packs;
- search results briefly.

Нельзя кэшировать как истину:

- AI summaries;
- action recommendations;
- provider permissions;
- auth status;
- external entity state after write.

---

# 7. API / Backend Contracts

## 7.1 API style

Зафиксированное решение: **REST API**.

Причины:

- просто тестировать;
- понятно FastAPI;
- удобно для Next.js;
- не нужен GraphQL для MVP.

Base path:

```txt
/api/v1
```

## 7.2 General API rules

Every endpoint must:

- validate user session;
- validate workspace access;
- validate input schema;
- return typed response;
- return safe errors;
- not expose secrets;
- log request id.

---

## 7.3 Auth endpoints

### POST `/auth/login`

Purpose: login.

Input:

```json
{
  "email": "founder@example.com",
  "password": "string"
}
```

Output:

```json
{
  "user": {
    "id": "uuid",
    "email": "founder@example.com"
  }
}
```

Errors:

- 400 invalid input;
- 401 invalid credentials;
- 403 disabled user.

Side effects:

- creates session cookie;
- creates AuditLog.

Acceptance criteria:

- invalid email rejected;
- session cookie is httpOnly;
- no password in logs.

---

### POST `/auth/logout`

Output:

```json
{ "ok": true }
```

Side effects:

- clears session.

---

### GET `/auth/me`

Output:

```json
{
  "user": {},
  "workspaces": []
}
```

---

## 7.4 Workspace endpoints

### POST `/workspaces`

Input:

```json
{
  "name": "My Startup"
}
```

Output:

```json
{
  "workspace": {
    "id": "uuid",
    "name": "My Startup"
  }
}
```

Validation:

- name required;
- max length 120.

---

### GET `/workspaces/{workspace_id}`

Output:

```json
{
  "workspace": {},
  "membership": {}
}
```

Access:

- membership required.

---

## 7.5 Connector endpoints

### GET `/workspaces/{workspace_id}/connections`

Output:

```json
{
  "connections": [
    {
      "id": "uuid",
      "provider": "github",
      "status": "connected",
      "display_name": "Founder GitHub",
      "last_sync_at": "datetime",
      "last_error": null
    }
  ]
}
```

---

### POST `/workspaces/{workspace_id}/connections/{provider}/oauth/start`

Supported provider:

- github;
- jira;
- gmail;
- drive.

Output:

```json
{
  "authorization_url": "https://provider.example/oauth"
}
```

Validation:

- provider supported;
- provider env vars configured;
- workspace access.

---

### GET `/oauth/{provider}/callback`

Purpose: OAuth callback.

Side effects:

- validates state;
- exchanges code;
- encrypts tokens;
- stores connection;
- redirects to UI.

Errors:

- invalid state;
- denied;
- token exchange failed.

---

### POST `/connections/{connection_id}/sync`

Input:

```json
{
  "sync_type": "manual"
}
```

Output:

```json
{
  "sync_job_id": "uuid",
  "status": "queued"
}
```

Side effects:

- creates SyncJob;
- enqueues RQ job.

---

## 7.6 Sync endpoints

### GET `/sync-jobs/{sync_job_id}`

Output:

```json
{
  "id": "uuid",
  "status": "running",
  "records_seen": 120,
  "records_created": 12,
  "records_updated": 7,
  "error_message": null
}
```

---

## 7.7 GitHub endpoints

### GET `/workspaces/{workspace_id}/github/repositories`

Query:

```txt
search?: string
page?: string
```

Output:

```json
{
  "items": [],
  "next_cursor": null
}
```

---

### GET `/workspaces/{workspace_id}/github/pull-requests`

Filters:

```txt
repo?: string
state?: open | closed | merged
stale_only?: boolean
```

---

### GET `/workspaces/{workspace_id}/github/issues`

Filters:

```txt
repo?: string
state?: open | closed
assignee?: string
```

---

## 7.8 Jira endpoints

### GET `/workspaces/{workspace_id}/jira/issues`

Filters:

```txt
project?: string
status?: string
assignee?: string
stale_only?: boolean
```

---

## 7.9 Gmail endpoints

### GET `/workspaces/{workspace_id}/gmail/threads`

Filters:

```txt
label?: string
search?: string
important_only?: boolean
```

---

### POST `/gmail/threads/{thread_id}/summarize`

Output:

```json
{
  "summary": "string",
  "evidence_refs": []
}
```

Rules:

- no sending;
- no external write;
- logs LLM call.

---

## 7.10 Drive endpoints

### GET `/workspaces/{workspace_id}/drive/files`

Filters:

```txt
folder?: string
mime_type?: string
search?: string
```

---

## 7.11 Documents endpoints

### POST `/workspaces/{workspace_id}/documents`

Input:

```json
{
  "title": "Launch Plan",
  "body_markdown": "...",
  "tags": ["launch"]
}
```

Output:

```json
{
  "document": {}
}
```

---

### PATCH `/documents/{document_id}`

Validation:

- title non-empty;
- body size limit;
- workspace access.

---

## 7.12 Brain endpoints

### GET `/workspaces/{workspace_id}/brain/entities`

Filters:

```txt
type?: string
search?: string
provider?: string
updated_since?: datetime
```

---

### GET `/brain/entities/{entity_id}`

Returns:

- entity;
- source records;
- evidence refs;
- related entities.

---

### GET `/workspaces/{workspace_id}/brain/timeline`

Returns recent normalized events.

---

## 7.13 Briefing endpoints

### POST `/workspaces/{workspace_id}/briefings/generate`

Input:

```json
{
  "period": "last_24h",
  "focus": ["risks", "blocked_work", "important_emails"]
}
```

Output:

```json
{
  "briefing_id": "uuid",
  "status": "generated"
}
```

Side effects:

- creates Briefing;
- creates BriefingItems;
- creates ActionProposals if valid.

Validation:

- workspace has enough data;
- LLM output valid JSON;
- every claim has evidence.

---

### GET `/briefings/{briefing_id}`

Returns full briefing.

---

## 7.14 Action endpoints

### GET `/workspaces/{workspace_id}/actions`

Filters:

```txt
status?: string
provider?: string
created_by?: string
```

---

### POST `/actions/{action_id}/approve`

Side effects:

- marks action approved;
- enqueues execution;
- creates audit log.

Rules:

- no duplicate approval;
- user must have workspace access;
- payload must validate.

---

### POST `/actions/{action_id}/reject`

Input:

```json
{
  "reason": "Not needed"
}
```

---

### GET `/actions/{action_id}`

Returns:

- proposal;
- evidence;
- execution result.

---

## 7.15 Repo Audit endpoint

### GET `/workspaces/{workspace_id}/repo-audit`

Returns latest repo audit.

Rules:

- read-only;
- no external writes;
- evidence visible.

---

# 8. Frontend Structure

## 8.1 UI principle

UI should be:

- clear;
- functional;
- fast;
- boring in a good way;
- evidence-first;
- action-oriented.

Не делать “красиво ради красоты”. Сначала рабочий интерфейс.

## 8.2 Navigation

Sidebar:

```txt
Dashboard
Company Brain
Connectors
GitHub
Jira
Gmail
Drive
Documents
Briefings
Actions
Repo Audit
Settings
```

Topbar:

- workspace name;
- sync status;
- user menu;
- environment badge in staging.

---

## 8.3 Pages

## `/login`

States:

- empty;
- submitting;
- invalid credentials;
- session expired;
- server error.

---

## `/dashboard`

Sections:

- connection health;
- last sync;
- active risks;
- stale PRs;
- stale tasks;
- important threads;
- recent documents;
- latest briefing;
- generate briefing CTA.

Empty state:

```txt
Connect GitHub to start building your Company Brain.
```

---

## `/connectors`

Cards:

- GitHub;
- Jira;
- Gmail;
- Google Drive.

Each card shows:

- status;
- display account;
- scopes;
- last sync;
- last error;
- connect button;
- sync now button;
- view data button.

---

## `/github`

Tabs:

- Repositories;
- Pull Requests;
- Issues;
- Activity.

Tables:

- repo name;
- visibility;
- open PRs;
- open issues;
- last activity;
- source link.

---

## `/jira`

Tabs:

- Projects;
- Issues;
- Stale;
- By Status.

Columns:

- key;
- title;
- status;
- assignee;
- updated;
- source link.

---

## `/gmail`

Tabs:

- Threads;
- Important;
- Summaries.

Thread detail:

- subject;
- participants;
- snippet;
- labels;
- summarize button;
- evidence;
- action proposal button.

---

## `/drive`

Tabs:

- Files;
- Folders;
- Indexed;
- Errors.

File detail:

- metadata;
- web link;
- extracted text status;
- related entities.

---

## `/documents`

Views:

- list;
- editor;
- detail.

Components:

- markdown editor;
- tags;
- related entities;
- save indicator.

---

## `/brain`

Tabs:

- Entities;
- Timeline;
- Source Records;
- Evidence.

Entity detail:

- canonical info;
- source records;
- evidence refs;
- related entities.

---

## `/briefings`

Views:

- list;
- detail;
- generate modal.

Briefing detail:

- summary;
- items;
- severity badge;
- confidence;
- evidence drawer;
- action proposals.

---

## `/actions`

Tabs:

- Proposed;
- Approved;
- Executed;
- Failed;
- Rejected.

Action detail:

- title;
- target provider;
- payload preview;
- evidence;
- approve;
- reject;
- execution status.

---

## `/repo-audit`

Sections:

- repository inventory;
- computed facts;
- warnings;
- evidence refs;
- export JSON.

---

## 8.4 Shared UI states

Every data view must support:

- loading;
- empty;
- error;
- success;
- partial;
- stale.

## 8.5 UX rules

- Show last synced at.
- Show provider errors.
- Show external source link.
- Every AI item has Evidence button.
- Dangerous action requires confirmation.
- Empty states tell next step.
- No raw stack traces.
- No secrets in UI.
- Tables have search/filter.
- Error messages should be human-readable.

---

# 9. Business Logic

## 9.1 OAuth connection

### Purpose

Connect external provider.

### Inputs

- provider;
- workspace id;
- OAuth code;
- OAuth state.

### Algorithm

1. Validate session.
2. Validate workspace access.
3. Generate OAuth state.
4. Redirect user to provider.
5. On callback validate state.
6. Exchange code for token.
7. Encrypt tokens.
8. Store IntegrationConnection.
9. Create audit log.
10. Redirect to connector page.

### Checks

- provider supported;
- env vars configured;
- state valid;
- scopes sufficient.

### Exceptions

- denied;
- invalid code;
- invalid state;
- token exchange failed;
- missing refresh token.

### Logging

Log:

- provider;
- workspace id;
- status;
- error class.

Never log:

- access token;
- refresh token;
- auth code;
- cookies.

### Tests

- success;
- invalid state;
- denied;
- missing env;
- token exchange failure.

---

## 9.2 Sync pipeline

### Purpose

Pull provider data into founderOS.

### Inputs

- connection id;
- sync type;
- cursor.

### Algorithm

1. Load connection.
2. Decrypt token.
3. Create SyncJob.
4. Mark running.
5. Call provider connector.
6. For each provider object:
   - map to ProviderRecord;
   - compute payload hash;
   - upsert SourceRecord;
   - call normalization;
   - create/update entity;
   - create evidence refs.
7. Save cursor.
8. Mark succeeded/partial/failed.
9. Update connection last_sync_at.
10. Log counts.

### Edge cases

- token expired;
- rate limited;
- provider timeout;
- partial failure;
- deleted external item;
- duplicate external id;
- schema missing field.

### Tests

- creates source records;
- idempotent sync;
- partial failure;
- token expired;
- normalization called;
- counts correct.

---

## 9.3 Normalization

### Purpose

Convert SourceRecord to founderOS entities.

### Inputs

- SourceRecord;
- provider;
- record_type.

### Algorithm

1. Detect mapping by provider and record type.
2. Extract canonical key.
3. Extract title/status/summary.
4. Resolve existing entity.
5. Create or update entity.
6. Create EvidenceRef.
7. Update related domain table.
8. Return normalized result.

### Edge cases

- missing canonical key;
- renamed repo;
- same person across providers;
- same task mentioned in email;
- deleted source.

### Tests

- GitHub repo -> Repository;
- GitHub issue -> Task;
- GitHub PR -> PullRequest;
- Jira issue -> Task;
- Gmail thread -> MessageThread;
- Drive file -> DriveFile;
- internal doc -> Document entity.

---

## 9.4 Company Brain search

### Purpose

Search across normalized company knowledge.

### Inputs

- query;
- filters;
- workspace.

### MVP algorithm

1. Validate query.
2. Search NormalizedEntity title/summary.
3. Search Document title/body_text.
4. Search SourceRecord metadata fields.
5. Rank by recency and type.
6. Return results with evidence/source.

### Post-MVP

- vector search;
- entity graph;
- semantic relationships.

---

## 9.5 Founder Briefing generation

### Purpose

Generate structured evidence-based briefing.

### Inputs

- workspace;
- period;
- focus.

### Algorithm

1. Load workspace context.
2. Load sync health.
3. Load recent source records.
4. Load normalized entities.
5. Load deterministic insights.
6. Load repo audit facts.
7. Build evidence map.
8. Build context pack.
9. Call LLM with strict prompt.
10. Validate JSON.
11. Validate evidence refs.
12. Drop unsupported claims.
13. Persist Briefing.
14. Persist BriefingItems.
15. Persist ActionProposals.
16. Return briefing.

### Checks

- enough data;
- evidence exists;
- output schema valid;
- no unsupported action;
- confidence in range.

### Edge cases

- no connectors;
- stale sync;
- invalid JSON;
- model timeout;
- context too large;
- conflicting data.

### Tests

- briefing created;
- invalid JSON handled;
- missing evidence rejected;
- no data state;
- action proposal generated;
- unsupported action removed.

---

## 9.6 Action proposal execution

### Purpose

Execute approved action.

### Inputs

- action id;
- user id.

### Algorithm

1. Load ActionProposal.
2. Validate workspace access.
3. Confirm status is proposed.
4. Validate payload schema.
5. Mark approved.
6. Create audit log.
7. Enqueue execution job.
8. Worker loads provider connection.
9. Execute connector action.
10. Store provider response.
11. Mark succeeded/failed.
12. Create SourceRecord for created external object if applicable.

### Edge cases

- duplicate approval;
- provider timeout;
- token expired;
- provider created item but response failed;
- permission denied;
- payload invalid.

### Tests

- approve success;
- reject success;
- duplicate approval blocked;
- execution failure stored;
- provider response stored;
- audit log created.

---

# 10. AI / Automation Logic

## 10.1 Где AI используется в MVP

AI используется в строго ограниченных местах:

- Founder Briefing;
- Gmail thread summary;
- insight explanation;
- action proposal generation;
- optional document summary.

AI не используется для:

- direct provider writes;
- arbitrary code execution;
- autonomous email sending;
- silent Jira/GitHub changes;
- replacing validation;
- making irreversible decisions.

## 10.2 Общие правила AI output

Каждый AI output:

- JSON only;
- schema validated;
- evidence required;
- confidence required;
- uncertainty allowed;
- no evidence -> no claim;
- action -> proposal only;
- prompt version logged;
- model logged.

---

## 10.3 Production prompt: Founder Briefing

### System prompt

```txt
You are founderOS Briefing Engine.

Your task is to generate a concise, evidence-based founder briefing from structured company data.

Rules:
- Use only the provided context.
- Do not invent facts.
- Every factual claim must reference at least one evidence_ref.
- If evidence is weak or missing, mark uncertainty.
- Prioritize issues that require founder attention.
- Prefer concrete operational insights over generic advice.
- Do not recommend external actions unless they can be represented as a human-approved action proposal.
- Return valid JSON only.
```

### User prompt template

```txt
Generate a founder briefing for workspace: {{workspace_name}}.

Period: {{period_start}} to {{period_end}}

Company context:
{{company_context}}

Goals:
{{goals_json}}

Recent entities:
{{entities_json}}

Sync health:
{{sync_health_json}}

Repo audit:
{{repo_audit_json}}

Evidence map:
{{evidence_refs_json}}

Return JSON in this schema:

{
  "summary": "string",
  "items": [
    {
      "category": "risk | opportunity | update | action",
      "title": "string",
      "summary": "string",
      "severity": "low | medium | high",
      "confidence": 0.0,
      "evidence_refs": ["uuid"],
      "recommended_action": {
        "needed": true,
        "action_type": "create_jira_issue | create_github_issue | internal_todo | none",
        "title": "string",
        "description": "string",
        "target_provider": "jira | github | internal | none",
        "payload": {}
      }
    }
  ],
  "uncertainties": [
    {
      "question": "string",
      "reason": "string",
      "missing_evidence": "string"
    }
  ]
}
```

### Validation failures

Reject if:

- invalid JSON;
- item has no evidence;
- unsupported provider;
- confidence outside 0-1;
- action payload invalid;
- output contains claim not in context.

---

## 10.4 Production prompt: Gmail Thread Summary

```txt
You are founderOS Email Summarizer.

Summarize the email thread for operational use.

Rules:
- Use only provided messages.
- Do not expose unnecessary personal details.
- Extract decisions, asks, commitments, blockers, and deadlines.
- Do not draft a reply unless explicitly requested.
- Every important point must include evidence_refs.
- Return valid JSON only.

Input:
{{thread_json}}

Schema:
{
  "summary": "string",
  "participants": ["string"],
  "decisions": [
    {
      "text": "string",
      "evidence_refs": ["uuid"]
    }
  ],
  "asks": [
    {
      "text": "string",
      "owner": "string | null",
      "deadline": "string | null",
      "evidence_refs": ["uuid"]
    }
  ],
  "risks": [
    {
      "text": "string",
      "severity": "low | medium | high",
      "evidence_refs": ["uuid"]
    }
  ],
  "suggested_actions": [
    {
      "title": "string",
      "action_type": "internal_todo | create_jira_issue | none",
      "evidence_refs": ["uuid"]
    }
  ]
}
```

---

## 10.5 Production prompt: Insight Explanation

```txt
You are founderOS Insight Explainer.

Explain why a deterministic system insight matters.

Rules:
- Do not invent new facts.
- Explain operational impact.
- Include concrete next step.
- Use evidence_refs.
- Return JSON only.

Insight:
{{insight_json}}

Related data:
{{related_entities_json}}

Schema:
{
  "plain_english": "string",
  "why_it_matters": "string",
  "recommended_next_step": "string",
  "evidence_refs": ["uuid"],
  "confidence": 0.0
}
```

---

## 10.6 Production prompt: Action Proposal Generator

```txt
You are founderOS Action Proposal Generator.

Create a human-reviewed action proposal based on a briefing item.

Rules:
- Do not execute anything.
- Do not send messages.
- Do not call external APIs.
- Produce only a proposal.
- Payload must match target action schema.
- Include evidence refs.

Briefing item:
{{briefing_item_json}}

Allowed actions:
{{allowed_actions_json}}

Schema:
{
  "target_provider": "jira | github | internal",
  "action_type": "create_jira_issue | create_github_issue | internal_todo",
  "title": "string",
  "description": "string",
  "payload": {},
  "evidence_refs": ["uuid"],
  "risk_level": "low | medium | high",
  "requires_confirmation": true
}
```

---

## 10.7 Human review rules

Human review required for:

- create Jira issue;
- create GitHub issue;
- send Gmail draft;
- create Gmail draft;
- change issue status;
- delete anything;
- publish document externally;
- schedule automation;
- run provider write.

---

# 11. Порядок разработки

## Phase 0 - Project Setup

### Цель

Стабилизировать repo и зафиксировать архитектуру.

### Tasks

1. Run repo audit.
2. Read existing docs.
3. Create/update `docs/DECISIONS.md`.
4. Create/update `docs/ROADMAP.md`.
5. Create/update `docs/TODO.md`.
6. Verify migrations.
7. Verify tests.
8. Verify lint.

### Commands

```bash
git status
pytest
ruff check .
alembic heads
alembic upgrade head
python -m compileall app scripts
```

Frontend if present:

```bash
cd web
pnpm install
pnpm lint
pnpm test
pnpm build
```

### Acceptance criteria

- current repo state understood;
- docs created;
- failures documented;
- no unrelated code changes.

### Definition of Done

- `DECISIONS.md` exists;
- `ROADMAP.md` exists;
- `TODO.md` exists;
- baseline checks recorded.

---

## Phase 1 - Database / Core Models

### Цель

Создать основу данных.

### Tasks

1. User / Workspace / Membership.
2. IntegrationConnection.
3. SyncJob.
4. SourceRecord.
5. EvidenceRef.
6. NormalizedEntity.
7. Document.
8. Briefing / BriefingItem.
9. ActionProposal / ActionExecution.
10. AuditLog.
11. Migrations.
12. Model tests.

### Commands

```bash
alembic revision --autogenerate -m "core founderos models"
alembic upgrade head
pytest tests/models
```

### Acceptance criteria

- migrations apply cleanly;
- models import;
- indexes exist;
- no plaintext token fields.

---

## Phase 2 - Backend Core

### Цель

Создать сервисный слой.

### Tasks

1. Auth service.
2. Workspace service.
3. Connector service.
4. Encryption utility.
5. Sync service.
6. Normalization service.
7. Brain service.
8. LLM service.
9. Action service.
10. Audit logging.

### Acceptance criteria

- services unit-tested;
- provider logic isolated;
- no secrets in logs;
- errors typed.

---

## Phase 3 - Frontend Core

### Цель

Создать UI shell.

### Tasks

1. App shell.
2. Login page.
3. Workspace onboarding.
4. Sidebar.
5. API client.
6. Error components.
7. Loading states.
8. Empty states.
9. Connectors page.
10. Dashboard skeleton.

### Acceptance criteria

- app runs locally;
- user can navigate;
- connector cards visible;
- empty states helpful.

---

## Phase 4 - Main User Flow End-to-End

### Цель

Получить первый рабочий E2E.

### Fixed first E2E

```txt
GitHub OAuth
-> GitHub Sync
-> SourceRecords
-> Normalized Entities
-> Dashboard
-> Company Brain
-> Briefing
-> Action Proposal
-> Approved GitHub Issue Creation
```

### Tasks

1. GitHub OAuth.
2. GitHub sync repos.
3. GitHub sync issues.
4. GitHub sync PRs.
5. Normalize GitHub records.
6. Dashboard GitHub data.
7. Brain entity view.
8. Briefing context pack.
9. LLM briefing.
10. GitHub create issue action.

### Acceptance criteria

- user connects GitHub through UI;
- sync completes;
- data visible;
- briefing generated;
- evidence visible;
- approved action creates GitHub issue.

---

## Phase 5 - Edge Cases & Polish

### Цель

Довести первый flow до usable.

### Tasks

- token expired handling;
- sync retry;
- partial sync;
- provider errors;
- evidence drawer;
- action failure UI;
- filters;
- search;
- stale data labels.

### Acceptance criteria

- no dead-end screens;
- user understands failures;
- retries possible.

---

## Phase 6 - Testing

### Цель

Закрыть критические сценарии.

### Tasks

- unit tests;
- integration tests;
- connector mocks;
- briefing validation tests;
- action approval tests;
- smoke tests;
- manual QA checklist.

### Acceptance criteria

- backend tests green;
- frontend build green;
- GitHub E2E covered;
- AI validation covered.

---

## Phase 7 - Deployment

### Цель

Production MVP online.

### Tasks

- Railway project;
- Postgres;
- Redis;
- backend service;
- worker service;
- frontend service;
- env vars;
- migrations;
- smoke tests;
- domain.

### Acceptance criteria

- production URL works;
- login works;
- GitHub connect works;
- sync works;
- briefing works;
- logs visible.

---

## Phase 8 - Post-launch Improvements

### Цель

Расширять без переписывания.

### Tasks

- Jira full sync;
- Gmail summary;
- Drive indexing;
- Goals;
- Insights v1;
- Scheduled briefings;
- Role briefings;
- Natural language rules;
- Sandbox research;
- Multi-model council.

---

# 12. Task Backlog для Claude Code / Codex

## FOS-000 - Repository baseline audit

### Goal

Understand current repository.

### Instructions

- Read README, pyproject/package files, app structure, migrations, tests.
- Read existing connector/service modules.
- Run safe checks.
- Do not change files.

### Expected output

- stack summary;
- directories;
- existing modules;
- test/lint/migration status;
- risks.

### Acceptance criteria

No code changed.

---

## FOS-001 - Create project docs

### Goal

Create scope control docs.

### Files

```txt
docs/DECISIONS.md
docs/ROADMAP.md
docs/TODO.md
docs/POST_MVP.md
```

### Instructions

- Add MVP scope.
- Add no-go list.
- Add stack decisions.
- Add first E2E.
- Do not touch app code.

### Acceptance criteria

Docs exist and match this playbook.

---

## FOS-002 - Add core database models

### Goal

Create MVP data model.

### Files likely

```txt
app/models/workspace.py
app/models/integration.py
app/models/sync_job.py
app/models/source_record.py
app/models/entity.py
app/models/document.py
app/models/briefing.py
app/models/action.py
app/models/audit_log.py
```

### Instructions

- Use existing model conventions.
- Add indexes.
- Add migrations.
- Add tests.
- No provider logic.

### Acceptance criteria

`alembic upgrade head` passes.

---

## FOS-003 - Add encryption utility

### Goal

Encrypt integration tokens.

### Files likely

```txt
app/core/encryption.py
app/tests/test_encryption.py
```

### Instructions

- Use env `ENCRYPTION_KEY`.
- Implement encrypt/decrypt.
- Never log plaintext.
- Add tests.

### Acceptance criteria

Roundtrip test passes.

---

## FOS-004 - Add connector base interface

### Goal

Create consistent connector contract.

### Files likely

```txt
app/connectors/base.py
```

### Contract includes

- ProviderClient;
- ProviderRecord;
- SyncResult;
- ProviderAction;
- ProviderError;
- ProviderAuthError;
- ProviderRateLimitError.

### Acceptance criteria

No provider-specific code in base.

---

## FOS-005 - Add sync service

### Goal

Implement generic sync pipeline.

### Files likely

```txt
app/services/sync_service.py
app/jobs/sync_jobs.py
```

### Instructions

- Create SyncJob.
- Execute connector.
- Store SourceRecord.
- Call normalization.
- Update counts.
- Handle partial failure.

### Acceptance criteria

Mock connector sync test passes.

---

## FOS-006 - Add normalization service

### Goal

Raw records become entities.

### Files likely

```txt
app/services/normalization_service.py
```

### Instructions

- Route by provider and record_type.
- Upsert NormalizedEntity.
- Create EvidenceRef.
- Add tests for mock records.

### Acceptance criteria

SourceRecord -> Entity -> Evidence works.

---

## FOS-007 - GitHub OAuth

### Goal

Connect GitHub.

### Files likely

```txt
app/api/routes/connectors.py
app/connectors/github/client.py
app/services/connector_service.py
```

### Instructions

- OAuth state.
- Callback.
- Token encryption.
- Connection status.
- Tests with mocked exchange.

### Acceptance criteria

GitHub connection stored.

---

## FOS-008 - GitHub sync repositories

### Goal

Sync repositories.

### Files likely

```txt
app/connectors/github/sync.py
app/connectors/github/mapper.py
```

### Instructions

- Fetch repositories.
- Map to ProviderRecord.
- Store SourceRecords.
- Normalize Repository.

### Acceptance criteria

Idempotent sync.

---

## FOS-009 - GitHub sync issues and PRs

### Goal

Sync operational GitHub work.

### Instructions

- Fetch issues.
- Fetch PRs.
- Map to Task/PullRequest.
- Link to Repository.
- Add tests.

### Acceptance criteria

Dashboard can show open PRs and issues.

---

## FOS-010 - Connector UI page

### Goal

User can manage connections.

### Files likely

```txt
web/app/connectors/page.tsx
web/components/connectors/*
```

### Instructions

- Cards for providers.
- Connect button.
- Sync button.
- Status.
- Last error.

### Acceptance criteria

User can start OAuth.

---

## FOS-011 - Dashboard v0

### Goal

Show first synced data.

### Files likely

```txt
web/app/dashboard/page.tsx
app/api/routes/dashboard.py
```

### Instructions

- Counts.
- Last sync.
- Stale PRs/tasks.
- Empty state.

### Acceptance criteria

Dashboard works with GitHub data.

---

## FOS-012 - Brain entity API/UI

### Goal

Browse Company Brain.

### Files likely

```txt
app/api/routes/brain.py
web/app/brain/page.tsx
web/components/evidence/*
```

### Instructions

- Entity list.
- Entity detail.
- Evidence drawer.
- Source records.

### Acceptance criteria

Entity detail shows source records and evidence.

---

## FOS-013 - Briefing backend

### Goal

Generate AI briefing.

### Files likely

```txt
app/services/briefing_service.py
app/services/llm_service.py
app/api/routes/briefings.py
```

### Instructions

- Build context pack.
- Call LLM abstraction.
- Validate JSON.
- Persist briefing.
- Create action proposals.

### Acceptance criteria

Mock LLM test passes.

---

## FOS-014 - Briefing UI

### Goal

Display briefing.

### Files likely

```txt
web/app/briefings/page.tsx
web/components/briefing/*
```

### Instructions

- Generate button.
- Loading state.
- Items.
- Severity.
- Evidence.
- Actions.

### Acceptance criteria

User can generate and view briefing.

---

## FOS-015 - Action proposal API

### Goal

Human approval flow.

### Files likely

```txt
app/services/action_service.py
app/api/routes/actions.py
```

### Instructions

- list;
- detail;
- approve;
- reject;
- execution status;
- audit log.

### Acceptance criteria

Approval enqueues execution.

---

## FOS-016 - GitHub create issue action

### Goal

First approved external write.

### Instructions

- Validate approved status.
- Validate payload.
- Use idempotency key.
- Call GitHub connector action.
- Store provider response.

### Acceptance criteria

Approved action creates GitHub issue.

---

## FOS-017 - Jira connector minimal

### Goal

Read Jira issues.

### Instructions

- Connect Jira.
- Sync projects/issues.
- Normalize tasks.
- Display in UI.

### Acceptance criteria

Jira issues visible.

---

## FOS-018 - Gmail connector minimal

### Goal

Read Gmail threads.

### Instructions

- OAuth read-only.
- Sync recent threads.
- Store metadata/snippet.
- No sending.
- Add summary endpoint.

### Acceptance criteria

Threads visible and summarizable.

---

## FOS-019 - Drive connector minimal

### Goal

Read Drive files.

### Instructions

- OAuth.
- Sync file metadata.
- Store DriveFile.
- No binary copy.

### Acceptance criteria

Drive files visible.

---

## FOS-020 - Documents module

### Goal

Internal docs.

### Instructions

- CRUD docs.
- Tags.
- Search.
- Link to entities.
- Add to Brain.

### Acceptance criteria

Docs appear in Company Brain.

---

## FOS-021 - Repo Audit UI

### Goal

Expose existing repo audit work.

### Instructions

- Use existing repo_audit logic.
- No network writes.
- Show facts/evidence.
- Add UI page.

### Acceptance criteria

Repo audit page works.

---

## FOS-022 - Smoke tests

### Goal

Pre-launch confidence.

### Instructions

- Add smoke script.
- Test health, login, connectors, dashboard.
- Document command.

### Acceptance criteria

`make smoke` or equivalent passes.

---

# 13. Готовые промпты для Claude Code / Codex

## 13.1 Анализ текущего репозитория

```txt
You are working on founderOS.

Task: analyze the current repository before making changes.

Rules:
- Do not modify files.
- First read README, pyproject/package files, app structure, migrations, tests, and existing connector/service modules.
- Do not invent missing APIs or files.
- Identify existing conventions and use them in future tasks.
- Run available checks if safe: pytest, ruff check ., alembic heads, alembic upgrade head.
- Report failures honestly.

Return format:
1. Current stack
2. Important directories
3. Existing relevant modules
4. Test/lint/migration status
5. Risks
6. Recommended next task
```

---

## 13.2 Создание архитектурного плана

```txt
You are working on founderOS.

Task: create or update architecture docs for the next implementation slice.

Rules:
- Do not implement code.
- Read docs/DECISIONS.md, docs/ROADMAP.md, existing models, services, routes.
- Preserve current architecture unless there is a documented reason.
- Do not introduce microservices, microfrontends, or new frameworks.
- Focus on the next end-to-end flow only.

Output:
1. Files changed
2. Architecture decision summary
3. Updated task checklist
4. Open risks
```

---

## 13.3 Реализация конкретной задачи

```txt
You are working on founderOS.

Task: implement TASK_ID: [paste task here].

Before coding:
- Read relevant existing files.
- Identify conventions.
- Write a short implementation plan.
- Do not change unrelated files.
- Do not refactor unrelated code.
- Do not invent APIs if existing patterns already exist.

During coding:
- Keep changes minimal.
- Add tests for new behavior.
- Preserve existing behavior.
- Use existing config/logging/error patterns.
- Ensure backend validation is not only in frontend.

After coding:
- Run targeted tests.
- Run lint if feasible.
- Report exact files changed.
- Report commands run and results.
- Report any skipped checks.

Response format:
1. Plan
2. Changes made
3. Tests added/updated
4. Commands run
5. Acceptance criteria status
6. Risks/notes
```

---

## 13.4 Рефакторинг без изменения поведения

```txt
You are working on founderOS.

Task: refactor [module/file] without changing behavior.

Rules:
- First read tests covering this area.
- If tests are missing, add characterization tests before refactor.
- Do not change public API.
- Do not change database schema.
- Do not change UI behavior.
- Keep diff small.
- No opportunistic rewrites.

Verification:
- Run tests before and after.
- Explain why behavior is unchanged.

Return:
1. What was refactored
2. What stayed the same
3. Tests run
4. Any behavior risk
```

---

## 13.5 Написание тестов

```txt
You are working on founderOS.

Task: write tests for [feature].

Rules:
- Read implementation first.
- Test behavior, not implementation details.
- Cover success, validation failure, permission failure, and provider error.
- Use existing test fixtures and conventions.
- Do not rewrite production code unless necessary for testability.
- If production code is untestable, propose minimal seam.

Return:
1. Test files changed
2. Cases covered
3. Commands run
4. Remaining gaps
```

---

## 13.6 Исправление бага

```txt
You are working on founderOS.

Bug: [paste bug].

Rules:
- Reproduce or explain why reproduction is impossible.
- Find root cause before changing code.
- Add failing test first if practical.
- Make the smallest fix.
- Do not refactor unrelated code.
- Run targeted tests.
- Report exact cause.

Return:
1. Reproduction
2. Root cause
3. Fix
4. Test added
5. Commands run
6. Risk assessment
```

---

## 13.7 Базовая security-проверка

```txt
You are working on founderOS.

Task: run a basic security baseline review for the current changes.

Rules:
- Do not turn this into a full compliance project.
- Focus on MVP baseline:
  - secrets not committed
  - tokens encrypted
  - no tokens in logs
  - backend validation
  - access checks
  - no direct provider calls from frontend
  - no automatic destructive actions
- Do not add new security frameworks unless necessary.
- Report findings by severity.

Return:
1. Critical blockers
2. High priority
3. Medium priority
4. Safe to defer
5. Files inspected
6. Recommended minimal fixes
```

---

## 13.8 Подготовка к деплою

```txt
You are working on founderOS.

Task: prepare the app for deployment.

Rules:
- Read deployment docs and env config.
- Do not change business logic.
- Ensure env vars are documented.
- Ensure migrations can run.
- Ensure health endpoint exists.
- Ensure worker can start.
- Ensure frontend API base URL is configurable.
- Do not hardcode production secrets.

Return:
1. Deployment readiness status
2. Env vars required
3. Commands to run
4. Smoke tests
5. Rollback notes
```

---

## 13.9 Code review

```txt
You are reviewing founderOS changes.

Task: review the diff for correctness, maintainability, and MVP scope.

Rules:
- Do not make changes unless asked.
- Check for scope creep.
- Check for unrelated refactors.
- Check tests.
- Check error handling.
- Check security baseline.
- Check data model consistency.
- Check evidence_refs for AI claims.
- Be specific with file paths and line references.

Return:
1. Summary
2. Blockers
3. Non-blocking issues
4. Test gaps
5. Scope creep warnings
6. Recommendation: approve / request changes
```

---

## 13.10 Финальная проверка перед запуском

```txt
You are doing the founderOS launch gate.

Task: perform final pre-launch verification.

Rules:
- Do not add features.
- Do not refactor.
- Run full backend tests, frontend build, migrations, lint, smoke tests.
- Verify env docs.
- Verify critical user flows manually or through tests.
- Verify logs do not leak secrets.
- Verify rollback plan exists.
- Report exact results.

Return:
1. Launch readiness: GO / NO-GO
2. Checks run
3. Passed
4. Failed
5. Risks
6. Required fixes before launch
7. Post-launch follow-ups
```

---

# 14. Правила работы с AI-разработчиком

## 14.1 Как давать задачи

Правильный формат:

```txt
TASK_ID: FOS-008
Goal: GitHub sync repositories
Scope: only backend connector and tests
Files likely: ...
Do not touch: frontend, auth, migrations unless necessary
Acceptance criteria: ...
Run: pytest targeted
```

## 14.2 Как проверять результат

Проверять:

- `git diff`;
- какие файлы изменены;
- есть ли unrelated changes;
- есть ли tests;
- пройдены ли commands;
- не сломан ли scope;
- не добавлены ли secrets;
- не появился ли direct external write.

## 14.3 Когда разрешать много файлов

Разрешать много файлов только если:

- задача заранее описывает affected files;
- есть plan-first;
- есть tests;
- есть checkpoint branch;
- изменение не ломает основной flow.

## 14.4 Когда требовать plan-first

Всегда для:

- migrations;
- auth;
- connectors;
- AI;
- action execution;
- refactoring;
- deployment;
- data model changes.

## 14.5 Когда требовать тесты

Всегда для:

- models;
- services;
- sync;
- normalization;
- AI validation;
- action approval;
- permissions;
- bug fixes.

## 14.6 Когда откатывать изменения

Откатить, если агент:

- переписал стек;
- внёс unrelated refactor;
- удалил tests;
- сломал migrations;
- добавил secrets;
- сделал external write без approval;
- создал AI-логику без schema validation;
- изменил архитектуру без DECISIONS.md.

## 14.7 Как не потерять контроль

- Один task за раз.
- Один branch за task.
- Один commit за task.
- Все решения в `DECISIONS.md`.
- Все идеи после MVP в `POST_MVP.md`.
- Не принимать большие “улучшения” без plan.
- Не читать новые аналоги во время implementation sprint.

## 14.8 Changelog rule

Каждый значимый merge обновляет `CHANGELOG.md`.

Формат:

```md
## YYYY-MM-DD

### Added
- FOS-008 GitHub repository sync.

### Changed
- Improved sync status reporting.

### Fixed
- Prevent duplicate SourceRecords.

### Deferred
- Multi-model council moved post-MVP.
```

---

# 15. Git Strategy

## 15.1 Branches

```txt
main        production-ready
develop     integration branch
feat/fos-xxx-short-name
fix/fos-xxx-short-name
```

## 15.2 Commit names

Examples:

```txt
feat(connectors): add github oauth flow
feat(sync): store raw source records
feat(brain): add entity list endpoint
feat(briefings): generate evidence-based briefing
test(actions): validate approval flow
fix(sync): handle github rate limit
docs(decisions): lock mvp scope
```

## 15.3 Checkpoints

Make checkpoint:

- before migrations;
- after green tests;
- before refactor;
- before deploy;
- after GitHub E2E works.

## 15.4 Rollback

Uncommitted:

```bash
git status
git diff
git restore .
git clean -fd
```

Committed:

```bash
git revert <commit_sha>
```

Bad branch:

```bash
git checkout develop
git branch -D feat/bad-branch
```

## 15.5 Required docs

```txt
docs/DECISIONS.md
docs/ROADMAP.md
docs/TODO.md
docs/POST_MVP.md
docs/CHANGELOG.md
```

## 15.6 TODO discipline

`TODO.md` содержит только ближайшие задачи. Все идеи “потом” идут в `POST_MVP.md`.

---

# 16. Testing Strategy

## 16.1 Unit tests

Cover:

- encryption;
- model creation;
- source record hashing;
- normalization;
- AI JSON validation;
- action payload validation;
- permission helpers.

## 16.2 Integration tests

Cover:

- OAuth callback mocked;
- sync job with mock provider;
- SourceRecord -> Entity;
- Briefing generation with mock LLM;
- Action approval -> execution with mock provider.

## 16.3 E2E tests

MVP E2E:

```txt
login
-> connect GitHub mock
-> sync GitHub
-> dashboard shows data
-> generate briefing
-> approve action
-> action executed
```

## 16.4 Manual QA

Checklist:

- login works;
- logout works;
- workspace visible;
- connector page loads;
- GitHub connect starts;
- sync button works;
- sync status updates;
- dashboard shows data;
- brain entity opens;
- evidence drawer opens;
- briefing generates;
- action requires approval;
- reject works;
- failed action shows error.

## 16.5 Before commit checklist

- `git diff` reviewed;
- targeted tests pass;
- lint pass if relevant;
- no secrets;
- no unrelated files;
- acceptance criteria checked.

## 16.6 Before merge checklist

- backend tests pass;
- frontend build pass;
- migrations pass;
- no scope creep;
- code review done;
- CHANGELOG updated.

## 16.7 Before deploy checklist

- env vars configured;
- migrations tested;
- worker starts;
- health endpoint works;
- smoke tests pass;
- rollback plan ready.

## 16.8 After deploy checklist

- login production;
- dashboard production;
- sync one connector;
- generate briefing;
- check logs;
- check worker;
- check errors.

---

# 17. Error Handling & Observability

## 17.1 Error classes

Use typed errors:

```txt
AuthError
PermissionError
ProviderAuthError
ProviderRateLimitError
ProviderSchemaError
SyncPartialFailure
LLMValidationError
ActionExecutionError
DatabaseError
```

## 17.2 UI error rules

Show:

- plain language;
- provider;
- retry option;
- last sync;
- debug id if available.

Do not show:

- stack traces;
- tokens;
- cookies;
- raw secret values;
- private keys.

## 17.3 Logging rules

Log:

- request id;
- workspace id;
- provider;
- sync job id;
- action id;
- timing;
- counts;
- error class.

Do not log:

- OAuth tokens;
- passwords;
- cookies;
- full private email bodies;
- refresh tokens.

## 17.4 Metrics MVP

Track:

- sync success count;
- sync failure count;
- sync duration;
- records processed;
- LLM calls;
- LLM validation failures;
- action proposals created;
- actions approved;
- actions failed;
- frontend page errors.

## 17.5 Alerts later

Post-launch:

- worker down;
- sync failure spike;
- provider auth failures;
- DB errors;
- 500 rate spike;
- LLM failures;
- queue backlog.

---

# 18. Security Baseline

## 18.1 MVP security baseline

### Secrets

- secrets only through env;
- no secrets in code;
- no secrets in logs;
- separate staging/prod secrets.

### Tokens

- OAuth tokens encrypted;
- refresh tokens encrypted;
- frontend never receives tokens;
- token access only through backend services.

### Auth

- httpOnly session cookie;
- secure cookies in production;
- CSRF/state protection for OAuth;
- session expiry.

### Access checks

- every endpoint checks workspace membership;
- action approval checks membership;
- no cross-workspace access;
- provider records scoped by workspace.

### Validation

- backend validates all input;
- Pydantic schemas;
- action payload schemas;
- provider action allowlist.

### External writes

- no automatic external writes;
- human approval required;
- audit log required;
- idempotency required.

### Rate limits

MVP critical:

- login;
- sync now;
- briefing generation;
- action approval.

### Deployment defaults

- HTTPS;
- debug off;
- CORS restricted;
- migrations controlled;
- backups enabled.

## 18.2 Post-launch security hardening

После запуска:

- full endpoint audit;
- stricter RBAC;
- provider scope minimization;
- stricter rate limits;
- security headers;
- secret rotation;
- automated backups;
- restore drills;
- audit trail UI;
- penetration testing checklist;
- privacy review;
- data retention policy;
- incident response draft;
- dependency scanning;
- SSO later;
- SOC2 later.

---

# 19. Deployment Plan

## 19.1 Target

MVP deploy target: **Railway**.

Services:

- backend;
- frontend;
- worker;
- Postgres;
- Redis.

## 19.2 Backend env vars

```txt
APP_ENV=production
APP_URL=https://app.founderos.example
FRONTEND_URL=https://app.founderos.example
DATABASE_URL=...
REDIS_URL=...
SESSION_SECRET=...
ENCRYPTION_KEY=...
CORS_ORIGINS=...
OPENAI_API_KEY=...
LLM_MODEL=...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
JIRA_CLIENT_ID=...
JIRA_CLIENT_SECRET=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

## 19.3 Frontend env vars

```txt
NEXT_PUBLIC_API_BASE_URL=https://api.founderos.example/api/v1
NEXT_PUBLIC_APP_ENV=production
```

## 19.4 Deployment steps

1. Create Railway project.
2. Add Postgres.
3. Add Redis.
4. Add backend service.
5. Add worker service.
6. Add frontend service.
7. Set env vars.
8. Configure OAuth callback URLs.
9. Run migrations.
10. Deploy backend.
11. Deploy worker.
12. Deploy frontend.
13. Configure domain.
14. Run smoke tests.

## 19.5 Migration command

```bash
alembic upgrade head
```

## 19.6 Health checks

Backend:

```txt
GET /health
GET /api/v1/auth/me
```

Worker:

- can connect Redis;
- can process test job.

Frontend:

- login page loads;
- dashboard route loads after auth.

## 19.7 Rollback

- redeploy previous commit;
- avoid irreversible migrations before backup;
- keep migration notes;
- backup DB before major schema change.

## 19.8 Typical deployment errors

- missing env var;
- wrong callback URL;
- OAuth provider mismatch;
- CORS mismatch;
- worker not running;
- migration not applied;
- Redis unavailable;
- frontend API URL wrong.

---

# 20. Launch Checklist

## 20.1 Functionality

- login works;
- logout works;
- workspace works;
- connectors page works;
- GitHub connect works;
- GitHub sync works;
- Jira minimal works;
- Gmail minimal works;
- Drive minimal works;
- Documents CRUD works;
- Dashboard loads;
- Brain loads;
- Briefing generates;
- Evidence opens;
- Action proposal works;
- Action approval works.

## 20.2 Data

- SourceRecords created;
- entities normalized;
- evidence refs present;
- sync jobs tracked;
- audit logs created;
- no token plaintext.

## 20.3 UI

- loading states;
- empty states;
- error states;
- no blank screens;
- no raw tracebacks;
- external links work.

## 20.4 Backend

- migrations applied;
- health endpoint;
- structured logs;
- typed errors;
- access checks.

## 20.5 Auth

- session secure;
- logout clears session;
- workspace access enforced.

## 20.6 AI

- JSON validation;
- evidence required;
- bad output handled;
- token usage logged;
- no direct external writes.

## 20.7 Logs

- no secrets;
- sync logs;
- AI logs;
- action logs;
- errors visible.

## 20.8 Deployment

- domain;
- HTTPS;
- env vars;
- DB backup;
- worker running;
- smoke tests pass.

## 20.9 Legal/privacy minimum

- simple privacy notice;
- connected data sources listed;
- disconnect provider path;
- token revoke documented.

---

# 21. Anti-Procrastination / Execution Rules

## 21.1 Daily rule

Каждый рабочий день выбирается **одна задача из backlog** и доводится до Definition of Done.

## 21.2 Как выбирать следующую задачу

Приоритет:

1. broken E2E;
2. missing model;
3. missing backend service;
4. missing API;
5. missing UI;
6. missing tests;
7. polish;
8. new feature.

## 21.3 Когда задача завершена

Задача завершена, когда:

- acceptance criteria выполнены;
- tests добавлены;
- tests pass;
- diff reviewed;
- no unrelated changes;
- changelog updated if needed;
- commit made.

## 21.4 Когда запрещено рефакторить

Запрещено:

- до первого GitHub E2E;
- перед deploy;
- без tests;
- из-за вкуса;
- когда текущий flow broken.

## 21.5 Когда запрещено добавлять фичи

Запрещено:

- пока GitHub E2E не работает;
- пока Dashboard пустой;
- пока Briefing без evidence;
- пока Action approval не работает;
- пока production не запущен.

## 21.6 Если застрял

1. Stop coding.
2. Write exact blocker.
3. Create minimal reproduction.
4. Ask AI about one bug only.
5. Fix smallest possible thing.
6. Run targeted test.
7. Commit.

## 21.7 Как не уйти в бесконечное планирование

- не читать новые аналоги до launch;
- не переписывать architecture doc без task;
- не менять stack;
- не добавлять connectors вне плана;
- все новые идеи в `POST_MVP.md`;
- каждый день должен давать working increment.

---

# 22. Final Master Plan

## Этап 1 - Lock Scope

Do:

- create/update `DECISIONS.md`;
- create/update `ROADMAP.md`;
- create/update `TODO.md`;
- create/update `POST_MVP.md`;
- commit docs.

Done when:

- MVP scope locked;
- no-go list written;
- first E2E written.

---

## Этап 2 - Core Models

Do:

- add DB models;
- add migrations;
- add model tests.

Done when:

- migrations pass;
- tests pass.

---

## Этап 3 - Connector Framework

Do:

- base connector;
- sync service;
- source records;
- normalizer;
- evidence refs.

Done when:

- mock connector creates SourceRecord, Entity, EvidenceRef.

---

## Этап 4 - GitHub E2E

Do:

- GitHub OAuth;
- sync repos;
- sync issues;
- sync PRs;
- normalize;
- show in UI.

Done when:

- user sees GitHub data in Dashboard and Brain.

---

## Этап 5 - Briefing MVP

Do:

- context pack;
- LLM service;
- prompt;
- JSON validation;
- briefing UI;
- evidence drawer.

Done when:

- user generates briefing with evidence.

---

## Этап 6 - Action Approval

Do:

- ActionProposal;
- approve/reject;
- execution worker;
- GitHub create issue action;
- audit log.

Done when:

- approved action creates GitHub issue.

---

## Этап 7 - Jira Minimal

Do:

- connect;
- sync issues;
- normalize tasks;
- UI.

Done when:

- Jira issues visible.

---

## Этап 8 - Gmail Minimal

Do:

- connect;
- sync threads;
- summarize;
- UI.

Done when:

- Gmail threads visible and summarizable.

---

## Этап 9 - Drive Minimal

Do:

- connect;
- sync files;
- UI;
- link to Brain.

Done when:

- Drive files visible.

---

## Этап 10 - Documents

Do:

- CRUD docs;
- tags;
- search;
- Brain integration.

Done when:

- internal docs appear in Company Brain.

---

## Этап 11 - Polish

Do:

- errors;
- retries;
- empty states;
- filters;
- evidence UX;
- action failure UX.

Done when:

- user has no dead-end states.

---

## Этап 12 - Testing Gate

Do:

- full backend tests;
- frontend build;
- integration tests;
- smoke tests.

Done when:

- launch gate is green.

---

## Этап 13 - Deploy

Do:

- Railway;
- env vars;
- DB;
- Redis;
- backend;
- worker;
- frontend;
- migrations;
- smoke.

Done when:

- production URL works and first E2E passes.

---

## Этап 14 - Post-launch

Do later:

- scheduled briefings;
- goals;
- insights;
- role briefings;
- rule compiler;
- sandbox;
- multi-model council.

---

# 23. Формат и правила использования этого файла

## 23.1 Как использовать

Этот файл надо использовать как главный документ для разработки. Перед каждой задачей AI-разработчику даётся:

- relevant section;
- TASK_ID;
- acceptance criteria;
- files likely;
- what not to touch.

## 23.2 Что делать, если появилась новая идея

1. Не менять код сразу.
2. Записать идею в `POST_MVP.md`.
3. Проверить: ломает ли она MVP scope.
4. Если идея обязательна, обновить `DECISIONS.md`.
5. Только потом создавать task.

## 23.3 Что делать, если статья/аналог кажется лучше

Не менять архитектуру сразу.

Порядок:

1. Выписать конкретный паттерн.
2. Сравнить с MVP.
3. Решить: now или post-MVP.
4. Если post-MVP - записать в `POST_MVP.md`.
5. Если now - добавить в `DECISIONS.md` и backlog.

## 23.4 Итоговый продуктовый принцип

founderOS не должен быть просто “ещё одной панелью для Jira/GitHub/Gmail”. Он должен стать рабочим Company Brain с UI и AI-брифингом.

Но строить его надо строго по лестнице:

```txt
Connectors
-> Raw Records
-> Normalized Entities
-> Evidence
-> Dashboard
-> Briefing
-> Action Proposal
-> Human Approval
-> Execution
```

## 23.5 Последнее правило

Каждая неделя должна приближать к работающему founderOS, а не к более красивой фантазии о founderOS.
