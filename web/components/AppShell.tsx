"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { AuthGate } from "./AuthGate";

type AppShellProps = {
  children: ReactNode;
};

export const PUBLIC_SHELL_PATHS = ["/login", "/setup-password", "/start"] as const;

export function isPublicShellPath(pathname: string): boolean {
  return PUBLIC_SHELL_PATHS.some((path) => pathname === path);
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();

  // Enrollment and password entry points render outside authenticated chrome.
  // /onboarding itself stays behind AuthGate and uses the current session.
  if (isPublicShellPath(pathname)) {
    return <>{children}</>;
  }

  return <AuthGate>{children}</AuthGate>;
}
