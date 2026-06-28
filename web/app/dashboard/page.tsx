"use client";

import { useState } from "react";

import { ActionProposalsPanel } from "../../components/ActionProposalsPanel";
import { BriefingPanel } from "../../components/BriefingPanel";
import { CompanyBrainPanel } from "../../components/CompanyBrainPanel";
import { GitHubOperationalWorkPanel } from "../../components/GitHubOperationalWorkPanel";
import { GitHubSyncControls } from "../../components/GitHubSyncControls";
import { PageHeader } from "../../components/PageHeader";
import { SelectedRepositorySyncControls } from "../../components/SelectedRepositorySyncControls";
import { StatusCard } from "../../components/StatusCard";
import { useSession } from "../../lib/session";

export default function DashboardPage() {
  const session = useSession();
  const [operationalWorkRefresh, setOperationalWorkRefresh] = useState(0);
  const workspace = session?.workspaces[0] ?? null;

  return (
    <>
      <PageHeader
        eyebrow="Dashboard"
        title="MVP status"
        description="Signed-in view of the backend flow and the GitHub-first MVP surfaces."
      />
      <section className="grid">
        <StatusCard
          description="Same-origin API authenticated by your session cookie."
          title="Backend API"
          value="Connected"
        />
        <StatusCard
          description={workspace ? workspace.name : "No workspace for this account yet."}
          title="Workspace"
          value={workspace ? "Active" : "None"}
        />
        <StatusCard
          description="Local sync controls, Company Brain, and canonical work are loaded below."
          title="GitHub"
          value="Wired"
        />
        <StatusCard
          description="Manual deterministic Founder Briefing v0."
          title="Briefing"
          value="Wired"
        />
        <StatusCard
          description="Proposal, approval, and execution states."
          title="Actions"
          value="Local approval"
        />
      </section>
      <GitHubSyncControls
        onSyncComplete={() => setOperationalWorkRefresh((current) => current + 1)}
      />
      <SelectedRepositorySyncControls
        onSyncComplete={() => setOperationalWorkRefresh((current) => current + 1)}
      />
      <CompanyBrainPanel refreshSignal={operationalWorkRefresh} />
      <BriefingPanel />
      <ActionProposalsPanel />
      <GitHubOperationalWorkPanel refreshSignal={operationalWorkRefresh} />
    </>
  );
}
