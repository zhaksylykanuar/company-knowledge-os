import { useEffect, useState, type RefObject } from "react";

import type {
  HeadquartersOnboardingEvidence,
  HeadquartersOnboardingState,
  HeadquartersOnboardingStep,
  HeadquartersSnapshotResponse
} from "../lib/headquarters";
import { HeadquartersActionControl } from "./HeadquartersActionControl";
import { OverlayShell } from "./OverlayShell";

export function HeadquartersOnboardingModal({
  backgroundRef,
  onClose,
  onFinish,
  onRetry,
  snapshot
}: {
  backgroundRef: RefObject<HTMLDivElement | null>;
  onClose: () => void;
  onFinish: () => void;
  onRetry?: () => void;
  snapshot: HeadquartersSnapshotResponse;
}) {
  const onboarding = snapshot.onboarding;
  const defaultStepKey = onboarding.current_step_key ?? "headquarters";
  const [activeKey, setActiveKey] = useState<HeadquartersOnboardingStep["key"]>(
    defaultStepKey
  );
  useEffect(() => {
    void snapshot.snapshot.id;
    setActiveKey(defaultStepKey);
  }, [defaultStepKey, snapshot.snapshot.id]);
  const activeStep = onboarding.steps.find((step) => step.key === activeKey);

  if (!activeStep) {
    return null;
  }

  return (
    <OverlayShell
      backgroundRef={backgroundRef}
      closeLabel="Свернуть настройку"
      label="Запуск компании"
      mode="modal"
      onClose={onClose}
    >
      <div className="headquarters-onboarding">
        <header className="headquarters-onboarding-summary">
          <span>
            {onboarding.ready
              ? "Обязательные шаги завершены"
              : `Готово ${onboarding.completed_required} из ${onboarding.required_total} обязательных`}
          </span>
          <strong>{onboarding.completed_count}/{onboarding.total_count}</strong>
        </header>

        <ol
          aria-label="Пять шагов запуска FounderOS"
          className="headquarters-onboarding-steps"
        >
          {onboarding.steps.map((step, index) => (
            <li
              data-selected={step.key === activeStep.key}
              data-state={step.state}
              key={step.key}
            >
              <button
                aria-current={step.key === activeStep.key ? "step" : undefined}
                aria-label={`${shortStepLabel(step.key)}: ${railStateLabel(step.state)}`}
                onClick={() => setActiveKey(step.key)}
                type="button"
              >
                <span aria-hidden="true">
                  {step.state === "complete"
                    ? "✓"
                    : String(index + 1).padStart(2, "0")}
                </span>
                <small>{shortStepLabel(step.key)}</small>
              </button>
            </li>
          ))}
        </ol>

        <section
          aria-live="polite"
          className="headquarters-onboarding-stage"
          data-state={activeStep.state}
        >
          <div className="headquarters-onboarding-status">
            <span aria-hidden="true">{stateIcon(activeStep.state)}</span>
            {stateLabel(
              activeStep.state,
              onboarding.ready && activeStep.key === "headquarters",
              activeStep.key === onboarding.current_step_key
            )}
          </div>
          <p className="headquarters-onboarding-kicker">
            {activeStep.requirement === "required"
              ? "Обязательный шаг"
              : "Дополнительный шаг"}
          </p>
          <h3>
            {onboarding.ready && activeStep.key === "headquarters"
              ? "FounderOS готов к работе"
              : activeStep.label}
          </h3>
          <p className="headquarters-onboarding-benefit">{activeStep.benefit}</p>

          <div className="headquarters-onboarding-action">
            {onboarding.ready && activeStep.key === "headquarters" ? (
              <button
                className="headquarters-primary-action"
                onClick={onFinish}
                type="button"
              >
                <span>Открыть текущую картину</span><span aria-hidden="true">→</span>
              </button>
            ) : activeStep.state === "unknown" ? (
              <button
                className="headquarters-primary-action"
                disabled={!onRetry}
                onClick={onRetry}
                type="button"
              >
                <span>Проверить снова</span><span aria-hidden="true">↻</span>
              </button>
            ) : (
              <HeadquartersActionControl action={activeStep.action} />
            )}
            {!activeStep.action.enabled &&
            activeStep.action.disabled_reason ? (
              <p className="headquarters-disabled-reason">
                {activeStep.action.disabled_reason}
              </p>
            ) : null}
          </div>

          <details className="headquarters-onboarding-details">
            <summary>Подробнее</summary>
            <p>
              Галочка появляется только после серверной проверки текущего снимка.
              Пропуск и недоступность данных не считаются завершением.
            </p>
            <ul>
              {activeStep.evidence.map((item) => (
                <OnboardingEvidenceItem evidence={item} key={item.key} />
              ))}
            </ul>
          </details>
        </section>

        <p className="headquarters-onboarding-boundary">
          Проверка использует ту же картину компании только для чтения. Она не запускает
          провайдеров, LLM или внешние записи.
        </p>
      </div>
    </OverlayShell>
  );
}

function OnboardingEvidenceItem({
  evidence
}: {
  evidence: HeadquartersOnboardingEvidence;
}) {
  return (
    <li data-state={evidence.state}>
      <span aria-hidden="true">{stateIcon(evidence.state)}</span>
      <span>
        <strong>{evidence.label}</strong>
        <small>{evidenceValue(evidence)}</small>
      </span>
    </li>
  );
}

function evidenceValue(evidence: HeadquartersOnboardingEvidence): string {
  if (evidence.value === null || evidence.precision === "unavailable") {
    return "Не удалось подтвердить";
  }
  return `Подтверждено: ${evidence.value}`;
}

function stateIcon(state: HeadquartersOnboardingState): string {
  if (state === "complete") return "✓";
  if (state === "unknown") return "?";
  return "•";
}

function stateLabel(
  state: HeadquartersOnboardingState,
  readyView: boolean,
  isCurrentStep: boolean
): string {
  if (readyView || state === "complete") return "Подтверждено сервером";
  if (state === "unknown") return "Состояние пока неизвестно";
  return isCurrentStep ? "Следующий реальный шаг" : "Можно улучшить позже";
}

function railStateLabel(state: HeadquartersOnboardingState): string {
  if (state === "complete") return "подтверждено";
  if (state === "unknown") return "не удалось проверить";
  return "ещё не завершено";
}

function shortStepLabel(key: HeadquartersOnboardingStep["key"]): string {
  const labels: Record<HeadquartersOnboardingStep["key"], string> = {
    canonical_data: "Факты",
    company: "Компания",
    context: "Контекст",
    headquarters: "FounderOS",
    source: "Источник"
  };
  return labels[key];
}
