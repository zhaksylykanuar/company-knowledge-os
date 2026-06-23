"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Home" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/github", label: "GitHub" },
  { href: "/briefings", label: "Briefings" },
  { href: "/actions", label: "Actions" },
  { href: "/settings", label: "Settings" }
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-name">founderOS</span>
        <span className="brand-mode">MVP shell</span>
      </div>
      <nav className="nav" aria-label="Primary navigation">
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
