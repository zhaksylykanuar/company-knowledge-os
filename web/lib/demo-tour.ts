export type DemoPhase = "Увидеть" | "Понять" | "Решить" | "Изменить";

export type DemoSourceKey = "github" | "jira" | "gmail" | "drive";

export type DemoSceneId =
  | "scene-01"
  | "scene-02"
  | "scene-03"
  | "scene-04"
  | "scene-05"
  | "scene-06"
  | "scene-07"
  | "scene-08"
  | "scene-09"
  | "scene-10"
  | "scene-11"
  | "scene-12";

export type DemoScene = {
  benefit: string;
  id: DemoSceneId;
  kicker: string;
  navLabel: string;
  next: string;
  phase: DemoPhase;
  sources: readonly DemoSourceKey[];
  stopAutoplay?: boolean;
  summary: string;
  title: string;
};

export type DemoSource = {
  accent: string;
  freshness: string;
  key: DemoSourceKey;
  label: string;
  primaryMetric: string;
  primaryMetricLabel: string;
  records: number;
  secondaryMetrics: readonly { label: string; value: string }[];
  signal: string;
};

export const DEMO_SNAPSHOT_LABEL = "15 июля 2026 · 10:30";
export const DEMO_TRUTH_LABEL =
  "ДЕМО · все данные вымышлены · внешних действий нет";

export const DEMO_COMPANY = {
  name: "NovaFlow",
  stage: "B2B-сервис для компаний · стадия роста",
  mission: "Помогать операционным командам запускать изменения без потери контекста.",
  readiness: 100,
  records: 858,
  sourcesConnected: 4,
  sourcesTotal: 4,
  teamSize: 6,
  relationships: 3,
  touchpoints: 37
} as const;

export const DEMO_SOURCES: readonly DemoSource[] = [
  {
    accent: "#9cff57",
    freshness: "4 мин назад",
    key: "github",
    label: "GitHub",
    primaryMetric: "6",
    primaryMetricLabel: "репозиториев",
    records: 312,
    secondaryMetrics: [
      { label: "Открытые задачи", value: "23" },
      { label: "Запросы на слияние", value: "4" },
      { label: "Заблокировано", value: "2" }
    ],
    signal: "SSO (единый вход): изменение кода #642 блокирует выпуск"
  },
  {
    accent: "#7b8cff",
    freshness: "8 мин назад",
    key: "jira",
    label: "Jira",
    primaryMetric: "48",
    primaryMetricLabel: "активных задач",
    records: 186,
    secondaryMetrics: [
      { label: "Заблокировано", value: "7" },
      { label: "На этой неделе", value: "12" },
      { label: "Без владельца", value: "3" }
    ],
    signal: "SEC-218 ждёт проверки безопасности уже 2 дня"
  },
  {
    accent: "#ff9c66",
    freshness: "2 мин назад",
    key: "gmail",
    label: "Gmail",
    primaryMetric: "9",
    primaryMetricLabel: "клиентских веток",
    records: 146,
    secondaryMetrics: [
      { label: "Ждут ответа", value: "3" },
      { label: "Ключевые лица", value: "8" },
      { label: "Сегодня", value: "17" }
    ],
    signal: "Atlas подтвердил неизменный срок запуска"
  },
  {
    accent: "#ffd75f",
    freshness: "13 мин назад",
    key: "drive",
    label: "Drive",
    primaryMetric: "214",
    primaryMetricLabel: "документов",
    records: 214,
    secondaryMetrics: [
      { label: "Обновлено за неделю", value: "11" },
      { label: "Доступно клиентам", value: "6" },
      { label: "Нужен владелец", value: "1" }
    ],
    signal: "План запуска всё ещё без ответственного"
  }
] as const;

export const DEMO_TEAM = [
  {
    initials: "АС",
    name: "Алина Садыкова",
    role: "Основатель / генеральный директор",
    focus: "Решения и клиентский результат",
    status: "В штабе"
  },
  {
    initials: "ТВ",
    name: "Тимур Волков",
    role: "Технический директор",
    focus: "Архитектура и проверка безопасности",
    status: "В миссии"
  },
  {
    initials: "МО",
    name: "Мила Орлова",
    role: "Руководитель продукта",
    focus: "Объём запуска и приоритеты",
    status: "В штабе"
  },
  {
    initials: "ДИ",
    name: "Данияр Иманов",
    role: "Работа с заказчиками",
    focus: "Atlas Retail и коммуникация",
    status: "В миссии"
  },
  {
    initials: "СЛ",
    name: "София Лебедева",
    role: "Серверный разработчик",
    focus: "Реализация SSO",
    status: "В миссии"
  },
  {
    initials: "АК",
    name: "Арсен Ким",
    role: "Руководитель продаж",
    focus: "Volna Bank и воронка продаж",
    status: "В штабе"
  }
] as const;

