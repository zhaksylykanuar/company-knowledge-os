"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import type { AuthWorkspace } from "../../lib/auth";
import { logout } from "../../lib/auth";
import type {
  OnboardingCheckState,
  OnboardingProgress
} from "../../lib/onboarding";
import {
  deriveOnboardingProgress,
  firstIncompleteRequiredStep,
  loadOnboardingSnapshot,
  onboardingStepFromHash,
  ONBOARDING_STEP_IDS
} from "../../lib/onboarding";
import { useSession } from "../../lib/session";
import styles from "./onboarding.module.css";

const JOURNEY = [
  { id: "welcome", label: "Добро пожаловать" },
  { id: "company", label: "Ваша компания" },
  { id: "source", label: "Первые данные" },
  { id: "map", label: "Первая карта" },
  { id: "team", label: "Команда" },
  { id: "ready", label: "Можно начинать" }
] as const;

type OnboardingJourneyViewProps = {
  workspace: AuthWorkspace;
  progress: OnboardingProgress;
  activeStep: number;
  onChangeStep: (step: number) => void;
  onRefresh: () => void;
};

function stateLabel(state: OnboardingCheckState): string {
  if (state === "complete") {
    return "Готово";
  }
  if (state === "unknown") {
    return "Не удалось проверить";
  }
  return "Следующий шаг";
}

function StateBadge({ state }: { state: OnboardingCheckState }) {
  return (
    <span className={styles.stateBadge} data-state={state}>
      <span aria-hidden="true">
        {state === "complete" ? "✓" : state === "unknown" ? "?" : "•"}
      </span>
      {stateLabel(state)}
    </span>
  );
}

