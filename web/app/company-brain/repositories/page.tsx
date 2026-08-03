import { RepositoryIntelligencePageClient } from "../../../components/RepositoryIntelligencePageClient";
import { normalizeRepositoryIntelligenceRepositoryId } from "../../../lib/repository-intelligence";

type RepositoryIntelligencePageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function RepositoryIntelligencePage({
  searchParams
}: RepositoryIntelligencePageProps) {
  const params = searchParams ? await searchParams : {};
  const rawRepository = Array.isArray(params.repository)
    ? params.repository[0] ?? null
    : params.repository ?? null;

  return (
    <RepositoryIntelligencePageClient
      initialRepositoryId={normalizeRepositoryIntelligenceRepositoryId(
        rawRepository
      )}
    />
  );
}
