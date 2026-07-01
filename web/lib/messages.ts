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
    loginFailedUnknown: "Не удалось войти."
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
    liveSyncNoWrites: "Записи в GitHub не выполнялись."
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
    reposDescription: "Репозитории GitHub в сигналах детерминированной сводки.",
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
    noItems: "Бэкенд не вернул пунктов сводки.",
    metaSeverity: "Важность",
    metaConfidence: "Уверенность",
    metaNextStep: "Рекомендуемый следующий шаг",
    noNextStep: "Следующий шаг не указан",
    noEvidenceRef: "Системный детерминированный факт; отдельный источник не возвращён.",
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
    itemsLabel: "пунктов"
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
    listTitle: "Локальные предложения",
    noProposals: "Бэкенд не вернул предложений.",
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
    actionLabelInternalTodo: "Внутренняя задача"
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
    auditNoExternalWrite: " Внешней записи не было.",
    auditRecorded: " Событие аудита записано локально.",
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
    changeError: "Не удалось сменить пароль. Проверьте текущий пароль."
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
    placeholder: "Выберите источник, чтобы увидеть провайдера, источник, запись и URL."
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
  // Briefing capability line
  briefingCapability: (ai: boolean, live: boolean) =>
    `Ручная детерминированная сводка. Сводка ИИ: ${ai ? M.common.enabled : M.common.notEnabled}. ` +
    `Живая синхронизация провайдера: ${live ? M.common.enabled : M.common.notEnabled}. ` +
    `Внешние действия: здесь не выполняются.`,
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
  // GitHub work count-card descriptions
  workIssuesDescription: (state: string) =>
    `${state}: записи задач GitHub из канонического пути бэкенда.`,
  workPullRequestsDescription: (state: string) =>
    `${state}: пулреквесты, связанные с репозиториями, где это возможно.`,
  repoReadSource: (source: string) => `Источник чтения репозиториев: ${source}.`,
  githubRepositorySurfaceDescription: (source: string) =>
    `Источник поверхности репозиториев: ${source}. Живой provider-sync здесь не запускается.`,
  githubAppLiveSyncResult: (repos: number, issues: number, prs: number, status: string) =>
    `Синхронизировано через GitHub App: репозиториев — ${repos}, задач — ${issues}, пулреквестов — ${prs}. Статус: ${status}.`,
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
