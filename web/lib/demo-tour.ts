export type DemoSourceKey = "github" | "jira" | "gmail" | "drive";

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

export const DEMO_SNAPSHOT_LABEL = "16 июля 2026 · 10:30";
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
    impact: "Запуск Atlas Retail может сдвинуться на 5–8 рабочих дней.",
    nextStep: "Согласовать проверку безопасности, закрепить владельца отката и подтвердить статус заказчику.",
    owner: "Тимур · Данияр · София",
    sourceCount: 4,
    sourceKeys: ["github", "jira", "gmail", "drive"],
    status: "Ждёт решения",
    summary: "Клиентский срок, блокировка кода и незакрытые операционные роли сошлись в одной точке.",
    title: DEMO_SIGNAL.title,
    urgency: "Критично · до 12:00"
  },
  {
    evidenceRefs: 7,
    id: "DEMO-MISSION-041",
    impact: "Повторные уведомления могут создавать дубли и увеличивать нагрузку поддержки.",
    nextStep: "Назначить одного владельца повторной отправки и зафиксировать критерий успешной доставки.",
    owner: "Мила Орлова",
    sourceCount: 2,
    sourceKeys: ["github", "jira"],
    status: "Ждёт решения",
    summary: "Код повторной отправки уже менялся, но ответственность за итоговый сценарий не закреплена.",
    title: "Назначить владельца повторной отправки уведомлений",
    urgency: "Сегодня"
  },
  {
    evidenceRefs: 6,
    id: "DEMO-MISSION-040",
    impact: "Команда закупок Volna Bank не сможет завершить проверку поставщика сегодня.",
    nextStep: "Подтвердить владельца ответа и отправить согласованный пакет безопасности до 16:00.",
    owner: "Арсен Ким",
    sourceCount: 2,
    sourceKeys: ["gmail", "drive"],
    status: "Ждёт решения",
    summary: "Запрос заказчика подтверждён перепиской, а актуальный пакет уже собран в документах.",
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
