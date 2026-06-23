import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";

export default function BriefingsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Briefings"
        title="Manual Founder Briefing"
        description="The backend has a deterministic manual briefing endpoint for local workspace signals."
      />
      <section className="panel">
        <button className="button" disabled type="button">
          Generate briefing
        </button>
      </section>
      <EmptyState
        description="Briefing results will appear here after FOS-FE-02 wires the backend call."
        title="No briefing loaded"
      />
    </>
  );
}
