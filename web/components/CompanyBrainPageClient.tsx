"use client";

import { useState } from "react";

import { M } from "../lib/messages";
import { CompanyBrainPanel } from "./CompanyBrainPanel";
import { CompanyWorldPanel } from "./CompanyWorldPanel";
import { NormalizedEntitiesPanel } from "./NormalizedEntitiesPanel";

type CompanyBrainPageClientProps = {
  profileSelector: string | null;
};

export function CompanyBrainPageClient({
  profileSelector
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
        refreshSignal={refreshSignal}
      />
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
