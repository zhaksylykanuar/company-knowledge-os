"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { AuthGate } from "./AuthGate";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();

  // /login is public — render it bare, outside the authenticated chrome/gate.
  if (pathname === "/login") {
    return <>{children}</>;
  }

  return <AuthGate>{children}</AuthGate>;
}
