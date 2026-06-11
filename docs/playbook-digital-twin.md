---
title: "FounderOS - Company Digital Twin Playbook"
subtitle: "Implementation playbook for Codex and Claude"
author: "FounderOS"
date: "2026-06-11"
lang: ru-RU
geometry: margin=0.75in
mainfont: DejaVu Sans
monofont: DejaVu Sans Mono
fontsize: 10pt
toc: true
toc-depth: 3
---

# 0. Назначение документа

Этот playbook описывает, как проектировать и строить FounderOS как полноценную платформу цифрового двойника компании: с мозгом, живым графом знаний, текущими статусами, рекомендациями, second opinion, UI, Telegram-интерфейсом, безопасным action layer и настраиваемыми агентами.

Документ предназначен для Codex, Claude, технического архитектора, продуктовой команды и разработчиков. Его можно использовать как исходное техническое задание, архитектурный ориентир и backlog для итерационной разработки.

## 0.1. Главное правило

FounderOS - это не дайджест, не обычный чат-бот, не поиск по документам и не dashboard поверх Jira.

FounderOS - это живой цифровой двойник компании:

```text
All company sources
-> Company Knowledge Graph
-> Current Company State
-> AI Brain
-> Recommendations
-> Approved Actions
-> Web UI + Telegram
```

Цель: фаундер спрашивает систему, а не дергает людей без необходимости.

## 0.2. Правило нейтральных примеров

Не использовать реальные названия проектов, клиентов, репозиториев, людей и партнеров в примерах, тестах, фикстурах, демо-данных, документации и промптах.

Использовать только нейтральные placeholders:

```text
Projects: Project Alpha, Project Beta, Project Delta
Clients: Client One, Client Two, Client Three
People: Person A, Person B, Person C, Person D
Teams: Team Core, Team Platform, Team Delivery
Repositories: repo-alpha-api, repo-alpha-web, repo-beta-core
Jira keys: ALPHA-101, ALPHA-102, BETA-201
Documents: Alpha Requirements v1, Alpha Integration Draft
Meetings: Alpha Weekly Sync, Client One Review Call
```

Это важно, чтобы AI-агенты не начали путать реальные сущности с демо-примерами.

---

# 1. Vision

FounderOS должен стать операционной памятью и управленческим мозгом компании.

Фаундер должен иметь возможность открыть UI или Telegram и спросить:

```text
Что у нас с Project Alpha?
Что по разработке?
Почему Project Beta стал yellow?
Кто ждет моего ответа?
Какие задачи без движения?
Какие pull requests застряли?
Где Jira расходится с GitHub?
Что обещали Client One?
Подготовь меня к следующему звонку.
Создай задачи по последней встрече.
Какие решения ждут меня?
Какие риски по компании?
```

FounderOS должен отвечать не списком документов и не сухой статистикой, а управленческим выводом:

```text
- текущий статус;
- что изменилось;
- что реально сделано;
- что сейчас в работе;
- кто владелец;
- какие блокеры;
- какие риски;
- где источники противоречат друг другу;
- какие решения нужны;
- что система рекомендует сделать;
- какие источники подтверждают ответ;
- какой уровень уверенности.
```

## 1.1. Product definition

```text
FounderOS is a company digital twin platform that connects all operational sources,
builds a living company knowledge graph, maintains current state for projects, people,
clients, tasks, meetings and risks, provides AI second opinion, recommends management
actions, and lets the founder operate through Web UI and Telegram.
```

На русском:

```text
FounderOS - это платформа цифрового двойника компании, которая подключает рабочие
источники, строит живую карту компании, понимает текущее состояние проектов, людей,
клиентов, задач, встреч и рисков, сравнивает официальные статусы с фактической
активностью, дает second opinion, рекомендует действия и позволяет управлять через UI и
Telegram.
```

## 1.2. Core product promise

```text
Founder does not ask people "what is going on?"
Founder asks the company digital twin.
```

---

# 2. Product principles

## 2.1. Not a dashboard, but a company brain

Dashboard показывает данные. FounderOS должен объяснять, что эти данные значат.

Плохой ответ:

```text
В Jira 42 задачи, 12 in progress, 8 done.
```

Хороший ответ:

```text
Разработка движется, но главный bottleneck сейчас не количество задач, а review: 3 pull
requests ждут review больше 2 дней, один из них блокирует Project Alpha release. В Jira
статус выглядит стабильным, но GitHub показывает задержку.
```

## 2.2. Company state first

Ядро платформы - не документы и не сообщения, а текущее состояние компании.

```text
Company State
├── Project State
├── Engineering State
├── People State
├── Client State
├── Meeting State
├── Risk State
├── Decision State
├── Commitment State
├── Task State
└── Source Health State
```

## 2.3. Evidence-based reasoning

Каждый вывод должен иметь источники.

FounderOS должен уметь сказать:

```text
Я думаю так, потому что:
- Jira показывает ...
- GitHub показывает ...
- последнее письмо говорит ...
- документ был обновлен ...
- встреча создала action item ...

Уверенность: medium.
Почему не high: нет свежего update от владельца проекта.
```

## 2.4. Second opinion over status reporting

Система не просто пересказывает Jira или сообщения команды. Она сравнивает источники.

Пример:

```text
Reported status:
Jira показывает Project Alpha как on track.

Reality check:
GitHub показывает зависший PR, 2 задачи без активности и изменение требований в
документе без обновления backlog.

AI opinion:
Project Alpha должен быть yellow, не green.
```

## 2.5. No manual noise labeling

Пользователь не должен размечать шум.

FounderOS должен автоматически определять:

```text
- влияет ли событие на статус проекта;
- требует ли оно решения;
- создает ли риск;
- ждет ли внешний человек ответа;
- противоречит ли оно другим источникам;
- нужно ли создать задачу;
- обновляет ли оно знания компании.
```

Уточнения у пользователя допустимы только редко и только для важных вещей:

```text
Я нашел новую сущность "Project Alpha". Это проект, клиент или модуль?
[Project] [Client] [Module] [Ignore]
```

## 2.6. Push only when useful

Telegram не должен быть логом всех событий. Telegram - это command line фаундера и канал важных alerts.

Push only:

```text
- decision needed;
- client waiting;
- blocker;
- deadline risk;
- source conflict;
- important meeting prep;
- security event;
- repository/Jira mismatch;
- task/action suggestion that matters.
```

Everything else: store silently and show on demand.

---

# 3. Platform overview

## 3.1. Five-layer model

```text
1. Data Layer
   Connectors to company sources.

2. Knowledge Layer
   Company Knowledge Graph and entity relationships.

3. State Layer
   Current states for projects, clients, people, engineering, risks.

4. Intelligence Layer
   AI brain, reasoning, recommendations, second opinion.

5. Experience Layer
   Web UI, Telegram, approvals, settings, agent studio.
```

## 3.2. High-level architecture

```text
                 Web UI
        Command Center / Company Map / Rooms
                    |
               Telegram Bot
                    |
             AI Orchestrator
        Intent routing + tool selection
                    |
      ---------------------------------
      |               |               |
  Retrieval       Reasoning        Actions
   Agent           Agents          Agents
      |               |               |
      -------- Company Brain Core -----
              Knowledge Graph
              Company State
              Status Engine
              Recommendation Engine
                    |
      ---------------------------------
      |               |               |
   Postgres        pgvector        Raw Store
  entities        embeddings       files/events
                    |
             Sync + Connectors
 Jira / GitHub / Gmail / Calendar / Drive / Chat / CRM
```

