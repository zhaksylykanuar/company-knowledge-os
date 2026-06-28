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

const GENERIC_LOGIN_ERROR = "Invalid email or password.";
const LOCKED_LOGIN_ERROR = "Too many failed attempts. Try again later.";

export class LoginError extends Error {}

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
