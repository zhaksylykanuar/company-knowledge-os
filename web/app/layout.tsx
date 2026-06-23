import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "../components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "founderOS",
  description: "Minimal founderOS MVP shell"
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
