"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { M } from "../lib/messages";

type NavLink = {
  href: string;
  label: string;
};

type NavGroup = {
  label: string;
  links: readonly NavLink[];
};

export const NAV_GROUPS: readonly NavGroup[] = [
  {
    label: M.nav.groups.command,
    links: [
      { href: "/dashboard", label: M.nav.dashboard },
      { href: "/company-brain", label: M.nav.companyBrain }
    ]
  },
  {
    label: M.nav.groups.management,
    links: [
      { href: "/briefings", label: M.nav.briefings },
      { href: "/actions", label: M.nav.actions },
      { href: "/documents", label: M.nav.documents }
    ]
  },
  {
    label: M.nav.groups.sources,
    links: [
      { href: "/connectors", label: M.nav.connectors },
      { href: "/github", label: M.nav.github },
      { href: "/jira", label: M.nav.jira },
      { href: "/gmail", label: M.nav.gmail },
      { href: "/drive", label: M.nav.drive }
    ]
  },
  {
    label: M.nav.groups.system,
    links: [{ href: "/settings", label: M.nav.settings }]
  }
] as const;

export const NAV_LINKS: readonly NavLink[] = NAV_GROUPS.flatMap(
  (group) => group.links
);

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-name">{M.app.name}</span>
        <span className="brand-mode">{M.app.shellMode}</span>
      </div>
      <nav className="nav" aria-label={M.nav.primaryLabel}>
        {NAV_GROUPS.map((group) => (
          <div className="nav-group" key={group.label}>
            <span className="nav-group-label">{group.label}</span>
            <div className="nav-group-links">
              {group.links.map((link) => {
                const isActive = pathname.startsWith(link.href);
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
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
