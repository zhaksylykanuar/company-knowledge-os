import Link from "next/link";

import { PageHeader } from "../components/PageHeader";
import { StatusCard } from "../components/StatusCard";
import { M } from "../lib/messages";

const destinations = [
  { href: "/dashboard", ...M.home.cards.dashboard },
  { href: "/github", ...M.home.cards.github },
  { href: "/briefings", ...M.home.cards.briefings },
  { href: "/actions", ...M.home.cards.actions },
  { href: "/settings", ...M.home.cards.settings }
];

export default function HomePage() {
  return (
    <>
      <PageHeader
        eyebrow={M.home.eyebrow}
        title={M.home.title}
        description={M.home.description}
      />
      <section className="grid" aria-label={M.home.title}>
        {destinations.map((destination) => (
          <Link href={destination.href} key={destination.href}>
            <StatusCard
              description={destination.description}
              title={destination.title}
              value={destination.value}
            />
          </Link>
        ))}
      </section>
    </>
  );
}
