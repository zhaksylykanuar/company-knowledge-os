// Session-cookie auth client. All calls are SAME-ORIGIN (/api/... proxied to
// the backend by next.config.mjs) with credentials included, so the httpOnly
// session cookie is set and sent first-party. The operator API key is never
// used here — it stays server/CI-only and is never shipped to the browser.

export type AuthWorkspace = {
  id: string;
  name: string;
  slug: string;
  role: string;
};

export type AuthUser = {
  id: string;
  email: string;
  name: string | null;
  status: string;
};

export type MeResponse = {
  user: AuthUser;
  workspaces: AuthWorkspace[];
};

export type FounderEnrollmentRequest = {
  token: string;
  email: string;
  name: string;
  password: string;
  workspaceName: string;
  workspaceSlug: string;
};

export type FounderEnrollmentResponse = {
  status: "ok";
  user: AuthUser;
  workspace: AuthWorkspace & { role: "owner" };
};

import { M } from "./messages";

const GENERIC_LOGIN_ERROR = M.auth.loginFailedGeneric;
const LOCKED_LOGIN_ERROR = M.auth.loginFailedLocked;

export class LoginError extends Error {}

export class EnrollmentError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "EnrollmentError";
    this.status = status;
  }
}

export async function enrollFounder(
  request: FounderEnrollmentRequest
): Promise<FounderEnrollmentResponse> {
  const response = await fetch("/api/v1/auth/enroll", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      token: request.token,
      email: request.email,
      name: request.name,
      password: request.password,
      workspace_name: request.workspaceName,
      workspace_slug: request.workspaceSlug
    })
  });
  if (response.ok) {
    return (await response.json()) as FounderEnrollmentResponse;
  }
  if (response.status === 400) {
    throw new EnrollmentError(
      "Ссылка приглашения недействительна или устарела. Попросите новую ссылку.",
      response.status
    );
  }
  if (response.status === 409) {
    throw new EnrollmentError(
      "Такая почта или адрес компании уже используются. Проверьте данные или войдите в существующий аккаунт.",
      response.status
    );
  }
  throw new EnrollmentError(
    "Не удалось создать компанию. Данные не сохранены — попробуйте ещё раз.",
    response.status
  );
}

export async function login(email: string, password: string): Promise<void> {
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ email, password })
  });
  if (response.ok) {
    return;
  }
  if (response.status === 429) {
    throw new LoginError(LOCKED_LOGIN_ERROR);
  }
  // Generic for every other failure — never reveal whether the email exists.
  throw new LoginError(GENERIC_LOGIN_ERROR);
}

export async function logout(): Promise<void> {
  await fetch("/api/v1/auth/logout", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json" }
  });
}

export async function fetchMe(): Promise<MeResponse | null> {
  const response = await fetch("/api/v1/auth/me", {
    credentials: "include",
    headers: { Accept: "application/json" }
  });
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`auth/me failed: ${response.status}`);
  }
  return (await response.json()) as MeResponse;
}

export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<void> {
  const response = await fetch("/api/v1/auth/change-password", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword
    })
  });
  if (!response.ok) {
    throw new Error("change password failed");
  }
}

export async function setupPassword(token: string, newPassword: string): Promise<void> {
  const response = await fetch("/api/v1/auth/setup-password", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      token,
      new_password: newPassword
    })
  });
  if (!response.ok) {
    throw new Error("setup password failed");
  }
}
