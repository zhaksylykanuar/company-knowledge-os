import { ActionProposalsPanel } from "../../components/ActionProposalsPanel";

type ActionsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

const PROPOSAL_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default async function ActionsPage({ searchParams }: ActionsPageProps) {
  const params = searchParams ? await searchParams : {};
  const auditSource = firstSearchParam(params.audit_source);
  const origin = firstSearchParam(params.origin);
  const proposal = normalizeProposalId(firstSearchParam(params.proposal));
  const status = firstSearchParam(params.status);

  return (
    <ActionProposalsPanel
      initialAuditSourceFilter={auditSource}
      initialOriginFilter={origin}
      initialProposalId={proposal}
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

function normalizeProposalId(value: string | null): string | null {
  const candidate = value?.trim() ?? "";
  return PROPOSAL_ID_PATTERN.test(candidate) ? candidate : null;
}
