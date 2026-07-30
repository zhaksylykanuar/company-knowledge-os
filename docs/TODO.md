# FounderOS TODO

Только ближайшие задачи. Полный продуктовый контракт:
`../founderOS_MASTER_PLAYBOOK.md`. Проверяемый переход:
`AI_FOUNDEROS_ACCEPTANCE.md`.

## Сейчас — Repository Intelligence

1. После отдельного approval выполнить **RI-002**: read-only
   workspace-scoped L0 projection на synthetic canonical `Repository` и
   `SourceRecord`; no provider call, no filesystem snapshot as product truth,
   unknown при отсутствии evidence.
2. Затем отдельно согласовать RI-003 safe checkout manager. Checkout не может
   жить внутри FounderOS tree, выполнять target code или читать credentials.

RI-001 завершён: strict `repository_intelligence.v1`, synthetic L0/L1/L2
fixtures, object-shaped evidence, finite confidence, human-only resolution,
directional relationships и contradiction validation реализованы без migration,
persistence, UI, provider/LLM call или чтения company repositories (DEC-115).
Durable storage и migrations остаются RI-006 и требуют отдельного branch/PR
approval.

## Сейчас — завершение FounderOS 2.0 reset

1. Заново внести нужные provider credentials только через
   `Настройки → AI` и `Настройки → Подключения`, выполнить отдельные
   read-only проверки и не возвращать environment fallbacks.
2. Подключить approved external error-reporting/tracing sink без payloads и
   завершить fail-closed hosted topology/RLS gate. Локальные structured logs,
   request IDs, counters и database readiness уже реализованы.
3. Провести разрешённые authenticated session/workspace и desktop/mobile
   browser gates и проверить
   overflow, console и основные состояния.
4. Подтвердить один read-only GitHub App read из рабочей организации с видимым
   canonical результатом.
5. Настроить реальное независимое backup-хранилище и отдельное хранение ключа,
   выполнить первый encrypted export и полный restore drill. Механизм и
   runbook реализованы, но same-machine тест не является внешним proof.
6. В приватном GitHub проверить visibility, branch protection и private
   security-reporting channel; файлы LICENSE/SECURITY/CONTRIBUTING/CODEOWNERS
   уже добавлены локально.
7. Продолжать снижать ratchet для Headquarters, ActionProposalsPanel и global
   CSS только bounded slices с characterization конкретного поведения; broad
   refactor запрещён DEC-110.

## Следом — память и настоящее второе мнение

1. Добавить полные paginated live provider reads для Jira/Gmail/Drive, после
   чего подключить их к `source-reconciliation.v1`. Текущие локальные импорты
   не имеют права объявлять исчезновение.
2. Добавить обязательства клиентов, решения и риски с evidence.
3. Добавить contradiction detection между источниками.
4. Расширить Memory Control v1 с внутренних документов на provider-backed
   canonical records: exact dependency preview, evidence-safe cascade,
   reconciliation/reimport behavior и честная provider-side deletion boundary.

Workspace AI/privacy control, encrypted key lifecycle, provider-retention
acknowledgement, model/budget controls и synthetic read-only connection check
реализованы. Настоящий credentialed smoke ещё не выполнен.

Memory Control v1 реализован для FounderOS-authored документов: correction
purges prior versions, forget удаляет active row и все версии, stale preview
fail closed. Backups остаются до retention rotation; внешний provider cascade
ещё не реализован.

## Внешний gate

Один founder-approved repository-scoped read из рабочей GitHub-организации с
видимым canonical результатом и безопасной квитанцией. До него не подключать
новые provider-first продуктовые экраны.

Публичный multi-tenant hosting дополнительно заблокирован до полного RLS gate
из DEC-102. Составные tenant FK уже обязательны, но не заменяют RLS.

Disaster recovery operational readiness дополнительно заблокирован до первого
успешного restore drill с физически независимого хранилища и отдельно
восстановленного ключа (DEC-108).
