import {
  fetchCompanyBrain,
  fetchCompanyMap,
  fetchWorkspaceConnectors,
  fetchWorkspaceMembers
} from "./api";
import type {
  CompanyMapResponse,
  CompanyBrainResponse,
  ConnectorRegistryResponse,
  WorkspaceMembersResponse
} from "./types";

export type OnboardingCheckState = "complete" | "pending" | "unknown";
export const ONBOARDING_STEP_IDS = [
  "welcome",
  "company",
  "source",
  "map",
  "team",
  "ready"
] as const;

export function onboardingStepFromHash(hash: string): number {
  const stepId = hash.replace(/^#/, "");
  const stepIndex = ONBOARDING_STEP_IDS.findIndex((candidate) => candidate === stepId);
  return stepIndex >= 0 ? stepIndex : 0;
}

export type OnboardingDataSource =
  | "company-brain"
  | "company-map"
  | "connectors"
  | "members";

export type OnboardingSnapshot = {
  workspaceId: string;
  connectors: ConnectorRegistryResponse | null;
  companyBrain: CompanyBrainResponse | null;
  companyMap: CompanyMapResponse | null;
  members: WorkspaceMembersResponse | null;
  unavailable: OnboardingDataSource[];
};

export type OnboardingCheck = {
  id: "company" | "source" | "map" | "team" | "ready";
  state: OnboardingCheckState;
  evidence: string;
};

export type OnboardingProgress = {
  checks: Record<OnboardingCheck["id"], OnboardingCheck>;
  completedCount: number;
  totalCount: 4;
  ready: boolean;
  unavailable: OnboardingDataSource[];
};

export function firstIncompleteRequiredStep(
  progress: OnboardingProgress
): 2 | 3 | null {
  if (progress.checks.source.state !== "complete") {
    return 2;
  }
  if (progress.checks.map.state !== "complete") {
    return 3;
  }
  return null;
}

export async function loadOnboardingSnapshot(
  workspaceId: string
): Promise<OnboardingSnapshot> {
  const [connectorsResult, companyBrainResult, companyMapResult, membersResult] =
    await Promise.allSettled([
      fetchWorkspaceConnectors(workspaceId),
      fetchCompanyBrain(workspaceId),
      fetchCompanyMap(workspaceId),
      fetchWorkspaceMembers(workspaceId)
    ]);

  const unavailable: OnboardingDataSource[] = [];
  if (connectorsResult.status === "rejected") {
    unavailable.push("connectors");
  }
  if (companyBrainResult.status === "rejected") {
    unavailable.push("company-brain");
  }
  if (companyMapResult.status === "rejected") {
    unavailable.push("company-map");
  }
  if (membersResult.status === "rejected") {
    unavailable.push("members");
  }

  return {
    workspaceId,
    connectors:
      connectorsResult.status === "fulfilled" ? connectorsResult.value : null,
    companyBrain:
      companyBrainResult.status === "fulfilled" ? companyBrainResult.value : null,
    companyMap:
      companyMapResult.status === "fulfilled" ? companyMapResult.value : null,
    members: membersResult.status === "fulfilled" ? membersResult.value : null,
    unavailable
  };
}

function sourceCheck(snapshot: OnboardingSnapshot): OnboardingCheck {
  const connectedCount = snapshot.connectors?.summary.connected ?? 0;
  const sourceRecordCount = snapshot.companyBrain?.source_records?.total ?? 0;

  if (sourceRecordCount > 0) {
    const parts: string[] = [];
    parts.push(`загружено записей: ${sourceRecordCount}`);
    if (connectedCount > 0) {
      parts.push(`подключено источников: ${connectedCount}`);
    }
    return { id: "source", state: "complete", evidence: parts.join(" · ") };
  }

  if (snapshot.companyBrain !== null) {
    return {
      id: "source",
      state: "pending",
      evidence:
        connectedCount > 0
          ? `источников настроено: ${connectedCount}, но загруженных записей пока нет`
          : snapshot.connectors === null
            ? "Загруженных записей пока нет; состояние подключения не удалось проверить"
            : "Подключённых источников и загруженных записей пока нет"
    };
  }

  return {
    id: "source",
    state: "unknown",
    evidence: "Не удалось проверить все источники — готовность не подтверждена"
  };
}

function mapCheck(snapshot: OnboardingSnapshot): OnboardingCheck {
  if (snapshot.companyMap === null) {
    return {
      id: "map",
      state: "unknown",
      evidence: "Карта компании сейчас недоступна — готовность не подтверждена"
    };
  }

  const summary = snapshot.companyMap.summary;
  const mappedPeople = summary.internal_people + summary.confirmed_external_people;
  const mappedOrganizations = summary.confirmed_organizations;
  if (mappedPeople > 0 || mappedOrganizations > 0 || summary.touchpoints_in_window > 0) {
    return {
      id: "map",
      state: "complete",
      evidence: `людей: ${mappedPeople} · компаний: ${mappedOrganizations} · контактов: ${summary.touchpoints_in_window}`
    };
  }

  return {
    id: "map",
    state: "pending",
    evidence: "В карте пока нет людей, компаний или подтверждённых контактов"
  };
}

function teamCheck(snapshot: OnboardingSnapshot): OnboardingCheck {
  if (snapshot.members === null) {
    return {
      id: "team",
      state: "unknown",
      evidence: "Состав команды сейчас недоступен — приглашения не подтверждены"
    };
  }

  const memberCount = snapshot.members.members.length;
  return memberCount > 1
    ? {
        id: "team",
        state: "complete",
        evidence: `участников в рабочем пространстве: ${memberCount}`
      }
    : {
        id: "team",
        state: "pending",
        evidence: "Пока вы единственный участник — команду можно добавить позже"
      };
}

function readyState(
  company: OnboardingCheck,
  source: OnboardingCheck,
  map: OnboardingCheck
): OnboardingCheckState {
  const required = [company.state, source.state, map.state];
  if (required.every((state) => state === "complete")) {
    return "complete";
  }
  if (required.some((state) => state === "unknown")) {
    return "unknown";
  }
  return "pending";
}

export function deriveOnboardingProgress(
  snapshot: OnboardingSnapshot
): OnboardingProgress {
  const company: OnboardingCheck = {
    id: "company",
    state: "complete",
    evidence: "Рабочее пространство создано и доступно в текущей сессии"
  };
  const source = sourceCheck(snapshot);
  const map = mapCheck(snapshot);
  const team = teamCheck(snapshot);
  const readiness = readyState(company, source, map);
  const ready: OnboardingCheck = {
    id: "ready",
    state: readiness,
    evidence:
      readiness === "complete"
        ? "Компания, источник и карта подтверждены реальными данными"
        : readiness === "unknown"
          ? "Часть данных недоступна — FounderOS не будет считать настройку завершённой"
          : "Подключите источник и наполните карту, чтобы система начала видеть контекст"
  };
  const setupChecks = [company, source, map, team];

  return {
    checks: { company, source, map, team, ready },
    completedCount: setupChecks.filter((check) => check.state === "complete").length,
    totalCount: 4,
    ready: readiness === "complete",
    unavailable: snapshot.unavailable
  };
}
