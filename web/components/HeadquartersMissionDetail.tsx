"use client";

import { useId } from "react";

import type {
  HeadquartersEvidenceRef,
  HeadquartersMission
} from "../lib/headquarters";
import { HeadquartersActionControl } from "./HeadquartersActionControl";
import { SourceLink } from "./SourceLink";

export function HeadquartersMissionDetail({
  mission,
  onOpenDecision,
  onOpenProfile,
  position
}: {
  mission: HeadquartersMission;
  onOpenDecision?: (mission: HeadquartersMission) => void;
  onOpenProfile?: (selector: string, label: string) => void;
  position: "priority" | "queue";
}) {
  const profileTargets = missionProfileTargets(mission);
  return (
    <div className="headquarters-drawer-content headquarters-mission-detail">
      <span className="headquarters-drawer-kicker">
        {position === "priority" ? "Главный ход" : "Следующий ход"} · {mission.id}
      </span>
      <h3>{mission.title}</h3>
      <p className="headquarters-drawer-lead">{mission.summary}</p>

      <dl className="headquarters-mission-facts">
        <MissionFact
          evidence={[]}
          label="Почему сейчас"
          value={mission.why_now || null}
        />
        <MissionFact
          evidence={mission.fact_provenance.impact}
          label="Ожидаемый эффект"
          value={
            hasVerifiedFieldProvenance(mission.fact_provenance.impact)
              ? mission.impact
              : null
          }
        />
        <MissionFact
          evidence={mission.fact_provenance.due}
          label="Срок"
          value={
            hasVerifiedFieldProvenance(mission.fact_provenance.due)
              ? formatMissionDate(mission.due_at)
              : null
          }
        />
        <MissionFact
          evidence={mission.fact_provenance.owner}
          label="Ответственный"
          value={
            mission.owner_person_ids.length > 0 &&
            hasVerifiedFieldProvenance(mission.fact_provenance.owner)
              ? "Подтверждён"
              : null
          }
        />
        <MissionFact
          evidence={mission.fact_provenance.customer}
          label="Заказчик"
          value={
            mission.organization_id &&
            hasVerifiedFieldProvenance(mission.fact_provenance.customer)
              ? "Подтверждён"
              : null
          }
        />
        <MissionFact
          evidence={[]}
          label="Источники"
          value={mission.source_keys.length > 0 ? mission.source_keys.join(", ") : null}
        />
      </dl>

      {profileTargets.length > 0 ? (
        <section className="headquarters-mission-profiles" aria-label="Связанные профили">
          <strong>Связанные профили</strong>
          <div>
            {profileTargets.map((target) => (
              <button
                key={`${target.selector}:${target.label}`}
                onClick={() => onOpenProfile?.(target.selector, target.label)}
                type="button"
              >
                {target.label}<span aria-hidden="true">→</span>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <EvidenceList evidence={mission.evidence_refs} heading="Основания миссии" />

      {mission.proposal_id && onOpenDecision ? (
        <button
          className="headquarters-primary-action"
          onClick={() => onOpenDecision(mission)}
          type="button"
        >
          <span>Открыть точное решение</span><span aria-hidden="true">→</span>
        </button>
      ) : (
        <HeadquartersActionControl action={mission.action} />
      )}
      {!mission.action.enabled && mission.action.disabled_reason ? (
        <p className="headquarters-disabled-reason">{mission.action.disabled_reason}</p>
      ) : null}
    </div>
  );
}

export function EvidenceList({
  evidence,
  heading = "Основания"
}: {
  evidence: HeadquartersEvidenceRef[];
  heading?: string;
}) {
  const reactId = useId();
  const headingId = `headquarters-evidence-${reactId.replaceAll(":", "")}`;
  return (
    <section className="headquarters-evidence-list" aria-labelledby={headingId}>
      <header>
        <h3 id={headingId}>{heading}</h3>
        <span>{evidence.length}</span>
      </header>
      {evidence.length > 0 ? (
        <ul>
          {evidence.map((item) => (
            <li key={item.id}>
              <span className="headquarters-evidence-trust" data-trust={item.trust}>
                {item.trust === "verified" ? "✓" : "≈"}
              </span>
              <span>
                {item.target ? (
                  <SourceLink url={item.target}>{item.label}</SourceLink>
                ) : (
                  <strong>{item.label}</strong>
                )}
                <small>{evidenceSourceLabel(item.source_key)} · {evidenceTrustLabel(item.trust)}</small>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p>Подтверждённых оснований для этого поля нет.</p>
      )}
    </section>
  );
}

export function missionProfileTargets(mission: HeadquartersMission): Array<{
  label: string;
  selector: string;
}> {
  const targets: Array<{ label: string; selector: string }> = [];
  if (hasVerifiedFieldProvenance(mission.fact_provenance.owner)) {
    for (const personId of mission.owner_person_ids) {
      targets.push({ label: "Ответственный", selector: `v1:person:${personId}` });
    }
  }
  if (
    mission.primary_person_id &&
    hasVerifiedFieldProvenance(mission.fact_provenance.customer)
  ) {
    targets.push({ label: "Ключевое лицо", selector: `v1:person:${mission.primary_person_id}` });
  }
  if (
    mission.organization_id &&
    hasVerifiedFieldProvenance(mission.fact_provenance.customer)
  ) {
    targets.push({ label: "Компания-заказчик", selector: `v1:organization:${mission.organization_id}` });
  }
  const actionSelector = profileSelectorFromTarget(mission.action.target);
  if (mission.reference_type === "world" && actionSelector) {
    targets.push({ label: "Найденный профиль", selector: actionSelector });
  }
  const seen = new Set<string>();
  return targets.filter((target) => {
    if (seen.has(target.selector)) return false;
    seen.add(target.selector);
    return true;
  });
}

export function profileSelectorFromTarget(target: string | null): string | null {
  if (!target || !target.startsWith("/company-brain?")) return null;
  try {
    const url = new URL(target, "http://founderos.local");
    const selector = url.searchParams.get("profile");
    return selector?.startsWith("v1:") ? selector : null;
  } catch {
    return null;
  }
}

function MissionFact({
  evidence,
  label,
  value
}: {
  evidence: HeadquartersEvidenceRef[];
  label: string;
  value: string | null;
}) {
  const verified = hasVerifiedFieldProvenance(evidence);
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value ?? "Не определено"}</dd>
      {evidence.length > 0 ? (
        <details className="headquarters-field-evidence">
          <summary>
            {verified
              ? `${evidence.length} подтверждённых оснований поля`
              : `${evidence.length} агрегированных сигналов поля`}
          </summary>
          <ul>
            {evidence.map((item) => (
              <li key={item.id}>
                {item.target ? (
                  <SourceLink url={item.target}>{item.label}</SourceLink>
                ) : (
                  <strong>{item.label}</strong>
                )}
                <small>
                  {evidenceSourceLabel(item.source_key)} · {evidenceTrustLabel(item.trust)}
                </small>
              </li>
            ))}
          </ul>
        </details>
      ) : label !== "Почему сейчас" && label !== "Источники" ? (
        <small>Поле не подтверждено отдельным основанием</small>
      ) : null}
    </div>
  );
}

function hasVerifiedFieldProvenance(
  evidence: HeadquartersEvidenceRef[]
): boolean {
  return evidence.length > 0 && evidence.every((item) => item.trust === "verified");
}

function formatMissionDate(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? null
    : new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium" }).format(date);
}

function evidenceSourceLabel(source: HeadquartersEvidenceRef["source_key"]): string {
  const labels: Record<HeadquartersEvidenceRef["source_key"], string> = {
    drive: "Drive",
    github: "GitHub",
    gmail: "Gmail",
    internal: "FounderOS",
    jira: "Jira"
  };
  return labels[source];
}

function evidenceTrustLabel(trust: HeadquartersEvidenceRef["trust"]): string {
  return trust === "verified" ? "точное основание" : "агрегат снимка";
}