export const DEMO_RELATIONSHIPS = [
  {
    contacts: 4,
    kind: "Заказчик",
    name: "Atlas Retail",
    risk: "Запуск SSO под риском",
    tone: "critical",
    touchpoints: 21
  },
  {
    contacts: 2,
    kind: "Потенциальный заказчик",
    name: "Volna Bank",
    risk: "Ожидает ответ по безопасности",
    tone: "watch",
    touchpoints: 9
  },
  {
    contacts: 2,
    kind: "Партнёр",
    name: "Kinetic Legal",
    risk: "Контур стабилен",
    tone: "stable",
    touchpoints: 7
  }
] as const;

export const DEMO_ATLAS_PROFILE = {
  company: {
    accountOwner: "Данияр Иманов",
    contacts: 4,
    lastTouch: "2 часа назад",
    name: "Atlas Retail",
    status: "Стратегический заказчик",
    touchpoints: 21
  },
  people: [
    {
      decisionRole: "Принимает решение",
      initials: "ЕМ",
      name: "Елена Миронова",
      role: "Директор по цифровым продуктам",
      touchpoints: 11
    },
    {
      decisionRole: "Технический представитель",
      initials: "АТ",
      name: "Артём Титов",
      role: "Руководитель платформы",
      touchpoints: 6
    },
    {
      decisionRole: "Согласует закупку",
      initials: "ПР",
      name: "Полина Романова",
      role: "Руководитель закупок",
      touchpoints: 2
    },
    {
      decisionRole: "Отвечает за запуск",
      initials: "ОВ",
      name: "Олег Власов",
      role: "Руководитель ИТ-операций",
      touchpoints: 2
    }
  ],
  timeline: [
    { source: "Gmail", text: "Елена подтвердила запуск 22 июля", time: "сегодня · 08:42" },
    { source: "Drive", text: "Открыт план запуска Atlas SSO", time: "вчера · 17:10" },
    { source: "Gmail", text: "Артём запросил итог проверки безопасности", time: "вчера · 15:24" },
    { source: "Drive", text: "Обновлён план приёмки SSO", time: "14 июля · 11:05" }
  ]
} as const;

export const DEMO_SIGNAL = {
  confidence: 96,
  impact: "Риск срыва запуска на 5–8 рабочих дней",
  owner: "Тимур Волков",
  title: "Защитить запуск SSO для Atlas Retail",
  events: [
    {
      detail: "Изменение кода #642 нельзя объединить без проверки безопасности.",
      source: "GitHub",
      time: "09:06",
      title: "Технический блокер"
    },
    {
      detail: "SEC-218 заблокирована уже 2 дня.",
      source: "Jira",
      time: "09:11",
      title: "Задержка проверки"
    },
    {
      detail: "Клиент подтвердил, что дата 22 июля не переносится.",
      source: "Gmail",
      time: "09:18",
      title: "Срок зафиксирован"
    },
    {
      detail: "В плане запуска не указан ответственный за откат.",
      source: "Drive",
      time: "09:24",
      title: "Операционный пробел"
    }
  ]
} as const;

export const DEMO_DOCUMENTS = [
  {
    evidence: 4,
    name: "Atlas SSO · План запуска",
    owner: "Нужен владелец",
    status: "Требует решения",
    updated: "13 мин назад"
  },
  {
    evidence: 7,
    name: "Проверка безопасности · SEC-218",
    owner: "Тимур Волков",
    status: "На проверке",
    updated: "26 мин назад"
  },
  {
    evidence: 5,
    name: "Atlas · План приёмки",
    owner: "Мила Орлова",
    status: "Согласован",
    updated: "вчера"
  },
  {
    evidence: 3,
    name: "План сообщения заказчику",
    owner: "Данияр Иманов",
    status: "Актуален",
    updated: "2 часа назад"
  }
] as const;

export const DEMO_BRIEFING = [
  {
    evidence: 4,
    label: "Сделать сегодня",
    sources: "GitHub · Jira · Gmail · Drive",
    title: "Снять блокеры запуска Atlas SSO",
    tone: "critical"
  },
  {
    evidence: 2,
    label: "Проверить",
    sources: "GitHub · Jira",
    title: "Назначить владельца повторной отправки уведомлений",
    tone: "watch"
  },
  {
    evidence: 2,
    label: "Ответить",
    sources: "Gmail · Drive",
    title: "Вернуть пакет безопасности Volna Bank",
    tone: "normal"
  }
] as const;

