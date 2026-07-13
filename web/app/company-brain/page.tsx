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
      <details className="company-data-vault">
        <summary>
          <span aria-hidden="true">{M.companyBrainPage.dataLayerIndex}</span>
          <span>
            <strong>{M.companyBrainPage.dataLayerTitle}</strong>
            <small>{M.companyBrainPage.dataLayerDescription}</small>
          </span>
        </summary>
        <div className="operations-stack company-data-vault-body">
          <CompanyBrainPanel refreshSignal={refreshSignal} />
          <NormalizedEntitiesPanel refreshSignal={refreshSignal} />
        </div>
      </details>
    </>
  );
}