## 3.3. Build order

Не начинать с агентов. Начать с модели компании.

Правильный порядок:

```text
1. Entities
   Project, Person, Client, Task, Repo, PR, Document, Email, Meeting, Decision, Risk.

2. Relationships
   Кто с чем связан.

3. Events
   Что изменилось.

4. State
   Что происходит сейчас.

5. Answers
   Что это значит.

6. Recommendations
   Что стоит сделать.

7. Actions
   Сделать через approval.
```

---

# 4. Data sources

## 4.1. Required MVP sources

```text
Jira
GitHub or GitLab
Gmail or company email
Google Calendar
Google Drive
Telegram bot
```

## 4.2. Later sources

```text
Slack or internal chat
Notion or Confluence
Meeting transcription tools
CRM
Cloud logs
Analytics
Finance tools
Support tools
```

## 4.3. What to extract from each source

### Jira

```text
- projects;
- epics;
- tasks;
- status;
- assignee;
- reporter;
- priority;
- due date;
- sprint;
- comments;
- labels;
- blockers;
- linked issues;
- stale tasks;
- overdue tasks.
```

### GitHub / GitLab

```text
- repositories;
- branches;
- commits;
- pull requests / merge requests;
- reviews;
- reviewers;
- CI/CD runs;
- releases;
- tags;
- linked Jira keys;
- PRs without Jira tasks;
- Jira tasks without code activity;
- stale PRs;
- review bottlenecks.
```

### Email

```text
- client requests;
- commitments;
- promised deadlines;
- open questions;
- follow-ups;
- attached documents;
- requirement changes;
- security events;
- external waiting signals;
- project/client mentions.
```

Important: never expose verification codes, tokens, passwords or secrets in Telegram.

### Calendar

```text
- meetings;
- participants;
- organizer;
- agenda/title;
- description;
- project/client links;
- upcoming calls;
- meeting prep triggers;
- meeting history.
```

### Drive / Docs / Files

```text
- requirements;
- specifications;
- contracts;
- proposals;
- presentations;
- meeting notes;
- decision documents;
- roadmaps;
- updated documents;
- superseded documents.
```

### Chat

```text
- fast status updates;
- blockers;
- informal decisions;
- requests;
- project mentions;
- action items;
- owner signals.
```

---

# 5. Company Knowledge Graph

## 5.1. Core idea

FounderOS needs a living graph, not just vector search.

Question:

```text
What is happening with Project Alpha?
```

Should expand into:

```text
Project Alpha
-> Jira epics/tasks
-> GitHub repositories
-> pull requests
-> commits
-> people
-> meetings
-> emails
-> documents
-> decisions
-> risks
-> blockers
-> commitments
-> status history
```

## 5.2. Entity types

```text
Company
Project
Client
Person
Team
Task
Epic
Repository
PullRequest
Commit
Branch
Release
CICDRun
Document
Email
Thread
CalendarEvent
Meeting
MeetingTranscript
Decision
Risk
Blocker
ActionItem
Deadline
Milestone
Requirement
Feature
Module
Commitment
FollowUp
Source
SourceEvent
StatusSnapshot
EntityLink
Alias
Permission
AuditLog
Recommendation
AutomationRule
NotificationRule
```

## 5.3. Relationship examples

```text
Person owns Task
Person reviews PullRequest
Person attended Meeting
Person sent Email
Person responsible_for Project

Task belongs_to Project
Task belongs_to Epic
Task linked_to PullRequest
Task blocked_by Blocker
Task depends_on Task
Task implements Requirement

PullRequest modifies Repository
PullRequest linked_to Task
PullRequest blocked_by Review
PullRequest affects Feature

Commit belongs_to Repository
Commit linked_to PullRequest
Commit mentions Task

Email mentions Project
Email mentions Client
Email creates ActionItem
Email updates Requirement
Email contains Commitment
Email requires Reply

Meeting relates_to Project
Meeting relates_to Client
Meeting produced Decision
Meeting created ActionItem
Meeting updated Risk

Document defines Requirement
Document relates_to Project
Document supersedes Document
Document affects Task

Decision affects Requirement
Decision affects Project
Decision creates Task

Risk threatens Milestone
Risk affects Project
Risk caused_by Blocker

CalendarEvent relates_to Meeting
CalendarEvent relates_to Client
CalendarEvent requires Briefing
```

## 5.4. Entity resolution

FounderOS must detect that different strings may refer to the same object.

Examples:

```text
Project Alpha
Alpha Project
ALPHA
Project-A

Client One
Client 1
Client-One Ltd

Person A
A. Person
person.a@company.com
```

Resolution strategy:

```text
1. Maintain aliases table.
2. Use deterministic matching for emails, IDs, Jira keys, repo names.
3. Use AI-assisted matching for natural-language mentions.
4. Store confidence score.
5. Ask user only when the entity is important and confidence is not enough.
```

Clarification example:

```text
I found "Alpha" in several sources.
Should it be linked to Project Alpha?
[Yes] [No] [Create new entity]
```

---

# 6. Company State

## 6.1. Why state matters

Search answers: "Where is this mentioned?"

FounderOS answers: "What is the current state?"

State must be recomputed when important events happen.

## 6.2. Project State Card

```text
Project: Project Alpha
Status: GREEN / YELLOW / RED / UNKNOWN
Owner: Person A
Confidence: high / medium / low
Last meaningful update: timestamp

Summary:
One paragraph explaining what is happening.

What changed:
- recent task changes;
- recent PR activity;
- document updates;
- meeting outcomes;
- client requests.

Current work:
- features;
- tasks;
- PRs;
- documents;
- decisions.

Blockers:
- blockers from Jira;
- blocked PRs;
- missing inputs;
- external waiting.

Risks:
- timeline risk;
- owner missing;
- requirement mismatch;
- stale tasks;
- source conflict.

Recommendations:
- action 1;
- action 2;
- action 3.

Evidence:
- source IDs and human-readable source cards.
```

## 6.3. Client State Card

```text
Client: Client One
Status: active / waiting / blocked / inactive
Last contact: timestamp
Waiting from us: yes/no/unknown
Waiting from them: yes/no/unknown
Related projects: Project Alpha, Project Beta
Open items:
- requirements clarification;
- commercial follow-up;
- technical meeting;
- pending document.
Recommendations:
- send follow-up;
- create task;
- schedule meeting;
- confirm requirement.
```

## 6.4. Person State Card

```text
Person: Person B
Role: engineer / reviewer / manager / stakeholder
Projects: Project Alpha, Project Beta
Open tasks: count
Active tasks: count
Overdue tasks: count
PRs waiting for this person: count
PRs authored: count
Bottleneck risk: low / medium / high
Recent meaningful activity: timestamp
AI note: concise management interpretation.
```

## 6.5. Engineering State

```text
Engineering State
- active projects;
- stale tasks;
- stale PRs;
- PRs without Jira;
- Jira tasks without code activity;
- CI/CD failures;
- review bottlenecks;
- release blockers;
- people load;
- repository activity.
```

## 6.6. Source Health State

FounderOS must always know whether its sources are healthy.

