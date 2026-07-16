"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import styles from "../app/demo/demo.module.css";
import {
  DEMO_ASSISTANT_STARTERS,
  getDemoCommandCenterSnapshot,
  type DemoCommandCenterState,
  type DemoDetailKind,
  type DemoOverlay
} from "../lib/demo-command-center";
import {
  DEMO_ATLAS_PROFILE,
  DEMO_COMPANY,
  DEMO_DOCUMENTS,
  DEMO_MISSIONS,
  DEMO_PREVIEW,
  DEMO_RECEIPT,
  DEMO_RELATIONSHIPS,
  DEMO_SIGNAL,
  DEMO_SOURCES,
  DEMO_TEAM,
  DEMO_TRUTH_LABEL
} from "../lib/demo-tour";

type DemoCommandCenterOverlaysProps = {
  onAsk: (query: string) => void;
  onClose: () => void;
  onCompleteDecision: () => void;
  onConfirmationChange: (checked: boolean) => void;
  onOpen: (overlay: Exclude<DemoOverlay, null>) => void;
  onReset: () => void;
  state: DemoCommandCenterState;
};

export function DemoCommandCenterOverlays({
  onAsk,
  onClose,
  onCompleteDecision,
  onConfirmationChange,
  onOpen,
  onReset,
  state
}: DemoCommandCenterOverlaysProps) {
  if (!state.overlay) {
    return null;
  }

  if (state.overlay.kind === "assistant") {
    return (
      <AssistantDrawer
        messages={state.assistantMessages}
        onAsk={onAsk}
        onClose={onClose}
        onOpen={onOpen}
      />
    );
  }

  if (state.overlay.kind === "decision") {
    return (
      <DecisionDialog
        confirmationChecked={state.confirmationChecked}
        decisionCompleted={state.decisionCompleted}
        onClose={onClose}
        onCompleteDecision={onCompleteDecision}
        onConfirmationChange={onConfirmationChange}
        onReset={onReset}
      />
    );
  }

  if (state.overlay.kind === "mission") {
    return (
      <MissionDrawer
        missionId={state.overlay.missionId}
        onClose={onClose}
        onOpen={onOpen}
      />
    );
  }

  return (
    <DetailDrawer
      decisionCompleted={state.decisionCompleted}
      detail={state.overlay.detail}
      onClose={onClose}
      onOpen={onOpen}
    />
  );
}

