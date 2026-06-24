import { ActionProposalsPanel } from "../../components/ActionProposalsPanel";
import { PageHeader } from "../../components/PageHeader";

export default function ActionsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Actions"
        title="Human-approved action boundary"
        description="Action proposals move through local proposed, approved, and rejected states without external execution."
      />
      <ActionProposalsPanel />
    </>
  );
}
