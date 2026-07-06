// Central Russian UI message catalog. ALL user-facing copy lives here so wording
// is editable in one place and a second locale can be added later as a small
// addition (export another object of the same shape). Code identifiers, routes,
// data-testids, and backend enum values stay in English; only chrome is Russian.

export const M = {
  app: {
    name: "founderOS",
    shellMode: "MVP-оболочка",
    metaTitle: "founderOS",
    metaDescription: "Минимальная оболочка MVP founderOS"
  },

  nav: {
    primaryLabel: "Основная навигация",
    home: "Главная",
    dashboard: "Панель",
    github: "GitHub",
    jira: "Jira",
    gmail: "Gmail",
    connectors: "Коннекторы",
    audit: "Аудит репо",
    briefings: "Сводки",
    actions: "Действия",
    settings: "Настройки"
  },

  common: {
    loading: "Загрузка",
    retry: "Повторить",
    close: "Закрыть",
    refreshStatus: "Обновить статус",
    openSource: "Открыть источник",
    signOut: "Выйти",
    requestFailed: "Запрос не удался.",
    unknown: "неизвестно",
    none: "нет",
    yes: "да",
    no: "нет",
    noWorkspaceTitle: "Нет рабочего пространства",
    enabled: "включено",
    notEnabled: "не включено",
    available: "доступно",
    unavailable: "недоступно",
    warnings: "Предупреждения"
  },

  auth: {
    title: "founderOS",
    subtitle: "Войдите, чтобы продолжить.",
    email: "Эл. почта",
    password: "Пароль",
    signIn: "Войти",
    signingIn: "Выполняется вход…",
    loginFailedGeneric: "Неверная почта или пароль.",
    loginFailedLocked: "Слишком много неудачных попыток. Попробуйте позже.",
    loginFailedUnknown: "Не удалось войти.",
    setupTitle: "Задать пароль",
    setupSubtitle:
      "Введите новый локальный пароль по одноразовой ссылке приглашения.",
    setupPassword: "Новый пароль",
    setupSubmit: "Задать пароль и войти",
    setupSubmitting: "Настройка…",
    setupMissingToken: "Ссылка настройки пароля недействительна или неполная.",
    setupFailed: "Не удалось задать пароль. Проверьте ссылку или запросите новую."
  },

  home: {
    eyebrow: "founderOS",
    title: "Оболочка MVP founderOS",
    description: "Минимальная оболочка Next.js для GitHub-ориентированного пути MVP.",
    cards: {
      dashboard: {
        title: "Панель",
        value: "MVP",
        description: "Рабочее пространство, GitHub, сводка, действия и статус бэкенда."
      },
      github: {
        title: "GitHub",
        value: "Поток",
        description: "Подключение, репозитории, задания синхронизации и локальная нормализация."
      },
      briefings: {
        title: "Сводки",
        value: "Ручная",
        description: "Детерминированная сводка для основателя v0."
      },
      actions: {
        title: "Действия",
        value: "Одобрение",
        description: "Состояния предложений и граница записи с одобрением человеком."
      },
      settings: {
        title: "Настройки",
        value: "Аккаунт",
        description: "Ваш аккаунт, выход и смена пароля."
      }
    }
  },

  dashboard: {
    eyebrow: "Панель",
    title: "Статус MVP",
    description: "Вид после входа: поток бэкенда и GitHub-ориентированные экраны MVP.",
    backendTitle: "API бэкенда",
    backendValue: "Подключено",
    backendDescription: "API того же origin с авторизацией по сессионной cookie.",
    workspaceTitle: "Рабочее пространство",
    workspaceActive: "Активно",
    workspaceNone: "Нет",
    workspaceNoneDescription: "У этого аккаунта пока нет рабочего пространства.",
    githubTitle: "GitHub",
    githubValue: "Подключено",
    githubDescription:
      "Локальная синхронизация, Мозг компании и канонические данные загружаются ниже.",
    briefingTitle: "Сводка",
    briefingValue: "Подключено",
    briefingDescription: "Ручная детерминированная сводка для основателя v0.",
    actionsTitle: "Действия",
    actionsValue: "Локальное одобрение",
    actionsDescription: "Состояния предложений, одобрения и выполнения."
  },

  githubPage: {
    eyebrow: "GitHub",
    title: "Поток бэкенда GitHub",
    description: "Экраны MVP в рамках рабочего пространства поверх существующих контрактов бэкенда.",
    connectionTitle: "Статус подключения",
    connectionValue: "Бэкенд",
    connectionDescription:
      "Читает /api/v1/workspaces/{workspace_id}/github/connection-status.",
    reposTitle: "Репозитории",
    reposValue: "Бэкенд",
    reposDescription: "Читает локальную опись репозиториев через бэкенд.",
    syncJobsTitle: "Задания синхронизации",
    syncJobsValue: "Вручную",
    syncJobsDescription: "Записи SyncJob локальны, пока нет рабочего процесса воркера.",
    normalizationTitle: "Локальная нормализация",
    normalizationValue: "Канонические",
    normalizationDescription:
      "Канонические репозитории, задачи и пулреквесты видны на панели.",
    scaffoldTitle: "Управление потоком GitHub — пока локальные заготовки MVP.",
    scaffoldDescription:
      "Панель уже читает каноническую работу GitHub. Эти элементы подключения и синхронизации остаются заготовками до появления продуктового подключения/синхронизации."
  },

  githubProductConnect: {
    eyebrow: "GitHub App",
    title: "Продуктовое подключение GitHub",
    badgeReadOnly: "Только чтение",
    description:
      "Фундамент подключения через GitHub App: установка привязана к рабочему пространству, токены установки не хранятся, внешние записи отключены.",
    loading: "Загрузка состояния GitHub App",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — подключать нечего.",
    unavailableTitle: "Состояние GitHub App недоступно",
    unavailableDescription: "Панель не смогла загрузить состояние продуктового подключения GitHub.",
    appTitle: "GitHub App",
    appConnected: "Подключено",
    appConfigured: "Готово",
    appNotConfigured: "Не настроено",
    appInstallationDescription: "Установка GitHub App записана в этом рабочем пространстве.",
    appReadyDescription: "Конфигурация GitHub App готова; можно установить приложение для рабочего пространства.",
    appMissingDescription: "Нужны server-side env-поля GitHub App перед установкой.",
    repositoriesTitle: "Локальная поверхность репозиториев",
    tokenTitle: "Токены установки хранятся",
    tokenDescription: "Для GitHub App токены установки должны выпускаться just-in-time и не сохраняться.",
    writeTitle: "Записи в GitHub",
    writeDescription: "Product connect остаётся read-only; write-actions включаются только отдельным approval path.",
    missingEnvTitle: "Не хватает server-side env-полей",
    openSetup: "Открыть установку GitHub App",
    liveSyncTitle: "Живая read-only синхронизация",
    liveSyncDescription:
      "Запускает backend polling-only GitHub App sync для одного явно указанного репозитория. Токен установки выпускается just-in-time, не сохраняется, записи в GitHub не выполняются.",
    liveSyncRepositoryLabel: "Репозиторий для синхронизации",
    liveSyncRepositoryPlaceholder: "owner/repo",
    liveSyncRepositoryNote:
      "Репозиторий должен быть доступен текущей установке GitHub App. Массовая синхронизация всей организации здесь не запускается.",
    liveSyncRepositoryInvalid: "Укажите репозиторий в формате owner/repo без пробелов.",
    liveSyncRequiresApp: "Сначала нужна подключённая запись GitHub App installation.",
    liveSyncRun: "Синхронизировать read-only",
    liveSyncRunning: "Идёт read-only синхронизация",
    liveSyncFailedTitle: "Живая read-only синхронизация не удалась",
    liveSyncFailedDescription: "Backend не смог выполнить GitHub App read sync.",
    liveSyncResultTitle: "Итог GitHub App read sync",
    liveSyncNoWrites: "Записи в GitHub не выполнялись.",
    repositoryListTitle: "Репозитории",
    repositoryListEmptyTitle: "Репозитории не найдены",
    repositoryListEmptyDescription:
      "Локальная поверхность репозиториев пуста. Сначала подготовьте repository surface или подключите GitHub App.",
    repositoryFocusTitle: "Фокус локальной repo surface",
    repositoryFocusLabel: "Фильтр локальной поверхности репозиториев",
    repositoryFocusDescription:
      "Фильтр работает только по уже загруженному списку репозиториев и не запускает provider calls, bulk sync или внешние записи.",
    repositoryFocusAll: "Все repo",
    repositoryFocusActive: "Активные",
    repositoryFocusArchived: "Архивные",
    repositoryFocusPrivate: "Private",
    repositoryFocusWithEvidence: "С evidence",
    repositoryListNoReposForFilter:
      "Для выбранного локального фильтра репозиториев нет."
  },

  githubSync: {
    eyebrow: "GitHub",
    title: "Локальная синхронизация",
    badgeNoLiveProvider: "Без живого провайдера",
    loading: "Загрузка состояния подключения GitHub",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — синхронизировать нечего.",
    stateUnavailableTitle: "Состояние синхронизации GitHub недоступно",
    stateUnavailableDescription: "Панель не смогла загрузить состояние синхронизации GitHub.",
    connectionRecordTitle: "Запись подключения",
    connectionRecordMissing: "Отсутствует",
    executionModeTitle: "Режим выполнения",
    executionModeValue: "Только локально",
    executionModeDescription: "Живой OAuth и выполнение у провайдера из этого интерфейса не включены.",
    repoSourceTitle: "Источник репозиториев",
    repoSourceAvailable: "Доступен",
    repoSourceUnavailable: "Недоступен",
    connectionRequiredTitle: "Требуется запись подключения GitHub",
    connectionRequiredDescription:
      "Живой OAuth ещё не включён. Этот элемент может нормализовать локальные данные GitHub после появления записи подключения GitHub в бэкенде.",
    connectionNotReadyTitle: "Запись подключения GitHub не готова",
    runSync: "Запустить локальную синхронизацию GitHub",
    runningSync: "Идёт локальная синхронизация",
    syncFailedTitle: "Локальная синхронизация GitHub не удалась",
    syncFailedDescription: "Запрос локальной синхронизации GitHub не удался.",
    noConnectionRecord: "В бэкенде нет записи подключения GitHub для этого рабочего пространства.",
    connectionRecordFound: "Запись подключения GitHub найдена в бэкенде."
  },

  githubWork: {
    eyebrow: "GitHub",
    title: "Оперативная работа",
    stateLabel: "Состояние работы GitHub",
    stateAll: "Все",
    stateOpen: "Открытые",
    stateClosed: "Закрытые",
    stateMerged: "Слитые",
    loading: "Загрузка работы GitHub",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — работы GitHub нет.",
    unavailableTitle: "Оперативная работа GitHub недоступна",
    unavailableDescription: "Панель не смогла загрузить работу GitHub.",
    emptyTitle: "Оперативная работа GitHub ещё не синхронизирована",
    emptyDescription:
      "Запустите локальную нормализацию GitHub с канонической записью, чтобы наполнить задачи и пулреквесты.",
    issuesTitle: "Задачи",
    pullRequestsTitle: "Пулреквесты",
    noIssuesForFilter: "Нет задач для этого фильтра.",
    noPullRequestsForFilter: "Нет пулреквестов для этого фильтра.",
    badgeIssue: "Задача",
    badgePr: "PR",
    metaRepository: "Репозиторий",
    metaState: "Состояние",
    metaReference: "Ссылка",
    metaUpdated: "Обновлено",
    repositoryUnavailable: "Репозиторий недоступен",
    noExternalId: "Нет внешнего идентификатора",
    timestampUnknown: "Неизвестно"
  },

  selectedSync: {
    eyebrow: "GitHub",
    title: "Синхронизация выбранного репозитория",
    badgeReadOnly: "Только чтение",
    intro:
      "Синхронизация выбранного репозитория только для чтения. Записи в GitHub не выполняются. Задачи и пулреквесты читаются из выбранных разрешённых репозиториев. Это не создаёт, не закрывает, не сливает и не комментирует элементы GitHub.",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — синхронизировать нечего.",
    loading: "Загрузка состояния подключения GitHub",
    unavailableTitle: "Синхронизация выбранного репозитория недоступна",
    unavailableDescription: "Панель не смогла загрузить состояние подключения GitHub.",
    connectionRequiredTitle: "Требуется подключение GitHub",
    connectionRequiredDescription:
      "Для синхронизации выбранного репозитория сначала нужно настроить подключение GitHub для этого рабочего пространства. Настройте подключение и повторите.",
    repoLabel: "Репозиторий (владелец/репозиторий)",
    repoPlaceholder: "владелец/репозиторий",
    repoNote:
      "Выбранные репозитории должны быть разрешены конфигурацией бэкенда. Этот интерфейс синхронизирует по одному явному репозиторию за раз и никогда не синхронизирует все репозитории организации.",
    runIssues: "Запустить синхронизацию задач",
    syncingIssues: "Синхронизация задач",
    runPr: "Запустить синхронизацию пулреквестов",
    syncingPr: "Синхронизация пулреквестов",
    runBoth: "Синхронизировать задачи и пулреквесты",
    syncingBoth: "Синхронизация задач и пулреквестов",
    errorAllowlist: "Репозиторий не в списке разрешённых для выбранной синхронизации.",
    errorPermission: "Ваша роль в рабочем пространстве не позволяет запускать синхронизацию выбранного репозитория. Требуется роль администратора.",
    errorGeneric: "Запрос синхронизации выбранного репозитория не удался.",
    errorTitleAllowlist: "Репозиторий не в списке разрешённых",
    errorTitlePermission: "Недостаточно прав в рабочем пространстве",
    errorTitleGeneric: "Синхронизация выбранного репозитория не удалась",
    validationEmpty: "Укажите полное имя репозитория в виде владелец/репозиторий.",
    validationFormat: "Репозиторий должен быть в формате владелец/репозиторий без пробелов.",
    issueSummaryTitle: "Итог синхронизации задач",
    noIssuesSynced: "Для выбранного репозитория записи задач не синхронизированы.",
    prSummaryTitle: "Итог синхронизации пулреквестов",
    noPrsSynced: "Для выбранного репозитория записи пулреквестов не синхронизированы.",
    noWrites: "Записи в GitHub не выполнялись."
  },

  briefingsPage: {
    eyebrow: "Сводки",
    title: "Ручная сводка для основателя",
    description: "В бэкенде есть детерминированный эндпоинт ручной сводки по сигналам локального рабочего пространства."
  },

  briefingPanel: {
    eyebrow: "Сводка",
    title: "Ручная сводка для основателя",
    generate: "Сформировать сводку",
    refresh: "Обновить сводку",
    generating: "Формирование сводки",
    loadingDeterministic: "Формирование детерминированной сводки",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — формировать сводку не по чему.",
    unsupportedTitle: "Ручная сводка не поддерживается",
    unsupportedDescription: "Бэкенд не сообщил о поддержке ручной детерминированной сводки.",
    unavailableTitle: "Сводка недоступна",
    unavailableDescription: "Запрос ручной сводки не удался.",
    noBriefingTitle: "Сводка не загружена",
    noBriefingDescription:
      "Нажмите кнопку формирования, чтобы запросить детерминированную ручную сводку по имеющимся записям рабочего пространства.",
    intro:
      "Ручная детерминированная сводка по записям компании, подтверждённым источниками. Генерация ИИ, живая синхронизация провайдера и выполнение действий не используются.",
    summaryLabel: "Сводка показателей",
    reposTitle: "Репозитории",
    reposDescription: "Canonical repo rows, доступные детерминированной сводке.",
    workTitle: "Работа",
    workDescription: "Открытые задачи и PR в Company Brain coverage.",
    evidenceTitle: "Evidence",
    evidenceDescription: "Evidence refs, доступные этой сводке.",
    modeTitle: "Режим",
    modeDescription: "Локальное/живое чтение и LLM boundary для сводки.",
    modeLocal: "Local DB",
    modeLive: "Live",
    queuedTitle: "Задания синхронизации в очереди",
    queuedDescription: "Локальные задания синхронизации GitHub в очереди.",
    latestSyncTitle: "Последняя синхронизация",
    latestSyncDescription: "Статус последнего локального задания синхронизации GitHub.",
    latestSyncNone: "Нет",
    aiTitle: "ИИ / хранение",
    aiDescription: "Режим сводки.",
    aiValue: "ИИ",
    capabilityTitle: "Текущий режим возможностей",
    itemsSectionTitle: "Пункты сводки",
    itemFilterTitle: "Фокус пунктов сводки",
    itemFilterLabel: "Фильтр пунктов сводки по категории",
    itemFilterDescription:
      "Фильтр работает только по уже загруженной детерминированной сводке и не запускает provider calls или LLM.",
    itemFilterAll: "Все категории",
    noItems: "Бэкенд не вернул пунктов сводки.",
    noItemsForFilter: "Для выбранной категории пунктов сводки нет.",
    metaSeverity: "Важность",
    metaConfidence: "Уверенность",
    metaNextStep: "Рекомендуемый следующий шаг",
    noNextStep: "Следующий шаг не указан",
    noEvidenceRef: "Системный детерминированный факт; отдельный источник не возвращён.",
    evidenceDefaultContext:
      "Источник по умолчанию из первого видимого пункта сводки. Выберите другой источник, чтобы закрепить его.",
    evidenceManualContext:
      "Источник выбран вручную. Нажмите «Закрыть», чтобы вернуться к источнику по умолчанию для видимых пунктов.",
    actionSummaryTitle: "Локальные действия из сводки",
    actionSummaryDescription:
      "Сводка читает уже созданные локальные предложения и не запускает provider calls, внешние записи или LLM.",
    actionSummaryEmpty:
      "По видимым пунктам сводки ещё нет локальных предложений действий.",
    openActions: "Открыть действия",
    actionCreate: "Создать локальное действие",
    actionCreating: "Создание локального действия",
    actionAlreadyCreated: "Действие уже создано",
    actionCreateSuccess:
      "Локальное действие создано. Проверьте его в блоке «Действия» перед одобрением.",
    storedValue: "Сохранено"
  },

  briefingHistory: {
    title: "История сводок",
    description: "Сохранённые сводки этого рабочего пространства, новые — сверху.",
    empty: "Сохранённых сводок пока нет. Сформируйте первую сводку выше.",
    loading: "Загрузка истории сводок",
    failed: "Не удалось загрузить историю сводок.",
    open: "Открыть",
    current: "Открыта",
    itemsLabel: "пунктов",
    coverageLabel: "Coverage",
    deltaLabel: "Изменение к открытой",
    noDelta: "Откройте сводку, чтобы сравнить историю."
  },

  actionsPage: {
    eyebrow: "Действия",
    title: "Граница действий с одобрением человеком",
    description:
      "Предложения действий проходят локальные состояния «предложено», «одобрено» и «отклонено» без внешнего выполнения."
  },

  actionsPanel: {
    eyebrow: "Действия",
    title: "Предложения действий",
    badgeLocalApproval: "Локальное одобрение",
    intro:
      "Процесс локального одобрения. Одобрение фиксирует решение человека; этот экран не выполняет записи у провайдера.",
    capabilityTitle: "Текущий режим возможностей",
    loading: "Загрузка предложений действий",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — предложений нет.",
    unsupportedTitle: "Предложения действий не поддерживаются",
    unsupportedDescription: "Бэкенд не сообщил о поддержке локальных предложений действий.",
    unavailableTitle: "Предложения действий недоступны",
    unavailableDescription: "Запрос предложений действий не удался.",
    emptyTitle: "Пока нет предложений действий",
    emptyDescription: "Для этого рабочего пространства ещё не создано локальных предложений действий.",
    summaryLabel: "Сводка предложений",
    proposedTitle: "Предложено",
    proposedDescription: "Локальные предложения, ожидающие проверки.",
    approvedTitle: "Одобрено",
    approvedDescription: "Локальные предложения, одобренные человеком; этим интерфейсом не выполняются.",
    rejectedTitle: "Отклонено",
    rejectedDescription: "Локально отклонённые предложения.",
    totalTitle: "Всего",
    totalDescription: "Количество из списка бэкенда.",
    filterTitle: "Фокус проверки",
    filterLabel: "Фильтр локальных предложений",
    filterDescription:
      "Фильтр работает только по уже загруженному локальному списку и не запускает provider calls.",
    filterProposed: "Нужно решение",
    filterApproved: "Одобрено",
    filterRejected: "Отклонено",
    filterAll: "Все",
    originFilterTitle: "Источник предложения",
    originFilterLabel: "Фильтр источника локальных предложений",
    originFilterDescription:
      "Источник фильтруется поверх выбранного статуса и не запускает provider calls.",
    originFilterAll: "Все источники",
    originFilterAudit: "Из аудита репо",
    originFilterBriefing: "Из сводки",
    originFilterGithub: "GitHub задачи",
    originFilterInternal: "Internal todo",
    auditSourceFilterTitle: "Тип аудита",
    auditSourceFilterLabel: "Фильтр типа аудита",
    auditSourceFilterDescription:
      "Подфильтр работает только внутри источника «аудит репо»: локальный deterministic audit или импортированный результат внешнего аудита.",
    auditSourceFilterAll: "Все audit findings",
    auditSourceFilterDeterministic: "Детерминированный аудит",
    auditSourceFilterImported: "Импортированный аудит",
    bulkTitle: "Массовая локальная проверка",
    bulkLabel: "Массовые локальные действия с предложениями",
    bulkDescription:
      "Выбор применяется только к видимым предложениям в статусе «Нужно решение». Массовое действие меняет локальный статус и не запускает внешнее выполнение.",
    bulkSelectVisible: "Выбрать видимые ожидающие",
    bulkClearSelection: "Снять выбор",
    bulkApproveSelected: "Одобрить выбранные локально",
    bulkApproving: "Одобрение выбранных",
    bulkRejectSelected: "Отклонить выбранные локально",
    bulkRejecting: "Отклонение выбранных",
    bulkSelectProposal: "Выбрать для локальной проверки",
    listTitle: "Локальные предложения",
    noProposals: "Бэкенд не вернул предложений.",
    noProposalsForFilter: "Для выбранного фильтра локальных предложений нет.",
    metaTarget: "Цель",
    metaAction: "Действие",
    metaStatus: "Статус",
    metaExecution: "Выполнение",
    executionReported: "сообщено бэкендом",
    executionNotExecuted: "этим интерфейсом не выполнено",
    metaCreated: "Создано",
    metaUpdated: "Обновлено",
    metaApprovedAt: "Одобрено локально",
    metaRejectedAt: "Отклонено локально",
    metaRejectionReason: "Причина отклонения",
    payloadRepository: "Репозиторий",
    payloadTargetRecord: "Целевая запись",
    payloadInternalNote: "Внутренняя заметка",
    payloadNone: "Целевой репозиторий, заголовок задачи или внутренняя заметка не возвращены.",
    noEvidenceRefs: "Бэкенд не вернул источников для этого предложения.",
    approve: "Одобрить",
    approving: "Одобрение",
    reject: "Отклонить",
    rejecting: "Отклонение",
    createError: "Для локального предложения задачи GitHub нужны заголовок и репозиторий.",
    createSuccess: "Локальное предложение создано. Внешнее выполнение здесь отключено.",
    approveSuccess: "Одобрено локально. Внешнее выполнение в этом интерфейсе не включено.",
    rejectSuccess: "Отклонено локально. Источники и история предложения сохранены.",
    rejectReason: "Отклонено локально из интерфейса продукта.",
    actionsApprovedNote: "Одобрено локально. Внешнее выполнение в этом интерфейсе отключено.",
    actionsRejectedNote: "Отклонено локально. Внешнее действие не запускалось.",
    actionsOtherNote: "Статус возвращён бэкендом. Этот интерфейс не выполнял работу у провайдера.",
    actionLabelCreateIssue: "Создать задачу GitHub",
    actionLabelInternalTodo: "Внутренняя задача",
    groupsLabel: "Группы предложений по источнику",
    groupAuditTitle: "Из аудита репозиториев",
    groupAuditDescription:
      "Локальные действия, созданные из детерминированного аудита репозиториев (read-only).",
    groupBriefingTitle: "Из пунктов сводки",
    groupBriefingDescription:
      "Локальные действия, созданные из evidence пунктов сводки.",
    groupGithubTitle: "Предложения задач GitHub",
    groupGithubDescription:
      "Локальные предложения будущих задач GitHub. Запись в GitHub здесь не выполняется.",
    groupInternalTitle: "Внутренние задачи",
    groupInternalDescription: "Внутренние локальные задачи, созданные вручную.",
    originAuditBadge: "Из аудита",
    originAuditDeterministicBadge: "Локальный deterministic",
    originAuditImportedBadge: "Импорт внешнего аудита",
    originBriefingBadge: "Из сводки",
    auditSourceDeterministic: "Детерминированный локальный аудит",
    auditSourceImported: "Импортированный внешний аудит",
    payloadAuditSource: "Тип аудита",
    payloadBriefingItem: "Ключ пункта сводки",
    payloadCategory: "Категория",
    payloadSeverity: "Важность",
    payloadNextStep: "Рекомендуемый следующий шаг",
    payloadAuditArea: "Область-кандидат (аудит)",
    payloadAuditActivity: "Активность репозитория (аудит)",
    payloadRelatedEntities: "Связанные сущности"
  },

  actionCreate: {
    typeLabel: "Тип предложения",
    typeGithubIssue: "Предложение задачи GitHub",
    typeInternalTodo: "Внутреннее предложение-задача",
    titleLabel: "Заголовок",
    titlePlaceholder: "Опишите локальное предложение действия",
    descriptionLabel: "Описание",
    descriptionPlaceholder: "Зачем это предложение и какие источники стоит проверить",
    repositoryLabel: "Репозиторий",
    repositoryPlaceholder: "владелец/репозиторий",
    issueBodyLabel: "Текст задачи",
    issueBodyPlaceholder: "Текст для предлагаемой будущей задачи GitHub",
    submit: "Создать предложение",
    submitting: "Создание предложения",
    note: "Создание предложения сохраняет только локальное состояние проверки. Оно не создаёт задачу GitHub и не вызывает живого провайдера."
  },

  actionExecution: {
    previewTitle: "Предпросмотр выполнения",
    previewIntro:
      "Одобрение не выполняет записи у провайдера. Используйте предпросмотр, чтобы изучить защищённое действие с задачей GitHub до рассмотрения живого пути записи.",
    approveFirst: "Сначала одобрите локально, чтобы проверить готовность к выполнению.",
    preview: "Предпросмотр выполнения",
    preparingPreview: "Подготовка предпросмотра",
    previewOnly: "Только предпросмотр. Это не запишет в GitHub.",
    metaProvider: "Провайдер",
    metaAction: "Действие",
    metaRepository: "Репозиторий",
    metaIssueTitle: "Заголовок задачи",
    metaIssueBody: "Текст задачи",
    metaLabels: "Метки",
    metaAssignees: "Исполнители",
    noEvidence: "Для этого предложения источники не возвращены. Интерфейс не выдумывает источники.",
    liveLabel: "Подтверждение живого выполнения",
    liveWarning:
      "Это создаст настоящую задачу GitHub. Требуются явное подтверждение и идентификатор подключённого подключения GitHub.",
    connectionIdLabel: "ID подключения",
    connectionIdPlaceholder: "ID GitHub IntegrationConnection",
    confirmCheckbox: "Я подтверждаю, что это может записать в GitHub.",
    execute: "Выполнить с подтверждением",
    executing: "Выполнение с подтверждением",
    externalDisabled: "Внешнее выполнение отключено в этом окружении.",
    receiptLabel: "Квитанция выполнения",
    receiptStatus: "Статус",
    receiptProviderResult: "Результат провайдера",
    receiptExternalWrite: "Внешняя запись",
    receiptConfirmation: "Подтверждение",
    receiptExternalIssue: "Внешняя задача",
    receiptExternalUrl: "Внешний URL",
    receiptError: "Ошибка",
    openGithubIssue: "Открыть задачу GitHub",
    confirmationReceived: "получено",
    confirmationNotReceived: "не получено",
    resultLabel: "Результат выполнения",
    resultStatus: "Статус выполнения",
    resultExternalWrite: "Внешняя запись выполнена",
    resultExternalId: "Внешний id",
    yes: "да",
    no: "нет",
    createdIssue: "Задача GitHub создана. Квитанция выполнения записана.",
    auditTitle: "Локальный аудит решений и выполнения",
    auditCreated: "Время",
    auditActor: "Актор",
    auditProvider: "Провайдер",
    auditAction: "Действие",
    auditExternalWrite: "Внешняя запись",
    auditNoExternalWrite: "Внешней записи не было.",
    auditRecorded: "Событие аудита записано локально.",
    historyLoad: "Показать историю решений",
    historyLoading: "Загрузка истории решений",
    historyLoaded: "История решений загружена. Внешней записи не было.",
    historyEmpty: "Локальных событий решений для этого предложения пока нет.",
    noWorkspacePreview: "У вашего аккаунта нет рабочего пространства — предпросмотр недоступен.",
    noWorkspaceExecute: "У вашего аккаунта нет рабочего пространства — выполнение недоступно.",
    previewLoaded: "Предпросмотр выполнения загружен. Внешней записи не было.",
    externalDisabledError: "Внешнее выполнение отключено в этом окружении.",
    confirmRequired: "Перед выполнением нужны ID подключения и явное подтверждение.",
    successExisting: "Возвращена существующая квитанция выполнения. Дополнительной внешней записи не было.",
    successExternalResult: "Бэкенд сообщил о результате внешнего выполнения.",
    successNoWrite: "Запрос на выполнение завершён без внешней записи.",
    fallbackCreated: "Локальное предложение действия создано.",
    fallbackApproved: "Предложение одобрено локально. Внешняя запись не выполнялась.",
    fallbackRejected: "Предложение отклонено локально. Внешняя запись не выполнялась."
  },

  settings: {
    eyebrow: "Аккаунт",
    title: "Ваш аккаунт",
    description: "Вы вошли по сессионной cookie. Операторский API-ключ в браузере не используется.",
    signedInAs: "Вы вошли как:",
    workspace: "Рабочее пространство:",
    workspaceNone: "Нет",
    changePasswordTitle: "Сменить пароль",
    currentPassword: "Текущий пароль",
    newPassword: "Новый пароль",
    changePassword: "Сменить пароль",
    changing: "Смена пароля…",
    changeSuccess: "Пароль изменён. На других устройствах выполнен выход.",
    changeError: "Не удалось сменить пароль. Проверьте текущий пароль.",
    teamTitle: "Команда рабочего пространства",
    teamDescription:
      "Локальные участники workspace. Этот экран не отправляет email-инвайты, не вызывает identity provider и не делает external writes.",
    teamLoading: "Загрузка участников",
    teamUnavailableTitle: "Участники недоступны",
    teamUnavailableDescription: "Не удалось загрузить локальных участников workspace.",
    teamNoWorkspace: "У аккаунта пока нет workspace — участников показать нельзя.",
    teamEmpty: "В этом workspace пока нет участников.",
    teamMemberStatus: "Статус",
    teamMemberRole: "Роль",
    teamProvisionTitle: "Добавить участника локально",
    teamProvisionDescription:
      "Создаёт только локальные User + Membership. Пароль, email invite и self-service onboarding остаются отдельным шагом.",
    teamProvisionEmail: "Email участника",
    teamProvisionName: "Имя (необязательно)",
    teamProvisionRole: "Роль",
    teamProvisionPassword: "Начальный пароль (необязательно, минимум 8 символов)",
    teamProvisionPasswordHint:
      "Задайте начальный локальный пароль, чтобы участник мог войти. Он сможет сменить его в разделе «Сменить пароль». Пароль не отправляется по email.",
    teamProvisionSetupLink: "Создать одноразовую setup-ссылку вместо пароля",
    teamProvisionSetupLinkHint:
      "Ссылка появится один раз после создания участника. Скопируйте её teammate вручную; email не отправляется.",
    teamProvisionSubmit: "Добавить участника",
    teamProvisioning: "Добавление…",
    teamProvisionSuccess: "Локальный участник добавлен. Email invite не отправлялся.",
    teamProvisionSuccessWithLogin:
      "Локальный участник добавлен с начальным паролем — он может войти и затем сменить пароль. Email invite не отправлялся.",
    teamProvisionSuccessNoLogin:
      "Локальный участник добавлен без пароля — задайте начальный пароль, чтобы он мог войти. Email invite не отправлялся.",
    teamProvisionSetupLinkGenerated:
      "Одноразовая setup-ссылка создана. Скопируйте её сейчас — raw token не хранится.",
    teamProvisionSetupLinkLabel: "Setup-ссылка",
    teamProvisionSetupLinkExpires: "Истекает",
    teamProvisionError: "Не удалось добавить участника.",
    teamProvisionForbidden:
      "Добавлять участников могут только owner/admin текущего workspace.",
    teamBoundary:
      "Boundary: local DB only — external_invite_sent=false, provider_write_performed=false.",
    roleOwner: "Owner",
    roleAdmin: "Admin",
    roleMember: "Member",
    roleViewer: "Viewer"
  },

  connectors: {
    eyebrow: "Коннекторы",
    title: "Коннекторы источников",
    description:
      "Обзор коннекторов из MVP-набора (GitHub, Jira, Gmail, Google Drive). Экран только читает локальное состояние: без provider calls, external writes и LLM.",
    badgeReadOnly: "Только чтение",
    loading: "Загрузка коннекторов",
    noWorkspaceDescription:
      "У этого аккаунта пока нет рабочего пространства — коннекторы недоступны.",
    unavailableTitle: "Коннекторы недоступны",
    unavailableDescription: "Не удалось загрузить реестр коннекторов.",
    summaryLabel: "Сводка коннекторов",
    totalTitle: "Всего",
    totalDescription: "Коннекторы в MVP-наборе.",
    availableTitle: "Доступно",
    availableDescription: "Есть продуктовый путь в приложении.",
    plannedTitle: "Запланировано",
    plannedDescription: "В MVP-scope, ещё не реализовано.",
    connectedTitle: "Подключено",
    connectedDescription: "Есть хотя бы одно подключение в рабочем пространстве.",
    listLabel: "Список коннекторов",
    statusAvailable: "Доступен",
    statusPlanned: "Запланирован",
    connectionsLabel: "Подключений",
    connectedLabel: "Активных",
    manageLink: "Открыть",
    plannedHint: "Появится позже; провайдер-вызовы и записи не выполняются.",
    boundaryNote:
      "Реестр вычисляется локально из уже сохранённых записей подключений. Он не вызывает провайдеров, не запускает синхронизацию, не делает external writes и не читает секреты."
  },


  gmail: {
    eyebrow: "Gmail",
    title: "Gmail messages",
    description:
      "Минимальный Gmail-коннектор MVP: локальный импорт message JSON в canonical SourceRecord (без raw body) без provider calls, sync, external writes и LLM.",
    badgeLocalOnly: "Local-only",
    loading: "Загрузка Gmail messages",
    noWorkspaceDescription:
      "У этого аккаунта пока нет рабочего пространства — Gmail-коннектор недоступен.",
    unavailableTitle: "Gmail messages недоступны",
    unavailableDescription: "Не удалось загрузить локальные Gmail messages.",
    summaryLabel: "Сводка Gmail",
    totalTitle: "Всего",
    totalDescription: "Локально импортированные Gmail messages.",
    unreadTitle: "Непрочитанные",
    unreadDescription: "Messages с меткой UNREAD.",
    readTitle: "Прочитанные",
    readDescription: "Messages без метки UNREAD.",
    emptyTitle: "Gmail messages ещё не импортированы",
    emptyDescription:
      "Вставьте JSON export/payload с Gmail messages. FounderOS сохранит только безопасную нормализованную проекцию без тела письма.",
    listLabel: "Список Gmail messages",
    fromLabel: "От",
    labelsLabel: "Метки",
    receivedLabel: "Получено",
    evidenceLabel: "Evidence refs",
    unreadBadge: "Непрочитано",
    importTitle: "Локальный импорт Gmail JSON",
    importDescription:
      "Поддерживается массив messages или объект { messages: [...] }. Импорт пишет только локальную БД и не вызывает Gmail API.",
    importTextareaLabel: "Gmail JSON",
    importPlaceholder:
      '[{"id":"msg-1","subject":"Investor follow-up","from":"founder@example.com","labels":["INBOX","UNREAD"]}]',
    importSubmit: "Импортировать локально",
    importing: "Импорт…",
    importSuccess: (imported: number, failed: number) =>
      `Импортировано: ${imported}. Ошибок: ${failed}.`,
    importParseError: "JSON должен быть массивом messages или объектом с полем messages.",
    boundaryNote:
      "Gmail-коннектор сейчас local-only: provider_calls=false, sync_started=false, external_writes=false, llm=false, секреты и raw body не читаются/не сохраняются.",
    warningsTitle: "Предупреждения"
  },

  jira: {
    eyebrow: "Jira",
    title: "Jira issues",
    description:
      "Минимальный Jira-коннектор MVP: локальный импорт issue JSON в canonical SourceRecord/Task без provider calls, sync, external writes и LLM.",
    badgeLocalOnly: "Local-only",
    loading: "Загрузка Jira issues",
    noWorkspaceDescription:
      "У этого аккаунта пока нет рабочего пространства — Jira-коннектор недоступен.",
    unavailableTitle: "Jira issues недоступны",
    unavailableDescription: "Не удалось загрузить локальные Jira issues.",
    summaryLabel: "Сводка Jira",
    totalTitle: "Всего",
    totalDescription: "Локально импортированные Jira issues.",
    notDoneTitle: "Не завершено",
    notDoneDescription: "Issues без done/closed/resolved статуса.",
    doneTitle: "Done",
    doneDescription: "Issues со статусом done/closed/resolved.",
    emptyTitle: "Jira issues ещё не импортированы",
    emptyDescription:
      "Вставьте JSON export/payload с Jira issues. FounderOS сохранит только безопасную нормализованную проекцию.",
    listLabel: "Список Jira issues",
    keyLabel: "Ключ",
    statusLabel: "Статус",
    priorityLabel: "Приоритет",
    dueDateLabel: "Due date",
    updatedLabel: "Обновлено",
    evidenceLabel: "Evidence refs",
    importTitle: "Локальный импорт Jira JSON",
    importDescription:
      "Поддерживается массив issues или объект { issues: [...] }. Импорт пишет только локальную БД и не вызывает Jira API.",
    importTextareaLabel: "Jira JSON",
    importPlaceholder:
      '[{"key":"FOS-123","summary":"Review onboarding","status":"To Do","url":"https://jira.example/browse/FOS-123"}]',
    importSubmit: "Импортировать локально",
    importing: "Импорт…",
    importSuccess: (imported: number, failed: number) =>
      `Импортировано: ${imported}. Ошибок: ${failed}.`,
    importParseError: "JSON должен быть массивом issues или объектом с полем issues.",
    boundaryNote:
      "Jira-коннектор сейчас local-only: provider_calls=false, sync_started=false, external_writes=false, llm=false, секреты не читаются.",
    warningsTitle: "Предупреждения"
  },

  evidence: {
    eyebrow: "Источники",
    title: "Детали источника",
    label: "Метка",
    source: "Источник",
    kind: "Тип",
    record: "Запись",
    snippet: "Фрагмент",
    noSnippet: "Бэкенд не вернул фрагмент.",
    unknownSource: "Неизвестный источник",
    noRecordId: "Идентификатор записи не возвращён",
    placeholder: "Выберите источник, чтобы увидеть провайдера, источник, запись и URL.",
    contextTitle: "Контекст",
    contextDefault:
      "Источник по умолчанию из первого видимого предложения. Выберите другой, чтобы закрепить его.",
    contextManual: "Источник выбран вручную. Нажмите «Закрыть», чтобы вернуться к варианту по умолчанию.",
    countLabel: "Источников у предложения"
  },

  sourceCoverage: {
    eyebrow: "Покрытие источников",
    title: "Что FounderOS уже знает",
    badgeDeterministic: "Без ИИ / без provider calls",
    loading: "Загрузка покрытия источников",
    noWorkspaceDescription:
      "У этого аккаунта пока нет рабочего пространства — покрытие источников недоступно.",
    unavailableTitle: "Покрытие источников недоступно",
    unavailableDescription: "Панель не смогла загрузить покрытие источников.",
    emptyTitle: "Источники ещё не загружены",
    emptyDescription:
      "В этом рабочем пространстве пока нет канонических записей. Подготовьте локальную поверхность источников или запустите подтверждённую read-only синхронизацию позже.",
    intro:
      "Сводка показывает только уже сохранённые канонические данные рабочего пространства. Живые provider-запросы и LLM здесь не запускаются.",
    summaryLabel: "Сводка покрытия источников",
    repositoriesTitle: "Repo",
    repositoriesDescription:
      "Канонические GitHub-репозитории, уже сохранённые в рабочем пространстве.",
    workTitle: "Работа",
    workDescription: "Открытые задачи и PR из канонического GitHub-пути.",
    evidenceTitle: "Evidence",
    evidenceDescription: "Источник-ссылки, возвращённые для текущей выборки Company Brain.",
    modeTitle: "Режим",
    modeDescription: "Текущий экран читает локальную БД и не делает live provider calls.",
    modeLive: "Live",
    modeLocal: "Local DB",
    detailsLabel: "Детали покрытия источников",
    detailsTitle: "Статус источников",
    repositoriesLabel: "GitHub репозитории",
    repositoriesEmpty: "Канонические repo rows пока отсутствуют.",
    liveProviderLabel: "Живой провайдер",
    liveProviderEnabledDescription:
      "Backend capability сообщает, что live provider sync доступен, но этот экран сам его не запускает.",
    liveProviderDeferredDescription:
      "Real GitHub provider read отложен и запускается только отдельным подтверждённым действием.",
    llmLabel: "LLM / AI",
    llmEnabledDescription:
      "Capability включён, но этот экран не генерирует текст и не мутирует данные через LLM.",
    llmOffDescription:
      "LLM briefing/extraction сейчас выключены; экран полностью детерминированный.",
    evidenceLabel: "Evidence refs",
    evidenceEmpty:
      "Для текущей выборки Company Brain отдельные source refs не вернулись; unsupported claims не добавляются.",
    statusReady: "Готово",
    statusEmpty: "Пусто",
    statusDeferred: "Отложено",
    statusEnabled: "Включено",
    statusOff: "Выключено",
    statusNeedsEvidence: "Нужно evidence",
    breakdownLabel: "Разбивка покрытия источников",
    breakdownTitle: "Что уже покрыто",
    closedWorkTitle: "Закрытая работа",
    closedWorkDescription:
      "Закрытые задачи и слитые PR из канонического GitHub-пути.",
    recentTitle: "Недавняя активность",
    recentDescription:
      "Недавно обновлённые задачи/PR в текущей выборке Company Brain.",
    evidenceKindsTitle: "Evidence по типу",
    evidenceKindsDescription:
      "Локальная разбивка уже полученных source refs по типу (kind). Без provider calls и без LLM.",
    evidenceKindsEmpty:
      "Типы evidence пока недоступны: отдельные source refs не вернулись.",
    nextStepsLabel: "Следующие шаги покрытия источников",
    nextStepsTitle: "Что проверить дальше",
    nextStepDataLabel: "Каноническая поверхность",
    nextStepDataMissingDescription:
      "Сначала нужен хотя бы один canonical repo row. Подготовьте локальную поверхность источников или запустите отдельно подтверждённый scoped read-only sync.",
    nextStepEvidenceLabel: "Evidence gaps",
    nextStepEvidenceReadyDescription:
      "Evidence refs есть у текущей выборки; unsupported claims не добавляются.",
    nextStepEvidenceMissingDescription:
      "Company Brain вернул данные без source refs. Следующий шаг — восстановить evidence перед любыми выводами или действиями.",
    nextStepWorkLabel: "Открытая работа",
    nextStepNoOpenWorkDescription:
      "Открытой работы в текущей canonical выборке нет; можно перейти к readiness/deploy checklist.",
    nextStepProviderLabel: "Live provider read",
    nextStepProviderEnabledDescription:
      "Capability доступен, но запуск остаётся отдельным подтверждённым scoped действием, а не автоматикой dashboard.",
    nextStepProviderDeferredDescription:
      "Real GitHub provider read отложен; dashboard только показывает локальную картину и не запускает sync.",
    nextStepAiLabel: "AI boundary",
    nextStepAiEnabledDescription:
      "Capability включён, но coverage next steps остаются deterministic и не генерируют новые claims.",
    nextStepAiOffDescription:
      "LLM выключен; любые будущие AI outputs должны быть strict JSON, validated and evidence-backed.",
    statusNeedsData: "Нужны данные",
    statusReview: "К разбору",
    statusBoundary: "Boundary"
  },

  privateBetaReadiness: {
    eyebrow: "Private beta",
    title: "Готовность к ручному запуску",
    badgeManual: "Manual / no external writes",
    loading: "Загрузка готовности private beta",
    noWorkspaceDescription:
      "У этого аккаунта пока нет рабочего пространства — готовность private beta недоступна.",
    unavailableTitle: "Готовность private beta недоступна",
    unavailableDescription: "Панель не смогла загрузить локальные данные готовности.",
    intro:
      "Панель показывает только локальные условия для ручного private-beta запуска. Она не деплоит, не пушит, не запускает provider writes и не вызывает LLM.",
    summaryLabel: "Сводка готовности private beta",
    dataTitle: "Данные",
    dataDescription: "Канонические repo/evidence уже есть в локальной БД.",
    externalWritesTitle: "External writes",
    externalWritesDescription: "Записи во внешние сервисы остаются отключёнными.",
    externalWritesValue: "Отключены",
    deployTitle: "Deploy",
    deployDescription: "Только ручной runbook + smoke gate.",
    deployValue: "Manual",
    aiTitle: "LLM",
    aiDescription: "AI generation для сводок/действий не запускается.",
    aiValue: "Off",
    detailsLabel: "Чеклист готовности private beta",
    detailsTitle: "Чеклист перед ручным запуском",
    dataLabel: "Канонические данные и evidence",
    dataNeedsEvidenceDescription:
      "Нужно иметь хотя бы один canonical repo row и evidence ref перед уверенным smoke/readiness выводом.",
    sessionLabel: "Сессионный логин",
    sessionDescription:
      "Продуктовый UI работает через first-party session cookie; operator key не отправляется браузером.",
    manualDeployLabel: "Manual deploy runbook",
    manualDeployDescription:
      "Railway/private-beta deploy остаётся ручным: backup, deploy, alembic upgrade head и smoke выполняются человеком.",
    runbookLabel: "Manual deploy/smoke runbook",
    runbookTitle: "Ручной runbook запуска",
    runbookDescription:
      "Короткая карта ручного запуска из docs/deploy/private-beta.md. Эта панель только показывает шаги и не выполняет команды.",
    runbookStatusLocalGate: "Local gate",
    runbookStatusManual: "Manual",
    runbookStatusReadOnly: "Read-only",
    runbookStatusRollback: "Rollback",
    runbookLocalGateLabel: "Локальные gates",
    runbookLocalGateDescription:
      "Перед deploy вручную запустить secret scan, ruff, backend pytest, frontend tests/build/typecheck/lint и убедиться, что worktree не содержит unrelated changes.",
    runbookBackupLabel: "Backup перед миграцией",
    runbookBackupDescription:
      "Перед private-beta migration человек создаёт backup managed Postgres и проверяет restore path в hosting UI.",
    runbookMigrationLabel: "Миграция вручную",
    runbookMigrationDescription:
      "После backup выполнить alembic upgrade head вручную против private-beta Postgres; реальные database URLs не писать в docs/logs.",
    runbookServicesLabel: "Backend + frontend services",
    runbookServicesDescription:
      "Запустить backend Uvicorn и frontend Next.js как отдельные services; GitHub writes, provider-write smoke и LLM остаются выключенными.",
    runbookSmokeLabel: "Read-only smoke",
    runbookSmokeDescription:
      "Проверить health, login, dashboard, /github, /audit, /actions и evidence views read-only; не запускать provider writes или execute paths.",
    runbookRollbackLabel: "Rollback boundary",
    runbookRollbackDescription:
      "Rollback остаётся ручным: остановить services/вернуть commit и восстановить Postgres из backup при data-impacting migration failure.",
    runbookBoundary:
      "Runbook checklist — только навигация и контрольный список. Он не деплоит, не пушит, не вызывает провайдеров и не меняет production data.",
    providerReadLabel: "GitHub provider read",
    providerReadAvailableDescription:
      "Backend capability допускает live provider read, но эта панель сама его не запускает.",
    providerReadDeferredDescription:
      "Первый real-provider read остаётся отдельным scoped action с явным подтверждением; здесь он не запускается.",
    externalWritesLabel: "Внешние записи",
    externalWritesOffDescription:
      "GitHub/Jira/прочие provider writes не запускаются из readiness/dashboard path.",
    llmLabel: "LLM / AI generation",
    llmAvailableDescription:
      "Capability включён, но readiness не вызывает LLM и не мутирует данные через AI.",
    llmOffDescription:
      "LLM briefing/extraction выключены; readiness основан на детерминированных локальных данных.",
    statusReady: "Готово",
    statusNeedsData: "Нужны данные",
    statusManual: "Ручной",
    statusAvailable: "Доступно",
    statusDeferred: "Отложено",
    statusOff: "Выключено"
  },

  repoAudit: {
    eyebrow: "Аудит репозиториев",
    title: "Полный аудит всех репозиториев",
    badgeDeterministic: "Deterministic / read-only / no external writes",
    loading: "Загрузка аудита репозиториев",
    noWorkspaceDescription:
      "У этого аккаунта пока нет рабочего пространства — аудит репозиториев недоступен.",
    unavailableTitle: "Аудит репозиториев недоступен",
    unavailableDescription: "Панель не смогла загрузить детерминированный аудит репозиториев.",
    emptyTitle: "Аудит репозиториев пуст",
    emptyDescription:
      "Локальный снимок GitHub discovery не дал репозиториев для аудита. Подготовьте снимок и вернитесь сюда.",
    intro:
      "Детерминированный аудит всех репозиториев организации из локального снимка discovery. Он вычисляется локально: без сетевых вызовов, LLM и записей во внешние сервисы. Отдельный полный аудит другой моделью можно импортировать позже как результат.",
    summaryLabel: "Сводка аудита репозиториев",
    guardrailsTitle: "Границы аудита",
    guardrailsSummary:
      "preview-only, вычислено локально, БД не менялась, сетевых вызовов нет, внешних записей нет.",
    snapshotTitle: "Локальный снимок",
    snapshotUnavailable: "Локальный снимок discovery недоступен.",
    reposTitle: "Репозитории",
    reposDescription: "Репозитории, вычисленные из локального снимка discovery.",
    riskTitle: "Риск-флаги",
    riskDescription: "Суммарные детерминированные риск-флаги по всем репозиториям.",
    listTitle: "Репозитории под аудитом",
    listLabel: "Список репозиториев под аудитом",
    focusLabel: "Фильтр аудита репозиториев",
    focusTitle: "Фокус аудита",
    focusDescription:
      "Фильтр работает только по уже вычисленному аудиту и не запускает сетевые вызовы, provider-запросы или LLM.",
    focusAll: "Все",
    focusRisks: "С рисками",
    focusStale: "Неактивные",
    focusNeedsConfirm: "Нужно подтверждение",
    noReposForFilter: "Для выбранного фильтра репозиториев нет.",
    metaVisibility: "Видимость",
    metaActivity: "Активность",
    metaArea: "Область-кандидат",
    metaStack: "Стек",
    metaReadme: "README",
    metaTests: "Тесты",
    metaCi: "CI",
    metaEvidence: "Источники",
    risksLabel: "Риск-флаги",
    unknownsLabel: "Неизвестно",
    createAction: "Создать локальное действие из аудита",
    creatingAction: "Создание локального действия",
    actionAlreadyCreated: "Действие уже создано",
    createActionSuccess:
      "Локальное действие из аудита создано. Проверьте его в блоке «Действия» перед одобрением.",
    createActionError: "Не удалось создать локальное действие из аудита.",
    openActions: "Открыть действия",
    noRisks: "Детерминированные риск-флаги не обнаружены.",
    linkedActionsTitle: "Локальные действия из аудита",
    linkedActionsEmpty:
      "По репозиториям аудита ещё нет локальных предложений действий.",
    boundaryNote:
      "Read-only: аудит и создание локального действия не пишут во внешние сервисы, не вызывают провайдеров и не используют LLM.",
    importTitle: "Импорт результата внешнего аудита",
    importDescription:
      "Вставьте JSON от другой модели, чтобы превратить findings в локальные internal_todo proposals. Поддерживается массив findings или объект { findings: [...] }.",
    importLabel: "JSON findings",
    importPlaceholder:
      "[{\"repository_full_name\":\"qtwin-io/base-collector\",\"title\":\"Проверить CI\",\"summary\":\"CI не найден\",\"risks\":[\"ci_not_detected\"],\"evidence_refs\":[\"audit:base-collector:ci\"]}]",
    importSubmit: "Импортировать локальные действия",
    importing: "Импорт локальных действий",
    importBoundary:
      "Импорт пишет только локальные ActionProposal rows; внешние сервисы, provider calls и LLM не запускаются. Secret-like fragments в известных полях редактируются.",
    importInvalidJson: "JSON импорта не распознан.",
    importNoFindings:
      "Импорт не содержит валидных findings с repository_full_name в формате owner/repo и evidence_refs.",
    importFailed: "Импорт внешнего аудита не удался.",
    importPartialFailure:
      "Часть findings не удалось сохранить локально; успешные local proposals сохранены.",
    importPreviewTitle: "Предпросмотр findings перед импортом",
    importPreviewEmpty:
      "Вставьте JSON выше, чтобы увидеть предпросмотр findings перед импортом.",
    importPreviewValidBadge: "Готово к импорту",
    importPreviewInvalidBadge: "Не пройдёт валидацию",
    importSelectAllValid: "Выбрать все валидные",
    importClearSelection: "Снять выбор",
    importSelectFinding: "Выбрать для импорта",
    importNoValidSelected:
      "Не выбрано ни одного валидного finding для импорта.",
    importBackendFailureLabel: "Бэкенд отклонил finding",
    importIssueNotObject: "Элемент не является объектом finding.",
    importIssueRepoFormat:
      "repository_full_name должен быть в формате owner/repo.",
    importIssueEvidence: "Нужен хотя бы один evidence_ref."
  },

  repoAuditOverview: {
    eyebrow: "Аудит репозиториев",
    title: "Обзор аудита и локальных действий",
    badge: "Deterministic / read-only",
    loading: "Загрузка обзора аудита репозиториев",
    noWorkspaceDescription:
      "У этого аккаунта пока нет рабочего пространства — обзор аудита недоступен.",
    unavailableTitle: "Обзор аудита недоступен",
    unavailableDescription:
      "Панель не смогла загрузить детерминированный аудит репозиториев.",
    intro:
      "Сводка по детерминированному аудиту всех репозиториев и локальным действиям, созданным из аудита. Считается локально из уже загруженных данных: без сетевых вызовов, provider-запросов, external writes и LLM.",
    summaryLabel: "Сводка обзора аудита",
    reposTitle: "Репозитории",
    reposDescription: "Репозитории в детерминированном аудите из локального снимка discovery.",
    riskTitle: "Риск-флаги",
    riskDescription: "Суммарные детерминированные риск-флаги по всем репозиториям.",
    snapshotTitle: "Локальный снимок",
    snapshotDescription: "Репозитории в текущем снимке GitHub discovery.",
    actionsTitle: "Действия из аудита",
    actionsDescription: "Локальные предложения, созданные из аудита (детерминированные + импортированные).",
    actionsBreakdownLabel: "Действия из аудита по источнику",
    actionsDeterministicTitle: "Детерминированные",
    actionsDeterministicDescription:
      "Локальные действия из детерминированного аудита репозиториев (source=repo_audit).",
    actionsImportedTitle: "Импортированные",
    actionsImportedDescription:
      "Локальные действия из импортированного внешнего аудита (source=repo_audit_import).",
    actionsProposedTitle: "Нужно решение",
    actionsProposedDescription: "Действия из аудита в статусе «предложено», ожидающие локальной проверки.",
    boundaryNote:
      "Read-only: обзор не пишет во внешние сервисы, не вызывает провайдеров и не использует LLM.",
    openAudit: "Открыть аудит репозиториев",
    openAuditActions: "Открыть действия из аудита",
    openDeterministicActions: "Детерминированные действия",
    openImportedActions: "Импортированные действия",
    emptyActionsHint:
      "Локальных действий из аудита пока нет. Создайте их на странице аудита из per-repo фактов или импорта внешнего аудита."
  },

  companyBrain: {
    eyebrow: "Мозг компании",
    title: "Состояние GitHub, подтверждённое источниками",
    badgeDeterministic: "Детерминированно",
    loading: "Загрузка Мозга компании",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — Мозга компании нет.",
    unavailableTitle: "Мозг компании недоступен",
    unavailableDescription: "Панель не смогла загрузить состояние Мозга компании.",
    emptyTitle: "Пока нет данных Мозга компании",
    emptyDescription:
      "Канонические записи GitHub ещё не синхронизированы. Запустите локальную синхронизацию GitHub и вернитесь сюда за состоянием, подтверждённым источниками.",
    intro:
      "Мозг компании основан на синхронизированных канонических записях GitHub. Живой OAuth, синхронизация провайдера и сводка ИИ в этом виде не включены.",
    summaryLabel: "Сводка Мозга компании",
    reposTitle: "Репозитории",
    reposDescription: "Канонические репозитории GitHub, известные этому рабочему пространству.",
    openIssuesTitle: "Открытые задачи",
    openIssuesDescription: "Открытые записи задач GitHub из канонических задач.",
    openPrsTitle: "Открытые пулреквесты",
    openPrsDescription: "Открытые пулреквесты, связанные с каноническими репозиториями.",
    closedTitle: "Закрытые / слитые",
    closedDescription: "Закрытые задачи и слитые пулреквесты.",
    openIssuesSection: "Открытые задачи",
    noOpenIssues: "Нет открытых задач в Мозге компании.",
    openPrsSection: "Открытые пулреквесты",
    noOpenPrs: "Нет открытых пулреквестов в Мозге компании.",
    recentSection: "Недавняя работа GitHub",
    noRecent: "Недавняя работа GitHub ещё не синхронизирована.",
    reposSection: "Репозитории",
    noRepos: "Канонические репозитории ещё не синхронизированы.",
    evidenceSection: "Источники",
    noEvidence: "Для текущих записей источники не возвращены.",
    capabilityTitle: "Текущий режим возможностей",
    badgeIssue: "Задача",
    badgePr: "PR",
    metaRepository: "Репозиторий",
    metaState: "Состояние",
    metaReference: "Ссылка",
    unknownRepository: "Неизвестный репозиторий",
    noSourceRef: "Каноническая синхронизированная запись; отдельный источник не возвращён.",
    metaVisibility: "Видимость",
    repoBadge: "Репозиторий",
    archived: "Архивирован"
  }
} as const;