```text
Source: Jira
Status: connected / degraded / disconnected
Last successful sync: timestamp
Last error: message
Indexed objects: count
Webhook status: active/inactive
Permission status: valid/expired
```

If a source is stale, FounderOS must reduce confidence.

---

# 7. AI Brain

## 7.1. Brain components

```text
1. Memory
   Maintains company knowledge and aliases.

2. Understanding
   Extracts entities, decisions, risks, tasks and commitments from events.

3. Reasoning
   Compares sources and forms operational conclusions.

4. Recommendation
   Suggests next best actions.

5. Action
   Creates or updates external objects through approval.

6. Learning
   Improves aliases, rules, links and preferences by exception.

7. Explanation
   Shows evidence, confidence and gaps.
```

## 7.2. Agent responsibilities

### Founder Telegram Agent

```text
- receive natural-language questions;
- understand intent;
- route to the correct agent;
- produce short Telegram answers;
- show buttons;
- request approval for actions.
```

### UI Orchestrator Agent

```text
- power AI Ask Bar in web UI;
- provide page-aware answers;
- render evidence cards;
- suggest UI actions;
- preserve context of current page.
```

### Retrieval Agent

```text
- search graph, relational data, vector index and raw sources;
- return relevant facts;
- rank by freshness, authority and relevance;
- expose source IDs;
- separate facts from assumptions.
```

### Status Agent

```text
- build project/client/person status cards;
- summarize what changed;
- identify current work;
- list blockers and risks;
- compute confidence;
- create status snapshots.
```

### Engineering Agent

```text
- compare Jira with GitHub/GitLab;
- find PRs without tasks;
- find tasks without code activity;
- detect review bottlenecks;
- detect stale PRs;
- detect CI failures;
- explain development reality.
```

### Meeting Agent

```text
- prepare meeting briefings;
- link meetings to projects and clients;
- extract decisions and action items from transcripts;
- propose follow-up emails;
- propose Jira tasks;
- update affected project states.
```

### Risk Agent

```text
- detect risks;
- detect contradictions;
- detect external waiting;
- detect stale tasks;
- detect missing owners;
- detect promises without tasks;
- recommend mitigation.
```

### Jira Agent

```text
- create issue drafts;
- update issue drafts;
- add comments;
- generate acceptance criteria;
- suggest assignees and priorities;
- link issues to sources;
- require approval before write operations.
```

### Memory Agent

```text
- maintain aliases;
- merge duplicate entities;
- mark documents as outdated;
- maintain source of truth rules;
- ask clarification only for important ambiguous entities.
```

### Permission Agent

```text
- enforce read/write permissions;
- hide secrets;
- require approval;
- log all actions;
- prevent data leakage between users or projects.
```

---

# 8. Second Opinion Engine

## 8.1. Core checks

FounderOS must detect operational mismatches.

```text
1. Jira says in progress, but repository has no activity.
2. Repository has commits or PRs, but no linked Jira task.
3. Client requested change by email, but backlog was not updated.
4. Meeting created a decision, but no task exists.
5. Task is overdue, but project status is green.
6. PR waits for review longer than threshold.
7. Person has few tasks but is a review bottleneck.
8. Requirements document changed, but tasks did not change.
9. Important meeting is soon, but there is no agenda.
10. Email contains promised date, but no milestone exists.
11. Different sources show different status.
12. Old document is still being referenced.
13. Client is waiting for reply.
14. Chat says done, but PR is not merged.
15. PR is merged, but Jira task is still in progress.
```

## 8.2. Conflict answer format

```text
Data conflict found.

Jira:
- says Project Alpha is on track.

GitHub:
- PR #42 has waited for review for 3 days;
- no merged PRs in the last 5 days.

Documents:
- Alpha Requirements v2 was updated yesterday.

AI assessment:
- Project Alpha should be YELLOW, not GREEN.

Recommended action:
1. Review PR #42.
2. Create/update tasks from the new requirement.
3. Ask the project owner to confirm timeline.

Confidence: medium.
Reason: sources are fresh, but project owner has no recent written update.
```

## 8.3. Source of truth rules

```text
Development reality:
GitHub/GitLab and CI/CD are stronger than chat messages.

Task ownership:
Jira is stronger than chat, but chat can show Jira is outdated.

Client commitments:
Email and meeting transcripts are stronger than informal internal messages.

Calendar:
Calendar is source of truth for meeting time and participants.

Requirements:
Latest approved specification is stronger than old documents.

Decisions:
Decision log or meeting notes are stronger than casual messages.
```

If sources conflict, do not silently pick one. Show conflict, confidence and recommendation.

---

# 9. Recommendation Engine

## 9.1. Recommendation types

```text
Decision needed
Task needed
Follow-up needed
Review needed
Owner needed
Clarification needed
Risk mitigation
Calendar preparation
Backlog sync
Source conflict resolution
Security check
Source health fix
```

## 9.2. Recommendation object

```text
Recommendation
- id
- type
- title
- summary
- affected entity
- impact
- suggested action
- confidence
- evidence source IDs
- created_at
- status: open / accepted / dismissed / resolved
- owner
- expiration timestamp
```

## 9.3. Recommendation card example

```text
Type: Owner needed
Entity: Project Alpha integration module

Reason:
The integration work appears in documents and meeting notes, but no owner exists in
Jira.

Impact:
Timeline risk for Project Alpha.

Suggested action:
Assign owner and create Jira task for requirement confirmation.

Confidence: medium
Evidence: Jira + Drive + Meeting notes

Actions:
[Assign owner] [Create task] [Dismiss]
```

## 9.4. Ranking recommendations

Rank by:

```text
1. business impact;
2. deadline proximity;
3. external waiting;
4. blocker severity;
5. confidence;
6. source freshness;
7. affected project priority;
8. repeated occurrence;
9. user preferences.
```

---

# 10. Web UI

## 10.1. Main navigation

```text
Command Center
Company Map
Projects
Engineering
People
Clients
Meetings
Decisions
Risks
Tasks
Sources
Agents
Settings
```

## 10.2. Command Center

The home screen for the founder.

Should show:

```text
Company status: GREEN / YELLOW / RED
Needs your decision
Top risks
Clients waiting
Important changes
Meetings today/tomorrow
Engineering reality summary
AI recommendations
Second opinion alerts
Ask Bar
```

Example layout:

```text
FounderOS Command Center

Company state: YELLOW - mostly stable, 3 attention areas

Needs your decision:
- Project Alpha integration owner
- Project Beta pilot timeline

Risks:
- PR review bottleneck in Project Alpha
- Client One waiting for follow-up
- Requirements updated without Jira sync

Engineering:
- 4 active PRs
- 1 stale PR
- 3 Jira tasks without code activity
- 2 commits without linked tasks

AI recommendations:
1. Create Jira tasks from Client One email.
2. Review Project Alpha PR.
3. Prepare agenda for Project Beta call.

Ask FounderOS: [________________]
```

## 10.3. Company Map

Interactive graph/tree of company knowledge.

Should show:

```text
Company
├── Projects
├── Clients
├── People
├── Teams
├── Repositories
├── Jira Projects
├── Documents
├── Meetings
├── Decisions
├── Risks
└── Action Items
```

Opening Project Alpha should show connected:

