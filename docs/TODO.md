# FounderOS TODO

Только ближайшие задачи. Полный продуктовый контракт:
`../founderOS_MASTER_PLAYBOOK.md`. Проверяемый переход:
`AI_FOUNDEROS_ACCEPTANCE.md`.

## Сейчас — завершение FounderOS 2.0 reset

1. Разделить smoke-gates на публичную живость, authenticated session,
   workspace read и browser E2E; добавить database-backed readiness и
   наблюдаемость без утечки данных.
2. Закрыть hosted auth/security gates: admission policy, trusted proxy,
   shared rate limiting, cleanup, CSRF, security headers и production OpenAPI.
3. Провести разрешённый authenticated desktop/mobile browser QA и проверить
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
