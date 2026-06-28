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
import { M } from "../../lib/messages";
import { useSession } from "../../lib/session";

export default function DashboardPage() {
  const session = useSession();
  const [operationalWorkRefresh, setOperationalWorkRefresh] = useState(0);
  const workspace = session?.workspaces[0] ?? null;

  return (
    <>
      <PageHeader
        eyebrow={M.dashboard.eyebrow}
        title={M.dashboard.title}
        description={M.dashboard.description}
      />
      <section className="grid">
        <StatusCard
          description={M.dashboard.backendDescription}
          title={M.dashboard.backendTitle}
          value={M.dashboard.backendValue}
        />
        <StatusCard
          description={workspace ? workspace.name : M.dashboard.workspaceNoneDescription}
          title={M.dashboard.workspaceTitle}
          value={workspace ? M.dashboard.workspaceActive : M.dashboard.workspaceNone}
        />
        <StatusCard
          description={M.dashboard.githubDescription}
          title={M.dashboard.githubTitle}
          value={M.dashboard.githubValue}
        />
        <StatusCard
          description={M.dashboard.briefingDescription}
          title={M.dashboard.briefingTitle}
          value={M.dashboard.briefingValue}
        />
        <StatusCard
          description={M.dashboard.actionsDescription}
          title={M.dashboard.actionsTitle}
          value={M.dashboard.actionsValue}
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
