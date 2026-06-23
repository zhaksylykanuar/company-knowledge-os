export type OperatorConfig = {
  apiBaseUrl: string;
  apiKey: string;
  ownerEmail: string;
  workspaceId: string;
};

export type ApiErrorPayload = {
  detail?: string;
  message?: string;
};

export type ApiFetchOptions = RequestInit & {
  apiBaseUrl?: string | null;
  apiKey?: string | null;
  includeOwnerEmail?: boolean;
  ownerEmail?: string | null;
};
