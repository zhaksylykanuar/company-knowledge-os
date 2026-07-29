// Central Russian UI message catalog. ALL user-facing copy lives here so wording
// is editable in one place and a second locale can be added later as a small
// addition (export another object of the same shape). Code identifiers, routes,
// data-testids, and backend enum values stay in English; only chrome is Russian.

function russianPlural(
  count: number,
  one: string,
  few: string,
  many: string
): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export const M = {
  app: {
    name: "founderOS",
    shellMode: "AI-партнёр компании",
    metaTitle: "founderOS",
    metaDescription: "Второе мнение с проверяемой памятью о компании"
  },

  nav: {
    primaryLabel: "Основная навигация",
    brandHomeLabel: "FounderOS — открыть текущую картину",
    now: "Сейчас",
    ask: "Спросить",
    company: "Компания",
    primaryZones: "Основные зоны компании",
    boundary: "Память с доказательствами",
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
    warnings: "Предупреждения",
    sourceAdminOnlyNote:
      "На этом экране вам доступен только просмотр. Импорт, подключение и синхронизацию может запускать только владелец или администратор компании."
  },

  auth: {
    title: "Войдите в компанию",
    subtitle: "Откроем её текущую картину и покажем один следующий ход.",
    email: "Логин",
    password: "Пароль",
    signIn: "Войти",
    signingIn: "Выполняется вход…",
    loginFailedGeneric: "Неверный логин или пароль.",
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

  companyBrainPage: {
    eyebrow: "Карта связей",
    title: "Компания",
    description: "Нажмите на человека или компанию — справа откроется профиль.",
    dataLayerTitle: "Канонические данные",
    dataLayerIndex: "ДАННЫЕ",
    dataLayerDescription:
      "Технический слой карты: работа, источники, нормализованные сущности и подтверждающие материалы без выдуманных связей."
  },

  companyWorld: {
    eyebrow: "Операционная карта",
    title: "Компания",
    worldEyebrow: "Связи компании",
    worldDescription:
      "Команда, подтверждённые связи и новые сигналы в одной рабочей сцене.",
    refreshWorld: "Обновить карту",
    badge: "Подтверждается источниками",
    intro:
      "Карта строится только из участников рабочего пространства и нормализованных источников. Внешние люди и компании остаются кандидатами до подтверждения.",
    boardEyebrow: "Стратегическая сцена",
    boardTitle: "Кто находится вокруг компании",
    boardDescription:
      "Компания находится в центре. Сплошной контур — подтверждённые люди и отношения; пунктирный контур — сигналы, которые ещё должен разобрать человек.",
    boardLegend: "Легенда стратегической карты",
    zoneFilterLabel: "Показать область компании",
    allContours: "Вся компания",
    confirmedContour: "Подтверждённый контур",
    discoveryContour: "Требует разбора",
    operatingCenter: "Центр управления",
    companyCoreHint: "Профиль и общая история",
    teamZoneDescription: "Подтверждённые участники рабочего пространства.",
    confirmedNetwork: "Деловой контур",
    confirmedNetworkDescription: "Связи, которые уже подтвердила команда.",
    discoveryZone: "Разведка",
    discoveryDescription: "Кандидаты из источников — без автоматически назначенных ролей.",
    discoveryComplete: "Новых людей и организаций для разбора сейчас нет.",
    discoveryCompleteInWindow:
      "В показанном окне новых людей и организаций для разбора нет.",
    needsReview: "Нужно разобрать",
    reviewRailTitle: (count: number, isLowerBound = false) =>
      `${isLowerBound ? "Не менее " : ""}${count} ${russianPlural(
        count,
        "сигнал ждёт",
        "сигнала ждут",
        "сигналов ждут"
      )} разбора`,
    reviewRailNext: (label: string) => `Следующий: ${label}`,
    reviewRailCurrent: (label: string) =>
      `Сейчас открыт ${label} — решение доступно в профиле справа.`,
    reviewRailClearTitle: "Новых сигналов нет",
    reviewRailClearDescription: "Текущий контур разобран — можно изучать профили и историю.",
    reviewRailWindowClearTitle: "В показанном окне новых сигналов нет",
    reviewRailWindowClearDescription:
      "Более ранние сообщения не входят в этот снимок; вывод не относится ко всей истории.",
    openNextCandidate: "Разобрать следующий",
    openAllTouchpoints: "Показать все соприкосновения компании",
    confirmedPeopleInOrganization: "Люди с подтверждённой связью с организацией",
    noConfirmedPeopleInOrganization:
      "Подтверждённых людей с явной связью с этой организацией пока нет.",
    standaloneConfirmedPeople: "Подтверждённые без организации",
    noConfirmedAffiliation: "Организация не подтверждена",
    domainSignalNotAffiliation: "Совпадение домена — не подтверждённая связь",
    relationshipNotSpecified: "Связь не классифицирована",
    domainNotSpecified: "Домен не указан",
    loading: "Собираем карту компании…",
    noWorkspaceDescription: "Войдите в рабочее пространство, чтобы увидеть карту компании.",
    unavailableTitle: "Карта компании недоступна",
    unavailableDescription: "Не удалось загрузить людей, организации и соприкосновения.",
    emptyTitle: "Карта ещё не собрана",
    emptyDescription: "Добавьте участников или импортируйте Gmail-сигналы.",
    summaryLabel: "Сводка карты компании",
    internalPeople: "Команда",
    internalPeopleDescription: "Подтверждённые участники рабочего пространства.",
    confirmedExternalPeople: "Подтверждённые внешние лица",
    confirmedExternalPeopleDescription:
      "Люди, которых участник команды подтвердил вручную.",
    confirmedOrganizations: "Подтверждённые организации",
    confirmedOrganizationsDescription:
      "Организации с явно выбранным человеком типом отношений.",
    externalPeople: "Люди в поле зрения",
    externalPeopleDescription: "Внешние контакты-кандидаты в текущем окне.",
    organizations: "Организации",
    organizationsDescription:
      "Корпоративные домены-кандидаты в текущем окне, не подтверждённые заказчики.",
    touchpoints: "Соприкосновения",
    touchpointsDescription: "Подтверждённые события коммуникации в текущем окне.",
    companySection: "Ваша компания",
    teamSection: "Команда",
    contactsSection: "Ключевые лица в поле зрения",
    organizationsSection: "Компании в поле зрения",
    confirmedContactsSection: "Подтверждённые внешние лица",
    confirmedOrganizationsSection: "Подтверждённые организации",
    timelineSection: "Журнал соприкосновений",
    profileTimeline: "История этого профиля",
    allCompanyTouchpoints: "Все соприкосновения компании",
    showMoreTouchpoints: "Показать остальные соприкосновения",
    noProfileTouchpoints: "Для выбранного профиля соприкосновений в текущем окне нет.",
    noContacts: "Внешние контакты пока не обнаружены.",
    noOrganizations: "Корпоративные организации пока не обнаружены.",
    noConfirmedContacts: "Подтверждённых внешних лиц пока нет.",
    noConfirmedOrganizations: "Подтверждённых организаций пока нет.",
    noTouchpoints: "Соприкосновения пока не загружены.",
    windowLabel: "Почтовое окно",
    windowTruncated: "показаны последние сообщения",
    capabilities: "Границы проекции",
    readOnly: "Только чтение",
    resolutionEnabled: "Локальные подтверждения доступны",
    noProviderCalls: "Без вызовов внешних сервисов",
    noExternalWrites: "Без записей во внешние сервисы",
    noLlm: "Без языковой модели",
    localProjection: "Локальная проекция",
    candidate: "Кандидат",
    confirmed: "Подтверждено",
    needsConfirmation: "Нужно подтвердить роль",
    organizationNeedsConfirmation: "Нужно определить отношения",
    relationshipType: "Тип связи с человеком",
    organizationRelationshipKind: "Тип отношений с организацией",
    selectClassification: "Не выбрано",
    relationshipTypes: {
      contact: "Контакт",
      employee: "Сотрудник",
      decision_maker: "Лицо, принимающее решение",
      account_owner: "Ответственный за аккаунт",
      advisor: "Советник",
      other: "Другое"
    },
    organizationRelationshipKinds: {
      unknown: "Не определено",
      prospect: "Потенциальный заказчик",
      customer: "Заказчик",
      partner: "Партнёр",
      vendor: "Поставщик",
      other: "Другое"
    },
    statuses: {
      active: "Активен",
      archived: "В архиве",
      confirmed: "Подтверждено"
    },
    roleTitle: "Роль или должность",
    roleRequiresRelationship: "Сначала выберите тип связи с организацией.",
    displayName: "Отображаемое имя",
    organizationName: "Название организации",
    classificationOptional: "Необязательно — укажите только то, что знаете.",
    humanClassificationBoundary:
      "Классификацию задаёт человек. Система не назначает автоматически заказчика, сотрудника или ключевое лицо.",
    confirmCandidate: "Подтвердить",
    dismissCandidate: "Отклонить кандидата",
    resolutionPersonQuestion: "Добавить этого человека в карту компании?",
    resolutionOrganizationQuestion: "Добавить эту организацию в деловой контур?",
    resolutionQuestionHint:
      "Система показывает сигнал из источника, но решение и классификацию задаёт человек.",
    resolutionKeepPerson: "Да, разобрать человека",
    resolutionKeepOrganization: "Да, разобрать организацию",
    resolutionNamePersonQuestion: "Как подписать этого человека?",
    resolutionNameOrganizationQuestion: "Как подписать эту организацию?",
    resolutionPersonRelationshipQuestion: "Кем этот человек приходится организации?",
    resolutionOrganizationRelationshipQuestion: "Кем эта организация приходится вам?",
    resolutionRoleTitleQuestion: "Какая у человека должность?",
    resolutionBack: "Назад",
    resolutionContinue: "Продолжить",
    resolutionSave: "Сохранить в карту",
    resolutionOptionalAnswer: "Можно оставить пустым, если пока неизвестно.",
    resolutionStepLabel: "Вопрос",
    resolvingCandidate: "Сохраняем решение…",
    resolutionPending: "Решение сохраняется локально…",
    resolutionConfirmed: "Кандидат подтверждён. Карта обновляется.",
    resolutionDismissed: "Кандидат отклонён. Карта обновляется.",
    resolutionConfirmedRefreshed: "Кандидат подтверждён. Карта обновлена.",
    resolutionDismissedRefreshed: "Кандидат отклонён. Карта обновлена.",
    resolutionSavedRefreshFailed:
      "Решение сохранено, но обновить карту не удалось. Повторите обновление карты.",
    resolutionConflict:
      "Кандидат изменился после загрузки. Карта обновлена — проверьте факты и повторите решение.",
    resolutionNotFound:
      "Кандидат уже отсутствует или был обработан. Карта обновляется.",
    resolutionForbidden:
      "Права доступа изменились. Карта обновляется в режиме только чтения.",
    resolutionValidation:
      "Сервер не принял выбранные значения. Проверьте классификацию и повторите.",
    resolutionError: "Не удалось сохранить решение. Проверьте данные и повторите.",
    resolutionReadOnly:
      "У вас доступ только для чтения. Подтверждение и отклонение доступны роли «Участник» и выше.",
    resolutionStatusLabel: "Состояние решения по кандидату",
    organizationResolutionRequired: "Сначала решите судьбу организации",
    organizationResolutionRequiredDescription:
      "Человек связан с организацией-кандидатом. Участник команды должен подтвердить или отклонить организацию, затем вернуться к человеку.",
    openOrganizationProfile: "Открыть организацию",
    confirmedOrganizationForPerson: "Организация из сигнала уже подтверждена",
    confirmedOrganizationForPersonDescription:
      "Совпадение домена ещё не является связью человека. Выберите роль вручную, только если вы её действительно знаете.",
    standalonePerson:
      "Подтверждённой организации нет. Человек будет сохранён как самостоятельный контакт.",
    openProfile: "Открыть профиль",
    profileTitle: "Профиль",
    companyProfile: "Профиль компании",
    personProfile: "Профиль человека",
    organizationProfile: "Профиль организации",
    touchpointProfile: "Событие",
    role: "Роль",
    status: "Статус",
    email: "Эл. почта",
    domain: "Домен",
    workspace: "Рабочее пространство",
    interactions: "Соприкосновения",
    inShownWindow: "в показанном окне",
    people: "Люди",
    lastInteraction: "Последний контакт",
    evidence: "Подтверждающие источники",
    evidenceDisclosure: "Показать источники и происхождение данных",
    technicalDisclosure: "Показать технические границы карты",
    noEvidence: "Нет связанных источников.",
    direction: "Направление",
    directions: {
      inbound: "Входящее",
      outbound: "Исходящее",
      mixed: "Смешанное",
      unknown: "Не определено"
    },
    roles: {
      owner: "Владелец",
      admin: "Администратор",
      member: "Участник",
      viewer: "Наблюдатель"
    },
    boundary:
      "Доступ только внутри рабочего пространства. Наблюдатель читает карту; роль «Участник» и выше может локально подтвердить либо отклонить кандидата. Домен письма не означает, что организация является заказчиком."
  },

  githubAppSetup: {
    eyebrow: "Подключение без терминала",
    title: "Настройте GitHub прямо здесь",
    badge: "Репозитории — только чтение",
    description:
      "FounderOS создаст и установит GitHub App. Код, задачи и пулреквесты не изменяются.",
    loading: "Проверяем, какой шаг уже готов…",
    loadErrorTitle: "Не удалось открыть настройку GitHub",
    loadErrorDescription:
      "Существующие данные не изменились. Проверьте локальный сервер и повторите запрос.",
    retry: "Повторить",
    adminOnly:
      "Подключение настраивает владелец или администратор компании. Вы можете просматривать уже загруженные данные.",
    flowLabel: "Этапы подключения GitHub",
    stepCreate: "Создать App",
    stepCreateHint: "FounderOS подготовит безопасное приложение.",
    stepInstall: "Установить",
    stepInstallHint: "Вы подтвердите доступ на стороне GitHub.",
    stepRepositories: "Репозитории",
    stepRepositoriesHint: "Вы выберете, что видеть в FounderOS.",
    stepReady: "Готово",
    stepReadyHint: "Задачи и PR можно загружать.",
    ownerLegend: "Где создать GitHub App?",
    ownerUser: "В личном аккаунте",
    ownerUserHint: "Подходит для личной разработки и быстрого старта.",
    ownerOrganization: "В организации",
    ownerOrganizationHint: "Выберите, если репозитории принадлежат команде.",
    organizationLabel: "Название организации в GitHub",
    organizationPlaceholder: "например, my-company",
    organizationRequired: "Укажите название организации GitHub.",
    start: "Настроить GitHub за 2 минуты",
    startPending: "Открываем GitHub…",
    startHint:
      "GitHub откроется в этой вкладке. Подтвердите создание — затем вы автоматически вернётесь сюда.",
    registrationPendingTitle: "Ждём подтверждение в GitHub",
    registrationPendingDescription:
      "Завершите создание приложения в открывшейся вкладке. Если вы отменили действие, начните заново.",
    exchangePendingTitle: "Сохраняем безопасное подключение",
    exchangePendingDescription:
      "FounderOS получает данные приложения и сразу шифрует секреты.",
    installTitle: "Приложение создано — осталось установить",
    installDescription:
      "На стороне GitHub выберите аккаунт и разрешите только нужные репозитории.",
    install: "Установить и выбрать репозитории",
    installPending: "Открываем установку…",
    verifyTitle: "Проверяем установку",
    verifyDescription:
      "FounderOS подтверждает, что установка принадлежит вашему аккаунту. Временный токен пользователя не сохраняется.",
    repositoriesTitle: "Какие репозитории использовать?",
    repositoriesDescription:
      "Доступные репозитории уже отмечены. Снимите лишние: FounderOS будет видеть только сохранённый выбор.",
    repositoriesEmptyTitle: "GitHub не дал доступ ни к одному репозиторию",
    repositoriesEmptyDescription:
      "Разрешите репозитории в настройках установки GitHub, затем проверьте доступ ещё раз.",
    openRepositoryAccess: "Открыть настройки доступа",
    refreshRepositories: "Проверить доступ ещё раз",
    refreshRepositorySelection: "Обновить список репозиториев",
    refreshingRepositories: "Проверяем репозитории…",
    repositorySelectionRequired: "Выберите хотя бы один репозиторий.",
    repositorySelectionLimit: "Можно выбрать не более 100 репозиториев.",
    saveRepositories: "Сохранить выбор",
    savingRepositories: "Сохраняем выбор…",
    connectedTitle: "GitHub подключён",
    connectedDescription:
      "FounderOS видит выбранные репозитории и ничего в них не меняет.",
    connectedManageHint:
      "Нужно изменить набор? Сначала обновите доступ в GitHub, затем загрузите список и сохраните новый выбор.",
    connectedAccount: "Аккаунт",
    connectedApp: "Приложение",
    connectedRepositories: "Репозиториев",
    restart: "Начать заново",
    restarting: "Сбрасываем настройку…",
    cancelledTitle: "Подключение отменено",
    cancelledDescription:
      "Ничего не подключено. Можно безопасно начать настройку ещё раз.",
    failedTitle: "Подключение требует внимания",
    failedDescription:
      "FounderOS не завершил проверку. Данные GitHub не были приняты как подтверждённые.",
    errorExpired: "Время подтверждения истекло. Начните настройку заново.",
    errorReplay: "Эта ссылка уже использована. Начните новую безопасную настройку.",
    errorDenied: "GitHub не получил подтверждение доступа. Попробуйте ещё раз.",
    errorInstallationMissing:
      "FounderOS не смог подтвердить установку для вашего аккаунта GitHub.",
    errorProvider: "GitHub временно недоступен. Повторите попытку позже.",
    errorGeneric: "Не удалось завершить действие. Попробуйте ещё раз.",
    launchBlocked:
      "FounderOS отклонил небезопасный адрес перехода. Настройка не продолжена."
  },

  githubProductConnect: {
    eyebrow: "Источник данных",
    title: "Центр GitHub",
    badgeReadOnly: "Репозитории — только чтение",
    description:
      "Выберите один репозиторий и загрузите его задачи и пулреквесты в рабочую картину FounderOS.",
    notConnectedBadge: "Не подключён",
    connectionAttentionBadge: "Нужно завершить",
    connectedBadge: "Подключён",
    connectTitle: "Подключите GitHub",
    connectDescription:
      "Выберите аккаунт и репозитории — FounderOS соберёт задачи и pull requests в одном месте.",
    connectionAttentionTitle: "Завершите подключение",
    connectionAttentionDescription:
      "Установка уже начата. Продолжите с текущего шага — повторно создавать приложение не нужно.",
    connectedTitle: "GitHub готов к работе",
    connectedDescription:
      "Доступ подтверждён. Выберите репозиторий и обновите данные.",
    capabilitiesLabel: "Что появится после подключения",
    capabilityRepositories: "Доступ только к выбранным репозиториям",
    capabilityIssues: "Задачи и их текущие статусы",
    capabilityPullRequests: "Pull requests без изменений в GitHub",
    connectAction: "Подключить GitHub",
    continueSetupAction: "Продолжить подключение",
    closeSetupAction: "Закрыть",
    manageConnection: "Управление",
    setupPanelTitle: "Подключение GitHub",
    readOnlyPromise: "Только чтение · GitHub не изменяется",
    repositoryControlEyebrow: "Рабочий репозиторий",
    repositoryControlTitle: "Что обновить?",
    repositoryControlDescription:
      "FounderOS загрузит задачи и pull requests только из выбранного репозитория.",
    repositorySelectLabel: "Репозиторий",
    updateData: "Обновить данные",
    updatingData: "Обновляем…",
    openRepository: "Открыть в GitHub",
    manageRepositoryAccess: "Изменить доступ",
    lastUpdatedLabel: "Последнее обновление",
    repositoryCountLabel: "Доступно репозиториев",
    safetyDetails: "Доступ и безопасность",
    safetyDescription:
      "FounderOS использует временный токен установки и не выполняет запись в GitHub.",
    loading: "Проверяем подключение и репозитории…",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — подключать нечего.",
    unavailableTitle: "Состояние GitHub App недоступно",
    unavailableDescription:
      "Не удалось проверить подключение. Повторите запрос — существующие данные не изменятся.",
    errorDetails: "Показать техническую причину",
    missionViewerCurrent: "GitHub доступен вам для просмотра",
    missionConnectionCurrent: "GitHub ещё не готов к загрузке",
    missionConnectionAttentionCurrent: "Подключение GitHub требует внимания",
    missionEmptyCurrent: "Подключение готово, но список репозиториев пуст",
    missionReadyCurrent: "Можно загрузить работу из одного репозитория",
    missionSyncedCurrent: "Выбранный репозиторий загружен",
    missionViewerAction: "Проверьте доступные репозитории и их состояние",
    missionConnectionAction: "Подключите GitHub App",
    missionConnectionAttentionAction:
      "Проверьте статус установки и блокеры",
    missionTechnicalAction: "Откройте технические детали и снимите блокеры",
    missionSelfServiceSetupAction: "Начните подключение в мастере выше",
    missionEmptyAction: "Проверьте установку и доступ к репозиториям",
    missionReadyAction: "Выберите репозиторий и запустите загрузку",
    missionPartialCurrent: "Репозиторий загружен частично",
    missionPartialAction: "Проверьте предупреждения и при необходимости повторите загрузку",
    missionViewerOutcome: "Вы увидите, какие данные уже доступны в FounderOS",
    missionConnectionOutcome:
      "После подключения FounderOS сможет читать выбранные репозитории",
    missionEmptyOutcome: "Доступные репозитории появятся в списке выбора",
    missionReadyOutcome: "Задачи и PR появятся в оперативной картине FounderOS",
    missionPartialOutcome:
      "Пульс обновлён доступными данными; отсутствующие категории отмечены предупреждением",
    missionSyncedOutcome: "Пульс работы ниже обновлён данными выбранного репозитория",
    missionSafeDetails:
      "FounderOS только читает выбранный репозиторий. Массовой загрузки и изменений в GitHub эта кнопка не выполняет.",
    flowLabel: "Путь данных из GitHub в FounderOS",
    flowConnectionTitle: "Подключение",
    flowConnectionDescription: "GitHub App даёт безопасный доступ на чтение.",
    flowRepositoryTitle: "Репозиторий",
    flowRepositoryDescription: "Вы выбираете один понятный источник работы.",
    flowFounderOSTitle: "Задачи и PR",
    flowFounderOSDescription: "FounderOS обновляет оперативную картину.",
    metricsTitle: "Состояние источника",
    metricsLabel: "Ключевые метрики GitHub",
    metricsHintLabel: "Как читать метрики GitHub?",
    metricsHint:
      "Счётчики относятся только к уже загруженному ответу. FounderOS не достраивает отсутствующие данные и не выдаёт локальную копию за живой GitHub.",
    connectionMetricTitle: "Подключение",
    connectionMetricConnected: "Готово",
    connectionMetricAttention: "Нужно внимание",
    loadedMetricTitle: "В выборке",
    activeMetricTitle: "Активные",
    activeMetricHint: "Неархивные репозитории в загруженной выборке.",
    lastSyncMetricTitle: "Последняя загрузка",
    lastSyncMetricHint: "Время последней записанной синхронизации подключения.",
    lastSyncNever: "Ещё не было",
    setupActionHint:
      "Установите приложение, вернитесь на страницу и проверьте подключение.",
    repositoryAccessActionHint:
      "Разрешите доступ хотя бы к одному репозиторию, затем обновите состояние.",
    connectionAttentionActionHint:
      "Установка уже записана. Проверьте её статус и блокеры — создавать вторую установку не нужно.",
    refreshConnection: "Проверить подключение",
    repositoryWorkbenchEyebrow: "Ваш выбор",
    repositoryWorkbenchTitle: "Какой репозиторий загрузить?",
    repositoryWorkbenchDescription:
      "Сначала выберите карточку. Затем нажмите одну кнопку под списком.",
    repositoryActive: "Активный",
    repositoryArchived: "Архивный",
    repositorySourceTitle: "Источник списка",
    technicalDetails: "Технические детали и безопасность",
    technicalDescription:
      "Здесь собраны safety-факты, источник выборки и предупреждения. Настройка выполняется выше через понятные шаги.",
    receiptEyebrow: "Готово",
    receiptPartialEyebrow: "Частично готово",
    receiptPendingEyebrow: "В процессе",
    receiptErrorEyebrow: "Требует внимания",
    receiptTechnicalDetails: "Предупреждения синхронизации",
    appTitle: "GitHub App",
    appConnected: "Подключено",
    appConfigured: "Готово",
    appNotConfigured: "Не настроено",
    appInstallationDescription: "Установка GitHub App записана в этом рабочем пространстве.",
    appConnectionAttentionDescription:
      "Запись установки найдена, но подключение сейчас не находится в состоянии «Готово».",
    appReadyDescription: "Конфигурация GitHub App готова; можно установить приложение для рабочего пространства.",
    appMissingDescription: "Нужны server-side env-поля GitHub App перед установкой.",
    appManagedSetupDescription:
      "Завершите безопасный мастер выше — терминал и env-настройка не нужны.",
    repositoriesTitle: "Локальная поверхность репозиториев",
    tokenTitle: "Токены установки хранятся",
    tokenDescription: "Для GitHub App токены установки должны выпускаться just-in-time и не сохраняться.",
    writeTitle: "Записи в GitHub",
    writeDescription: "Product connect остаётся read-only; write-actions включаются только отдельным approval path.",
    realReadReadinessTitle: "Готовность первого real read",
    realReadReadinessLabel: "Готовность GitHub App real-provider read run",
    realReadReadinessDescription:
      "Сводка повторяет локальную проверку настройки: наличие переменных, подключение установки к компании и доступные репозитории. Она не читает и не изменяет данные GitHub.",
    realReadStatusTitle: "Статус",
    realReadStatusDescription: "Можно ли запускать отдельный human-approved scoped read.",
    realReadReady: "Готово",
    realReadBlocked: "Заблокировано",
    realReadEnvTitle: "GitHub App env",
    realReadEnvDescription: "Показываются только имена отсутствующих env-полей, без значений секретов.",
    realReadInstallationTitle: "Installation connection",
    realReadInstallationDescription:
      "Workspace должен иметь connected GitHub App installation record.",
    realReadRepoSurfaceTitle: "Repo surface",
    realReadRepoSurfaceDescription:
      "Нужен минимум один локальный repo target перед scoped read sync.",
    realReadBlockersTitle: "Блокеры",
    realReadBlockerEnv: "GitHub App env incomplete",
    realReadBlockerConnectionMissing: "Installation connection missing",
    realReadBlockerConnectionNotConnected: "Installation connection not connected",
    realReadBlockerReposEmpty: "Local repository surface empty",
    realReadBoundary:
      "Даже когда статус готов, запуск остаётся отдельным explicit action по одному выбранному репозиторию.",
    missingEnvTitle: "Не хватает server-side env-полей",
    openSetup: "Подключить GitHub App",
    openSetupSettings: "Открыть настройки GitHub App",
    liveSyncTitle: "Живая read-only синхронизация",
    liveSyncDescription:
      "Запускает backend polling-only GitHub App sync для одного явно указанного репозитория. Токен установки выпускается just-in-time, не сохраняется, записи в GitHub не выполняются.",
    liveSyncRepositoryLabel: "Репозиторий для синхронизации",
    liveSyncRepositoryPlaceholder: "owner/repo",
    liveSyncRepositoryNote:
      "Репозиторий должен быть доступен текущей установке GitHub App. Массовая синхронизация всей организации здесь не запускается.",
    liveSyncRepositoryInvalid: "Укажите репозиторий в формате owner/repo без пробелов.",
    liveSyncRequiresApp: "Сначала нужна подключённая запись GitHub App installation.",
    liveSyncRun: "Загрузить задачи и PR",
    liveSyncRunning: "Загружаем задачи и PR…",
    liveSyncFailedTitle: "Не удалось загрузить репозиторий",
    liveSyncFailedDescription: "FounderOS не смог прочитать выбранный репозиторий.",
    liveSyncResultTitle: "Результат загрузки",
    liveSyncPendingTitle: "Загрузка ещё выполняется",
    liveSyncPendingDescription:
      "Backend вернул промежуточный статус. Автоматическое ожидание не запущено — можно обновить страницу или повторить чтение.",
    liveSyncPartialTitle: "Загрузка завершена частично",
    liveSyncPartialDescription:
      "FounderOS обновил всё, что удалось прочитать. Одна или несколько запрошенных категорий оказались пустыми — подробности есть в предупреждениях.",
    liveSyncResultFailedTitle: "Загрузка завершилась с ошибкой",
    liveSyncResultFailedDescription:
      "Данные не считаются обновлёнными. Проверьте предупреждения и повторите чтение.",
    liveSyncNoWrites: "GitHub не изменён — выполнено только чтение.",
    repositoryListTitle: "Репозитории",
    repositoryListEmptyTitle: "Репозитории не найдены",
    repositoryListEmptyDescription:
      "FounderOS пока не видит доступных репозиториев. Подключите GitHub App или разрешите ему доступ к нужным репозиториям.",
    repositoryFocusLabel: "Фильтр локальной поверхности репозиториев",
    repositoryFocusAll: "Все",
    repositoryFocusActive: "Активные",
    repositoryFocusArchived: "Архивные",
    repositoryFocusPrivate: "Приватные",
    repositoryFocusWithEvidence: "С источниками",
    repositoryListNoReposForFilter:
      "Для выбранного локального фильтра репозиториев нет."
  },

  githubWork: {
    eyebrow: "Работа",
    title: "Задачи и pull requests",
    description: "Последние сохранённые данные GitHub.",
    repositoryPrefix: "Репозиторий:",
    stateLabel: "Статус",
    kindLabel: "Тип работы",
    stateAll: "Все",
    stateOpen: "Открытые",
    stateClosed: "Закрытые",
    stateMerged: "Слитые",
    loading: "Загрузка работы GitHub",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — работы GitHub нет.",
    unavailableTitle: "Оперативная работа GitHub недоступна",
    unavailableDescription:
      "Не удалось прочитать сохранённые задачи и PR. Повторите запрос — данные не изменятся.",
    errorDetails: "Показать техническую причину",
    sampleNote:
      "Метрики относятся к текущему фильтру локально загруженной выборки — до 100 задач и 100 PR.",
    emptyTitle: "Оперативная работа GitHub ещё не синхронизирована",
    emptyDescription:
      "Запустите локальную нормализацию GitHub с канонической записью, чтобы наполнить задачи и пулреквесты.",
    issuesTitle: "Задачи",
    pullRequestsTitle: "Pull requests",
    noIssuesForFilter: "Нет задач для этого фильтра.",
    noPullRequestsForFilter: "Нет пулреквестов для этого фильтра.",
    nothingFoundTitle: "Здесь пока пусто",
    showMore: "Показать ещё",
    openInGitHub: "Открыть",
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
    noBriefingReadOnlyDescription:
      "Сохранённых сводок пока нет. В режиме просмотра новую сводку создаёт участник, администратор или владелец.",
    readOnlyMode: "Только просмотр",
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
    actionReadOnlyDescription:
      "В режиме просмотра можно изучать уже созданные действия, но нельзя создавать новые.",
    actionSummaryEmpty:
      "По видимым пунктам сводки ещё нет локальных предложений действий.",
    openActions: "Открыть действия",
    actionGenerate: "Сгенерировать локальные действия из сводки",
    actionGeneratingFromBriefing: "Генерация локальных действий",
    actionCreate: "Создать локальное действие",
    actionCreating: "Создание локального действия",
    actionAlreadyCreated: "Действие уже создано",
    actionCreateSuccess:
      "Локальное действие создано. Проверьте его в блоке «Действия» перед одобрением.",
    actionGenerateSuccess:
      "Локальные действия из сводки сгенерированы. Проверьте их в блоке «Действия» перед одобрением.",
    storedValue: "Сохранено"
  },

  briefingHistory: {
    title: "История сводок",
    description: "Сохранённые сводки этого рабочего пространства, новые — сверху.",
    empty: "Сохранённых сводок пока нет. Сформируйте первую сводку выше.",
    emptyReadOnly:
      "Сохранённых сводок пока нет. Попросите участника, администратора или владельца создать первую.",
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
    eyebrow: "Комната решений",
    title: "Решения",
    description: "Решите, что компания делает дальше — на основании фактов."
  },

  actionsPanel: {
    eyebrow: "Комната решений",
    title: "Решения",
    badgeLocalApproval: "Под контролем человека",
    intro: "Сначала — решения, которые ждут вашего решения.",
    capabilityTitle: "Как это работает безопасно",
    loading: "Загрузка предложений действий",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — предложений нет.",
    unsupportedTitle: "Предложения действий не поддерживаются",
    unsupportedDescription: "Бэкенд не сообщил о поддержке локальных предложений действий.",
    unavailableTitle: "Предложения действий недоступны",
    unavailableDescription: "Запрос предложений действий не удался.",
    linkedProposalNotFoundTitle: "Предложение не найдено",
    linkedProposalNotFoundDescription:
      "Это предложение удалено, устарело или относится к другой компании.",
    linkedProposalForbiddenTitle: "Нет доступа к предложению",
    linkedProposalForbiddenDescription:
      "У вашей роли нет доступа к предложению по этой ссылке.",
    linkedProposalUnavailableDescription:
      "Не удалось безопасно открыть предложение по ссылке. Повторите попытку.",
    linkedProposalOutsideFilter:
      "Предложение из ссылки показано поверх текущего фильтра.",
    emptyTitle: "Решений пока нет",
    emptyDescription: "Добавьте первый следующий ход компании.",
    summaryLabel: "Сводка предложений",
    proposedTitle: "Ждут решения",
    proposedDescription: "Проверьте основание и ответьте.",
    approvedTitle: "Приняты",
    approvedDescription: "Подтверждённые человеком решения.",
    rejectedTitle: "Отклонены",
    rejectedDescription: "Предложения, которые не пойдут дальше.",
    totalTitle: "Всего",
    totalDescription: "Количество из списка бэкенда.",
    readinessTitle: "Техническая готовность",
    readinessLabel: "Сводка готовности предложений к локальной проверке и предпросмотру",
    readinessDescription:
      "Сводка считается только по уже загруженным предложениям. Она не запускает внешние действия, синхронизацию или ИИ.",
    readinessPendingTitle: "Ждут ответа",
    readinessPendingDescription: "Эти предложения нужно принять или отклонить.",
    readinessPreviewTitle: "Готовы к проверке",
    readinessPreviewDescription: "Основания собраны; внешний запрос ещё не выполняется.",
    readinessLocalOnlyTitle: "Останутся внутри",
    readinessLocalOnlyDescription: "Внутренние задачи не отправляются во внешние системы.",
    readinessMissingEvidenceTitle: "Не хватает основания",
    readinessMissingEvidenceDescription: "Без доказательств действие нельзя отправлять дальше.",
    readinessExternalResultTitle: "Есть результат",
    readinessExternalResultDescription: "Для действия сохранена квитанция выполнения.",
    readinessBoundary:
      "Эта сводка только помогает выбрать следующий локальный шаг; внешнее выполнение здесь не запускается.",
    filterTitle: "Показать",
    filterLabel: "Фильтр локальных предложений",
    filterDescription: "Выберите, на каких решениях сосредоточиться сейчас.",
    filterProposed: "Нужно решение",
    filterApproved: "Одобрено",
    filterRejected: "Отклонено",
    filterAll: "Все",
    originFilterTitle: "Откуда появилось решение",
    originFilterLabel: "Фильтр источника локальных предложений",
    originFilterDescription: "Показываем происхождение, не выдавая его за решение человека.",
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
    listTitle: "Решения компании",
    noProposals: "В загруженной очереди решений нет.",
    noProposalsForFilter: "В выбранном фокусе решений нет.",
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
    approve: "Принять решение",
    approving: "Сохраняем решение",
    reject: "Не делать",
    rejecting: "Сохраняем отказ",
    createError: "Для локального предложения задачи GitHub нужны заголовок и репозиторий.",
    createSuccess: "Локальное предложение создано. Внешнее выполнение здесь отключено.",
    approveSuccess: "Решение сохранено в FounderOS. Внешнее действие не запускалось.",
    rejectSuccess: "Отказ сохранён в FounderOS. Внешнее действие не запускалось.",
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
    typeLabel: "Тип решения",
    typeGithubIssue: "Будущая задача GitHub",
    typeInternalTodo: "Внутренняя задача",
    titleLabel: "Заголовок",
    titlePlaceholder: "Что должна сделать компания",
    descriptionLabel: "Описание",
    descriptionPlaceholder: "Зачем это предложение и какие источники стоит проверить",
    repositoryLabel: "Репозиторий",
    repositoryPlaceholder: "владелец/репозиторий",
    issueBodyLabel: "Текст задачи",
    issueBodyPlaceholder: "Текст для предлагаемой будущей задачи GitHub",
    submit: "Добавить решение",
    submitting: "Добавляем решение",
    note: "Решение сохранится в FounderOS. Оно не создаст задачу GitHub и не вызовет внешний сервис."
  },

  actionExecution: {
    previewTitle: "Проверить внешний шаг",
    previewIntro:
      "Принятое решение ничего не отправляет. Сначала посмотрите точный будущий запрос к GitHub.",
    approveFirst: "Сначала примите решение внутри FounderOS.",
    preview: "Проверить внешний шаг",
    preparingPreview: "Готовим безопасный просмотр",
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
    auditRefreshFailed:
      "Предпросмотр получен, но свежую историю аудита загрузить не удалось. Повторять внешний шаг не нужно.",
    auditRefreshAfterExecuteFailed:
      "Действие уже завершено и квитанция сохранена, но свежую историю аудита загрузить не удалось. Не повторяйте действие — обновите историю позже.",
    noWorkspacePreview: "У вашего аккаунта нет рабочего пространства — предпросмотр недоступен.",
    noWorkspaceExecute: "У вашего аккаунта нет рабочего пространства — выполнение недоступно.",
    previewLoaded: "Предпросмотр выполнения загружен. Внешней записи не было.",
    externalDisabledError: "Внешнее выполнение отключено в этом окружении.",
    confirmRequired: "Перед выполнением нужны ID подключения и явное подтверждение.",
    successExisting: "Возвращена существующая квитанция выполнения. Дополнительной внешней записи не было.",
    successExternalResult: "Бэкенд сообщил о результате внешнего выполнения.",
    successNoWrite: "Запрос на выполнение завершён без внешней записи.",
    reconciliationTitle: "Сначала проверим результат",
    reconciliationDescription:
      "Ответ GitHub потерян или выполнение осталось незавершённым. Не запускайте действие ещё раз: FounderOS безопасно проверит GitHub только на чтение.",
    reconciliationRequired:
      "Результат внешнего шага пока не подтверждён. Повторное выполнение заблокировано; запустите безопасную проверку.",
    reconcile: "Проверить результат в GitHub",
    reconciling: "Проверяем результат",
    reconciliationPending:
      "GitHub ещё может обновлять данные. Внешнее действие остаётся заблокированным; повторите только безопасную проверку позже.",
    reconciliationSucceeded:
      "FounderOS нашёл точную задачу GitHub и записал подтверждённый результат.",
    reconciliationNoWrite:
      "Полная проверка не нашла внешнюю задачу. Повтор возможен только после нового подтверждения.",
    reconciliationRetryAfter: "Следующая безопасная проверка после:",
    fallbackCreated: "Локальное предложение действия создано.",
    fallbackApproved: "Предложение одобрено локально. Внешняя запись не выполнялась.",
    fallbackRejected: "Предложение отклонено локально. Внешняя запись не выполнялась."
  },

  settings: {
    eyebrow: "Люди и доступ",
    title: "Команда и аккаунт",
    description: "Управляйте участниками компании и безопасностью своего входа.",
    signedInAs: "Вы вошли как:",
    workspace: "Компания:",
    workspaceNone: "Нет",
    changePasswordTitle: "Сменить пароль",
    currentPassword: "Текущий пароль",
    newPassword: "Новый пароль",
    newPasswordHint: "От 8 до 256 символов.",
    changePassword: "Сменить пароль",
    changing: "Смена пароля…",
    changeSuccess: "Пароль изменён. На других устройствах выполнен выход.",
    changeError: "Не удалось сменить пароль. Проверьте текущий пароль.",
    teamTitle: "Команда",
    teamDescription: "Кто видит компанию и какие действия ему доступны.",
    teamLoading: "Загрузка участников",
    teamUnavailableTitle: "Участники недоступны",
    teamUnavailableDescription: "Не удалось загрузить локальных участников workspace.",
    teamNoWorkspace: "У аккаунта пока нет workspace — участников показать нельзя.",
    teamEmpty: "В этом workspace пока нет участников.",
    teamMemberStatus: "Статус",
    teamMemberRole: "Роль",
    teamProvisionTitle: "Добавить сотрудника",
    teamProvisionDescription:
      "Создаёт локального участника и одноразовую setup-ссылку. Новый человек сам задаёт пароль; администратор пароль за него не выбирает.",
    teamProvisionEmail: "Email участника",
    teamProvisionName: "Имя (необязательно)",
    teamProvisionRole: "Роль",
    teamProvisionSetupLinkHint:
      "Для нового локального аккаунта setup-ссылка появится один раз после добавления. Передайте её человеку по доверенному каналу: email автоматически не отправляется. Существующий аккаунт из другой компании должен принять отдельное приглашение — этот сценарий пока заблокирован.",
    teamProvisionSubmit: "Добавить в команду",
    teamProvisioning: "Добавление…",
    teamProvisionSuccess: "Локальный участник добавлен. Email invite не отправлялся.",
    teamProvisionExistingAccount:
      "Существующий локальный аккаунт добавлен без изменения его пароля.",
    teamProvisionSetupLinkGenerated:
      "Одноразовая setup-ссылка создана. Скопируйте её сейчас — raw token не хранится.",
    teamProvisionSetupLinkLabel: "Setup-ссылка",
    teamProvisionSetupLinkExpires: "Истекает",
    teamProvisionError: "Не удалось добавить участника.",
    teamProvisionForbidden:
      "Добавлять участников могут только owner/admin текущего workspace.",
    teamBoundary:
      "Boundary: local DB only — external_invite_sent=false, provider_write_performed=false.",
    roleOwner: "Владелец",
    roleAdmin: "Администратор",
    roleMember: "Участник",
    roleViewer: "Наблюдатель"
  },

  documents: {
    eyebrow: "Документы",
    title: "Внутренние документы",
    description:
      "Внутренние документы founderOS: заметки, планы и справочники создаются прямо в системе, попадают в Company Brain и доступны для поиска. Без provider calls, external writes и LLM.",
    badgeLocalOnly: "Локально",
    loading: "Загрузка документов",
    noWorkspaceDescription:
      "У этого аккаунта пока нет рабочего пространства — документы недоступны.",
    unavailableTitle: "Документы недоступны",
    unavailableDescription: "Не удалось загрузить документы рабочего пространства.",
    summaryLabel: "Сводка документов",
    totalTitle: "Всего",
    totalDescription: "Документы в текущей выборке.",
    publishedTitle: "Опубликовано",
    publishedDescription: "Документы со статусом published.",
    draftTitle: "Черновики",
    draftDescription: "Документы со статусом draft.",
    emptyTitle: "Документов пока нет",
    emptyDescription:
      "Создайте первый внутренний документ через форму ниже. Он появится в Company Brain.",
    emptyReadOnlyDescription:
      "Документов пока нет. Создать первый может участник, администратор или владелец компании.",
    readOnlyNotice:
      "У вас режим просмотра: документы можно читать и искать, а создавать, менять и удалять — только с ролью участника, администратора или владельца.",
    listLabel: "Список документов",
    statusLabel: "Статус",
    tagsLabel: "Теги",
    updatedLabel: "Обновлён",
    searchLabel: "Поиск по документам",
    searchPlaceholder: "Например: launch",
    searchSubmit: "Искать",
    searchClear: "Сбросить",
    openDocument: "Открыть",
    createTitle: "Новый документ",
    createDescription:
      "Документ сохраняется локально; body_markdown хранится как есть, а plain-text проекция используется для поиска и Company Brain.",
    fieldTitle: "Заголовок",
    fieldTitlePlaceholder: "Например: План запуска",
    fieldBody: "Текст (Markdown)",
    fieldBodyPlaceholder: "# Заголовок\n\nТело документа…",
    fieldTags: "Теги (через запятую)",
    fieldTagsPlaceholder: "launch, beta",
    fieldStatus: "Статус",
    statusDraft: "Черновик",
    statusPublished: "Опубликован",
    statusArchived: "Архив",
    createSubmit: "Создать документ",
    creating: "Создание…",
    createSuccess: "Документ создан.",
    titleRequired: "Укажите заголовок документа.",
    editDocument: "Редактировать",
    editTitle: "Редактирование документа",
    saveChanges: "Сохранить изменения",
    saving: "Сохранение…",
    updateSuccess: "Документ обновлён.",
    cancelEdit: "Отмена",
    deleteDocument: "Удалить",
    deleteConfirm: "Удалить этот документ? Это действие необратимо.",
    deleteConfirmYes: "Подтвердить удаление",
    deleting: "Удаление…",
    boundaryNote:
      "Документы local-only: provider_calls=false, external_writes=false, llm=false, секреты не читаются.",
    detailBackToList: "К списку документов",
    detailBodyLabel: "Содержимое",
    versionHistoryTitle: "История версий",
    versionHistoryEmpty: "Версии документа ещё не записаны.",
    viewVersion: "Показать snapshot",
    selectedVersionBadge: "выбрана",
    versionSnapshotTitle: "Snapshot версии",
    versionSnapshotBodyLabel: "Содержимое snapshot",
    versionCreatedLabel: "Записана",
    versionSnapshotBoundary:
      "Snapshot читается из локальной истории документа: без provider calls, external writes, secret reads или LLM.",
    versionLabel: (version: number) => `Версия ${version}`
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

  companyBrain: {
    eyebrow: "Мозг компании",
    title: "Состояние компании, подтверждённое источниками",
    badgeDeterministic: "Детерминированно",
    loading: "Загрузка Мозга компании",
    noWorkspaceDescription: "У этого аккаунта пока нет рабочего пространства — Мозга компании нет.",
    unavailableTitle: "Мозг компании недоступен",
    unavailableDescription: "Панель не смогла загрузить состояние Мозга компании.",
    emptyTitle: "Пока нет данных Мозга компании",
    emptyDescription:
      "Канонические записи ещё не синхронизированы или не импортированы. Запустите локальную синхронизацию/импорт и вернитесь сюда за состоянием, подтверждённым источниками.",
    intro:
      "Мозг компании основан на локальных канонических записях GitHub/Jira и сводном покрытии источников. Живое подключение, синхронизация внешних сервисов и сводка ИИ в этом виде не включены.",
    summaryLabel: "Сводка Мозга компании",
    reposTitle: "Репозитории",
    reposDescription: "Канонические репозитории GitHub, известные этому рабочему пространству.",
    openIssuesTitle: "Открытые задачи",
    openIssuesDescription: "Открытые GitHub/Jira задачи из канонических задач.",
    openPrsTitle: "Открытые пулреквесты",
    openPrsDescription: "Открытые пулреквесты, связанные с каноническими репозиториями.",
    closedTitle: "Закрытые / слитые",
    closedDescription: "Закрытые задачи и слитые пулреквесты.",
    openIssuesSection: "Открытые задачи",
    noOpenIssues: "Нет открытых задач в Мозге компании.",
    openPrsSection: "Открытые пулреквесты",
    noOpenPrs: "Нет открытых пулреквестов в Мозге компании.",
    recentSection: "Недавняя работа",
    noRecent: "Недавняя работа ещё не синхронизирована или не импортирована.",
    messagesSection: "Письма Gmail",
    noMessages: "Письма Gmail ещё не импортированы.",
    filesSection: "Файлы Drive",
    noFiles: "Файлы Drive ещё не импортированы.",
    reposSection: "Репозитории",
    noRepos: "Канонические репозитории ещё не синхронизированы.",
    evidenceSection: "Источники",
    noEvidence: "Для текущих записей источники не возвращены.",
    capabilityTitle: "Текущий режим возможностей",
    badgeIssue: "Задача",
    badgePr: "PR",
    badgeMessage: "Письмо",
    badgeUnread: "Не прочитано",
    badgeFile: "Файл",
    badgeSharedFile: "Общий файл",
    metaProvider: "Провайдер",
    metaRepository: "Репозиторий",
    metaScope: "Проект/репозиторий",
    metaFrom: "От",
    metaLabels: "Метки",
    metaMimeType: "Тип файла",
    metaOwner: "Владелец",
    metaState: "Состояние",
    metaReference: "Ссылка",
    unknownRepository: "Неизвестный репозиторий",
    noSourceRef: "Каноническая синхронизированная запись; отдельный источник не возвращён.",
    metaVisibility: "Видимость",
    repoBadge: "Репозиторий",
    archived: "Архивирован"
  },

  companyBrainEntities: {
    eyebrow: "Сущности",
    title: "Нормализованные сущности",
    badgeProjection: "Проекция только для чтения",
    loading: "Загрузка нормализованных сущностей",
    unavailableTitle: "Сущности недоступны",
    unavailableDescription: "Панель не смогла загрузить нормализованные сущности.",
    noWorkspaceDescription:
      "У этого аккаунта пока нет рабочего пространства — сущности недоступны.",
    emptyTitle: "Сущностей пока нет",
    emptyDescription:
      "Канонические записи ещё не синхронизированы или не импортированы. Когда Мозг компании получит данные, они появятся здесь как нормализованные сущности.",
    intro:
      "Проекция только для чтения поверх Мозга компании: репозитории, задачи, пулреквесты, письма, файлы Drive и внутренние документы в одном списке с подтверждающими источниками. Без вызовов внешних сервисов, синхронизации, внешних записей и языковой модели.",
    summaryLabel: "Сводка нормализованных сущностей",
    totalTitle: "Всего",
    totalDescription: "Сущности из текущей канонической проекции.",
    typesTitle: "Типы",
    typesDescription: "Количество типов сущностей в проекции.",
    providersTitle: "Провайдеры",
    providersDescription: "Количество источников данных в проекции.",
    evidenceTitle: "Подтверждающие источники",
    evidenceDescription: "Уникальные ссылки на источники, привязанные к сущностям.",
    listLabel: "Список нормализованных сущностей",
    filterTitle: "Фокус сущностей",
    filterLabel: "Фильтр нормализованных сущностей по типу",
    filterDescription:
      "Фильтр работает только по уже загруженному локальному списку и не вызывает внешние сервисы.",
    filterAll: "Все",
    noEntitiesForFilter: "Для выбранного типа сущностей ничего не найдено.",
    typeBreakdownTitle: "По типам",
    providerBreakdownTitle: "По источникам",
    noEvidence: "Для текущих сущностей подтверждающие ссылки не возвращены.",
    metaType: "Тип",
    metaProvider: "Источник",
    metaStatus: "Статус",
    metaReference: "Ссылка",
    metaUpdated: "Обновлено",
    boundaryNote:
      "Сущности вычисляются локально из уже сохранённых канонических записей. Панель не вызывает внешние сервисы, не запускает синхронизацию, не делает внешних записей и не использует языковую модель."
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
  briefingActionGenerateResult: (created: number, skipped: number) =>
    `Создано локальных действий: ${created} · пропущено: ${skipped}`,
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
  actionsReadinessNextStep: (
    pending: number,
    previewReady: number,
    missingEvidence: number,
    externalResult: number
  ) => {
    if (pending > 0) {
      return `Следующий шаг: локально разобрать proposed proposals (${pending}) через approve/reject; внешнее выполнение не запускать.`;
    }
    if (previewReady > 0) {
      return `Следующий шаг: открыть execution preview для одобренных GitHub proposals (${previewReady}) и проверить evidence до любого live-write approval.`;
    }
    if (missingEvidence > 0) {
      return `Следующий шаг: отклонить или пересоздать предложения без evidence (${missingEvidence}); unsupported claims не исполнять.`;
    }
    if (externalResult > 0) {
      return `Следующий шаг: проверить execution audit/receipt для предложений с reported execution (${externalResult}).`;
    }
    return "Следующий шаг: новых локальных действий не требуется; дождитесь новых briefing/audit signals или live-provider approval.";
  },
  // GitHub work count-card descriptions
  workIssuesDescription: (state: string) =>
    `${state}: записи задач GitHub из канонического пути бэкенда.`,
  workPullRequestsDescription: (state: string) =>
    `${state}: пулреквесты, связанные с репозиториями, где это возможно.`,
  githubWorkMetricComposition: (count: number, sampleSize: number) =>
    sampleSize === 0
      ? "Пустая выборка текущего фильтра."
      : `${count} из ${sampleSize} записей текущего фильтра.`,
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
  githubLoadedRepositorySample: (loaded: number, reported: number) => {
    if (reported > loaded) {
      return `На экране ${loaded} из ${reported} записей ответа; метрика не выдаёт часть выборки за полный список.`;
    }
    return `На экране все ${loaded} репозиториев из загруженного ответа.`;
  },
  githubSelectedRepositoryAction: (repository: string) =>
    `Будет прочитан только ${repository}; массовая загрузка не запускается.`,
  githubShowMoreRepositories: (count: number) =>
    `Показать остальные репозитории · ${count}`,
  githubAppLiveSyncResult: (repos: number, issues: number, prs: number, status: string) => {
    const statusLabel =
      status === "succeeded"
        ? "готово"
        : status === "failed"
          ? "ошибка"
          : status === "running"
            ? "выполняется"
            : status;
    return `Прочитано: репозиториев — ${repos}, задач — ${issues}, пулреквестов — ${prs}. Статус: ${statusLabel}.`;
  },
  githubRealReadNextStep: (
    appEnvConfigured: boolean,
    hasAppInstallationConnection: boolean,
    installationConnected: boolean,
    localRepositorySurfaceAvailable: boolean,
    ready: boolean
  ) => {
    if (!appEnvConfigured) {
      return "Следующий шаг: настроить server-side GitHub App env (app id, slug/setup url, private key) до real read.";
    }
    if (!hasAppInstallationConnection) {
      return "Следующий шаг: записать workspace-scoped GitHub App installation connection до real read.";
    }
    if (!installationConnected) {
      return "Следующий шаг: довести GitHub App installation connection до состояния connected.";
    }
    if (!localRepositorySurfaceAvailable) {
      return "Следующий шаг: загрузить минимум один локальный repo target перед scoped read sync.";
    }
    if (ready) {
      return "Readiness checks pass. Человек может запустить один explicit per-repository read-only sync.";
    }
    return "Следующий шаг: снять перечисленные блокеры перед real read run.";
  },
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
  sourceCoverageSourceRecordProvider: (provider: string, count: number) =>
    `${provider}: ${count}`,
  sourceCoverageSourceRecordType: (recordType: string, count: number) =>
    `${recordType}: ${count}`,
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
