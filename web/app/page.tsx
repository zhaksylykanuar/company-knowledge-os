import Link from "next/link";

import { PageHeader } from "../components/PageHeader";
import { StatusCard } from "../components/StatusCard";

const destinations = [
  {
    href: "/dashboard",
    title: "Dashboard",
    value: "MVP",
    description: "Workspace, GitHub, briefing, action, and backend status."
  },
  {
    href: "/github",
    title: "GitHub",
    value: "Flow",
    description: "Connection, repositories, sync jobs, and local normalization."
  },
  {
    href: "/briefings",
    title: "Briefings",
    value: "Manual",
    description: "Deterministic Founder Briefing v0 surface."
  },
  {
    href: "/actions",
    title: "Actions",
    value: "Approval",
    description: "Proposal states and the human-approved write boundary."
  },
  {
    href: "/settings",
    title: "Settings",
    value: "Account",
    description: "Your signed-in account, sign out, and change password."
  }
];

export default function HomePage() {
  return (
    <>
      <PageHeader
        eyebrow="founderOS"
        title="MVP frontend shell"
        description="A minimal Next.js shell for the backend GitHub-first MVP path."
      />
      <section className="grid" aria-label="MVP sections">
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
