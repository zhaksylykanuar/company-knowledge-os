import {
  getConfiguredApiBaseUrl,
  readOperatorConfig,
  resolveApiBaseUrl
} from "./config";
import type { ApiErrorPayload, ApiFetchOptions } from "./types";

const API_KEY_HEADER = "X-FounderOS-API-Key";

function buildUrl(path: string, baseUrl: string): URL {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return new URL(path);
  }
  return new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
}

function appendOwnerEmail(url: URL, ownerEmail: string | null | undefined): void {
  if (!ownerEmail || url.searchParams.has("owner_email")) {
    return;
  }
  url.searchParams.set("owner_email", ownerEmail);
}

async function readError(response: Response): Promise<string> {
  const fallback = `${response.status} ${response.statusText}`.trim();
  try {
    const payload = (await response.json()) as ApiErrorPayload;
    return payload.detail || payload.message || fallback;
  } catch {
    return fallback;
  }
}

export async function apiFetch<TResponse>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<TResponse> {
  const localConfig = readOperatorConfig();
  const baseUrl = options.apiBaseUrl || resolveApiBaseUrl(localConfig);
  const url = buildUrl(path, baseUrl || getConfiguredApiBaseUrl());
  if (options.includeOwnerEmail !== false) {
    appendOwnerEmail(url, options.ownerEmail ?? localConfig.ownerEmail);
  }

  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const apiKey = options.apiKey ?? localConfig.apiKey;
  if (apiKey) {
    headers.set(API_KEY_HEADER, apiKey);
  }

  const response = await fetch(url, {
    ...options,
    headers
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  return (await response.json()) as TResponse;
}

export { API_KEY_HEADER };
