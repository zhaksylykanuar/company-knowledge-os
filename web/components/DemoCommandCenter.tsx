"use client";

import Link from "next/link";
import { useCallback, useEffect, useReducer, useRef } from "react";

import styles from "../app/demo/demo.module.css";
import {
  demoCommandCenterReducer,
  getDemoCommandCenterSnapshot,
  INITIAL_DEMO_COMMAND_CENTER_STATE,
  type DemoOverlay
} from "../lib/demo-command-center";
import {
  DEMO_ATLAS_PROFILE,
  DEMO_COMPANY,
  DEMO_SIGNAL,
  DEMO_SNAPSHOT_LABEL,
  DEMO_SOURCES,
  DEMO_TEAM,
  DEMO_TRUTH_LABEL
} from "../lib/demo-tour";
import { DemoCommandCenterOverlays } from "./DemoCommandCenterOverlays";

export function DemoCommandCenter() {
  const [state, dispatch] = useReducer(
    demoCommandCenterReducer,
    INITIAL_DEMO_COMMAND_CENTER_STATE
  );
  const backgroundRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const snapshot = getDemoCommandCenterSnapshot(state.decisionCompleted);
  const isAtlasPriority = !state.decisionCompleted;
  const activeSources = DEMO_SOURCES.filter((source) =>
    (snapshot.activeMission.sourceKeys as readonly string[]).includes(source.key)
  );

  const openOverlay = useCallback((overlay: Exclude<DemoOverlay, null>) => {
    if (!state.overlay) {
      returnFocusRef.current = document.activeElement as HTMLElement | null;
    }
    dispatch({ overlay, type: "open" });
  }, [state.overlay]);

  const closeOverlay = useCallback(() => {
    dispatch({ type: "close" });
    window.queueMicrotask(() => {
      returnFocusRef.current?.focus();
      returnFocusRef.current = null;
    });
  }, []);

  const resetDemo = useCallback(() => {
    dispatch({ type: "reset" });
    window.queueMicrotask(() => {
      returnFocusRef.current?.focus();
      returnFocusRef.current = null;
    });
  }, []);

  useEffect(() => {
    const background = backgroundRef.current;
    if (!background) {
      return;
    }
    if (state.overlay) {
      background.setAttribute("inert", "");
      background.setAttribute("aria-hidden", "true");
    } else {
      background.removeAttribute("inert");
      background.removeAttribute("aria-hidden");
    }
  }, [state.overlay]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openOverlay({ kind: "assistant" });
      } else if (event.key === "Escape" && state.overlay) {
        event.preventDefault();
        closeOverlay();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [closeOverlay, openOverlay, state.overlay]);

  const activeOwners = isAtlasPriority
    ? DEMO_TEAM.filter((person) => person.status === "В миссии")
    : DEMO_TEAM.filter((person) => person.name === "Мила Орлова");

  return (
    <main className={styles.commandCenterPage}>
      <div className={styles.commandCenterBackground} ref={backgroundRef}>
        <header className={styles.commandHeader}>
          <div className={styles.brandLockup}>
            <span className={styles.brandMark} aria-hidden="true">F</span>
            <div>
              <strong>FounderOS</strong>
              <small>{DEMO_COMPANY.name} · живой штаб</small>
            </div>
          </div>

          <button
            className={styles.sourceHealth}
            onClick={() => openOverlay({ detail: "sources", kind: "detail" })}
            type="button"
          >
            <i aria-hidden="true" />
            <span><strong>4 из 4 источников</strong><small>обновлено 2 мин назад</small></span>
          </button>

          <button
            className={styles.assistantLauncher}
            onClick={() => openOverlay({ kind: "assistant" })}
            type="button"
          >
            <span className={styles.assistantSpark} aria-hidden="true">✦</span>
            <span>Спросить FounderOS</span>
            <kbd>⌘ K</kbd>
          </button>

          <span className={styles.demoBadge} title={DEMO_TRUTH_LABEL}>Демо-данные</span>
          <Link className={styles.exitLink} href="/dashboard" prefetch={false}>Выйти</Link>
        </header>

        <section className={styles.commandCanvas} aria-label="Живой штаб NovaFlow">
          <div className={styles.canvasIntro}>
            <div>
              <span>Четверг, 16 июля</span>
              <h1>{state.decisionCompleted ? "Штаб обновлён" : "Доброе утро, Алина"}</h1>
            </div>
            <p>
              {state.decisionCompleted
                ? "Результат учтён. На поверхности остался только следующий ход."
                : "Вот единственное решение, которое сейчас требует вашего внимания."}
            </p>
          </div>

          <section
            className={`${styles.priorityCard} ${state.decisionCompleted ? styles.priorityCardResolved : ""}`}
            aria-labelledby="demo-priority-title"
          >
            <div className={styles.priorityContent}>
              <div className={styles.priorityTopline}>
                <span className={styles.priorityStatus}>
                  {state.decisionCompleted ? "Новый приоритет" : "Требует решения"}
                </span>
                <button
                  onClick={() => openOverlay({ detail: "priority", kind: "detail" })}
                  type="button"
                >
                  {snapshot.activeMission.sourceCount} источника · {snapshot.activeMission.evidenceRefs} оснований
                  <span aria-hidden="true">↗</span>
                </button>
              </div>
              <h2 id="demo-priority-title">{snapshot.activeMission.title}</h2>
              <p>
                {isAtlasPriority
                  ? "Срок заказчика совпал с техническим и операционным блокером. Без решения запуск может сдвинуться на 5–8 рабочих дней."
                  : "Atlas SSO перешёл под контроль. Теперь важнее назначить одного владельца следующего подтверждённого пробела."}
              </p>

              <dl className={styles.priorityFacts}>
                <div><dt>Срок</dt><dd>{isAtlasPriority ? "Сегодня · 12:00" : "Сегодня · 15:00"}</dd></div>
                <div><dt>Заказчик</dt><dd>{isAtlasPriority ? DEMO_ATLAS_PROFILE.company.name : "Внутренняя платформа"}</dd></div>
                <div><dt>Ущерб</dt><dd>{isAtlasPriority ? "5–8 рабочих дней" : "Повторные сбои"}</dd></div>
              </dl>

              <div className={styles.priorityActions}>
                <button
                  className={styles.primaryAction}
                  onClick={() => openOverlay(
                    state.decisionCompleted
                      ? { kind: "mission", missionId: snapshot.activeMission.id }
                      : { kind: "decision" }
                  )}
                  type="button"
                >
                  {state.decisionCompleted ? "Разобрать следующий ход" : "Принять решение"}
                  <span aria-hidden="true">→</span>
                </button>
                <button
                  className={styles.secondaryAction}
                  onClick={() => openOverlay(
                    state.decisionCompleted
                      ? { kind: "decision" }
                      : { detail: "priority", kind: "detail" }
                  )}
                  type="button"
                >
                  {state.decisionCompleted ? "Квитанция Atlas" : "Почему это №1?"}
                </button>
              </div>
            </div>

            <div className={styles.priorityVisual} aria-label="Связанные основания приоритета">
              <div className={styles.signalOrbit} aria-hidden="true">
                <i /><i /><i />
                <span className={styles.orbitCore}>{state.decisionCompleted ? "02" : "01"}</span>
                {activeSources.map((source, index) => (
                  <span
                    className={styles.orbitSource}
                    key={source.key}
                    style={{
                      "--orbit-accent": source.accent,
                      "--orbit-index": index
                    } as React.CSSProperties}
                  >
                    {source.label.slice(0, 1)}
                  </span>
                ))}
              </div>
              <div className={styles.ownerCluster}>
                <span>Владельцы</span>
                <div>
                  {activeOwners.map((person) => (
                    <i key={person.name} title={person.name}>{person.initials}</i>
                  ))}
                </div>
                <strong>{isAtlasPriority ? "Тимур · Данияр · София" : "Мила Орлова"}</strong>
              </div>
            </div>
          </section>

          <section className={styles.pulseGrid} aria-label="Компания сейчас">
            <button onClick={() => openOverlay({ detail: "changes", kind: "detail" })} type="button">
              <span className={styles.pulseIcon} aria-hidden="true">◎</span>
              <strong>{snapshot.waiting}</strong>
              <span>решения ждут</span>
              <small>{state.decisionCompleted ? "одно закрыто" : "из 12 загруженных"}</small>
            </button>
            <button onClick={() => openOverlay({ detail: "priority", kind: "detail" })} type="button">
              <span className={`${styles.pulseIcon} ${styles.pulseIconRisk}`} aria-hidden="true">!</span>
              <strong>{snapshot.criticalRisks}</strong>
              <span>критический риск</span>
              <small>{state.decisionCompleted ? "Atlas под контролем" : "до 12:00"}</small>
            </button>
            <button onClick={() => openOverlay({ detail: "team", kind: "detail" })} type="button">
              <span className={styles.pulseIcon} aria-hidden="true">⋮</span>
              <strong>{DEMO_COMPANY.teamSize}</strong>
              <span>сотрудников</span>
              <small>{activeOwners.length} в текущем фокусе</small>
            </button>
          </section>

          <div className={styles.lowerGrid}>
            <section className={styles.nextMoves}>
              <header>
                <div><span>Дальше</span><h2>Следующие решения</h2></div>
                <small>{snapshot.nextMissions.length} в очереди</small>
              </header>
              <div className={styles.nextMoveList}>
                {snapshot.nextMissions.map((mission, index) => (
                  <button
                    key={mission.id}
                    onClick={() => openOverlay({ kind: "mission", missionId: mission.id })}
                    type="button"
                  >
                    <span className={styles.moveNumber}>0{index + 2}</span>
                    <span><strong>{mission.title}</strong><small>{mission.owner}</small></span>
                    <em>{mission.urgency}</em>
                    <i aria-hidden="true">→</i>
                  </button>
                ))}
                {snapshot.nextMissions.length === 1 ? (
                  <div className={styles.queueClear}>
                    <span aria-hidden="true">✓</span>
                    После него очередь решений разобрана
                  </div>
                ) : null}
              </div>
            </section>

            <section className={styles.changeFeed}>
              <header>
                <div><span>Что изменилось</span><h2>Последние сигналы</h2></div>
                <button onClick={() => openOverlay({ detail: "changes", kind: "detail" })} type="button">Все →</button>
              </header>
              <ol>
                {state.decisionCompleted ? (
                  <li className={styles.changeResolved}>
                    <i aria-hidden="true">✓</i>
                    <div><strong>Решение Atlas зафиксировано</strong><small>FounderOS · только что</small></div>
                  </li>
                ) : null}
                {DEMO_SIGNAL.events.slice(state.decisionCompleted ? 2 : 1, 4).map((event) => (
                  <li key={event.source}>
                    <i aria-hidden="true" />
                    <div><strong>{event.title}</strong><small>{event.source} · {event.time}</small></div>
                  </li>
                ))}
              </ol>
            </section>
          </div>

          <footer className={styles.commandFooter}>
            <span>{DEMO_SNAPSHOT_LABEL}</span>
            <span>{DEMO_TRUTH_LABEL}</span>
          </footer>
        </section>
      </div>

      <DemoCommandCenterOverlays
        onAsk={(query) => dispatch({ query, type: "ask" })}
        onClose={closeOverlay}
        onCompleteDecision={() => dispatch({ type: "complete-decision" })}
        onConfirmationChange={(checked) => dispatch({ checked, type: "confirm" })}
        onOpen={openOverlay}
        onReset={resetDemo}
        state={state}
      />
    </main>
  );
}
