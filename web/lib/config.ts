import type { OperatorConfig } from "./types";

export const OPERATOR_CONFIG_STORAGE_KEY = "founderos.operatorConfig.v1";

export const DEFAULT_OPERATOR_CONFIG: OperatorConfig = {
  apiBaseUrl: "",
  apiKey: "",
  ownerEmail: "",
  workspaceId: ""
};

export function getConfiguredApiBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
    "http://localhost:8000"
  );
}

export function readOperatorConfig(): OperatorConfig {
  if (typeof window === "undefined") {
    return DEFAULT_OPERATOR_CONFIG;
  }

  const raw = window.localStorage.getItem(OPERATOR_CONFIG_STORAGE_KEY);
  if (!raw) {
    return DEFAULT_OPERATOR_CONFIG;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<OperatorConfig>;
    return {
      apiBaseUrl: parsed.apiBaseUrl ?? "",
      apiKey: parsed.apiKey ?? "",
      ownerEmail: parsed.ownerEmail ?? "",
      workspaceId: parsed.workspaceId ?? ""
    };
  } catch {
    return DEFAULT_OPERATOR_CONFIG;
  }
}

export function writeOperatorConfig(config: OperatorConfig): void {
  window.localStorage.setItem(OPERATOR_CONFIG_STORAGE_KEY, JSON.stringify(config));
}

export function clearOperatorConfig(): void {
  window.localStorage.removeItem(OPERATOR_CONFIG_STORAGE_KEY);
}

export function resolveApiBaseUrl(config?: OperatorConfig): string {
  const localBaseUrl = config?.apiBaseUrl.trim();
  return localBaseUrl || getConfiguredApiBaseUrl();
}
