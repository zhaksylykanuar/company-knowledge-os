import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "../components/AppShell";
import { M } from "../lib/messages";
import "./globals.css";

export const metadata: Metadata = {
  title: M.app.metaTitle,
  description: M.app.metaDescription
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="ru">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