```text
Project Alpha
├── owner
├── client
├── Jira epic
├── repositories
├── open tasks
├── PRs
├── documents
├── meetings
├── decisions
├── risks
└── recommendations
```

## 10.4. Projects page

Project list with state cards.

Columns:

```text
Project
Status
Owner
Last meaningful update
Main risk
Open decisions
Confidence
Sources health
```

Each project opens Project Room.

## 10.5. Project Room

Project Room is the most important object page.

Page blocks:

```text
Header:
- status;
- owner;
- client;
- confidence;
- last meaningful update;
- main risk;
- Ask about this project.

AI Summary:
- concise operational summary.

What changed:
- recent meaningful changes.

Current work:
- active tasks, PRs, documents, decisions.

Risks and blockers:
- with evidence.

Engineering reality:
- Jira vs GitHub.

Meetings:
- last meeting;
- next meeting;
- open action items.

Documents:
- active requirements;
- outdated docs;
- recently updated docs.

Decisions:
- active decisions;
- superseded decisions.

Recommendations:
- actionable cards.

Evidence:
- source cards.

History:
- status snapshots timeline.
```

## 10.6. Engineering page

Focus: reality of development, not just Jira.

Blocks:

```text
Engineering state summary
Jira vs GitHub Reality Check
Active PRs
Stale PRs
Stale tasks
CI/CD failures
Review bottlenecks
PRs without Jira
Jira tasks without code
People load
Repository activity
Release blockers
```

Example insight:

```text
Jira shows 12 tasks in progress.
GitHub confirms active work on 5.
3 PRs have no linked Jira task.
2 Jira tasks have no code activity for 8 days.
Main bottleneck: Person C review queue.
```

## 10.7. People page

Show operational load and bottlenecks.

Person card:

```text
Person B
Role: engineer / reviewer
Projects: Project Alpha, Project Beta
Open tasks: 8
Active tasks: 3
Overdue: 1
PRs awaiting review: 4
Recent activity: today
Bottleneck risk: high
AI note: not overloaded by task count, but blocking reviews.
```

## 10.8. Clients page

Client room should show:

```text
Client state
Related projects
Last contact
Waiting from us
Waiting from them
Open questions
Commitments
Documents
Meetings
Commercial items
Risks
Next best action
```

## 10.9. Meetings page

Meeting Intelligence:

```text
Today
Upcoming
Needs prep
Past meetings
Transcripts
Action items
Decisions
Follow-up drafts
```

Meeting briefing:

```text
Meeting: Client One Review Call
Time: tomorrow 10:00
Related project: Project Alpha
Participants: Person A, Person B, Client Contact 1

Context:
- last call discussed integration requirements;
- client asked for timeline;
- 2 Jira tasks are still open.

Open questions:
1. Confirm target deadline.
2. Confirm technical owner from client side.
3. Confirm API fields.

Recommendations:
- ask for final requirement approval;
- propose follow-up task creation.
```

## 10.10. Decisions page

Decision Log is critical.

Decision object:

```text
Decision
- title
- summary
- date
- participants
- source
- affected projects
- affected requirements
- affected tasks
- status: active / superseded / outdated
- rationale
- follow-up actions
```

Example:

```text
Decision: Use external authentication provider for Project Alpha.
Source: Alpha Weekly Sync.
Impact: backend API, auth module, requirements document.
AI note: Jira tasks do not fully reflect this decision.
```

## 10.11. Risks page

Risk Center:

```text
Critical
- Client waiting for reply.
- Release blocked by review.

Medium
- Jira/GitHub mismatch in Project Alpha.
- Requirements updated without backlog sync.

Low
- Project Delta has no owner for follow-up.
```

Risk card:

```text
Risk
- type
- affected project/client/person
- severity
- confidence
- evidence
- owner
- suggested action
- status
- history
```

## 10.12. Sources page

Show all integrations and health.

```text
Source
Status
Last sync
Last event
Indexed objects
Webhook status
Permissions
Errors
Owner
```

## 10.13. Agents page

Agent Studio.

For each agent:

```text
Status Agent: on/off
Engineering Agent: on/off
Meeting Agent: on/off
Risk Agent: on/off
Jira Agent: on/off
Memory Agent: on/off

Agent permissions:
- can read;
- can suggest;
- can write with approval;
- can never do.

Agent rules:
- monitored projects;
- alert thresholds;
- approval rules;
- quiet hours.
```

## 10.14. Settings

Settings should include:

```text
Company ontology
Aliases
Project priorities
Client priorities
Source of truth rules
Notification rules
Automation rules
Permissions
Audit log
Data retention
Security controls
```

---

# 11. Telegram UX

## 11.1. Telegram role

Telegram is not the main data UI. Telegram is:

```text
- command line for founder;
- important alert channel;
- quick approval interface;
- meeting prep delivery;
- fast project status Q&A.
```

## 11.2. Natural language questions

FounderOS should understand:

```text
what is happening with Project Alpha?
why is Project Beta yellow?
what changed this week?
what is the engineering status?
who is overloaded?
who is waiting for my response?
prepare me for the next meeting
create tasks from the last call
show stale PRs
where does Jira conflict with GitHub?
```

## 11.3. Commands

```text
/status Project Alpha
/changes Project Alpha 7d
/risks
/dev
/blocked
/reviews
/stale
/calendar today
/prep next
/followups
/create-task
/sources Project Alpha
/decisions Project Alpha
/people
/client Client One
```

## 11.4. Telegram answer format

Keep it short and expandable.

Template:

```text
Project Alpha - current status

Status: YELLOW
Summary: Development is moving, but review and requirements sync create timeline risk.

What changed:
- PR opened for API module;
- requirements document updated;
- 2 Jira tasks stale.

Risks:
- PR review delay;
- requirements not reflected in backlog.

Second opinion:
Jira looks stable, but GitHub shows a review bottleneck.

Recommended actions:
1. Review PR.
2. Create tasks from updated requirements.
3. Confirm integration owner.

Confidence: medium
Sources: Jira, GitHub, Drive, Calendar

[Deeper] [Tasks] [PRs] [Sources] [Create task]
```

## 11.5. Push alert examples

```text
Decision needed:
Project Alpha has no owner for integration work.
[Assign owner] [Create task] [Dismiss]
```

```text
Client waiting:
Client One has been waiting for a reply for 3 days.
[Draft follow-up] [Open thread] [Dismiss]
```

```text
Source conflict:
Jira says Project Beta is on track, but GitHub has no activity for 7 days.
[Show evidence] [Ask owner] [Dismiss]
```

## 11.6. Telegram buttons

Project status:

```text
[Deeper] [Show tasks] [Show PRs] [Show sources] [Create task]
```

Engineering:

```text
[By project] [By person] [PR review] [Stale tasks] [Jira vs GitHub]
```

Meeting:

```text
[Open materials] [Create agenda] [History] [Follow-up]
```

Action:

```text
[Approve] [Edit] [Cancel]
```

Risk:

```text
[Show facts] [Create task] [Ask owner] [Dismiss]
```

---

# 12. Data pipeline

## 12.1. Source event pipeline

