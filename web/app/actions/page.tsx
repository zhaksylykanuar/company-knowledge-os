import { ActionProposalsPanel } from "../../components/ActionProposalsPanel";
import { PageHeader } from "../../components/PageHeader";
import { M } from "../../lib/messages";

export default function ActionsPage() {
  return (
    <>
      <PageHeader
        eyebrow={M.actionsPage.eyebrow}
        title={M.actionsPage.title}
        description={M.actionsPage.description}
      />
      <ActionProposalsPanel />
    </>
  );
}
