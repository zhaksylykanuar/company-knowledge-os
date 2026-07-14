"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { M } from "../lib/messages";

type NavIcon = "building" | "decision" | "settings" | "sources" | "today";

export type NavLink = {
  activePaths?: readonly string[];
  href: string;
  icon?: NavIcon;
  label: string;
};

type NavGroup = {
  label: string;
  links: readonly NavLink[];
};

export const PRIMARY_NAV: readonly NavLink[] = [
  {
    href: "/dashboard",
    label: M.nav.hq,
    icon: "today",
    activePaths: ["/dashboard", "/briefings"]
  },
  {
    href: "/company-brain",
    label: M.nav.world,
    icon: "building",
    activePaths: ["/company-brain", "/documents"]
  },
  {
    href: "/actions",
    label: M.nav.missions,
    icon: "decision",
    activePaths: ["/actions"]
  }
] as const;

export const BACKSTAGE_NAV: readonly NavLink[] = [
  {
    href: "/connectors",
    label: M.nav.radars,
    icon: "sources",
    activePaths: ["/connectors", "/github", "/jira", "/gmail", "/drive"]
  },
  {
    href: "/settings",
    label: M.nav.settings,
    icon: "settings",
    activePaths: ["/settings"]
  }
] as const;

export const SOURCE_NAV: readonly NavLink[] = [
  { href: "/connectors", label: M.nav.sourceOverview },
  { href: "/github", label: M.nav.github },
  { href: "/jira", label: M.nav.jira },
  { href: "/gmail", label: M.nav.gmail },
  { href: "/drive", label: M.nav.drive }
] as const;

export const TODAY_NAV: readonly NavLink[] = [
  { href: "/dashboard", label: M.nav.todayOverview },
  { href: "/briefings", label: M.nav.briefings }
] as const;

export const COMPANY_NAV: readonly NavLink[] = [
  { href: "/company-brain", label: M.nav.companyMap },
  { href: "/documents", label: M.nav.documents }
] as const;

// Kept as compatibility exports for tests and consumers that need a flattened
// navigation model. Briefings and documents remain reachable product routes,
// but the rendered shell no longer treats them as primary sub-navigation.
export const NAV_GROUPS: readonly NavGroup[] = [
  { label: M.nav.primaryZones, links: PRIMARY_NAV },
  { label: M.nav.backstage, links: BACKSTAGE_NAV },
  { label: M.nav.sourceProviders, links: SOURCE_NAV }
] as const;

export const NAV_LINKS: readonly NavLink[] = [
  ...PRIMARY_NAV,
  ...BACKSTAGE_NAV,
  TODAY_NAV[1],
  COMPANY_NAV[1],
  ...SOURCE_NAV.slice(1)
];

export function isNavigationItemActive(pathname: string, link: NavLink): boolean {
  const activePaths = link.activePaths ?? [link.href];
  return activePaths.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`)
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <Link className="brand" href="/dashboard" aria-label={M.nav.brandHomeLabel}>
        <span className="brand-mark" aria-hidden="true">
          F
        </span>
        <span className="brand-copy">
          <span className="brand-name">{M.app.name}</span>
          <span className="brand-mode">{M.app.shellMode}</span>
        </span>
      </Link>

      <nav className="nav" aria-label={M.nav.primaryLabel}>
        {PRIMARY_NAV.map((link) => {
          const isActive = isNavigationItemActive(pathname, link);
          return (
            <div className="nav-zone" key={link.href}>
              <Link
                aria-current={pathname === link.href ? "page" : undefined}
                className={isActive ? "nav-link active" : "nav-link"}
                href={link.href}
              >
                {link.icon ? <NavGlyph icon={link.icon} /> : null}
                <span>{link.label}</span>
              </Link>

            </div>
          );
        })}
      </nav>

      <nav className="backstage-nav" aria-label={M.nav.backstage}>
        {BACKSTAGE_NAV.map((link) => {
          const isActive = isNavigationItemActive(pathname, link);
          return (
            <Link
              aria-current={pathname === link.href ? "page" : undefined}
              className={
                isActive
                  ? "nav-link backstage-nav-link active"
                  : "nav-link backstage-nav-link"
              }
              href={link.href}
              key={link.href}
            >
              {link.icon ? <NavGlyph icon={link.icon} /> : null}
              <span>{link.label}</span>
            </Link>
          );
        })}
      </nav>

      <p className="sidebar-boundary">{M.nav.boundary}</p>
    </aside>
  );
}

export function MobilePrimaryNavigation() {
  const pathname = usePathname();

  return (
    <nav className="mobile-nav" aria-label={M.nav.primaryLabel}>
      {PRIMARY_NAV.map((link) => {
        const isActive = isNavigationItemActive(pathname, link);
        return (
          <Link
            aria-current={pathname === link.href ? "page" : undefined}
            className={isActive ? "nav-link active" : "nav-link"}
            href={link.href}
            key={link.href}
          >
            {link.icon ? <NavGlyph icon={link.icon} /> : null}
            <span>{link.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function ContextNavigation() {
  const pathname = usePathname();
  const context = getContextNavigation(pathname);

  if (context === null) {
    return null;
  }

  return (
    <nav className="context-nav" aria-label={context.label}>
      <span className="context-nav-label">{context.label}</span>
      <div className="context-nav-links">
        {context.links.map((link) => {
          const active = isNavigationItemActive(pathname, link);
          return (
            <Link
              aria-current={pathname === link.href ? "page" : undefined}
              className={active ? "context-nav-link active" : "context-nav-link"}
              href={link.href}
              key={link.href}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export function getContextNavigation(pathname: string): NavGroup | null {
  const isSourceRoute = SOURCE_NAV.some((link) =>
    isNavigationItemActive(pathname, link)
  );
  return isSourceRoute
    ? { label: M.nav.sourceProviders, links: SOURCE_NAV }
    : null;
}

function NavGlyph({ icon }: { icon: NavIcon }) {
  const paths: Record<NavIcon, ReactNode> = {
    today: (
      <>
        <path d="M4 5.5h16M7 3v5M17 3v5" />
        <path d="M5 8.5h14v11H5z" />
        <path d="m9 14 2 2 4-5" />
      </>
    ),
    building: (
      <>
        <path d="M4 20V7l8-4 8 4v13" />
        <path d="M8 10h1M8 14h1M15 10h1M15 14h1M10 20v-3h4v3" />
      </>
    ),
    decision: (
      <>
        <path d="M4 6h10M4 12h7M4 18h10" />
        <path d="m15 12 2 2 4-5" />
      </>
    ),
    sources: (
      <>
        <circle cx="6" cy="6" r="2.5" />
        <circle cx="18" cy="7" r="2.5" />
        <circle cx="12" cy="18" r="2.5" />
        <path d="m8.3 7 7.2-.2M7.3 8.2l3.5 7.6M16.8 9.1l-3.5 6.7" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" />
      </>
    )
  };

  return (
    <svg
      aria-hidden="true"
      className="nav-icon"
      fill="none"
      viewBox="0 0 24 24"
    >
      <g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7">
        {paths[icon]}
      </g>
    </svg>
  );
}