function StepBody({
  activeStep,
  workspace,
  progress,
  onChangeStep,
  onRefresh
}: OnboardingJourneyViewProps) {
  const next = () => onChangeStep(Math.min(activeStep + 1, JOURNEY.length - 1));
  const canManageWorkspace = workspace.role === "owner" || workspace.role === "admin";

  if (activeStep === 0) {
    return (
      <>
        <p className={styles.kicker}>Добро пожаловать</p>
        <h1>За несколько минут компания станет понятной.</h1>
        <p className={styles.lead}>
          FounderOS не просит изучать админку. Мы пройдём по компании как по живой
          карте: сначала контекст, затем люди и только потом решения.
        </p>
        <div className={styles.promiseGrid}>
          <div><strong>01</strong><span>Загрузим первые реальные данные</span></div>
          <div><strong>02</strong><span>Соберём людей и компании</span></div>
          <div><strong>03</strong><span>Покажем один следующий ход</span></div>
        </div>
        <button className={styles.primaryAction} onClick={next} type="button">
          Показать мою компанию
        </button>
      </>
    );
  }

  if (activeStep === 1) {
    const check = progress.checks.company;
    return (
      <>
        <StateBadge state={check.state} />
        <p className={styles.kicker}>Ваша компания</p>
        <h1>{workspace.name}</h1>
        <p className={styles.lead}>
          Это ваш отдельный мир в FounderOS. Данные других компаний сюда не попадут.
        </p>
        <div className={styles.factCard}>
          <span>Рабочее пространство</span>
          <strong>{workspace.name}</strong>
          <small>{check.evidence}</small>
        </div>
        <button className={styles.primaryAction} onClick={next} type="button">
          Всё верно
        </button>
      </>
    );
  }

  if (activeStep === 2) {
    const check = progress.checks.source;
    return (
      <>
        <StateBadge state={check.state} />
        <p className={styles.kicker}>Первые данные</p>
        <h1>
          {check.state === "complete"
            ? "Контекст уже поступает."
            : "Откуда FounderOS узнает правду?"}
        </h1>
        <p className={styles.lead}>
          {canManageWorkspace
            ? "Выберите GitHub для чтения или загрузите экспорт Jira, Gmail либо Drive. FounderOS назовёт данные загруженными только после реальной записи и не запустит внешнее действие сам."
            : "Посмотрите доступные данные. Подключение и загрузка доступны только владельцу или администратору; просмотр не запускает внешних действий."}
        </p>
        <div className={styles.evidenceCard} data-state={check.state}>
          <span>Проверено по данным системы</span>
          <strong>{check.evidence}</strong>
        </div>
        {check.state === "unknown" ? (
          <button className={styles.primaryAction} onClick={onRefresh} type="button">
            Проверить ещё раз
          </button>
        ) : check.state === "complete" ? (
          <button className={styles.primaryAction} onClick={next} type="button">
            Посмотреть первую карту
          </button>
        ) : (
          <Link className={styles.primaryAction} href="/connectors">
            {canManageWorkspace ? "Добавить первые данные" : "Посмотреть данные"}
          </Link>
        )}
        {check.state !== "complete" ? (
          <button className={styles.textAction} onClick={next} type="button">
            Пока продолжить без источника
          </button>
        ) : null}
      </>
    );
  }

  if (activeStep === 3) {
    const check = progress.checks.map;
    return (
      <>
        <StateBadge state={check.state} />
        <p className={styles.kicker}>Первая карта</p>
        <h1>
          {check.state === "complete"
            ? "Компания уже обрела форму."
            : "Карта вырастет из фактов."}
        </h1>
        <p className={styles.lead}>
          Здесь появятся сотрудники, ключевые лица заказчиков, компании и реальные
          соприкосновения. FounderOS не придумывает отсутствующие связи.
        </p>
        <div className={styles.mapPreview} aria-label="Состояние карты компании">
          <span className={styles.companyNode}>{workspace.name}</span>
          <span className={styles.personNode}>Вы</span>
          <span className={styles.futureNode}>Следующий контакт</span>
        </div>
        <p className={styles.evidenceLine}>{check.evidence}</p>
        {check.state === "unknown" ? (
          <>
            <button className={styles.primaryAction} onClick={onRefresh} type="button">
              Проверить ещё раз
            </button>
            <button className={styles.textAction} onClick={next} type="button">
              Пока продолжить без проверки
            </button>
          </>
        ) : (
          <button className={styles.primaryAction} onClick={next} type="button">
            Продолжить
          </button>
        )}
        <Link className={styles.textAction} href="/company-brain">
          Открыть карту целиком
        </Link>
      </>
    );
  }

  if (activeStep === 4) {
    const check = progress.checks.team;
    return (
      <>
        <StateBadge state={check.state} />
        <p className={styles.kicker}>Команда</p>
        <h1>
          {check.state === "complete"
            ? "Вы уже не один."
            : "Кому ещё нужна эта картина?"}
        </h1>
        <p className={styles.lead}>
          {canManageWorkspace
            ? "Добавьте человека, который принимает решения вместе с вами. Уровень доступа задаётся отдельно, а приглашение не отправляется во внешние сервисы само."
            : "Посмотрите, кто уже входит в рабочее пространство. Менять состав может только владелец или администратор."}
        </p>
        <div className={styles.evidenceCard} data-state={check.state}>
          <span>Состав рабочего пространства</span>
          <strong>{check.evidence}</strong>
        </div>
        {check.state === "unknown" ? (
          <>
            <button className={styles.primaryAction} onClick={onRefresh} type="button">
              Проверить ещё раз
            </button>
            <button className={styles.textAction} onClick={next} type="button">
              Продолжить без изменений
            </button>
          </>
        ) : check.state === "complete" ? (
          <button className={styles.primaryAction} onClick={next} type="button">
            Завершить настройку
          </button>
        ) : (
          <Link className={styles.primaryAction} href="/settings">
            {canManageWorkspace ? "Добавить человека" : "Посмотреть команду"}
          </Link>
        )}
        {check.state !== "complete" ? (
          <button className={styles.textAction} onClick={next} type="button">
            {canManageWorkspace ? "Пока работать одному" : "Продолжить без изменений"}
          </button>
        ) : null}
      </>
    );
  }

  const check = progress.checks.ready;
  return (
    <>
      <StateBadge state={check.state} />
      <p className={styles.kicker}>Можно начинать</p>
      <h1>{progress.ready ? "Система видит вашу компанию." : "Начало положено."}</h1>
      <p className={styles.lead}>
        {progress.ready
          ? "Основной контекст подтверждён данными. На экране «Сегодня» FounderOS покажет один следующий ход."
          : "FounderOS уже доступен, но незавершённые шаги останутся видимыми. Мы не будем выдавать пропуск за подключение или недоступные данные за готовность."}
      </p>
      <div className={styles.readinessSummary}>
        <div>
          <strong>{progress.completedCount}</strong>
          <span>из {progress.totalCount} шагов подтверждены</span>
        </div>
        <p>{check.evidence}</p>
      </div>
      <Link className={styles.primaryAction} href="/dashboard">
        Перейти к экрану «Сегодня»
      </Link>
      {!progress.ready ? (
        <button
          className={styles.textAction}
          onClick={() => onChangeStep(firstIncompleteRequiredStep(progress) ?? 2)}
          type="button"
        >
          Вернуться к незавершённым шагам
        </button>
      ) : null}
    </>
  );
}

