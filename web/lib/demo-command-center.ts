import {
  DEMO_MISSIONS,
  DEMO_MISSION_SUMMARY,
  DEMO_RECEIPT,
  DEMO_SIGNAL
} from "./demo-tour";

export type DemoDetailKind =
  | "priority"
  | "sources"
  | "team"
  | "company"
  | "changes";

export type DemoMissionId = (typeof DEMO_MISSIONS)[number]["id"];

export type DemoOverlay =
  | null
  | { kind: "assistant" }
  | { detail: DemoDetailKind; kind: "detail" }
  | { kind: "mission"; missionId: DemoMissionId }
  | { kind: "decision" };

export type DemoAssistantAction = {
  label: string;
  overlay: Exclude<DemoOverlay, null | { kind: "assistant" }>;
};

export type DemoAssistantCitation = {
  label: string;
  source: "GitHub" | "Jira" | "Gmail" | "Drive" | "FounderOS";
};

export type DemoAssistantMessage = {
  action?: DemoAssistantAction;
  citations?: readonly DemoAssistantCitation[];
  id: string;
  role: "assistant" | "user";
  text: string;
};

export type DemoCommandCenterState = {
  assistantMessages: readonly DemoAssistantMessage[];
  confirmationChecked: boolean;
  decisionCompleted: boolean;
  overlay: DemoOverlay;
};

export type DemoCommandCenterAction =
  | { overlay: DemoOverlay; type: "open" }
  | { type: "close" }
  | { checked: boolean; type: "confirm" }
  | { type: "complete-decision" }
  | { query: string; type: "ask" }
  | { type: "reset" };

export const DEMO_ASSISTANT_STARTERS = [
  "Что главное сегодня?",
  "Почему Atlas первый?",
  "Кто отвечает?"
] as const;

const INITIAL_ASSISTANT_MESSAGE: DemoAssistantMessage = {
  id: "assistant-0",
  role: "assistant",
  text: "Я вижу текущий штаб NovaFlow. Спросите о приоритете, заказчике, владельцах или основаниях — отвечу коротко и покажу, куда провалиться дальше."
};

export const INITIAL_DEMO_COMMAND_CENTER_STATE: DemoCommandCenterState = {
  assistantMessages: [INITIAL_ASSISTANT_MESSAGE],
  confirmationChecked: false,
  decisionCompleted: false,
  overlay: null
};

export function getDemoCommandCenterSnapshot(decisionCompleted: boolean) {
  const queue = decisionCompleted ? DEMO_MISSIONS.slice(1) : DEMO_MISSIONS;

  return {
    activeMission: queue[0],
    approved: DEMO_MISSION_SUMMARY.approved,
    completed: DEMO_MISSION_SUMMARY.completed + (decisionCompleted ? 1 : 0),
    criticalRisks: decisionCompleted ? 0 : 1,
    nextMissions: queue.slice(1, 3),
    queue,
    waiting: decisionCompleted
      ? DEMO_MISSION_SUMMARY.waitingAfter
      : DEMO_MISSION_SUMMARY.waiting
  } as const;
}

