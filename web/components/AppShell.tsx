"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { AuthGate } from "./AuthGate";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();

  // /login and /setup-password are public — render them bare, outside the
  // authenticated chrome/gate.
  if (pathname === "/login" || pathname === "/setup-password") {
    return <>{children}</>;
  }

  return <AuthGate>{children}</AuthGate>;
}
