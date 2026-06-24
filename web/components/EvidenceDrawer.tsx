import type { BriefingEvidenceRef } from "../lib/types";

type EvidenceDrawerProps = {
  evidence: BriefingEvidenceRef | null;
  itemTitle?: string | null;
  onClose?: () => void;
};

export function EvidenceDrawer({
  evidence,
  itemTitle = null,
  onClose
}: EvidenceDrawerProps) {
  return (
    <aside className="evidence-drawer" aria-labelledby="evidence-drawer-title">
      <div className="section-header">
        <div>
          <span className="eyebrow">Evidence</span>
          <h2 id="evidence-drawer-title">Source detail</h2>
        </div>
        {onClose ? (
          <button className="button secondary" onClick={onClose} type="button">
            Close
          </button>
        ) : null}
      </div>

      {evidence ? (
        <dl className="work-meta">
          <div>
            <dt>Label</dt>
            <dd>{evidence.ref || itemTitle || "Unknown source"}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{evidence.source || "unknown"}</dd>
          </div>
          <div>
            <dt>Kind</dt>
            <dd>{evidence.kind || "unknown"}</dd>
          </div>
          <div>
            <dt>Record</dt>
            <dd>{evidence.ref || "No record id returned"}</dd>
          </div>
          <div>
            <dt>Snippet</dt>
            <dd>No snippet returned by backend.</dd>
          </div>
        </dl>
      ) : (
        <p className="muted">
          Select an evidence ref to inspect provider, source, record, and URL details.
        </p>
      )}

      {evidence?.url ? (
        <a className="source-link" href={evidence.url} rel="noreferrer" target="_blank">
          Open source
        </a>
      ) : null}
    </aside>
  );
}
