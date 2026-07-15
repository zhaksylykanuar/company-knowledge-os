import type { CompanyMapResponse } from "./types";

const COMPANY_WORLD_PATH = "/company-brain";
const COMPANY_WORLD_PROFILE_ANCHOR = "company-world-profile";
const COMPANY_WORLD_PROFILE_PARAM = "profile";
const MAX_PROFILE_SELECTOR_LENGTH = 512;

export type CompanyWorldProfileTarget = {
  href: string;
  selectedKey: string;
  selector: string;
};

/**
 * Build a deep link without putting raw Company Map keys into browser history.
 *
 * Candidate keys may contain an email address or domain. The selector therefore
 * uses only workspace-scoped opaque ids and evidence-version hashes; the current
 * CompanyMapResponse remains the authority that resolves it back to a profile.
 */
export function buildCompanyWorldProfileTarget(
  data: CompanyMapResponse,
  selectedKey: string
): CompanyWorldProfileTarget | null {
  const selector = profileSelectorForKey(data, selectedKey);
  if (!selector) {
    return null;
  }
  const params = new URLSearchParams();
  params.set(COMPANY_WORLD_PROFILE_PARAM, selector);
  return {
    href: `${COMPANY_WORLD_PATH}?${params.toString()}#${COMPANY_WORLD_PROFILE_ANCHOR}`,
    selectedKey,
    selector
  };
}

export function readCompanyWorldProfileSelector(search: string): string | null {
  return normalizeCompanyWorldProfileSelector(
    new URLSearchParams(search).get(COMPANY_WORLD_PROFILE_PARAM)
  );
}

export function normalizeCompanyWorldProfileSelector(
  selector: string | null
): string | null {
  if (
    !selector ||
    selector.length > MAX_PROFILE_SELECTOR_LENGTH ||
    /[\u0000-\u001f\u007f]/.test(selector)
  ) {
    return null;
  }
  return selector;
}

export function resolveCompanyWorldProfileSelector(
  data: CompanyMapResponse,
  selector: string | null
): string | null {
  const normalizedSelector = normalizeCompanyWorldProfileSelector(selector);
  if (!normalizedSelector) {
    return null;
  }

  const keys = [
    data.company.key,
    ...data.people.internal.map((person) => person.key),
    ...data.people.confirmed_external.map((person) => person.key),
    ...data.people.external_candidates.map((person) => person.key),
    ...data.confirmed_organizations.map((organization) => organization.key),
    ...data.organizations.map((organization) => organization.key)
  ];
  return (
    keys.find((key) => profileSelectorForKey(data, key) === normalizedSelector) ?? null
  );
}

function profileSelectorForKey(
  data: CompanyMapResponse,
  selectedKey: string
): string | null {
  if (selectedKey === data.company.key) {
    return "v1:company";
  }

  const member = data.people.internal.find((person) => person.key === selectedKey);
  if (member) {
    return `v1:member:${member.user_id}`;
  }

  const confirmedPerson = data.people.confirmed_external.find(
    (person) => person.key === selectedKey
  );
  if (confirmedPerson) {
    return `v1:person:${confirmedPerson.person_id}`;
  }

  const personCandidate = data.people.external_candidates.find(
    (person) => person.key === selectedKey
  );
  if (personCandidate) {
    return `v1:person-candidate:${personCandidate.candidate_version}`;
  }

  const confirmedOrganization = data.confirmed_organizations.find(
    (organization) => organization.key === selectedKey
  );
  if (confirmedOrganization) {
    return `v1:organization:${confirmedOrganization.organization_id}`;
  }

  const organizationCandidate = data.organizations.find(
    (organization) => organization.key === selectedKey
  );
  if (organizationCandidate) {
    return `v1:organization-candidate:${organizationCandidate.candidate_version}`;
  }

  return null;
}
