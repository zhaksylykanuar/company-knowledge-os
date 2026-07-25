"use client";

import Link from "next/link";
import { useState } from "react";

import { GitHubOperationalWorkPanel } from "../../../../components/GitHubOperationalWorkPanel";
import { GitHubProductConnectPanel } from "../../../../components/GitHubProductConnectPanel";
import { PageHeader } from "../../../../components/PageHeader";

export default function GitHubIntegrationPage() {
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [connectionReady, setConnectionReady] = useState(false);
  const [selectedRepository, setSelectedRepository] = useState<string | null>(
    null
  );

  return (
    <div className="github-page">
      <Link
        className="onboarding-return"
        href="/settings/integrations?provider=github"
      >
        <span aria-hidden="true">←</span>
        Вернуться к источникам
      </Link>
      <PageHeader
        eyebrow="Настройки · GitHub"
        title="Рабочая GitHub-организация"
        description="Выберите организацию и только те репозитории, которые FounderOS может читать для памяти компании."
      />
      <div className="github-page__content">
        <GitHubProductConnectPanel
          onConnectionReadyChange={setConnectionReady}
          onSelectedRepositoryChange={setSelectedRepository}
          onSyncComplete={() => setRefreshSignal((current) => current + 1)}
        />
        {connectionReady && selectedRepository ? (
          <GitHubOperationalWorkPanel
            refreshSignal={refreshSignal}
            repositoryFullName={selectedRepository}
          />
        ) : null}
      </div>
    </div>
  );
}
