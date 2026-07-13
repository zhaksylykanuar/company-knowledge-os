"use client";

import { useState } from "react";

import { CompanyBrainPanel } from "../../components/CompanyBrainPanel";
import { CompanyWorldPanel } from "../../components/CompanyWorldPanel";
import { NormalizedEntitiesPanel } from "../../components/NormalizedEntitiesPanel";
import { PageHeader } from "../../components/PageHeader";
import { M } from "../../lib/messages";

export default function CompanyBrainPage() {
  // Company World v1 composes the new workspace-scoped company map with the
  // existing canonical Company Brain and normalized-entity projections.
  const [refreshSignal, setRefreshSignal] = useState(0);

  return (
    <>
      <PageHeader
        eyebrow={M.companyBrainPage.eyebrow}
        title={M.companyBrainPage.title}
        description={M.companyBrainPage.description}
      />
      <div className="actions-row">
        <button
          className="button secondary"
          onClick={() => setRefreshSignal((current) => current + 1)}
          type="button"
        >
          {M.common.refreshStatus}
        </button>
      </div>
      <CompanyWorldPanel refreshSignal={refreshSignal} />
      <section className="dashboard-layer">
        <header className="layer-heading">
          <span aria-hidden="true">{M.companyBrainPage.dataLayerIndex}</span>
          <div>
            <h2>{M.companyBrainPage.dataLayerTitle}</h2>
            <p>{M.companyBrainPage.dataLayerDescription}</p>
          </div>
        </header>
        <div className="operations-stack">
          <CompanyBrainPanel refreshSignal={refreshSignal} />
          <NormalizedEntitiesPanel refreshSignal={refreshSignal} />
        </div>
      </section>
    </>
  );
}
