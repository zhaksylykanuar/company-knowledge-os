"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import styles from "../app/demo/demo.module.css";
import {
  DEMO_SCENES,
  DEMO_SNAPSHOT_LABEL,
  DEMO_SOURCES,
  DEMO_TRUTH_LABEL,
  sceneIndexFromHash,
  type DemoPhase,
  type DemoSourceKey
} from "../lib/demo-tour";
import {
  DemoTourScenes,
  type DemoDecisionStep,
  type DemoProfileView
} from "./DemoTourScenes";

const AUTOPLAY_SPEEDS = [5, 7, 10] as const;
const PHASES: readonly DemoPhase[] = ["Увидеть", "Понять", "Решить", "Изменить"];

export function DemoProductTour() {
  const rootRef = useRef<HTMLElement>(null);
  const [sceneIndex, setSceneIndex] = useState(0);
  const [visitedScenes, setVisitedScenes] = useState<ReadonlySet<number>>(
    () => new Set([0])
  );
  const [isPlaying, setIsPlaying] = useState(false);
  const [autoplaySeconds, setAutoplaySeconds] = useState<(typeof AUTOPLAY_SPEEDS)[number]>(7);
  const [remainingMs, setRemainingMs] = useState(7000);
  const [isHoveringStage, setIsHoveringStage] = useState(false);
  const [isFocusWithinStage, setIsFocusWithinStage] = useState(false);
  const [isDocumentVisible, setIsDocumentVisible] = useState(true);
  const [hintsVisible, setHintsVisible] = useState(true);
  const [exploreMode, setExploreMode] = useState(false);
  const [outlineOpen, setOutlineOpen] = useState(true);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<DemoSourceKey>("github");
  const [selectedRelationship, setSelectedRelationship] = useState("Atlas Retail");
  const [profileView, setProfileView] = useState<DemoProfileView>("person");
  const [decisionStep, setDecisionStep] = useState<DemoDecisionStep>("review");
  const [confirmationChecked, setConfirmationChecked] = useState(false);
  const [actionSimulated, setActionSimulated] = useState(false);

  const baseScene = DEMO_SCENES[sceneIndex];
  const scene = actionSimulated && sceneIndex === 3
    ? {
        ...baseScene,
        benefit: "После решения штаб пересчитывает очередь и сразу показывает следующий объяснимый приоритет.",
        kicker: "Штаб после решения",
        next: "Открыть обновлённую очередь из двух оставшихся решений.",
        sources: ["github", "jira"] as const,
        summary: "Atlas SSO перешёл под контроль, квитанция сохранена, а повторная отправка уведомлений стала новым приоритетом №1.",
        title: "Результат действительно изменил картину компании"
      }
    : actionSimulated && sceneIndex === 9
      ? {
          ...baseScene,
          benefit: "Завершённая миссия исчезает из ожидания, а все счётчики и следующий приоритет меняются вместе.",
          kicker: "Очередь после результата",
          next: "Разобрать повторную отправку уведомлений как следующий цикл, когда будет выбран новый план решения.",
          sources: ["github", "jira"] as const,
          summary: "В ожидании осталось две миссии, с результатом стало восемь, а Atlas SSO больше не занимает очередь.",
          title: "Очередь честно пересчиталась после квитанции"
        }
    : actionSimulated && sceneIndex === 10
      ? {
          ...baseScene,
          benefit: "Завершённую симуляцию нельзя случайно выполнить повторно: вместо старых контролов виден её статус.",
          kicker: "Решение завершено",
          next: "Открыть квитанцию и затем проверить обновлённый штаб.",
          summary: "Решение Atlas SSO уже зафиксировано, очередь пересчитана, а повторное выполнение закрыто.",
          title: "Комната решения помнит завершённый цикл"
        }
    : !actionSimulated && sceneIndex === 11
      ? {
          ...baseScene,
          benefit: "Финальный экран заранее показывает формат результата, но не выдаёт ожидаемое состояние за сохранённое.",
          kicker: "Предпросмотр результата",
          next: "Вернуться в комнату решений, подтвердить симуляцию и получить квитанцию.",
          summary: "Квитанция и изменение очереди появятся только после явного подтверждения на предыдущем шаге.",
          title: "Сначала решение — затем проверяемый результат"
        }
    : baseScene;
  const progress = ((sceneIndex + 1) / DEMO_SCENES.length) * 100;
  const autoplayProgress = Math.max(0, Math.min(100, (remainingMs / (autoplaySeconds * 1000)) * 100));
  const isAutoplayBlocked = Boolean(
    scene.stopAutoplay ||
      exploreMode ||
      isHoveringStage ||
      isFocusWithinStage ||
      !isDocumentVisible
  );
  const isTimerRunning = isPlaying && !isAutoplayBlocked;

  const updateScene = useCallback(
    (nextIndex: number, historyMode: "push" | "replace" = "push") => {
      const boundedIndex = Math.max(0, Math.min(DEMO_SCENES.length - 1, nextIndex));
      const nextScene = DEMO_SCENES[boundedIndex];
      setSceneIndex(boundedIndex);
      setVisitedScenes((current) => new Set([...current, boundedIndex]));
      setRemainingMs(autoplaySeconds * 1000);
      setCopyStatus(null);
      if (typeof window !== "undefined") {
        const url = `${window.location.pathname}${window.location.search}#${nextScene.id}`;
        if (historyMode === "replace") {
          window.history.replaceState(null, "", url);
        } else {
          window.history.pushState(null, "", url);
        }
      }
    },
    [autoplaySeconds]
  );

  useEffect(() => {
    const initialIndex = sceneIndexFromHash(window.location.hash);
    setSceneIndex(initialIndex);
    setVisitedScenes(new Set([initialIndex]));
    const expectedHash = `#${DEMO_SCENES[initialIndex].id}`;
    if (window.location.hash !== expectedHash) {
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${window.location.search}${expectedHash}`
      );
    }
  }, []);

  useEffect(() => {
    const handleHistory = () => {
      const nextIndex = sceneIndexFromHash(window.location.hash);
      setSceneIndex(nextIndex);
      setVisitedScenes((current) => new Set([...current, nextIndex]));
      setRemainingMs(autoplaySeconds * 1000);
    };
    window.addEventListener("hashchange", handleHistory);
    window.addEventListener("popstate", handleHistory);
    return () => {
      window.removeEventListener("hashchange", handleHistory);
      window.removeEventListener("popstate", handleHistory);
    };
  }, [autoplaySeconds]);

  useEffect(() => {
    const handleVisibility = () => setIsDocumentVisible(document.visibilityState === "visible");
    handleVisibility();
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  useEffect(() => {
    setRemainingMs(autoplaySeconds * 1000);
  }, [autoplaySeconds, sceneIndex]);

  useEffect(() => {
    if (!isTimerRunning) {
      return;
    }

    const interval = window.setInterval(() => {
      setRemainingMs((current) => {
        const next = current - 100;
        if (next > 0) {
          return next;
        }
        const nextSceneIndex = sceneIndex >= DEMO_SCENES.length - 1 ? 0 : sceneIndex + 1;
        window.queueMicrotask(() => updateScene(nextSceneIndex, "replace"));
        return autoplaySeconds * 1000;
      });
    }, 100);

    return () => window.clearInterval(interval);
  }, [autoplaySeconds, isTimerRunning, sceneIndex, updateScene]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isInteractive = Boolean(
        target?.closest("a, button, input, select, textarea, [contenteditable='true'], [role='button']")
      );
      if (isInteractive) {
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        updateScene(sceneIndex + 1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        updateScene(sceneIndex - 1);
      } else if (event.key === "Home") {
        event.preventDefault();
        updateScene(0);
      } else if (event.key === "End") {
        event.preventDefault();
        updateScene(DEMO_SCENES.length - 1);
      } else if (event.key === " ") {
        event.preventDefault();
        setExploreMode(false);
        setIsPlaying((current) => !current);
      } else if (event.key === "Escape" && document.fullscreenElement) {
        void document.exitFullscreen();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [sceneIndex, updateScene]);

  const activeSourceLabels = useMemo(
    () =>
      scene.sources.map(
        (sourceKey) => DEMO_SOURCES.find((source) => source.key === sourceKey)?.label ?? sourceKey
      ),
    [scene.sources]
  );

  function toggleAutoplay() {
    if (scene.stopAutoplay) {
      return;
    }
    setExploreMode(false);
    setRemainingMs(autoplaySeconds * 1000);
    setIsPlaying((current) => !current);
  }

  function toggleExploreMode() {
    setExploreMode((current) => !current);
    setIsPlaying(false);
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await rootRef.current?.requestFullscreen();
      }
    } catch {
      // Fullscreen is an optional presentation enhancement.
    }
  }

  async function copySceneLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopyStatus("Ссылка скопирована");
    } catch {
      setCopyStatus("Скопируйте URL из адресной строки");
    }
  }

  function restartTour() {
    setIsPlaying(false);
    setExploreMode(false);
    setActionSimulated(false);
    setConfirmationChecked(false);
    setDecisionStep("review");
    setVisitedScenes(new Set([0]));
    updateScene(0, "replace");
  }

  function simulateAction() {
    setActionSimulated(true);
    setIsPlaying(false);
    updateScene(11);
  }

  return (
    <main className={styles.demoPage} ref={rootRef}>
      <header className={styles.demoTopbar}>
        <div className={styles.demoBrand}>
          <span aria-hidden="true">F</span>
          <div><strong>FounderOS</strong><small>интерактивная продуктовая симуляция</small></div>
        </div>
        <div className={styles.truthBanner}>
          <i aria-hidden="true" />
          <span>{DEMO_TRUTH_LABEL}</span>
        </div>
        <div className={styles.topbarControls}>
          <button aria-pressed={hintsVisible} className={styles.ghostButton} onClick={() => setHintsVisible((current) => !current)} type="button">
            {hintsVisible ? "Скрыть подсказки" : "Показать подсказки"}
          </button>
          <button className={styles.ghostButton} onClick={() => void toggleFullscreen()} type="button">
            Режим презентации
          </button>
          <Link className={styles.exitButton} href="/dashboard" prefetch={false}>Выйти из демо</Link>
        </div>
      </header>

      <div className={styles.demoWorkspace}>
        <aside className={styles.tourOutline} aria-label="Оглавление демо-тура">
          <div className={styles.outlineHeader}>
            <div><span>Полный путь пользователя</span><strong>{DEMO_SCENES.length} сцен</strong></div>
            <button aria-expanded={outlineOpen} onClick={() => setOutlineOpen((current) => !current)} type="button">
              {outlineOpen ? "−" : "+"}
            </button>
          </div>
          {outlineOpen ? (
            <nav className={styles.sceneNavigation}>
              {DEMO_SCENES.map((item, index) => (
                <button
                  aria-current={index === sceneIndex ? "step" : undefined}
                  className={`${styles.sceneNavButton} ${index === sceneIndex ? styles.sceneNavButtonActive : ""} ${visitedScenes.has(index) ? styles.sceneNavButtonVisited : ""}`}
                  key={item.id}
                  onClick={() => updateScene(index)}
                  type="button"
                >
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <span><strong>{item.navLabel}</strong><small>{item.phase}</small></span>
                </button>
              ))}
            </nav>
          ) : (
            <div className={styles.compactOutline}>
              <strong>{String(sceneIndex + 1).padStart(2, "0")}</strong>
              <span>{scene.navLabel}</span>
            </div>
          )}
          <div className={styles.outlineFooter}>
            <span>{visitedScenes.size} из {DEMO_SCENES.length} просмотрено</span>
            <div><i style={{ width: `${(visitedScenes.size / DEMO_SCENES.length) * 100}%` }} /></div>
          </div>
        </aside>

        <section className={styles.stageColumn} aria-label={`Сцена ${sceneIndex + 1}: ${scene.title}`}>
          <div
            className={`${styles.productStage} ${hintsVisible ? styles.productStageWithHints : ""}`}
            onBlur={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget)) {
                setIsFocusWithinStage(false);
              }
            }}
            onFocusCapture={() => setIsFocusWithinStage(true)}
            onMouseEnter={() => setIsHoveringStage(true)}
            onMouseLeave={() => setIsHoveringStage(false)}
          >
            <div className={styles.productWindowBar}>
              <div className={styles.windowDots} aria-hidden="true"><i /><i /><i /></div>
              <span>NovaFlow · FounderOS</span>
              <small>{DEMO_SNAPSHOT_LABEL}</small>
            </div>
            <div className={styles.productShell}>
              <nav className={styles.productRail} aria-label="Навигация симуляции">
                <button className={sceneIndex === 3 ? styles.productRailActive : ""} onClick={() => updateScene(3)} title="Штаб" type="button"><span>⌂</span><small>Штаб</small></button>
                <button className={sceneIndex >= 4 && sceneIndex <= 7 ? styles.productRailActive : ""} onClick={() => updateScene(4)} title="Мир" type="button"><span>◎</span><small>Мир</small></button>
                <button className={sceneIndex >= 8 ? styles.productRailActive : ""} onClick={() => updateScene(9)} title="Миссии" type="button"><span>✓</span><small>Миссии</small></button>
                <button className={sceneIndex <= 2 ? styles.productRailActive : ""} onClick={() => updateScene(1)} title="Радары" type="button"><span>⌁</span><small>Радары</small></button>
              </nav>
              <section className={styles.productScreen}>
                <div className={styles.screenTruth}>{DEMO_TRUTH_LABEL}</div>
                <DemoTourScenes
                  actionSimulated={actionSimulated}
                  confirmationChecked={confirmationChecked}
                  decisionStep={decisionStep}
                  hintsVisible={hintsVisible}
                  onConfirmationChange={setConfirmationChecked}
                  onDecisionStepChange={(step) => {
                    setDecisionStep(step);
                    setIsPlaying(false);
                  }}
                  onNavigate={updateScene}
                  onProfileViewChange={setProfileView}
                  onSelectRelationship={setSelectedRelationship}
                  onSelectSource={setSelectedSource}
                  onSimulateAction={simulateAction}
                  profileView={profileView}
                  sceneIndex={sceneIndex}
                  selectedRelationship={selectedRelationship}
                  selectedSource={selectedSource}
                />
              </section>
            </div>
          </div>

          <div className={styles.transportBar}>
            <button aria-label="Предыдущая сцена" disabled={sceneIndex === 0} onClick={() => updateScene(sceneIndex - 1)} type="button">←</button>
            <button className={styles.playButton} disabled={Boolean(scene.stopAutoplay)} onClick={toggleAutoplay} type="button">
              {scene.stopAutoplay ? "Ручной режим" : isPlaying ? "Пауза" : "Запустить показ"}
            </button>
            <button aria-label="Следующая сцена" disabled={sceneIndex === DEMO_SCENES.length - 1} onClick={() => updateScene(sceneIndex + 1)} type="button">→</button>
            <div className={styles.transportProgress}>
              <div><i style={{ width: `${progress}%` }} /></div>
              <span>{sceneIndex + 1} / {DEMO_SCENES.length}</span>
            </div>
            <label className={styles.speedControl}>
              Темп
              <select value={autoplaySeconds} onChange={(event) => setAutoplaySeconds(Number(event.target.value) as (typeof AUTOPLAY_SPEEDS)[number])}>
                {AUTOPLAY_SPEEDS.map((seconds) => <option key={seconds} value={seconds}>{seconds} сек</option>)}
              </select>
            </label>
            <button aria-pressed={exploreMode} className={exploreMode ? styles.exploreActive : ""} onClick={toggleExploreMode} type="button">
              {exploreMode ? "Исследование включено" : "Исследовать"}
            </button>
            <div className={styles.autoplayMeter} title={isAutoplayBlocked ? "Автопоказ временно остановлен" : "До следующей сцены"}>
              <i style={{ width: `${autoplayProgress}%` }} />
            </div>
          </div>
        </section>

        <aside className={styles.guidePanel} aria-label="Пояснение к текущей сцене">
          <div className={styles.phaseRail} aria-label="Этап пользовательского цикла">
            {PHASES.map((phase) => (
              <span className={phase === scene.phase ? styles.phaseActive : ""} key={phase}>{phase}</span>
            ))}
          </div>
          <div className={styles.guideSceneNumber}>Сцена {String(sceneIndex + 1).padStart(2, "0")}</div>
          <span className={styles.guideKicker}>{scene.kicker}</span>
          <h1>{scene.title}</h1>
          <p className={styles.guideSummary}>{scene.summary}</p>

          <section className={styles.guideBenefit}>
            <small>Почему это полезно</small>
            <p>{scene.benefit}</p>
          </section>

          <section className={styles.guideSources}>
            <small>Основания на сцене</small>
            {activeSourceLabels.length > 0 ? (
              <div>{activeSourceLabels.map((label) => <span key={label}>{label}</span>)}</div>
            ) : (
              <p>Роли подтверждены настройками команды.</p>
            )}
          </section>

          <section className={styles.guideNext}>
            <small>Следующий ход</small>
            <p>{scene.next}</p>
          </section>

          <div className={styles.guideActions}>
            <button onClick={() => void copySceneLink()} type="button">Скопировать ссылку</button>
            <button onClick={restartTour} type="button">Начать заново</button>
          </div>
          <p className={styles.copyStatus} role="status">{copyStatus ?? ""}</p>

          <details className={styles.shortcutHelp}>
            <summary>Горячие клавиши</summary>
            <dl>
              <div><dt>← / →</dt><dd>сменить сцену</dd></div>
              <div><dt>Space</dt><dd>показ / пауза</dd></div>
              <div><dt>Home / End</dt><dd>начало / финал</dd></div>
              <div><dt>Esc</dt><dd>выйти из fullscreen</dd></div>
            </dl>
          </details>
        </aside>
      </div>

      <p className={styles.srOnly} aria-live="polite">
        Открыта сцена {sceneIndex + 1} из {DEMO_SCENES.length}: {scene.title}.
      </p>
    </main>
  );
}
