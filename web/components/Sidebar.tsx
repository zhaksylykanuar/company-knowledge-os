"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { M } from "../lib/messages";

export const NAV_LINKS = [
  { href: "/", label: M.nav.home },
  { href: "/dashboard", label: M.nav.dashboard },
  { href: "/company-brain", label: M.nav.companyBrain },
  { href: "/github", label: M.nav.github },
  { href: "/jira", label: M.nav.jira },
  { href: "/gmail", label: M.nav.gmail },
  { href: "/drive", label: M.nav.drive },
  { href: "/documents", label: M.nav.documents },
  { href: "/connectors", label: M.nav.connectors },
  { href: "/audit", label: M.nav.audit },
  { href: "/briefings", label: M.nav.briefings },
  { href: "/actions", label: M.nav.actions },
  { href: "/settings", label: M.nav.settings }
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-name">{M.app.name}</span>
        <span className="brand-mode">{M.app.shellMode}</span>
      </div>
      <nav className="nav" aria-label={M.nav.primaryLabel}>
        {NAV_LINKS.map((link) => {
          const isActive =
            link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
          return (
            <Link
              className={isActive ? "nav-link active" : "nav-link"}
              href={link.href}
              key={link.href}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
