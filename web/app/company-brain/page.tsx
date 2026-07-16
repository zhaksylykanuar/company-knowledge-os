import { CompanyBrainPageClient } from "../../components/CompanyBrainPageClient";
import { normalizeCompanyWorldProfileSelector } from "../../lib/company-world-profile";

type CompanyBrainPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function CompanyBrainPage({
  searchParams
}: CompanyBrainPageProps) {
  const params = searchParams ? await searchParams : {};
  const rawProfile = Array.isArray(params.profile)
    ? params.profile[0] ?? null
    : params.profile ?? null;

  return (
    <CompanyBrainPageClient
      profileSelector={normalizeCompanyWorldProfileSelector(rawProfile)}
      profileSelectorRequested={rawProfile !== null}
    />
  );
}
