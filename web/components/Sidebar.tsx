"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { M } from "../lib/messages";

type NavIcon = "ask" | "building" | "settings" | "today";

export type NavLink = {
  activePaths?: readonly string[];
  href: string;
  icon: NavIcon;
  label: string;
};

type NavGroup = {
  label: string;
  links: readonly NavLink[];
};

export const PRIMARY_NAV: readonly NavLink[] = [
  {
    href: "/dashboard",
    label: M.nav.now,
    icon: "today",
    activePaths: ["/dashboard"]
  },
  {
    href: "/company-brain",
    label: M.nav.company,
    icon: "building",
    activePaths: ["/company-brain", "/documents", "/briefings", "/actions"]
  },
  {
    href: "/ask",
    label: M.nav.ask,
    icon: "ask",
    activePaths: ["/ask"]
  }
] as const;

export const BACKSTAGE_NAV: readonly NavLink[] = [
  {
    href: "/settings",
    label: M.nav.settings,
    icon: "settings",
    activePaths: ["/settings"]
  }
] as const;

export const NAV_GROUPS: readonly NavGroup[] = [
  { label: M.nav.primaryZones, links: PRIMARY_NAV },
  { label: M.nav.settings, links: BACKSTAGE_NAV }
] as const;

export const NAV_LINKS: readonly NavLink[] = [
  ...PRIMARY_NAV,
  ...BACKSTAGE_NAV
];

export function isNavigationItemActive(pathname: string, link: NavLink): boolean {
  const activePaths = link.activePaths ?? [link.href];
  return activePaths.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`)
  );
}

export function Sidebar({ locked = false }: { locked?: boolean } = {}) {
  const pathname = usePathname();

  return (
    <aside className="sidebar" inert={locked}>
      <Link className="brand" href="/dashboard" aria-label={M.nav.brandHomeLabel}>
        <span className="brand-mark" aria-hidden="true">F</span>
        <span className="brand-copy">
          <span className="brand-name">{M.app.name}</span>
          <span className="brand-mode">{M.app.shellMode}</span>
        </span>
      </Link>

      <nav className="nav" aria-label={M.nav.primaryLabel}>
        {PRIMARY_NAV.map((link) => (
          <NavigationLink key={link.href} link={link} pathname={pathname} />
        ))}
      </nav>

      <nav className="backstage-nav" aria-label={M.nav.settings}>
        {BACKSTAGE_NAV.map((link) => (
          <NavigationLink
            extraClassName="backstage-nav-link"
            key={link.href}
            link={link}
            pathname={pathname}
          />
        ))}
      </nav>

      <p className="sidebar-boundary">{M.nav.boundary}</p>
    </aside>
  );
}

export function MobilePrimaryNavigation({
  locked = false
}: {
  locked?: boolean;
} = {}) {
  const pathname = usePathname();

  return (
    <nav className="mobile-nav" aria-label={M.nav.primaryLabel} inert={locked}>
      {PRIMARY_NAV.map((link) => (
        <NavigationLink key={link.href} link={link} pathname={pathname} />
      ))}
    </nav>
  );
}

function NavigationLink({
  extraClassName = "",
  link,
  pathname
}: {
  extraClassName?: string;
  link: NavLink;
  pathname: string;
}) {
  const active = isNavigationItemActive(pathname, link);
  return (
    <Link
      aria-current={pathname === link.href ? "page" : undefined}
      className={`nav-link${extraClassName ? ` ${extraClassName}` : ""}${active ? " active" : ""}`}
      href={link.href}
    >
      <NavGlyph icon={link.icon} />
      <span>{link.label}</span>
    </Link>
  );
}

function NavGlyph({ icon }: { icon: NavIcon }) {
  const paths: Record<NavIcon, ReactNode> = {
    today: (
      <>
        <circle cx="12" cy="12" r="8" />
        <path d="M12 8v4l3 2" />
      </>
    ),
    building: (
      <>
        <path d="M4 20V7l8-4 8 4v13" />
        <path d="M8 10h1M8 14h1M15 10h1M15 14h1M10 20v-3h4v3" />
      </>
    ),
    ask: (
      <>
        <path d="M12 3a8 8 0 1 0 4.8 14.4L21 19l-1.6-4.2A8 8 0 0 0 12 3Z" />
        <path d="M9 10.2a3 3 0 0 1 5.7 1.3c0 2-2.7 2-2.7 3.5M12 18h.01" />
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
      <g
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.7"
      >
        {paths[icon]}
      </g>
    </svg>
  );
}
