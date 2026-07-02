import { PageHeader } from "../../components/PageHeader";
import { RepositoryAuditPanel } from "../../components/RepositoryAuditPanel";
import { M } from "../../lib/messages";

export default function AuditPage() {
  return (
    <>
      <PageHeader
        eyebrow={M.repoAudit.eyebrow}
        title={M.repoAudit.title}
        description={M.repoAudit.intro}
      />
      <RepositoryAuditPanel />
    </>
  );
}