```text
1. Source event arrives
   Example: new PR, email, Jira update, calendar event, document update.

2. Normalize
   Convert to common SourceEvent format.

3. Extract
   Extract entities, dates, risks, blockers, decisions, requirements, tasks,
   commitments.

4. Link
   Connect event to projects, clients, people, repos, tasks and documents.

5. Store
   Save raw payload, normalized event, extracted entities and links.

6. Update graph
   Update Company Knowledge Graph.

7. Update state
   Recompute affected Project State, Client State, Person State or Engineering State.

8. Reason
   Run second opinion checks and risk detection.

9. Recommend
   Create or update recommendations.

10. Decide notification
   Push only if important, otherwise store silently.

11. Act if approved
   Execute approved writes through action tools and log everything.
```

## 12.2. Normalized SourceEvent schema

```text
SourceEvent
- id
- source_type
- source_id
- source_url
- event_type
- title
- body_text
- author_id
- participant_ids
- occurred_at
- received_at
- raw_payload_uri
- permission_scope
- project_candidates
- client_candidates
- entity_candidates
- extracted_status
- processing_status
```

## 12.3. Extraction result schema

```text
ExtractionResult
- event_id
- extracted_entities
- extracted_relationships
- action_items
- decisions
- risks
- blockers
- deadlines
- commitments
- requirements
- confidence
- extraction_model
- created_at
```

## 12.4. Processing rules

```text
- Always keep raw event.
- Do not overwrite facts. Create new events and snapshots.
- Status snapshots are versioned.
- Every AI-generated conclusion must link to evidence.
- Store confidence with extraction and reasoning outputs.
- Recompute state when new important evidence appears.
```

---

# 13. Status Engine logic

## 13.1. Inputs

```text
- recent source events;
- Jira issues;
- PRs and commits;
- meeting notes;
- documents;
- emails;
- decisions;
- action items;
- risks;
- source health;
- prior status snapshots.
```

## 13.2. Output

```text
StatusSnapshot
- id
- entity_type: project/client/person/engineering/company
- entity_id
- status_color: green/yellow/red/unknown
- summary
- what_changed
- current_work
- blockers
- risks
- recommendations
- confidence
- confidence_reason
- last_meaningful_update_at
- evidence_source_ids
- created_at
```

## 13.3. Status colors

```text
GREEN:
Evidence shows normal progress and no major unresolved blockers.

YELLOW:
Progress exists, but there are risks, stale items, missing owner, source conflict or
external waiting.

RED:
Critical blocker, missed deadline, client escalation, release blocked, security issue or
major unresolved decision.

UNKNOWN:
Not enough fresh data or important source is disconnected.
```

## 13.4. Confidence scoring

Confidence should consider:

```text
- freshness of sources;
- number of independent sources;
- source authority;
- conflicts between sources;
- source health;
- entity resolution confidence;
- missing owner updates;
- raw evidence quality.
```

Example:

```text
Confidence: medium
Reason: Jira and GitHub are fresh, but latest client requirements were not confirmed by
project owner.
```

## 13.5. Status recomputation triggers

```text
- Jira task status changed;
- new or updated PR;
- CI failure;
- new client email;
- updated requirements document;
- meeting transcript processed;
- action item created or closed;
- deadline changed;
- risk created or resolved;
- source health changed.
```

---

# 14. Engineering Intelligence

## 14.1. Goals

Engineering Intelligence must answer:

```text
What is actually happening in development?
Where is work moving?
Where is work stuck?
Who is blocking review?
Which Jira tasks lack code activity?
Which PRs lack Jira tasks?
Which projects have risk?
```

## 14.2. Core checks

```text
PR without Jira key
Commit without task reference
Jira task in progress without PR/commit activity
Stale PR
Stale review
CI failure
Task marked done but PR not merged
PR merged but Jira still in progress
High task count
High review queue
Low activity in critical project
Release branch blocked
```

## 14.3. Engineering dashboard widgets

```text
Development summary
Jira vs GitHub reality check
Active PRs
Stale PRs
Review bottlenecks
CI/CD failures
Tasks without code
Code without tasks
People load
Repo activity
Release readiness
```

## 14.4. Engineering answer example

```text
Engineering - current status

Overall: YELLOW
Development is moving, but review is the main bottleneck.

By project:
1. Project Alpha
- backend activity exists;
- 1 PR waiting for review;
- 2 Jira tasks stale;
- risk: requirements sync.

2. Project Beta
- low repository activity in the last 5 days;
- Jira still shows tasks in progress;
- risk: status may be outdated.

Main bottlenecks:
- Person C review queue;
- tasks without linked PRs;
- requirements not reflected in backlog.

Second opinion:
The risk is not task count. The risk is mismatch between work tracking and actual code
movement.

Recommended actions:
1. Review stale PRs.
2. Link PRs to Jira tasks.
3. Update backlog from latest requirements.
```

---

# 15. Meeting and Client Intelligence

## 15.1. Before meeting

Trigger meeting briefing when:

```text
- meeting starts in 30-60 minutes;
- meeting has external participants;
- meeting is linked to active project;
- meeting has unresolved action items;
- related client has open questions;
- related project is yellow/red.
```

Briefing must include:

```text
- meeting title;
- time;
- participants;
- linked project/client;
- last interaction;
- open questions;
- our commitments;
- their commitments;
- related tasks;
- related documents;
- risks;
- recommended questions;
- suggested agenda.
```

## 15.2. After meeting

After transcript or notes arrive:

```text
1. Extract decisions.
2. Extract action items.
3. Extract risks and blockers.
4. Link to project/client/person.
5. Update state.
6. Suggest Jira tasks.
7. Suggest follow-up email.
8. Create reminders after approval.
```

## 15.3. Meeting summary example

```text
Meeting summary - Client One Review Call

Decisions:
- Client One wants phased rollout for Project Alpha.

Action items:
1. Person A to prepare updated API timeline.
2. Person B to confirm authentication requirements.
3. Client Contact 1 to send sample data.

Risks:
- timeline depends on external input.

Suggested Jira tasks:
1. Project Alpha: confirm authentication requirements.
2. Project Alpha: update API rollout plan.

Suggested follow-up:
- send recap and ask for sample data.

[Create tasks] [Draft email] [Open sources]
```

---

# 16. Action Layer

## 16.1. Principle

Read operations can run automatically. Write operations require approval.

```text
Can do automatically:
- search;
- summarize;
- link evidence;
- suggest;
- draft;
- prepare.

Needs approval:
- create Jira task;
- update Jira task;
- send email;
- create calendar event;
- send message to person;
- assign owner;
- close risk;
- update source of truth.
```

## 16.2. Jira task creation

FounderOS should create rich tasks, not empty tickets.

Task draft fields:

```text
Title
Description
Acceptance Criteria
Project
Epic
Priority
Assignee suggestion
Deadline suggestion
Source links
Related document
Related meeting
Related email
Related PR
Dependencies
Reason why this task is needed
```

Example:

```text
Title:
Project Alpha: confirm integration requirements

Description:
Based on the latest Client One review call and the updated Alpha Integration Draft, the
team needs to confirm final fields and integration scenarios.

Acceptance criteria:
- final field list confirmed;
- unclear scenarios marked;
- Jira backlog updated;
- engineering team receives final integration schema.

Suggested assignee: Person A
Priority: High
Sources: meeting, document, email thread

[Create] [Edit] [Cancel]
```

## 16.3. Follow-up email draft

```text
Subject: Project Alpha - follow-up and next steps

Hi Client Contact,

Thank you for the call. Here is a concise recap:
- decision 1;
- action item 1;
- action item 2.

Open question:
- please confirm ...

Next step:
- our team will ...

[Send] [Edit] [Cancel]
```