export function OnboardingJourneyView(props: OnboardingJourneyViewProps) {
  const stageCardRef = useRef<HTMLDivElement>(null);
  const progressPercent = Math.round(
    (props.progress.completedCount / props.progress.totalCount) * 100
  );

  useEffect(() => {
    stageCardRef.current?.focus();
  }, [props.activeStep]);

  return (
    <div className={styles.page}>
      <aside className={styles.journey} aria-label="Путь настройки">
        <div>
          <p className={styles.journeyEyebrow}>Запуск FounderOS</p>
          <h2>Оживляем компанию</h2>
        </div>
        <div
          className={styles.progressTrack}
          role="progressbar"
          aria-label="Подтверждённые шаги настройки"
          aria-valuemin={0}
          aria-valuemax={props.progress.totalCount}
          aria-valuenow={props.progress.completedCount}
        >
          <span style={{ width: `${progressPercent}%` }} />
        </div>
        <nav className={styles.stepList} aria-label="Шаги онбординга">
          {JOURNEY.map((step, index) => {
            const check =
              step.id === "welcome"
                ? null
                : props.progress.checks[step.id as keyof OnboardingProgress["checks"]];
            const state = check?.state ?? (props.activeStep > 0 ? "complete" : "pending");
            return (
              <button
                aria-current={props.activeStep === index ? "step" : undefined}
                className={styles.stepButton}
                data-active={props.activeStep === index}
                data-state={state}
                key={step.id}
                onClick={() => props.onChangeStep(index)}
                type="button"
              >
                <span>{state === "complete" ? "✓" : String(index + 1).padStart(2, "0")}</span>
                {step.label}
              </button>
            );
          })}
        </nav>
        <p className={styles.journeyNote}>
          Пропущенный шаг не станет «готовым». Статус меняется только после проверки
          реальных данных.
        </p>
      </aside>
      <section className={styles.stage} aria-live="polite">
        <div
          aria-label={`Шаг: ${JOURNEY[props.activeStep]?.label ?? "Настройка"}`}
          className={styles.stageCard}
          ref={stageCardRef}
          role="region"
          tabIndex={-1}
        >
          <StepBody {...props} />
        </div>
      </section>
    </div>
  );
}

export function OnboardingRecoveryView({ onSignOut }: { onSignOut: () => void }) {
  return (
    <div className={styles.recoveryPage}>
      <section className={styles.recoveryCard}>
        <span className={styles.recoveryMark} aria-hidden="true">!</span>
        <p className={styles.kicker}>Аккаунт пока без компании</p>
        <h1>Компания пока не привязана к аккаунту.</h1>
        <p className={styles.lead}>
          Мы не будем угадывать рабочее пространство или создавать его без разрешения.
          Сообщите администратору почту этого аккаунта и попросите добавить вас в
          нужную компанию. Новая ссылка основателя создаёт другой аккаунт и не
          исправит эту привязку.
        </p>
        <button className={styles.primaryAction} onClick={onSignOut} type="button">
          Выйти из аккаунта
        </button>
      </section>
    </div>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const session = useSession();
  const [activeStep, setActiveStep] = useState(0);
  const [progress, setProgress] = useState<OnboardingProgress | null>(null);
  const [loading, setLoading] = useState(true);

  const workspaceId = session?.workspaceId ?? null;
  const workspace =
    session?.workspaces.find((candidate) => candidate.id === workspaceId) ?? null;

  const refresh = useCallback(async () => {
    if (workspaceId === null) {
      setLoading(false);
      setProgress(null);
      return;
    }
    setLoading(true);
    const snapshot = await loadOnboardingSnapshot(workspaceId);
    setProgress(deriveOnboardingProgress(snapshot));
    setLoading(false);
  }, [workspaceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const syncStepFromHash = () => {
      setActiveStep(onboardingStepFromHash(window.location.hash));
    };
    syncStepFromHash();
    window.addEventListener("hashchange", syncStepFromHash);
    return () => window.removeEventListener("hashchange", syncStepFromHash);
  }, []);

  const changeStep = useCallback((step: number) => {
    const safeStep = Math.min(Math.max(step, 0), ONBOARDING_STEP_IDS.length - 1);
    setActiveStep(safeStep);
    const stepId = ONBOARDING_STEP_IDS[safeStep];
    if (stepId) {
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${window.location.search}#${stepId}`
      );
    }
  }, []);

  if (session && workspaceId === null) {
    return (
      <OnboardingRecoveryView
        onSignOut={() => {
          void logout().finally(() => router.replace("/login"));
        }}
      />
    );
  }

  if (loading || progress === null || workspace === null) {
    return (
      <div className={styles.loadingPage} aria-busy="true">
        <div className={styles.loadingPulse} />
        <p>Проверяем реальное состояние компании…</p>
      </div>
    );
  }

  return (
    <OnboardingJourneyView
      activeStep={activeStep}
      onChangeStep={changeStep}
      onRefresh={() => void refresh()}
      progress={progress}
      workspace={workspace}
    />
  );
}