export function resolveDemoAssistant(
  query: string,
  decisionCompleted: boolean
): Omit<DemoAssistantMessage, "id" | "role"> {
  const normalized = query.trim().toLocaleLowerCase("ru-RU");

  if (includesAny(normalized, ["кто", "отвеч", "владел", "команд"])) {
    return {
      action: {
        label: "Открыть команду миссии",
        overlay: { detail: "team", kind: "detail" }
      },
      citations: [
        { label: "Команда миссии", source: "FounderOS" },
        { label: "План запуска", source: "Drive" }
      ],
      text: decisionCompleted
        ? "За новый приоритет отвечает Мила Орлова. По завершённому Atlas SSO владельцами результата были Тимур, Данияр и София."
        : "Тимур отвечает за проверку безопасности, София — за план отката, Данияр — за статус для Atlas Retail. Система показывает ответственность, но не назначает людей сама."
    };
  }

  if (includesAny(normalized, ["заказчик", "клиент", "елена", "профил"])) {
    return {
      action: {
        label: "Открыть профиль Atlas Retail",
        overlay: { detail: "company", kind: "detail" }
      },
      citations: [
        { label: "21 касание", source: "Gmail" },
        { label: "План запуска", source: "Drive" }
      ],
      text: "Atlas Retail — стратегический заказчик. Ключевое лицо — Елена Миронова; она подтвердила запуск 22 июля. В профиле собраны четыре контакта и история обещаний."
    };
  }

  if (includesAny(normalized, ["источник", "радар", "синхрон", "данн"])) {
    return {
      action: {
        label: "Проверить источники",
        overlay: { detail: "sources", kind: "detail" }
      },
      citations: [
        { label: "Изменение кода #642", source: "GitHub" },
        { label: "SEC-218", source: "Jira" },
        { label: "Срок клиента", source: "Gmail" },
        { label: "План запуска", source: "Drive" }
      ],
      text: "Все четыре источника доступны в синтетическом снимке. Вместе они дают 858 согласованных записей и подтверждают один общий риск, а не четыре разрозненных уведомления."
    };
  }

  if (includesAny(normalized, ["решен", "действ", "сделать", "подтверд"])) {
    if (decisionCompleted) {
      return {
        action: {
          label: "Открыть квитанцию",
          overlay: { kind: "decision" }
        },
        citations: [{ label: DEMO_RECEIPT.receiptId, source: "FounderOS" }],
        text: "Решение уже завершено в симуляции: очередь пересчитана с 3 до 2, Atlas SSO перешёл под контроль, внешних записей не было."
      };
    }
    return {
      action: {
        label: "Подготовить решение",
        overlay: { kind: "decision" }
      },
      citations: [
        { label: "19 оснований", source: "FounderOS" },
        { label: "SEC-218", source: "Jira" }
      ],
      text: "Нужно согласовать проверку безопасности, назначить Софию ответственной за откат и подтвердить клиентский статус через Данияра. Перед фиксацией вы увидите точный предпросмотр."
    };
  }

  if (includesAny(normalized, ["почему", "atlas", "основан", "доказ", "риск"])) {
    return {
      action: {
        label: decisionCompleted ? "Посмотреть результат" : "Показать ключевые основания",
        overlay: { detail: "priority", kind: "detail" }
      },
      citations: [
        { label: "Изменение кода #642", source: "GitHub" },
        { label: "SEC-218", source: "Jira" },
        { label: "Запуск 22 июля", source: "Gmail" },
        { label: "Нет владельца отката", source: "Drive" }
      ],
      text: decisionCompleted
        ? "Atlas больше не первый: решение зафиксировано, поэтому штаб поднял следующий пробел — повторная отправка уведомлений без владельца."
        : "Atlas первый, потому что неизменный срок клиента совпал с задержкой проверки безопасности, заблокированным изменением кода и отсутствующим владельцем отката. Возможный ущерб — 5–8 рабочих дней."
    };
  }

  if (includesAny(normalized, ["главн", "важн", "сегодня", "приоритет"])) {
    const snapshot = getDemoCommandCenterSnapshot(decisionCompleted);
    return {
      action: {
        label: decisionCompleted ? "Открыть новый приоритет" : "Разобрать приоритет",
        overlay: { detail: "priority", kind: "detail" }
      },
      citations: [{ label: `${snapshot.activeMission.evidenceRefs} оснований`, source: "FounderOS" }],
      text: decisionCompleted
        ? "Сейчас главное — назначить владельца повторной отправки уведомлений. Atlas SSO уже на контроле, поэтому штаб честно переключил фокус."
        : `Сейчас главное — ${DEMO_SIGNAL.title}. Решение нужно до 12:00; его подтверждают четыре источника и 19 ссылок на факты.`
    };
  }

  return {
    citations: [{ label: "Снимок NovaFlow", source: "FounderOS" }],
    text: "Я могу коротко объяснить главный приоритет, показать заказчика, владельцев, источники или подготовить решение. В этой демонстрации ответы локальные и основаны только на вымышленных данных NovaFlow."
  };
}

export function demoCommandCenterReducer(
  state: DemoCommandCenterState,
  action: DemoCommandCenterAction
): DemoCommandCenterState {
  switch (action.type) {
    case "open":
      return { ...state, overlay: action.overlay };
    case "close":
      return { ...state, confirmationChecked: false, overlay: null };
    case "confirm":
      if (state.decisionCompleted) {
        return state;
      }
      return { ...state, confirmationChecked: action.checked };
    case "complete-decision":
      if (
        state.decisionCompleted ||
        !state.confirmationChecked ||
        state.overlay?.kind !== "decision"
      ) {
        return state;
      }
      return {
        ...state,
        confirmationChecked: false,
        decisionCompleted: true
      };
    case "ask": {
      const query = action.query.trim();
      if (!query) {
        return state;
      }
      const index = state.assistantMessages.length;
      const reply = resolveDemoAssistant(query, state.decisionCompleted);
      return {
        ...state,
        assistantMessages: [
          ...state.assistantMessages,
          { id: `user-${index}`, role: "user", text: query },
          { ...reply, id: `assistant-${index + 1}`, role: "assistant" }
        ]
      };
    }
    case "reset":
      return {
        ...INITIAL_DEMO_COMMAND_CENTER_STATE,
        assistantMessages: [...INITIAL_DEMO_COMMAND_CENTER_STATE.assistantMessages]
      };
    default:
      return state;
  }
}

function includesAny(value: string, fragments: readonly string[]): boolean {
  return fragments.some((fragment) => value.includes(fragment));
}
