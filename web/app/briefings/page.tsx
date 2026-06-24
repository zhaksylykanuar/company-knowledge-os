import { BriefingPanel } from "../../components/BriefingPanel";
import { PageHeader } from "../../components/PageHeader";

export default function BriefingsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Briefings"
        title="Manual Founder Briefing"
        description="The backend has a deterministic manual briefing endpoint for local workspace signals."
      />
      <BriefingPanel />
    </>
  );
}
