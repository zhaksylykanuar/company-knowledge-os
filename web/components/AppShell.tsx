"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { DEMO_TOUR_PATH } from "../lib/demo-tour-access";
import { AuthGate } from "./AuthGate";

type AppShellProps = {
  children: ReactNode;
};

export const PUBLIC_SHELL_PATHS = [
  "/login",
  "/setup-password",
  "/start",
  DEMO_TOUR_PATH
] as const;

export function isPublicShellPath(pathname: string): boolean {
  return PUBLIC_SHELL_PATHS.some((path) => pathname === path);
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();

  // Enrollment, password entry points, and the isolated demo tour render
  // outside authenticated chrome. /onboarding itself stays behind AuthGate and
  // uses the current session. Exact matching keeps every nested/unknown route
  // protected by default.
  if (isPublicShellPath(pathname)) {
    return <>{children}</>;
  }

  return <AuthGate>{children}</AuthGate>;
}
