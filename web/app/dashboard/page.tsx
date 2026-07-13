"use client";

import { useState } from "react";

import { ActionProposalsPanel } from "../../components/ActionProposalsPanel";
import { BriefingPanel } from "../../components/BriefingPanel";
import { CompanyBrainPanel } from "../../components/CompanyBrainPanel";
import { CompanyWorldPanel } from "../../components/CompanyWorldPanel";
import { GitHubOperationalWorkPanel } from "../../components/GitHubOperationalWorkPanel";
import { GitHubSyncControls } from "../../components/GitHubSyncControls";
import { NormalizedEntitiesPanel } from "../../components/NormalizedEntitiesPanel";
import { PageHeader } from "../../components/PageHeader";
import { PrivateBetaReadinessPanel } from "../../components/PrivateBetaReadinessPanel";
import { SelectedRepositorySyncControls } from "../../components/SelectedRepositorySyncControls";
import { SourceCoveragePanel } from "../../components/SourceCoveragePanel";
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
      <section className="command-deck" aria-label={M.dashboard.currentTurnAriaLabel}>
        <div>
          <span className="eyebrow">{M.dashboard.currentTurnLabel}</span>
          <h2>{workspace ? workspace.name : M.dashboard.workspaceNone}</h2>
          <p>{M.dashboard.currentTurnDescription}</p>
        </div>
        <div className="command-deck-state">
          <span>{M.dashboard.workspaceTitle}</span>
          <strong>
            {workspace ? M.dashboard.workspaceActive : M.dashboard.workspaceNone}
          </strong>
        </div>
      </section>

      <section className="dashboard-layer dashboard-layer--briefing">
        <LayerHeading
          index="01"
          title={M.dashboard.layers.briefingTitle}
          description={M.dashboard.layers.briefingDescription}
        />
        <BriefingPanel />
      </section>

      <section className="dashboard-layer dashboard-layer--decisions">
        <LayerHeading
          index="02"
          title={M.dashboard.layers.decisionsTitle}
          description={M.dashboard.layers.decisionsDescription}
        />
        <ActionProposalsPanel />
      </section>

      <section className="dashboard-layer dashboard-layer--world">
        <LayerHeading
          index="03"
          title={M.dashboard.layers.worldTitle}
          description={M.dashboard.layers.worldDescription}
        />
        <CompanyWorldPanel refreshSignal={operationalWorkRefresh} />
      </section>

      <section className="dashboard-layer dashboard-layer--operations">
        <LayerHeading
          index="04"
          title={M.dashboard.layers.operationsTitle}
          description={M.dashboard.layers.operationsDescription}
        />
        <div className="operations-stack">
          <GitHubSyncControls
            onSyncComplete={() => setOperationalWorkRefresh((current) => current + 1)}
          />
          <SelectedRepositorySyncControls
            onSyncComplete={() => setOperationalWorkRefresh((current) => current + 1)}
          />
          <SourceCoveragePanel refreshSignal={operationalWorkRefresh} />
          <PrivateBetaReadinessPanel refreshSignal={operationalWorkRefresh} />
          <GitHubOperationalWorkPanel refreshSignal={operationalWorkRefresh} />
          <CompanyBrainPanel refreshSignal={operationalWorkRefresh} />
          <NormalizedEntitiesPanel refreshSignal={operationalWorkRefresh} />
        </div>
      </section>
    </>
  );
}

function LayerHeading({
  description,
  index,
  title
}: {
  description: string;
  index: string;
  title: string;
}) {
  return (
    <header className="layer-heading">
      <span aria-hidden="true">{index}</span>
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </header>
  );
}