## 16.4. Audit log

Every action must log:

```text
- who requested;
- what agent proposed;
- what sources were used;
- what was approved;
- what external object changed;
- timestamp;
- before/after when possible.
```

---

# 17. Security and permissions

## 17.1. Required controls

```text
Read permissions separate from write permissions.
Role-based access control.
Source-level permissions.
Project-level permissions.
Approval for write actions.
Audit log.
Secret redaction.
Data retention settings.
Source disconnect controls.
User-visible source evidence.
Agent permission boundaries.
```

## 17.2. Sensitive data policy

Never show in Telegram:

```text
- verification codes;
- tokens;
- passwords;
- private keys;
- raw secrets;
- payment credentials;
- confidential attachments unless user is authorized.
```

Security event example:

```text
Security event detected:
A verification code email was received from a developer platform.
The code is not shown here.
If this was you, no action is needed. If not, review account access.
[Open email] [Dismiss]
```

## 17.3. Agent permissions

Each agent has:

```text
- allowed sources;
- allowed projects;
- allowed actions;
- approval requirements;
- redaction rules;
- audit requirements.
```

---

# 18. Technical stack

## 18.1. MVP stack

```text
Frontend:
Next.js + React + TypeScript

Backend:
FastAPI + Python or NestJS + Node.js

Database:
PostgreSQL

Vector search:
pgvector

Queue/workers:
Temporal, Celery, BullMQ or Redis Queue

Object storage:
S3-compatible storage

Integrations:
OAuth + webhooks + periodic sync

AI layer:
LLM orchestration + structured extraction + retrieval + tools

Interfaces:
Web UI + Telegram Bot API

Monitoring:
source health, worker health, audit log
```

## 18.2. Why start with Postgres + pgvector

Start simple:

```text
- relational entities;
- relationships table;
- source events;
- status snapshots;
- vector search in same database;
- easier operations;
- fewer moving parts.
```

Add graph database later only if required by complex graph queries and visualization scale.

## 18.3. Tool layer

Expose integrations as tools:

```text
jira.search_issues
jira.create_issue_draft
jira.create_issue
jira.update_issue

github.list_pull_requests
github.get_pull_request
github.get_commits
github.get_ci_runs

gmail.search_threads
gmail.get_thread
gmail.create_draft

calendar.list_events
calendar.get_event
calendar.create_event_draft

drive.search_documents
drive.get_document

knowledge.get_project_state
knowledge.get_client_state
knowledge.create_alias
knowledge.link_entities

risk.create_risk
recommendation.create
```

Agents should call tools through a permission and audit layer.

---

# 19. Database schema draft

This is not final SQL. It is an implementation blueprint.

## 19.1. Core tables

```text
organizations
- id
- name
- created_at

users
- id
- organization_id
- name
- email
- role
- created_at

sources
- id
- organization_id
- type
- name
- connection_status
- last_sync_at
- last_error
- permissions_json
- created_at

source_events
- id
- organization_id
- source_id
- source_type
- external_id
- event_type
- title
- body_text
- source_url
- raw_payload_uri
- occurred_at
- received_at
- processing_status
- permission_scope
- created_at

entities
- id
- organization_id
- type
- name
- canonical_name
- description
- status
- metadata_json
- created_at
- updated_at

aliases
- id
- organization_id
- entity_id
- alias
- confidence
- source
- created_at

entity_links
- id
- organization_id
- from_entity_id
- to_entity_id
- relationship_type
- confidence
- evidence_event_id
- created_at

embeddings
- id
- organization_id
- object_type
- object_id
- text_chunk
- embedding
- source_id
- created_at
```

## 19.2. Project state tables

```text
status_snapshots
- id
- organization_id
- entity_type
- entity_id
- status_color
- summary
- what_changed_json
- current_work_json
- blockers_json
- risks_json
- recommendations_json
- confidence
- confidence_reason
- last_meaningful_update_at
- evidence_source_ids_json
- created_at

recommendations
- id
- organization_id
- type
- title
- summary
- affected_entity_id
- impact
- suggested_action_json
- confidence
- evidence_source_ids_json
- status
- owner_user_id
- created_at
- resolved_at

risks
- id
- organization_id
- title
- description
- severity
- affected_entity_id
- owner_entity_id
- status
- confidence
- evidence_source_ids_json
- created_at
- resolved_at
```

## 19.3. External object tables

```text
jira_issues
- id
- organization_id
- source_id
- external_key
- title
- status
- assignee_entity_id
- project_entity_id
- priority
- due_date
- updated_at_external
- raw_json

git_pull_requests
- id
- organization_id
- source_id
- repo_entity_id
- external_id
- title
- status
- author_entity_id
- reviewer_entity_ids_json
- linked_task_entity_ids_json
- created_at_external
- updated_at_external
- merged_at_external
- raw_json

git_commits
- id
- organization_id
- source_id
- repo_entity_id
- external_sha
- message
- author_entity_id
- committed_at
- linked_task_keys_json
- raw_json

documents
- id
- organization_id
- source_id
- external_id
- title
- document_type
- owner_entity_id
- updated_at_external
- source_url
- raw_text_uri
- raw_json

emails
- id
- organization_id
- source_id
- thread_external_id
- external_id
- subject
- sender_entity_id
- recipient_entity_ids_json
- occurred_at
- requires_reply
- source_url
- raw_json

meetings
- id
- organization_id
- source_id
- external_id
- title
- starts_at
- ends_at
- participant_entity_ids_json
- related_entity_ids_json
- transcript_uri
- summary
- source_url
- raw_json
```

## 19.4. Audit and actions

```text
action_drafts
- id
- organization_id
- action_type
- proposed_by_agent
- requested_by_user_id
- payload_json
- evidence_source_ids_json
- status: draft / approved / rejected / executed
- created_at
- executed_at

audit_logs
- id
- organization_id
- actor_type
- actor_id
- action_type
- target_type
- target_id
- before_json
- after_json
- evidence_source_ids_json
- created_at
```

---

# 20. API endpoints draft

## 20.1. UI APIs

```text
GET /api/command-center
GET /api/company-map
GET /api/projects
GET /api/projects/{project_id}
GET /api/projects/{project_id}/status
GET /api/projects/{project_id}/history
GET /api/engineering
GET /api/people
GET /api/people/{person_id}
GET /api/clients
GET /api/clients/{client_id}
GET /api/meetings
GET /api/meetings/{meeting_id}
GET /api/risks
GET /api/decisions
GET /api/recommendations
GET /api/sources
GET /api/agents
GET /api/audit-log
```

## 20.2. Ask APIs

```text
POST /api/ask
POST /api/telegram/webhook
POST /api/agents/run
POST /api/status/recompute
```

Ask request:

```json
{
  "question": "What is happening with Project Alpha?",
  "context": {
    "ui_page": "project_room",
    "entity_id": "project_alpha_id"
  }
}
```

Ask response:

```json
{
  "answer": "Project Alpha is YELLOW...",
  "status": "yellow",
  "confidence": "medium",
  "evidence": [
    {"source_type": "jira", "title": "ALPHA-101"},
    {"source_type": "github", "title": "PR #42"}
  ],
  "recommended_actions": [
    {"type": "create_task", "title": "Confirm integration requirements"}
  ],
  "buttons": ["deeper", "show_tasks", "show_sources"]
}
```

