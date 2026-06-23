"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";
import { readOperatorConfig, resolveApiBaseUrl } from "../../lib/config";
import type { OperatorConfig } from "../../lib/types";

export default function DashboardPage() {
  const [config, setConfig] = useState<OperatorConfig | null>(null);

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
          description="Connection, repositories, sync jobs, and normalization."
          title="GitHub"
          value="Placeholder"
        />
        <StatusCard
          description="Manual deterministic Founder Briefing v0."
          title="Briefing"
          value="Placeholder"
        />
        <StatusCard
          description="Proposal, approval, and execution states."
          title="Actions"
          value="Placeholder"
        />
      </section>
    </>
  );
}