function AssistantDrawer({
  messages,
  onAsk,
  onClose,
  onOpen
}: {
  messages: DemoCommandCenterState["assistantMessages"];
  onAsk: (query: string) => void;
  onClose: () => void;
  onOpen: (overlay: Exclude<DemoOverlay, null>) => void;
}) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = query.trim();
    if (!value) {
      return;
    }
    onAsk(value);
    setQuery("");
    window.queueMicrotask(() => inputRef.current?.focus());
  }

  return (
    <OverlayShell
      initialFocusSelector="#demo-assistant-query"
      label="Ассистент компании"
      mode="drawer"
      onClose={onClose}
    >
      <header className={styles.assistantHeader}>
        <div className={styles.assistantIdentity}>
          <span aria-hidden="true">✦</span>
          <div><strong>FounderOS</strong><small>Штабной ассистент</small></div>
        </div>
        <span className={styles.localMode}>Демо · локально</span>
      </header>

      <div className={styles.assistantContext}>
        <span>Текущий контекст</span>
        <strong>NovaFlow · живой штаб</strong>
      </div>

      <div className={styles.chatLog} role="log" aria-live="polite">
        {messages.map((message) => (
          <article
            className={message.role === "user" ? styles.userMessage : styles.assistantMessage}
            key={message.id}
          >
            {message.role === "assistant" ? <span className={styles.messageSpark}>✦</span> : null}
            <div>
              <p>{message.text}</p>
              {message.citations?.length ? (
                <div className={styles.citationRow} aria-label="Основания ответа">
                  {message.citations.map((citation) => (
                    <span key={`${message.id}-${citation.source}-${citation.label}`}>
                      {citation.source} · {citation.label}
                    </span>
                  ))}
                </div>
              ) : null}
              {message.action ? (
                <button
                  className={styles.messageAction}
                  onClick={() => onOpen(message.action!.overlay)}
                  type="button"
                >
                  {message.action.label} <span aria-hidden="true">→</span>
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>

      <div className={styles.starterQuestions}>
        {DEMO_ASSISTANT_STARTERS.map((question) => (
          <button key={question} onClick={() => onAsk(question)} type="button">{question}</button>
        ))}
      </div>

      <form className={styles.assistantComposer} onSubmit={submit}>
        <label className={styles.srOnly} htmlFor="demo-assistant-query">Вопрос о компании</label>
        <input
          id="demo-assistant-query"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Спросите о компании…"
          ref={inputRef}
          value={query}
        />
        <button aria-label="Отправить вопрос" disabled={!query.trim()} type="submit">↑</button>
      </form>
      <p className={styles.assistantBoundary}>Ответы синтетические. Ассистент ничего не записывает и не запускает.</p>
    </OverlayShell>
  );
}

function DetailDrawer({
  decisionCompleted,
  detail,
  onClose,
  onOpen
}: {
  decisionCompleted: boolean;
  detail: DemoDetailKind;
  onClose: () => void;
  onOpen: (overlay: Exclude<DemoOverlay, null>) => void;
}) {
  const labels: Record<DemoDetailKind, { eyebrow: string; title: string }> = {
    changes: { eyebrow: "Очередь и сигналы", title: "Что происходит сейчас" },
    company: { eyebrow: "Профиль заказчика", title: "Atlas Retail" },
    priority: {
      eyebrow: decisionCompleted ? "Новый приоритет" : "Почему это №1",
      title: decisionCompleted
        ? "Назначить владельца повторной отправки"
        : DEMO_SIGNAL.title
    },
    sources: { eyebrow: "Радары компании", title: "4 источника работают" },
    team: { eyebrow: "Люди и ответственность", title: "Команда NovaFlow" }
  };

  return (
    <OverlayShell label={labels[detail].title} mode="drawer" onClose={onClose}>
      <DrawerTitle eyebrow={labels[detail].eyebrow} title={labels[detail].title} />
      {detail === "priority" ? (
        <PriorityDetail decisionCompleted={decisionCompleted} onOpen={onOpen} />
      ) : null}
      {detail === "sources" ? <SourcesDetail /> : null}
      {detail === "team" ? <TeamDetail decisionCompleted={decisionCompleted} /> : null}
      {detail === "company" ? <CompanyDetail /> : null}
      {detail === "changes" ? <ChangesDetail decisionCompleted={decisionCompleted} /> : null}
    </OverlayShell>
  );
}

function MissionDrawer({
  missionId,
  onClose,
  onOpen
}: {
  missionId: (typeof DEMO_MISSIONS)[number]["id"];
  onClose: () => void;
  onOpen: (overlay: Exclude<DemoOverlay, null>) => void;
}) {
  const mission = DEMO_MISSIONS.find((candidate) => candidate.id === missionId);

  if (!mission) {
    return null;
  }

  const sources = DEMO_SOURCES.filter((source) =>
    (mission.sourceKeys as readonly string[]).includes(source.key)
  );

  return (
    <OverlayShell label={mission.title} mode="drawer" onClose={onClose}>
      <DrawerTitle eyebrow={`Миссия · ${mission.id}`} title={mission.title} />
      <div className={styles.drawerBody}>
        <section className={styles.detailLead}>
          <span className={mission.id === "DEMO-MISSION-042" ? styles.criticalBadge : styles.watchBadge}>
            {mission.urgency}
          </span>
          <p>{mission.summary}</p>
        </section>
        <dl className={styles.detailFacts}>
          <div><dt>Владелец</dt><dd>{mission.owner}</dd></div>
          <div><dt>Основания</dt><dd>{mission.evidenceRefs} ссылок</dd></div>
          <div><dt>Источники</dt><dd>{mission.sourceCount}</dd></div>
        </dl>
        <section className={styles.missionContext}>
          <div><small>Если ничего не делать</small><strong>{mission.impact}</strong></div>
          <div><small>Что нужно решить</small><strong>{mission.nextStep}</strong></div>
        </section>
        <section className={styles.missionSources}>
          <span>Подтверждающие радары</span>
          <div>
            {sources.map((source) => (
              <span key={source.key}>{source.label} · {source.freshness}</span>
            ))}
          </div>
        </section>
        {mission.id === "DEMO-MISSION-042" ? (
          <button className={styles.drawerPrimary} onClick={() => onOpen({ kind: "decision" })} type="button">
            Перейти к решению →
          </button>
        ) : (
          <button className={styles.drawerPrimary} onClick={() => onOpen({ detail: "changes", kind: "detail" })} type="button">
            Посмотреть всю очередь →
          </button>
        )}
        <p className={styles.drawerNote}>Это синтетическая карточка разбора. Она не назначает владельца и ничего не записывает.</p>
      </div>
    </OverlayShell>
  );
}

function PriorityDetail({
  decisionCompleted,
  onOpen
}: {
  decisionCompleted: boolean;
  onOpen: (overlay: Exclude<DemoOverlay, null>) => void;
}) {
  if (decisionCompleted) {
    const nextMission = DEMO_MISSIONS[1];
    return (
      <div className={styles.drawerBody}>
        <section className={styles.detailLead}>
          <span className={styles.watchBadge}>Следующий подтверждённый пробел</span>
          <p>Atlas SSO завершён в симуляции, поэтому штаб поднял новую миссию вместо сохранения старого фокуса.</p>
        </section>
        <dl className={styles.detailFacts}>
          <div><dt>Владелец</dt><dd>{nextMission.owner}</dd></div>
          <div><dt>Срок</dt><dd>{nextMission.urgency}</dd></div>
          <div><dt>Основания</dt><dd>{nextMission.evidenceRefs} ссылок</dd></div>
        </dl>
        <section className={styles.receiptHint}>
          <span aria-hidden="true">✓</span>
          <div><strong>Atlas SSO · на контроле</strong><small>{DEMO_RECEIPT.receiptId} · внешняя запись: нет</small></div>
        </section>
        <button className={styles.drawerPrimary} onClick={() => onOpen({ kind: "mission", missionId: nextMission.id })} type="button">
          Открыть карточку миссии →
        </button>
      </div>
    );
  }

  return (
    <div className={styles.drawerBody}>
      <section className={styles.detailLead}>
        <span className={styles.criticalBadge}>Решение нужно до 12:00</span>
        <p>{DEMO_SIGNAL.impact}. Четыре независимых факта совпали по времени и заказчику.</p>
      </section>
      <dl className={styles.detailFacts}>
        <div><dt>Уверенность</dt><dd>{DEMO_SIGNAL.confidence}%</dd></div>
        <div><dt>Владелец разбора</dt><dd>{DEMO_SIGNAL.owner}</dd></div>
        <div><dt>Заказчик</dt><dd>{DEMO_ATLAS_PROFILE.company.name}</dd></div>
      </dl>
      <section className={styles.evidenceStack}>
        <header><span>4 ключевых факта</span><strong>19 ссылок суммарно</strong></header>
        {DEMO_SIGNAL.events.map((event, index) => (
          <article key={event.source}>
            <span className={styles.evidenceIndex}>0{index + 1}</span>
            <div><small>{event.source} · {event.time}</small><strong>{event.title}</strong><p>{event.detail}</p></div>
          </article>
        ))}
      </section>
      <p className={styles.drawerNote}>В демо подробно показаны четыре ключевых факта; остальные ссылочные записи не моделируются.</p>
      <button className={styles.drawerPrimary} onClick={() => onOpen({ kind: "decision" })} type="button">
        Перейти к решению →
      </button>
    </div>
  );
}

function SourcesDetail() {
  return (
    <div className={styles.drawerBody}>
      <section className={styles.sourceSummary}>
        <strong>{DEMO_COMPANY.records}</strong>
        <span>согласованных записей</span>
        <small>Синтетический снимок · без live-вызовов</small>
      </section>
      <div className={styles.sourceDetailList}>
        {DEMO_SOURCES.map((source) => (
          <article key={source.key} style={{ "--source-accent": source.accent } as React.CSSProperties}>
            <span className={styles.sourceGlyph}>{source.label.slice(0, 1)}</span>
            <div><strong>{source.label}</strong><small>{source.freshness}</small></div>
            <span><strong>{source.records}</strong><small>записей</small></span>
            <p>{source.signal}</p>
          </article>
        ))}
      </div>
      <p className={styles.drawerNote}>Статус показывает только вымышленный демо-снимок. Он не доказывает реальные подключения.</p>
    </div>
  );
}

function TeamDetail({ decisionCompleted }: { decisionCompleted: boolean }) {
  const missionTeam = decisionCompleted
    ? DEMO_TEAM.filter((person) => person.name === "Мила Орлова")
    : DEMO_TEAM.filter((person) => person.status === "В миссии");
  return (
    <div className={styles.drawerBody}>
      <section className={styles.missionSquad}>
        <span>{decisionCompleted ? "В новом приоритете" : "В текущей миссии"}</span>
        <div>
          {missionTeam.map((person) => (
            <article key={person.name}>
              <span>{person.initials}</span>
              <div><strong>{person.name}</strong><small>{person.focus}</small></div>
            </article>
          ))}
        </div>
      </section>
      <section className={styles.teamDirectory}>
        <header><span>Вся команда</span><strong>{DEMO_TEAM.length} человек</strong></header>
        {DEMO_TEAM.map((person) => (
          <article key={person.name}>
            <span>{person.initials}</span>
            <div><strong>{person.name}</strong><small>{person.role}</small></div>
            <em>{person.status}</em>
          </article>
        ))}
      </section>
      <p className={styles.drawerNote}>FounderOS показывает подтверждённые роли и контекст, но не назначает ответственность автоматически.</p>
    </div>
  );
}

function CompanyDetail() {
  const [tab, setTab] = useState<"overview" | "people" | "history">("overview");
  return (
    <div className={styles.drawerBody}>
      <section className={styles.companyHero}>
        <span className={styles.companyAvatar}>A</span>
        <div><strong>{DEMO_ATLAS_PROFILE.company.status}</strong><small>Владелец · {DEMO_ATLAS_PROFILE.company.accountOwner}</small></div>
        <dl>
          <div><dt>Контакты</dt><dd>{DEMO_ATLAS_PROFILE.company.contacts}</dd></div>
          <div><dt>Касания</dt><dd>{DEMO_ATLAS_PROFILE.company.touchpoints}</dd></div>
        </dl>
      </section>
      <div className={styles.detailTabs} role="tablist" aria-label="Разделы профиля Atlas Retail">
        <button aria-selected={tab === "overview"} onClick={() => setTab("overview")} role="tab" type="button">Обзор</button>
        <button aria-selected={tab === "people"} onClick={() => setTab("people")} role="tab" type="button">Люди</button>
        <button aria-selected={tab === "history"} onClick={() => setTab("history")} role="tab" type="button">История</button>
      </div>
      {tab === "overview" ? (
        <div className={styles.companyOverview} role="tabpanel">
          <section><small>Зафиксированное обещание</small><strong>Запуск 22 июля · проверка безопасности до 16 июля</strong></section>
          <section><small>Текущий риск</small><strong>Изменение кода заблокировано, владелец отката не указан</strong></section>
          <div className={styles.relationshipMiniList}>
            {DEMO_RELATIONSHIPS.map((relationship) => (
              <div key={relationship.name}><span>{relationship.kind}</span><strong>{relationship.name}</strong><small>{relationship.touchpoints} {touchpointLabel(relationship.touchpoints)}</small></div>
            ))}
          </div>
        </div>
      ) : null}
      {tab === "people" ? (
        <div className={styles.contactList} role="tabpanel">
          {DEMO_ATLAS_PROFILE.people.map((person) => (
            <article key={person.name}>
              <span>{person.initials}</span>
              <div><strong>{person.name}</strong><small>{person.role}</small></div>
              <em>{person.decisionRole}</em>
            </article>
          ))}
        </div>
      ) : null}
      {tab === "history" ? (
        <ol className={styles.companyTimeline} role="tabpanel">
          {DEMO_ATLAS_PROFILE.timeline.map((event) => (
            <li key={`${event.source}-${event.time}`}>
              <i aria-hidden="true" />
              <div><small>{event.source} · {event.time}</small><strong>{event.text}</strong></div>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

function ChangesDetail({ decisionCompleted }: { decisionCompleted: boolean }) {
  const snapshot = getDemoCommandCenterSnapshot(decisionCompleted);
  return (
    <div className={styles.drawerBody}>
      <section className={styles.queueSummary}>
        <div><strong>{snapshot.waiting}</strong><span>ждут</span></div>
        <div><strong>{snapshot.approved}</strong><span>одобрены</span></div>
        <div><strong>{snapshot.completed}</strong><span>с результатом</span></div>
      </section>
      <section className={styles.fullQueue}>
        <header><span>Очередь решений</span><small>из 12 загруженных</small></header>
        {snapshot.queue.map((mission, index) => (
          <article key={mission.id}>
            <span>0{index + 1}</span>
            <div><strong>{mission.title}</strong><small>{mission.owner}</small></div>
            <em>{mission.urgency}</em>
          </article>
        ))}
      </section>
      <section className={styles.documentCompactList}>
        <header><span>Связанные документы</span><small>{DEMO_DOCUMENTS.length}</small></header>
        {DEMO_DOCUMENTS.map((document) => (
          <article key={document.name}>
            <span aria-hidden="true">▤</span>
            <div><strong>{document.name}</strong><small>{document.owner} · {document.updated}</small></div>
            <em>{document.status}</em>
          </article>
        ))}
      </section>
    </div>
  );
}

function DecisionDialog({
  confirmationChecked,
  decisionCompleted,
  onClose,
  onCompleteDecision,
  onConfirmationChange,
  onReset
}: {
  confirmationChecked: boolean;
  decisionCompleted: boolean;
  onClose: () => void;
  onCompleteDecision: () => void;
  onConfirmationChange: (checked: boolean) => void;
  onReset: () => void;
}) {
  return (
    <OverlayShell
      initialFocusSelector={decisionCompleted ? "#demo-receipt-title" : undefined}
      label={decisionCompleted ? "Квитанция решения" : "Принять решение"}
      mode="modal"
      onClose={onClose}
    >
      {decisionCompleted ? (
        <div className={styles.receiptView}>
          <div className={styles.receiptMark} aria-hidden="true">✓</div>
          <span className={styles.receiptEyebrow}>Решение завершено в симуляции</span>
          <h2 id="demo-receipt-title" tabIndex={-1}>Штаб уже учёл результат</h2>
          <p>{DEMO_RECEIPT.summary}</p>
          <dl className={styles.receiptFacts}>
            <div><dt>Квитанция</dt><dd>{DEMO_RECEIPT.receiptId}</dd></div>
            <div><dt>Результат</dt><dd>{DEMO_RECEIPT.externalResult}</dd></div>
            <div><dt>Очередь</dt><dd>3 → 2 решения</dd></div>
            <div><dt>Внешняя запись</dt><dd>нет · false</dd></div>
          </dl>
          <section className={styles.resultTransition}>
            <div><small>Было</small><strong>Atlas SSO</strong><span>под риском</span></div>
            <i aria-hidden="true">→</i>
            <div><small>Стало</small><strong>Atlas SSO</strong><span>на контроле</span></div>
          </section>
          <div className={styles.receiptActions}>
            <button className={styles.primaryAction} onClick={onClose} type="button">Вернуться в обновлённый штаб</button>
            <button className={styles.textAction} onClick={onReset} type="button">Сбросить симуляцию</button>
          </div>
        </div>
      ) : (
        <div className={styles.decisionView}>
          <header className={styles.decisionHeader}>
            <div><span>Решение человека</span><h2>{DEMO_SIGNAL.title}</h2></div>
            <p>Контекст, точный предпросмотр и подтверждение находятся в одном окне.</p>
          </header>
          <div className={styles.decisionGrid}>
            <section className={styles.decisionWhy}>
              <span className={styles.criticalBadge}>До 12:00</span>
              <h3>Почему сейчас</h3>
              <p>Клиентский срок не изменился, а проверка безопасности задержана и план отката остаётся без владельца.</p>
              <dl>
                <div><dt>Ущерб</dt><dd>{DEMO_SIGNAL.impact}</dd></div>
                <div><dt>Владельцы</dt><dd>Тимур · Данияр · София</dd></div>
                <div><dt>Основания</dt><dd>4 источника · 19 ссылок</dd></div>
              </dl>
              <div className={styles.sourceChipRow}>
                {DEMO_SOURCES.map((source) => <span key={source.key}>{source.label}</span>)}
              </div>
            </section>
            <section className={styles.decisionPreview}>
              <span>Точный предпросмотр</span>
              <h3>Что было бы подготовлено</h3>
              <dl>
                <div><dt>Демо-репозиторий</dt><dd>{DEMO_PREVIEW.repository}</dd></div>
                <div><dt>Заголовок</dt><dd>{DEMO_PREVIEW.title}</dd></div>
                <div><dt>Исполнитель</dt><dd>{DEMO_PREVIEW.assignee}</dd></div>
                <div><dt>Описание</dt><dd>{DEMO_PREVIEW.body}</dd></div>
              </dl>
              <label className={styles.confirmationControl}>
                <input checked={confirmationChecked} onChange={(event) => onConfirmationChange(event.target.checked)} type="checkbox" />
                <span><strong>Подтверждаю симуляцию</strong><small>Внешней записи не будет. Изменится только состояние демо-штаба.</small></span>
              </label>
              <button className={styles.primaryAction} disabled={!confirmationChecked} onClick={onCompleteDecision} type="button">
                Зафиксировать результат →
              </button>
            </section>
          </div>
          <p className={styles.modalBoundary}>{DEMO_TRUTH_LABEL}</p>
        </div>
      )}
    </OverlayShell>
  );
}

function OverlayShell({
  children,
  initialFocusSelector,
  label,
  mode,
  onClose
}: {
  children: React.ReactNode;
  initialFocusSelector?: string;
  label: string;
  mode: "drawer" | "modal";
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const panel = panelRef.current;
    const firstFocusable = initialFocusSelector
      ? panel?.querySelector<HTMLElement>(initialFocusSelector)
      : panel?.querySelector<HTMLElement>(
          "button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex='-1'])"
        );
    firstFocusable?.focus();
  }, [initialFocusSelector]);

  function trapFocus(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") {
      return;
    }
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex='-1'])"
      )
    );
    if (focusable.length === 0) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className={`${styles.overlayRoot} ${mode === "modal" ? styles.modalRoot : ""}`}>
      <div className={styles.overlayBackdrop} aria-hidden="true" onMouseDown={onClose} />
      <section
        aria-label={label}
        aria-modal="true"
        className={mode === "drawer" ? styles.drawerPanel : styles.modalPanel}
        onKeyDown={trapFocus}
        ref={panelRef}
        role="dialog"
      >
        <button className={styles.overlayClose} onClick={onClose} type="button" aria-label="Закрыть">×</button>
        {children}
      </section>
    </div>
  );
}

function DrawerTitle({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <header className={styles.drawerTitle}>
      <span>{eyebrow}</span>
      <h2>{title}</h2>
    </header>
  );
}

function touchpointLabel(count: number) {
  const lastTwoDigits = count % 100;
  if (lastTwoDigits >= 11 && lastTwoDigits <= 14) {
    return "касаний";
  }
  const lastDigit = count % 10;
  if (lastDigit === 1) {
    return "касание";
  }
  if (lastDigit >= 2 && lastDigit <= 4) {
    return "касания";
  }
  return "касаний";
}
