import { M } from "../lib/messages";
import type { BriefingEvidenceRef } from "../lib/types";
import { SourceLink } from "./SourceLink";

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
          <span className="eyebrow">{M.evidence.eyebrow}</span>
          <h2 id="evidence-drawer-title">{M.evidence.title}</h2>
        </div>
        {onClose ? (
          <button className="button secondary" onClick={onClose} type="button">
            {M.common.close}
          </button>
        ) : null}
      </div>

      {evidence ? (
        <dl className="work-meta">
          <div>
            <dt>{M.evidence.label}</dt>
            <dd>{evidence.ref || itemTitle || M.evidence.unknownSource}</dd>
          </div>
          <div>
            <dt>{M.evidence.source}</dt>
            <dd>{evidence.source || M.common.unknown}</dd>
          </div>
          <div>
            <dt>{M.evidence.kind}</dt>
            <dd>{evidence.kind || M.common.unknown}</dd>
          </div>
          <div>
            <dt>{M.evidence.record}</dt>
            <dd>{evidence.ref || M.evidence.noRecordId}</dd>
          </div>
          <div>
            <dt>{M.evidence.snippet}</dt>
            <dd>{M.evidence.noSnippet}</dd>
          </div>
        </dl>
      ) : (
        <p className="muted">{M.evidence.placeholder}</p>
      )}

      {evidence?.url ? (
        <SourceLink url={evidence.url}>{M.common.openSource}</SourceLink>
      ) : null}
    </aside>
  );
}