## 20.3. Integration APIs

```text
POST /api/integrations/jira/connect
POST /api/integrations/github/connect
POST /api/integrations/google/connect
POST /api/webhooks/jira
POST /api/webhooks/github
POST /api/webhooks/google
POST /api/sync/{source_id}/run
```

## 20.4. Action APIs

```text
POST /api/actions/draft
POST /api/actions/{draft_id}/approve
POST /api/actions/{draft_id}/reject
POST /api/actions/{draft_id}/execute
```

---

# 21. Background jobs and workers

## 21.1. Sync workers

```text
sync_jira_projects
sync_jira_issues
sync_github_repos
sync_github_prs
sync_github_commits
sync_gmail_threads
sync_calendar_events
sync_drive_documents
```

## 21.2. Processing workers

```text
normalize_source_event
extract_entities_from_event
resolve_entities
link_entities
embed_text_chunks
update_knowledge_graph
recompute_project_state
recompute_client_state
recompute_person_state
run_second_opinion_checks
run_risk_detection
rank_recommendations
prepare_telegram_alerts
```

## 21.3. Meeting workers

```text
prepare_meeting_briefings
process_meeting_transcript
extract_meeting_decisions
extract_meeting_action_items
suggest_meeting_followups
```

## 21.4. Health workers

```text
check_source_health
check_webhook_health
check_permission_expiry
check_worker_backlog
alert_admin_on_sync_failure
```

---

# 22. Phased roadmap

## Phase 0 - Product framing and data inventory

Goal:
Define scope, sources, entity model and first user flows.

Build:

```text
- product vision;
- source inventory;
- placeholder demo data;
- entity taxonomy;
- relationship taxonomy;
- initial UI wireframes;
- security assumptions;
- MVP success criteria.
```

Acceptance criteria:

```text
- no real names in examples;
- 5-10 neutral demo entities exist;
- core user flows documented;
- architecture approved;
- MVP scope locked.
```

## Phase 1 - Digital Twin Core

Goal:
Create the living map of company objects.

Build:

```text
- source connectors for Jira, GitHub, Gmail, Calendar, Drive;
- normalized event store;
- source health;
- entity extraction;
- aliases;
- project/person/client/repo/task/document entities;
- basic entity links;
- initial Company Map;
- Telegram bot skeleton;
- Ask endpoint skeleton.
```

Acceptance criteria:

```text
- system ingests source events;
- system creates entities and links;
- Company Map shows projects, people, repos, tasks and docs;
- source health is visible;
- Telegram can answer basic lookup questions.
```

## Phase 2 - Current State Engine

Goal:
Make every project have a living status.

Build:

```text
- project state cards;
- status snapshots;
- status recomputation jobs;
- what changed;
- current work;
- blockers;
- risks;
- confidence score;
- evidence links;
- Project Room UI;
- /status Telegram flow.
```

Acceptance criteria:

```text
- user asks "what is happening with Project Alpha?";
- system returns current status, changes, risks, blockers and sources;
- status snapshot history is stored;
- confidence is shown and explained.
```

## Phase 3 - Engineering Reality

Goal:
Understand development beyond Jira.

Build:

```text
- Jira/GitHub linking;
- PR without Jira detection;
- Jira without code activity detection;
- stale PR detection;
- stale task detection;
- review bottleneck detection;
- CI/CD failure detection;
- Engineering page;
- /dev Telegram flow.
```

Acceptance criteria:

```text
- system explains engineering reality;
- system detects mismatch between Jira and GitHub;
- system identifies review bottlenecks;
- system gives recommendations.
```

## Phase 4 - Meeting and Client Intelligence

Goal:
Prepare founder for calls and convert meetings into actions.

Build:

```text
- calendar event linking;
- meeting briefing engine;
- client pages;
- transcript ingestion;
- decision extraction;
- action item extraction;
- follow-up suggestions;
- meeting-related project state updates;
- /prep Telegram flow.
```

Acceptance criteria:

```text
- before a Client One meeting, system shows context, open questions and recommendations;
- after a transcript, system extracts decisions and action items;
- system suggests Jira tasks and follow-up draft.
```

## Phase 5 - Recommendations and Second Opinion

Goal:
Make FounderOS proactive and opinionated based on evidence.

Build:

```text
- recommendation engine;
- second opinion checks;
- contradiction detection;
- external waiting detection;
- deadline risk detection;
- document/backlog mismatch;
- meeting decision without task;
- Jira/GitHub reality check;
- recommendation ranking;
- important Telegram alerts.
```

Acceptance criteria:

```text
- system proactively flags meaningful risks;
- system does not spam low-priority events;
- every alert has evidence, confidence and recommended action;
- user can dismiss, accept or convert recommendation into task.
```

## Phase 6 - Action Layer

Goal:
Let FounderOS help manage work safely.

Build:

```text
- Jira task draft creation;
- Jira task creation after approval;
- Jira update/comment after approval;
- email draft generation;
- calendar draft generation;
- reminder creation;
- owner assignment proposal;
- action drafts UI;
- approval flows;
- audit log.
```

Acceptance criteria:

```text
- from email/meeting/risk, system proposes high-quality Jira task;
- write action happens only after approval;
- action is logged with evidence;
- user can edit before executing.
```

## Phase 7 - Full Platform

Goal:
Make FounderOS a configurable company operating platform.

Build:

```text
- advanced dashboard;
- graph visualization;
- agent studio;
- automation builder;
- role-based access;
- team views;
- custom notification rules;
- advanced source of truth rules;
- decision log;
- risk register;
- API for integrations;
- enterprise security.
```

Acceptance criteria:

```text
- admin can configure sources, agents, permissions and notifications;
- founder can view company state across projects, people, clients and risks;
- agents act within configured permissions;
- all outputs remain evidence-based.
```

---

# 23. MVP: first two weeks

## 23.1. Goal

Build a thin but real vertical slice:

```text
Question: "What is happening with Project Alpha?"
Answer: current status from neutral demo data and at least one real connector stub or
sandbox source.
```

For the first version, use placeholders only.

## 23.2. Week 1

```text
Day 1:
- create repo structure;
- define entity model;
- define SourceEvent model;
- create Postgres schema draft;
- create mock data with Project Alpha, Client One, Person A, repo-alpha-api.

Day 2:
- implement backend skeleton;
- implement entities API;
- implement source events API;
- implement basic Company Map API.

Day 3:
- implement UI skeleton;
- Command Center page;
- Projects page;
- Project Room page.

Day 4:
- implement simple retrieval over mock events;
- implement Project State Card generator;
- store status snapshots.

Day 5:
- implement Telegram bot skeleton;
- implement /status Project Alpha;
- render evidence cards.
```

## 23.3. Week 2

```text
Day 6:
- add GitHub/Jira mock connectors or sandbox connectors;
- parse PR/task links from keys like ALPHA-101.

Day 7:
- implement stale task and stale PR checks;
- implement basic engineering reality summary.

Day 8:
- implement recommendation cards;
- add recommendation UI;
- add dismiss/accept states.

Day 9:
- add source health page;
- add audit log skeleton;
- add confidence explanation.

Day 10:
- polish Project Room;
- add seed demo data;
- add tests;
- prepare demo script.
```