// --- Template helpers for interpolated strings -----------------------------
export const T = {
  evidenceFor: (title: string) => `Источники для: ${title}`,
  evidenceWarningsFor: (title: string) => `Предупреждения выполнения для: ${title}`,
  executionControlsFor: (title: string) => `Элементы выполнения для: ${title}`,
  executionAuditFor: (title: string) => `Аудит выполнения для: ${title}`,
  evidenceButton: (ref: string) => `Источник: ${ref}`,
  evidenceAttached: (count: number) => `Прикреплено источников: ${count}`,
  related: (list: string) => `Связано: ${list}`,
  confidencePercent: (value: number) => `${Math.round(value * 100)}%`,
  // Briefing history entry meta: "<n> пунктов · <when>"
  briefingHistoryMeta: (count: number, when: string) =>
    `${count} ${M.briefingHistory.itemsLabel} · ${when}`,
  briefingHistoryCoverage: (
    repos: number,
    issues: number,
    prs: number,
    evidence: number,
    mode: string
  ) =>
    `${repos} repo · ${issues} задач / ${prs} PR · evidence ${evidence} · ${mode}`,
  briefingHistoryDelta: (itemsDelta: number, evidenceDelta: number) =>
    `Пункты ${formatSignedDelta(itemsDelta)} · evidence ${formatSignedDelta(evidenceDelta)}`,
  briefingActionSummary: (
    total: number,
    proposed: number,
    approved: number,
    rejected: number,
    executed: number,
    failed: number
  ) =>
    `Связано действий: ${total} · нужно решение ${proposed} · одобрено ${approved} · ` +
    `отклонено ${rejected} · выполнено ${executed} · ошибки ${failed}`,
  briefingItemActionSummary: (
    total: number,
    proposed: number,
    approved: number,
    rejected: number,
    executed: number,
    failed: number
  ) =>
    `Локальные действия по пункту: ${total} · нужно решение ${proposed} · ` +
    `одобрено ${approved} · отклонено ${rejected} · выполнено ${executed} · ошибки ${failed}`,
  // Briefing capability line
  briefingCapability: (ai: boolean, live: boolean) =>
    `Ручная детерминированная сводка. Сводка ИИ: ${ai ? M.common.enabled : M.common.notEnabled}. ` +
    `Живая синхронизация провайдера: ${live ? M.common.enabled : M.common.notEnabled}. ` +
    `Внешние действия: здесь не выполняются.`,
  briefingCoverageWork: (issues: number, prs: number) =>
    `${issues} задач / ${prs} PR`,
  // Company Brain capability line
  brainCapability: (
    localSync: boolean,
    oauth: boolean,
    providerSync: boolean,
    llm: boolean
  ) =>
    `Локальная синхронизация: ${localSync ? M.common.available : M.common.unavailable}. ` +
    `Живой OAuth: ${oauth ? M.common.enabled : M.common.notEnabled}. ` +
    `Синхронизация провайдера: ${providerSync ? M.common.enabled : M.common.notEnabled}. ` +
    `Сводка ИИ: ${llm ? M.common.enabled : M.common.notEnabled}.`,
  // Actions capability line (static)
  actionsCapability: () =>
    "Локальное одобрение: доступно. Внешнее выполнение: отключено в этом интерфейсе. " +
    "Живые записи у провайдера: здесь не запускаются. Генерация ИИ: здесь не используется.",
  actionsBulkSelection: (selected: number, visible: number) =>
    `Выбрано: ${selected}. Видимых ожидающих: ${visible}.`,
  actionsBulkApproveSuccess: (count: number) =>
    `Локально одобрено выбранных предложений: ${count}. Внешнее выполнение не запускалось.`,
  actionsBulkRejectSuccess: (count: number) =>
    `Локально отклонено выбранных предложений: ${count}. Внешнее выполнение не запускалось.`,
  actionsBulkApprovePartial: (succeeded: number, failed: number) =>
    `Локально одобрено: ${succeeded}. Не удалось: ${failed}. ` +
    `Успешные локальные изменения сохранены; внешнее выполнение не запускалось.`,
  actionsBulkRejectPartial: (succeeded: number, failed: number) =>
    `Локально отклонено: ${succeeded}. Не удалось: ${failed}. ` +
    `Успешные локальные изменения сохранены; внешнее выполнение не запускалось.`,
  actionsBulkAllFailed: (failed: number) =>
    `Не удалось обработать выбранные предложения: ${failed}. ` +
    `Локальные статусы не изменены; внешнее выполнение не запускалось.`,
  // GitHub work count-card descriptions
  workIssuesDescription: (state: string) =>
    `${state}: записи задач GitHub из канонического пути бэкенда.`,
  workPullRequestsDescription: (state: string) =>
    `${state}: пулреквесты, связанные с репозиториями, где это возможно.`,
  repoReadSource: (source: string) => `Источник чтения репозиториев: ${source}.`,
  githubRepositorySurfaceDescription: (source: string) =>
    `Источник поверхности репозиториев: ${source}. Живой provider-sync здесь не запускается.`,
  githubRepositoryMeta: (visibility: string, archived: boolean, source: string) =>
    `Видимость: ${visibility || M.common.unknown}. ` +
    `Статус: ${archived ? "архивный" : "активный"}. ` +
    `Источник: ${source || M.common.unknown}.`,
  githubRepositoryLastActivity: (value: string) =>
    `Последняя активность: ${value}.`,
  githubRepositoryFocusSummary: (
    total: number,
    active: number,
    archived: number,
    privateCount: number,
    withEvidence: number
  ) =>
    `Repo surface: всего ${total} · активных ${active} · архивных ${archived} · private ${privateCount} · с evidence ${withEvidence}.`,
  githubAppLiveSyncResult: (repos: number, issues: number, prs: number, status: string) =>
    `Синхронизировано через GitHub App: репозиториев — ${repos}, задач — ${issues}, пулреквестов — ${prs}. Статус: ${status}.`,
  sourceCoverageWork: (issues: number, prs: number) =>
    `${issues} задач / ${prs} PR`,
  sourceCoverageRepositoriesReady: (count: number) =>
    `Каноническая поверхность GitHub готова: ${count} repo rows в локальной БД.`,
  sourceCoverageEvidenceReady: (count: number) =>
    `Для текущей выборки возвращено evidence refs: ${count}.`,
  sourceCoverageClosedWork: (closedIssues: number, mergedPrs: number) =>
    `${closedIssues} задач / ${mergedPrs} PR`,
  sourceCoverageEvidenceKind: (kind: string, count: number) =>
    `${kind}: ${count}`,
  sourceCoverageReposWithEvidence: (withRefs: number, total: number) =>
    `Repo с source refs: ${withRefs} из ${total}.`,
  sourceCoverageReposWithoutEvidence: (withoutRefs: number) =>
    `Repo без source refs: ${withoutRefs} — для них нужно ещё evidence.`,
  sourceCoverageNextStepDataReady: (repositories: number) =>
    `Canonical repo rows уже есть: ${repositories}. Следующий шаг — смотреть gaps и открытые work items.`,
  sourceCoverageNextStepEvidenceGaps: (withoutRefs: number) =>
    `Repo без source refs: ${withoutRefs}. Следующий шаг — восстановить/подтвердить evidence перед claims.`,
  sourceCoverageNextStepOpenWork: (openItems: number) =>
    `Открытых задач/PR: ${openItems}. Следующий шаг — разбирать их через локальные actions/review без provider writes.`,
  repoAuditSnapshot: (repoCount: number, status: string) =>
    `Снимок: репозиториев ${repoCount} · статус ${status}.`,
  repoAuditActivity: (bucket: string, daysSincePush: number | null) =>
    daysSincePush === null
      ? `Активность: ${bucket}.`
      : `Активность: ${bucket} · дней с последнего push: ${daysSincePush}.`,
  repoAuditRiskCount: (count: number) => `Риск-флагов: ${count}.`,
  repoAuditLinkedActions: (total: number, proposed: number, decided: number) =>
    `Связано локальных действий: ${total} · нужно решение ${proposed} · решено ${decided}.`,
  repoAuditImportResult: (created: number, failed: number) =>
    `Импортировано локальных предложений из внешнего аудита: ${created}. Не удалось: ${failed}.`,
  repoAuditImportPreview: (total: number, valid: number, selected: number) =>
    `Разобрано findings: ${total} · валидных ${valid} · выбрано ${selected}.`,
  repoAuditOverviewActions: (
    total: number,
    deterministic: number,
    imported: number,
    proposed: number
  ) =>
    `Действий из аудита: ${total} · детерминированных ${deterministic} · импортированных ${imported} · нужно решение ${proposed}.`,
  privateBetaReadinessDataReady: (
    repositories: number,
    evidenceRefs: number,
    openWork: number
  ) =>
    `Локальная база содержит ${repositories} repo rows, evidence refs: ${evidenceRefs}, открытая работа: ${openWork}.`,
  connectionNotReady: (status: string) =>
    `Запись в бэкенде в статусе ${status}. Локальная нормализация требует подключённой записи GitHub.`,
  syncResultCounts: (repos: number, issues: number, prs: number, status: string) =>
    `Нормализовано: репозиториев — ${repos}, задач — ${issues}, пулреквестов — ${prs}. Статус: ${status}.`,
  selectedIssueSummary: (repos: number, issues: number, open: number, closed: number) =>
    `Синхронизировано репозиториев — ${repos}, задач — ${issues} (открытых ${open} / закрытых ${closed}).`,
  skippedPrs: (count: number) => `Пропущено записей задач в виде PR: ${count}.`,
  selectedIssueRepoDetail: (issues: number, open: number, closed: number) =>
    `задач — ${issues} (открытых ${open} / закрытых ${closed})`,
  selectedPrSummary: (
    repos: number,
    prs: number,
    open: number,
    closed: number,
    merged: number
  ) =>
    `Синхронизировано репозиториев — ${repos}, пулреквестов — ${prs} (открытых ${open} / закрытых ${closed} / слитых ${merged}).`,
  selectedPrRepoDetail: (prs: number, open: number, closed: number, merged: number) =>
    `пулреквестов — ${prs} (открытых ${open} / закрытых ${closed} / слитых ${merged})`
} as const;

function formatSignedDelta(value: number): string {
  if (value > 0) {
    return `+${value}`;
  }
  return String(value);
}
