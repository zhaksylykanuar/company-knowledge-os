"use client";

import { useState } from "react";

import { CompanyBrainPanel } from "../../components/CompanyBrainPanel";
import { NormalizedEntitiesPanel } from "../../components/NormalizedEntitiesPanel";
import { PageHeader } from "../../components/PageHeader";
import { M } from "../../lib/messages";

export default function CompanyBrainPage() {
  // A dedicated, navigable Company Brain view (playbook §1.4 "See Company Brain
  // entities" / §1.5 "Company Brain view"). It composes the existing read-only
  // panels so the founder can reach the canonical evidence-backed view without
  // scrolling the dashboard or using the terminal. No new data path is added.
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
      <CompanyBrainPanel refreshSignal={refreshSignal} />
      <NormalizedEntitiesPanel refreshSignal={refreshSignal} />
    </>
  );
}