export const DEMO_MISSION_SUMMARY = {
  approved: 2,
  completed: 7,
  loaded: 12,
  waiting: 3,
  waitingAfter: 2
} as const;

export const DEMO_MISSIONS = [
  {
    evidenceRefs: 19,
    id: "DEMO-MISSION-042",
    owner: "Тимур · Данияр · София",
    sourceCount: 4,
    status: "Ждёт решения",
    title: DEMO_SIGNAL.title,
    urgency: "Критично · до 12:00"
  },
  {
    evidenceRefs: 7,
    id: "DEMO-MISSION-041",
    owner: "Мила Орлова",
    sourceCount: 2,
    status: "Ждёт решения",
    title: "Назначить владельца повторной отправки уведомлений",
    urgency: "Сегодня"
  },
  {
    evidenceRefs: 6,
    id: "DEMO-MISSION-040",
    owner: "Арсен Ким",
    sourceCount: 2,
    status: "Ждёт решения",
    title: "Ответить Volna Bank по безопасности",
    urgency: "До 16:00"
  }
] as const;

export const DEMO_PREVIEW = {
  assignee: "@demo-sofia",
  body: "Получить согласование безопасности, назначить ответственного за откат и закрыть чек-лист запуска.",
  labels: ["priority:critical", "customer:atlas", "demo"],
  repository: "demo-novaflow/platform",
  title: "Снять блокеры запуска Atlas SSO"
} as const;

export const DEMO_RECEIPT = {
  action: "create_github_issue",
  externalResult: "SIM-GH-642",
  externalWrite: false,
  provider: "github-demo",
  receiptId: "DEMO-RCP-0042",
  status: "симуляция",
  summary:
    "Выполнено в симуляции. GitHub и другие внешние системы не изменялись."
} as const;

