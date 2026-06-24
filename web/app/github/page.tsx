import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";

export default function GitHubPage() {
  return (
    <>
      <PageHeader
        eyebrow="GitHub"
        title="GitHub backend flow"
        description="Workspace-scoped MVP panels for the existing backend contracts."
      />
      <section className="grid">
        <StatusCard
          description="Reads /api/v1/workspaces/{workspace_id}/github/connection-status."
          title="Connection status"
          value="Backend"
        />
        <StatusCard
          description="Reads local repository inventory through the backend."
          title="Repositories"
          value="Backend"
        />
        <StatusCard
          description="Manual SyncJob records are local until worker scope exists."
          title="Sync jobs"
          value="Manual"
        />
        <StatusCard
          description="Canonical repository, issue, and PR persistence is visible on the dashboard."
          title="Local normalization"
          value="Canonical"
        />
      </section>
      <EmptyState
        description="The dashboard now reads canonical GitHub operational work. These connection and sync controls remain scaffolded until product connect/sync scope."
        title="GitHub flow controls are still local MVP scaffolding."
      />
    </>
  );
}
