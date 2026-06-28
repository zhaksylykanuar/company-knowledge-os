import { BriefingPanel } from "../../components/BriefingPanel";
import { PageHeader } from "../../components/PageHeader";
import { M } from "../../lib/messages";

export default function BriefingsPage() {
  return (
    <>
      <PageHeader
        eyebrow={M.briefingsPage.eyebrow}
        title={M.briefingsPage.title}
        description={M.briefingsPage.description}
      />
      <BriefingPanel />
    </>
  );
}
