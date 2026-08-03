"use client";

import Link from "next/link";
import { useState } from "react";

import { M } from "../lib/messages";
import { CompanyBrainPanel } from "./CompanyBrainPanel";
import { CompanyWorldPanel } from "./CompanyWorldPanel";
import { NormalizedEntitiesPanel } from "./NormalizedEntitiesPanel";

type CompanyBrainPageClientProps = {
  profileSelector: string | null;
  profileSelectorRequested: boolean;
};

export function CompanyBrainPageClient({
  profileSelector,
  profileSelectorRequested
}: CompanyBrainPageClientProps) {
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [dataLayerOpen, setDataLayerOpen] = useState(false);

  function refreshWorld(): void {
    setRefreshSignal((current) => current + 1);
  }

  return (
    <>
      <CompanyWorldPanel
        onRefresh={refreshWorld}
        profileSelector={profileSelector}
        profileSelectorRequested={profileSelectorRequested}
        refreshSignal={refreshSignal}
      />
      <RepositoryIntelligenceEntry />
      <details
        className="company-data-vault"
        onToggle={(event) => setDataLayerOpen(event.currentTarget.open)}
      >
        <summary>
          <span aria-hidden="true">{M.companyBrainPage.dataLayerIndex}</span>
          <span>
            <strong>{M.companyBrainPage.dataLayerTitle}</strong>
            <small>{M.companyBrainPage.dataLayerDescription}</small>
          </span>
        </summary>
        {dataLayerOpen ? (
          <div className="operations-stack company-data-vault-body">
            <CompanyBrainPanel refreshSignal={refreshSignal} />
            <NormalizedEntitiesPanel refreshSignal={refreshSignal} />
          </div>
        ) : null}
      </details>
    </>
  );
}

export function RepositoryIntelligenceEntry() {
  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <span className="eyebrow">Repository Intelligence</span>
          <h2>Карта репозиториев</h2>
          <p className="muted">
            Назначение, направленные связи, риски, неизвестные и история
            сохранённых аудитов.
          </p>
        </div>
        <Link className="button secondary" href="/company-brain/repositories">
          Открыть карту
        </Link>
      </div>
    </section>
  );
}
