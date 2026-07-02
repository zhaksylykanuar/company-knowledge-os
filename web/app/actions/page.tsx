import { ActionProposalsPanel } from "../../components/ActionProposalsPanel";
import { PageHeader } from "../../components/PageHeader";
import { M } from "../../lib/messages";

type ActionsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ActionsPage({ searchParams }: ActionsPageProps) {
  const params = searchParams ? await searchParams : {};
  const origin = firstSearchParam(params.origin);
  const status = firstSearchParam(params.status);

  return (
    <>
      <PageHeader
        eyebrow={M.actionsPage.eyebrow}
        title={M.actionsPage.title}
        description={M.actionsPage.description}
      />
      <ActionProposalsPanel
        initialOriginFilter={origin}
        initialStatusFilter={status}
      />
    </>
  );
}

function firstSearchParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
}