export const DEMO_SCENES: readonly DemoScene[] = [
  {
    benefit: "Сразу видно, готова ли система приносить пользу, а не просто какие настройки заполнены.",
    id: "scene-01",
    kicker: "Система готова",
    navLabel: "Онбординг завершён",
    next: "Посмотреть, из чего складывается живая картина компании.",
    phase: "Увидеть",
    sources: ["github", "jira", "gmail", "drive"],
    summary: "Компания, команда и четыре источника уже образуют единый рабочий контур.",
    title: "NovaFlow подключена за один понятный проход"
  },
  {
    benefit: "Источники объясняют своё покрытие, свежесть и пробелы без технической диагностики.",
    id: "scene-02",
    kicker: "Радары",
    navLabel: "Все источники",
    next: "Открыть конкретный сигнал, который заметили несколько радаров.",
    phase: "Увидеть",
    sources: ["github", "jira", "gmail", "drive"],
    summary: "858 записей из разработки, задач, коммуникаций и документов уже согласованы во времени.",
    title: "FounderOS видит работу компании целиком"
  },
  {
    benefit: "Связанный сигнал сильнее одиночного уведомления: он показывает причину, срок и ущерб.",
    id: "scene-03",
    kicker: "Связанный сигнал",
    navLabel: "Сигнал из 4 источников",
    next: "Поднять сигнал в главный штаб и назначить владельца результата.",
    phase: "Увидеть",
    sources: ["github", "jira", "gmail", "drive"],
    summary: "Четыре независимых факта складываются в один риск запуска Atlas Retail.",
    title: "Проблема стала видна до того, как её озвучил клиент"
  },
  {
    benefit: "Основатель получает один следующий ход вместо стены метрик и разрозненных уведомлений.",
    id: "scene-04",
    kicker: "Живой штаб",
    navLabel: "Главный экран",
    next: "Понять, какие люди и компании связаны с риском.",
    phase: "Понять",
    sources: ["github", "jira", "gmail", "drive"],
    summary: "Штаб ставит Atlas SSO выше остальных сигналов и объясняет выбор четырьмя основаниями.",
    title: "Сегодня у компании один главный приоритет"
  },
  {
    benefit: "Контекст сохраняется вокруг реальных владельцев, заказчиков и ключевых лиц.",
    id: "scene-05",
    kicker: "Мир компании",
    navLabel: "Карта отношений",
    next: "Открыть Atlas Retail и человека, который принимает решение.",
    phase: "Понять",
    sources: ["gmail", "drive"],
    summary: "37 касаний распределены между заказчиком, потенциальным клиентом и партнёром.",
    title: "Работа показана как сеть людей, а не набор таблиц"
  },
  {
    benefit: "Перед действием видно, кто принимает решение, кто владеет отношением и что уже обещано.",
    id: "scene-06",
    kicker: "Профиль заказчика",
    navLabel: "Atlas Retail",
    next: "Сверить внутренних владельцев результата.",
    phase: "Понять",
    sources: ["gmail", "drive"],
    summary: "Профиль объединяет четыре контакта, 21 касание и историю обещаний по запуску.",
    title: "Елена Миронова — ключевое лицо этой миссии"
  },
  {
    benefit: "Ответственность становится явной: у каждого риска есть внутренние владельцы и зона вклада.",
    id: "scene-07",
    kicker: "Команда",
    navLabel: "Люди и роли",
    next: "Собрать рабочие документы и основания в один пакет.",
    phase: "Понять",
    sources: [],
    summary: "Тимур, Данияр и София связаны с миссией по ролям, а не назначены системой автоматически.",
    title: "Команда понимает, кто отвечает за результат"
  },
  {
    benefit: "Решение опирается на актуальный пакет знаний, а пробелы видны до выполнения.",
    id: "scene-08",
    kicker: "Знания",
    navLabel: "Документы и основания",
    next: "Получить короткую сводку основателя.",
    phase: "Понять",
    sources: ["drive", "github", "jira", "gmail"],
    summary: "План запуска, проверка безопасности, план приёмки и сообщение заказчику связаны с одной миссией.",
    title: "Все основания решения собраны рядом"
  },
  {
    benefit: "Сводка превращает накопленный контекст в три проверяемых хода на сегодня.",
    id: "scene-09",
    kicker: "Сводка основателя",
    navLabel: "Что делать сегодня",
    next: "Открыть очередь и выбрать решение.",
    phase: "Решить",
    sources: ["github", "jira", "gmail", "drive"],
    summary: "Каждый приоритет содержит владельца, срок и ссылки на основания.",
    title: "Не новости компании, а решения на сегодня"
  },
  {
    benefit: "Очередь сохраняет фокус: одна активная миссия и понятный порядок следующих.",
    id: "scene-10",
    kicker: "Миссии",
    navLabel: "Очередь решений",
    next: "Проверить ущерб и основания главной миссии.",
    phase: "Решить",
    sources: ["github", "jira", "gmail", "drive"],
    summary: "Из 12 миссий только три требуют решения сейчас; остальные уже приняты или завершены.",
    title: "Основатель решает только то, что действительно требует человека"
  },
  {
    benefit: "Предпросмотр отделён от решения и показывает точный будущий эффект до подтверждения.",
    id: "scene-11",
    kicker: "Комната решений",
    navLabel: "Решение и предпросмотр",
    next: "Симулировать подтверждение и увидеть безопасную квитанцию.",
    phase: "Решить",
    sources: ["github", "jira", "gmail", "drive"],
    stopAutoplay: true,
    summary: "Почему сейчас, ущерб, владельцы и четыре основания остаются на одном экране.",
    title: "Сначала решение человека — затем отдельный внешний шаг"
  },
  {
    benefit: "Цикл замыкается: результат возвращается в картину компании и меняет следующий приоритет.",
    id: "scene-12",
    kicker: "Результат",
    navLabel: "Квитанция и новый штаб",
    next: "Перезапустить тур или исследовать любую сцену в свободном порядке.",
    phase: "Изменить",
    sources: ["github"],
    stopAutoplay: true,
    summary: "В демо очередь меняется с 3 до 2, а Atlas SSO переходит в состояние «На контроле».",
    title: "Каждое действие заканчивается видимым результатом"
  }
] as const;

export function demoSourceRecordTotal(
  sources: readonly Pick<DemoSource, "records">[] = DEMO_SOURCES
): number {
  return sources.reduce((total, source) => total + source.records, 0);
}

export function demoTouchpointTotal(
  relationships: readonly { touchpoints: number }[] = DEMO_RELATIONSHIPS
): number {
  return relationships.reduce((total, relationship) => total + relationship.touchpoints, 0);
}

export function sceneIndexFromHash(hash: string): number {
  const normalized = hash.replace(/^#/, "");
  const index = DEMO_SCENES.findIndex((scene) => scene.id === normalized);
  return index >= 0 ? index : 0;
}
