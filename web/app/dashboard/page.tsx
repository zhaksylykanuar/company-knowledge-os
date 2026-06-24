"use client";

import { useEffect, useState } from "react";

import { BriefingPanel } from "../../components/BriefingPanel";
import { CompanyBrainPanel } from "../../components/CompanyBrainPanel";
import { GitHubOperationalWorkPanel } from "../../components/GitHubOperationalWorkPanel";
import { GitHubSyncControls } from "../../components/GitHubSyncControls";
import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";
import { readOperatorConfig, resolveApiBaseUrl } from "../../lib/config";
import type { OperatorConfig } from "../../lib/types";

export default function DashboardPage() {
  const [config, setConfig] = useState<OperatorConfig | null>(null);
  const [operationalWorkRefresh, setOperationalWorkRefresh] = useState(0);

  useEffect(() => {
    setConfig(readOperatorConfig());
  }, []);

  const apiBaseUrl = config ? resolveApiBaseUrl(config) : "Loading";
  const workspaceStatus = config?.workspaceId ? "Configured" : "Missing";
  const keyStatus = config?.apiKey ? "Configured" : "Missing";

  return (
    <>
      <PageHeader
        eyebrow="Dashboard"
        title="MVP status"
        description="Local operator view of the backend flow configuration and next UI surfaces."
      />
      <section className="grid">
        <StatusCard
          description={apiBaseUrl}
          title="Backend API"
          value={apiBaseUrl ? "Ready" : "Missing"}
        />
        <StatusCard
          description="Workspace ID stored in browser settings."
          title="Workspace"
          value={workspaceStatus}
        />
        <StatusCard
          description="Operator API key is required for local MVP calls."
          title="API key"
          value={keyStatus}
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
          value="Stub"
        />
      </section>
      <GitHubSyncControls
        onSyncComplete={() => setOperationalWorkRefresh((current) => current + 1)}
      />
      <CompanyBrainPanel refreshSignal={operationalWorkRefresh} />
      <BriefingPanel />
      <GitHubOperationalWorkPanel refreshSignal={operationalWorkRefresh} />
    </>
  );
}
