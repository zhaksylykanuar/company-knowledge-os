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
          value="Placeholder"
        />
        <StatusCard
          description="Reads local repository inventory through the backend."
          title="Repositories"
          value="Placeholder"
        />
        <StatusCard
          description="Manual SyncJob records are local until worker scope exists."
          title="Sync jobs"
          value="Placeholder"
        />
        <StatusCard
          description="Projection mode only; persistent graph upsert is deferred."
          title="Local normalization"
          value="Placeholder"
        />
      </section>
      <EmptyState
        description="FOS-FE-02 will wire these panels to the existing backend APIs."
        title="No frontend API calls are wired in this scaffold."
      />
    </>
  );
}
