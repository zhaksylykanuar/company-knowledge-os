import { PageHeader } from "../../components/PageHeader";
import { StatusCard } from "../../components/StatusCard";

export default function ActionsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Actions"
        title="Human-approved action boundary"
        description="Action proposals move through proposed, approved, and executed states."
      />
      <section className="callout">
        Execution requires explicit approval and confirmation through the backend.
      </section>
      <section className="grid">
        <StatusCard
          description="New proposed actions await human review."
          title="Proposed"
          value="Placeholder"
        />
        <StatusCard
          description="Approved actions are eligible for guarded execution."
          title="Approved"
          value="Placeholder"
        />
        <StatusCard
          description="Executions are tracked by backend ActionExecution records."
          title="Executed"
          value="Placeholder"
        />
      </section>
    </>
  );
}
