import { ActionProposalsPanel } from "../../components/ActionProposalsPanel";

type ActionsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ActionsPage({ searchParams }: ActionsPageProps) {
  const params = searchParams ? await searchParams : {};
  const auditSource = firstSearchParam(params.audit_source);
  const origin = firstSearchParam(params.origin);
  const status = firstSearchParam(params.status);

  return (
    <ActionProposalsPanel
      initialAuditSourceFilter={auditSource}
      initialOriginFilter={origin}
      initialStatusFilter={status}
    />
  );
}

function firstSearchParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
}
