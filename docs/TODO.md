# FounderOS TODO

Только ближайшие задачи. Полный продуктовый контракт:
`../founderOS_MASTER_PLAYBOOK.md`. Проверяемый переход:
`AI_FOUNDEROS_ACCEPTANCE.md`.

## Сейчас — завершение FounderOS 2.0 reset

1. Перенести live provider sync из длинного API request в durable jobs с
   lease/retry/resume/progress/cancel и короткими транзакциями.
2. Подключить approved external error-reporting/tracing sink без payloads и
   завершить fail-closed hosted topology/RLS gate. Локальные structured logs,
   request IDs, counters и database readiness уже реализованы.
3. Провести разрешённые authenticated session/workspace и desktop/mobile
   browser gates и проверить
   overflow, console и основные состояния.
4. Подтвердить один read-only GitHub App read из рабочей организации с видимым
   canonical результатом.

## Следом — память и настоящее второе мнение

1. Добавить полные paginated live provider reads для Jira/Gmail/Drive, после
   чего подключить их к `source-reconciliation.v1`. Текущие локальные импорты
   не имеют права объявлять исчезновение.
2. Добавить обязательства клиентов, решения и риски с evidence.
3. Добавить contradiction detection между источниками.
4. Спроектировать privacy/retention/schema для generative LLM path.
5. Добавить управляемое исправление, забывание и удаление памяти.

## Внешний gate

Один founder-approved repository-scoped read из рабочей GitHub-организации с
видимым canonical результатом и безопасной квитанцией. До него не подключать
новые provider-first продуктовые экраны.

Публичный multi-tenant hosting дополнительно заблокирован до полного RLS gate
из DEC-102. Составные tenant FK уже обязательны, но не заменяют RLS.