## 23.4. First demo script

```text
1. Open Command Center.
2. Show Company State: YELLOW due to Project Alpha risk.
3. Open Project Alpha.
4. Show current status, evidence, risks and recommendations.
5. Ask: "What is happening with Project Alpha?"
6. Show answer with evidence and confidence.
7. Open Engineering.
8. Show Jira vs GitHub mismatch.
9. Open Telegram.
10. Run /status Project Alpha.
11. Show recommendation: create Jira task draft.
```

---

# 24. Codex/Claude implementation instructions

## 24.1. General instruction

Use this playbook as the source of truth.

When implementing FounderOS:

```text
- Do not use real project names.
- Use only neutral placeholders from section 0.2.
- Build incrementally.
- Prefer vertical slices over broad unfinished architecture.
- Make state explicit and versioned.
- Every AI conclusion must include evidence and confidence.
- All write actions must require approval.
- Do not build a generic chatbot. Build a company state platform.
```

## 24.2. Codex prompt

```text
You are implementing FounderOS, a company digital twin platform.

Use the attached playbook as the product and architecture source of truth.

Important constraints:
- Do not use real project, client, repo or person names.
- Use placeholders: Project Alpha, Project Beta, Client One, Person A, repo-alpha-api,
  ALPHA-101.
- Build a vertical slice first: Project State Card for Project Alpha from mock source
  events.
- The system must store raw source events, extracted entities, entity links and status
  snapshots.
- The UI must include Command Center, Projects list and Project Room.
- The API must expose project status with evidence and confidence.
- All AI-generated conclusions must include evidence_source_ids.
- Write actions must be represented as drafts and require approval.

First task:
Create the initial repository structure, database schema, seed data and API endpoints
for:
1. sources
2. source_events
3. entities
4. entity_links
5. status_snapshots
6. recommendations
7. project status endpoint
8. mock Project Alpha data

Deliver production-quality code with tests and clear file structure.
```

## 24.3. Claude prompt for product/architecture refinement

```text
You are a CTO-level product architect helping design FounderOS, a company digital twin
platform.

Use the playbook as the source of truth.

Your job:
- refine the product architecture;
- identify missing data models;
- improve the phased roadmap;
- propose better UX for Command Center, Company Map and Project Room;
- improve agent responsibilities;
- keep everything implementation-ready;
- avoid abstract strategy without buildable details.

Constraints:
- Do not use real project or client names.
- Use only placeholders: Project Alpha, Client One, Person A, repo-alpha-api, ALPHA-101.
- FounderOS is not a chatbot or dashboard. It is a company digital twin with current
  state, second opinion, recommendations and approved actions.

Output:
1. Architecture improvements
2. Data model improvements
3. UX improvements
4. Risk areas
5. Build priorities for the next two weeks
6. Acceptance criteria
```

## 24.4. Prompt for generating UI spec

```text
Create a detailed UI specification for FounderOS.

Required pages:
- Command Center
- Company Map
- Projects
- Project Room
- Engineering
- People
- Clients
- Meetings
- Decisions
- Risks
- Sources
- Agents
- Settings

For each page include:
- purpose;
- primary user questions;
- key widgets;
- data required;
- empty states;
- loading states;
- important actions;
- examples using only Project Alpha, Client One, Person A and repo-alpha-api.

Do not use real names.
Make it practical for frontend implementation in Next.js.
```

## 24.5. Prompt for generating backend spec

```text
Create a backend technical specification for FounderOS.

Use the playbook as source of truth.

Include:
- PostgreSQL schema;
- API endpoints;
- worker jobs;
- source event pipeline;
- entity extraction pipeline;
- status snapshot pipeline;
- recommendation engine;
- permission and audit model;
- action draft and approval flow;
- test strategy.

Use only neutral examples:
Project Alpha, Client One, Person A, repo-alpha-api, ALPHA-101.
```

## 24.6. Prompt for building the first vertical slice

```text
Build the first vertical slice of FounderOS.

Feature:
Project Alpha current status.

Inputs:
- mock Jira task ALPHA-101;
- mock GitHub PR #42 in repo-alpha-api;
- mock document Alpha Requirements v1;
- mock meeting Alpha Weekly Sync;
- mock email thread from Client One.

Output:
- Project Room UI shows Project Alpha state;
- API returns status snapshot;
- Telegram /status Project Alpha returns concise answer;
- evidence cards are shown;
- confidence is shown;
- recommendation is created if PR waits for review or requirements are not synced.

Do not use real project names.
```

---

# 25. Acceptance criteria checklist

## 25.1. Product acceptance

```text
[ ] Founder can ask what is happening with Project Alpha.
[ ] Answer includes status, summary, changes, risks, recommendations.
[ ] Answer includes evidence and confidence.
[ ] UI shows Project Room.
[ ] Command Center shows top risks and recommendations.
[ ] Engineering page shows Jira/GitHub reality.
[ ] Telegram can return a useful one-screen answer.
[ ] System does not push low-priority noise.
[ ] No real project names are used in examples or tests.
```

## 25.2. Data acceptance

```text
[ ] Raw source events are stored.
[ ] Extracted entities are stored.
[ ] Entity links are stored.
[ ] Aliases exist.
[ ] Status snapshots are versioned.
[ ] Evidence source IDs are attached to AI outputs.
[ ] Source health is tracked.
```

## 25.3. AI acceptance

```text
[ ] AI separates facts from assumptions.
[ ] AI shows confidence.
[ ] AI detects at least one source conflict.
[ ] AI detects stale task or stale PR.
[ ] AI creates recommendation with evidence.
[ ] AI does not expose secrets.
[ ] AI does not execute write action without approval.
```

## 25.4. Security acceptance

```text
[ ] Read/write permissions are separate.
[ ] Write actions require approval.
[ ] Audit log records actions.
[ ] Secrets are redacted.
[ ] Source access can be revoked.
[ ] Telegram does not expose sensitive data.
```

---

# 26. Do and do not

## 26.1. Do

```text
Do build around Company State.
Do use neutral placeholders.
Do store raw events and evidence.
Do version status snapshots.
Do show confidence.
Do show conflicts.
Do make recommendations actionable.
Do require approvals for write actions.
Do keep Telegram concise.
Do make UI explain why something is yellow/red.
```

## 26.2. Do not

```text
Do not build a generic chatbot.
Do not build only a Jira dashboard.
Do not build only semantic search.
Do not spam Telegram.
Do not require user to label every noisy item.
Do not hallucinate without evidence.
Do not hide source conflicts.
Do not use real project/client names in demos.
Do not automatically send emails.
Do not automatically create Jira tasks without approval.
Do not expose verification codes or secrets.
```

---

# 27. Final product formula

```text
FounderOS =
Digital Twin Core
+ Company Knowledge Graph
+ Current State Engine
+ Engineering Reality Check
+ Meeting Intelligence
+ Recommendation Engine
+ Second Opinion
+ Approval-based Action Layer
+ Web UI
+ Telegram Founder Copilot
```

The simplest useful version:

```text
Ask: "What is happening with Project Alpha?"
Get: current status, evidence, risk, recommendation, confidence.
```

The final version:

```text
FounderOS becomes the living brain of the company:
it observes, understands, remembers, reasons, recommends, acts with approval and
explains itself.
```
