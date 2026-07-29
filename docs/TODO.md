# FounderOS TODO

Только ближайшие задачи. Полный продуктовый контракт:
`../founderOS_MASTER_PLAYBOOK.md`. Проверяемый переход:
`AI_FOUNDEROS_ACCEPTANCE.md`.

## Сейчас — high-priority audit remediation

1. Ввести строгую same-workspace evidence validation для approval/execution и
   унифицировать bulk decisions.
2. Закрепить workspace-owned связи составными PostgreSQL FK и отрицательными
   tenancy-тестами.

## Сейчас — завершение FounderOS 2.0 reset

1. Провести разрешённый authenticated desktop/mobile browser QA и проверить
   overflow, console и основные состояния.
2. Подтвердить один read-only GitHub App read из рабочей организации с видимым
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
