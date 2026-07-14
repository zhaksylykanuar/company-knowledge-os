"use client";

import { useState } from "react";

import { GitHubOperationalWorkPanel } from "../../components/GitHubOperationalWorkPanel";
import { GitHubProductConnectPanel } from "../../components/GitHubProductConnectPanel";
import { PageHeader } from "../../components/PageHeader";
import { M } from "../../lib/messages";

export default function GitHubPage() {
  const [refreshSignal, setRefreshSignal] = useState(0);

  return (
    <div className="github-page">
      <PageHeader
        eyebrow={M.githubPage.eyebrow}
        title={M.githubPage.title}
        description={M.githubPage.description}
      />
      <GitHubProductConnectPanel
        onSyncComplete={() => setRefreshSignal((current) => current + 1)}
      />
      <GitHubOperationalWorkPanel refreshSignal={refreshSignal} />
    </div>
  );
}
