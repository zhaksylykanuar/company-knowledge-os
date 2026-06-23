import type { ReactNode } from "react";

import { Sidebar } from "./Sidebar";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main">
        <div className="content">{children}</div>
      </main>
    </div>
  );
}
