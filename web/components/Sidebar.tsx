"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { M } from "../lib/messages";

const links = [
  { href: "/", label: M.nav.home },
  { href: "/dashboard", label: M.nav.dashboard },
  { href: "/github", label: M.nav.github },
  { href: "/briefings", label: M.nav.briefings },
  { href: "/actions", label: M.nav.actions },
  { href: "/settings", label: M.nav.settings }
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-name">{M.app.name}</span>
        <span className="brand-mode">{M.app.shellMode}</span>
      </div>
      <nav className="nav" aria-label={M.nav.primaryLabel}>
        {links.map((link) => {
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
