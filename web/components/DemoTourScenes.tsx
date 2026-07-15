import {
  DEMO_ATLAS_PROFILE,
  DEMO_BRIEFING,
  DEMO_COMPANY,
  DEMO_DOCUMENTS,
  DEMO_MISSIONS,
  DEMO_MISSION_SUMMARY,
  DEMO_PREVIEW,
  DEMO_RECEIPT,
  DEMO_RELATIONSHIPS,
  DEMO_SIGNAL,
  DEMO_SOURCES,
  DEMO_TEAM,
  DEMO_TRUTH_LABEL,
  type DemoSourceKey
} from "../lib/demo-tour";
import styles from "../app/demo/demo.module.css";

export type DemoDecisionStep = "review" | "preview";
export type DemoProfileView = "company" | "person";

type DemoTourScenesProps = {
  actionSimulated: boolean;
  confirmationChecked: boolean;
  decisionStep: DemoDecisionStep;
  hintsVisible: boolean;
  onConfirmationChange: (checked: boolean) => void;
  onDecisionStepChange: (step: DemoDecisionStep) => void;
  onNavigate: (sceneIndex: number) => void;
  onProfileViewChange: (view: DemoProfileView) => void;
  onSelectRelationship: (name: string) => void;
  onSelectSource: (source: DemoSourceKey) => void;
  onSimulateAction: () => void;
  profileView: DemoProfileView;
  sceneIndex: number;
  selectedRelationship: string;
  selectedSource: DemoSourceKey;
};

export function DemoTourScenes(props: DemoTourScenesProps) {
  switch (props.sceneIndex) {
    case 0:
      return <ReadyScene onNavigate={props.onNavigate} />;
    case 1:
      return (
        <SourcesScene
          onSelectSource={props.onSelectSource}
          selectedSource={props.selectedSource}
        />
      );
    case 2:
      return <SignalScene hintsVisible={props.hintsVisible} />;
    case 3:
      return (
        <HeadquartersScene
          actionSimulated={props.actionSimulated}
          onNavigate={props.onNavigate}
        />
      );
    case 4:
      return (
        <WorldScene
          onNavigate={props.onNavigate}
          onSelectRelationship={props.onSelectRelationship}
          selectedRelationship={props.selectedRelationship}
        />
      );
    case 5:
      return (
        <CustomerScene
          onProfileViewChange={props.onProfileViewChange}
          profileView={props.profileView}
        />
      );
    case 6:
      return <TeamScene />;
    case 7:
      return <KnowledgeScene />;
    case 8:
      return <BriefingScene onNavigate={props.onNavigate} />;
    case 9:
      return (
        <MissionsScene
          actionSimulated={props.actionSimulated}
          onNavigate={props.onNavigate}
        />
      );
    case 10:
      return (
        <DecisionScene
          actionSimulated={props.actionSimulated}
          confirmationChecked={props.confirmationChecked}
          decisionStep={props.decisionStep}
          onConfirmationChange={props.onConfirmationChange}
          onDecisionStepChange={props.onDecisionStepChange}
          onNavigate={props.onNavigate}
          onSimulateAction={props.onSimulateAction}
        />
      );
    default:
      return (
        <ResultScene
          actionSimulated={props.actionSimulated}
          onNavigate={props.onNavigate}
        />
      );
  }
}

function ReadyScene({ onNavigate }: { onNavigate: (sceneIndex: number) => void }) {
  const setupSteps = [
    ["Компания", "NovaFlow создана"],
    ["Источники", "4 из 4 подключены"],
    ["Данные", "858 записей согласованы"],
    ["Карта", "3 внешних контура"],
    ["Команда", "6 участников"],
    ["Штаб", "Первый приоритет готов"]
  ] as const;

  return (
    <SceneLayout eyebrow="Готовность 6 из 6" title="Компания уже живёт в FounderOS">
      <div className={styles.readyGrid}>
        <section className={`${styles.heroPanel} ${styles.heroPanelDark}`}>
          <div className={styles.readinessRing} aria-label="Готовность 100 процентов">
            <span>100%</span>
            <small>готово</small>
          </div>
          <div>
            <span className={styles.miniEyebrow}>NovaFlow · рабочий контур</span>
            <h3>Можно начинать день без дополнительной настройки</h3>
            <p>
              Источники, команда, отношения и первый приоритет уже связаны в одну
              проверяемую картину.
            </p>
            <button className={styles.primaryCta} onClick={() => onNavigate(1)} type="button">
              Посмотреть живую систему <span aria-hidden="true">→</span>
            </button>
          </div>
        </section>
        <section className={styles.setupChecklist} aria-label="Завершённые шаги настройки">
          {setupSteps.map(([label, value], index) => (
            <div className={styles.setupStep} key={label}>
              <span className={styles.checkMark} aria-hidden="true">✓</span>
              <span>
                <small>0{index + 1} · {label}</small>
                <strong>{value}</strong>
              </span>
            </div>
          ))}
        </section>
      </div>
      <MetricStrip
        items={[
          ["4 / 4", "источника"],
          ["858", "записей"],
          ["6", "сотрудников"],
          ["37", "касаний"]
        ]}
      />
    </SceneLayout>
  );
}

function SourcesScene({
  onSelectSource,
  selectedSource
}: {
  onSelectSource: (source: DemoSourceKey) => void;
  selectedSource: DemoSourceKey;
}) {
  const activeSource =
    DEMO_SOURCES.find((source) => source.key === selectedSource) ?? DEMO_SOURCES[0];

  return (
    <SceneLayout eyebrow="Радары · 4 из 4" title="Вся работа компании синхронизирована">
      <div className={styles.sourcesLayout}>
        <div className={styles.sourceGrid}>
          {DEMO_SOURCES.map((source) => (
            <button
              aria-pressed={source.key === activeSource.key}
              className={`${styles.sourceCard} ${source.key === activeSource.key ? styles.sourceCardActive : ""}`}
              key={source.key}
              onClick={() => onSelectSource(source.key)}
              style={{ "--source-accent": source.accent } as React.CSSProperties}
              type="button"
            >
              <span className={styles.sourceCardTop}>
                <span className={styles.sourceDot} aria-hidden="true" />
                <strong>{source.label}</strong>
                <small>{source.freshness}</small>
              </span>
              <span className={styles.sourceRecordCount}>{source.records}</span>
              <span>согласованных записей</span>
              <span className={styles.sourceSignal}>{source.signal}</span>
            </button>
          ))}
        </div>
        <section className={styles.sourceInspector} aria-live="polite">
          <span className={styles.liveStatus}><i aria-hidden="true" /> Подключён</span>
          <span className={styles.miniEyebrow}>{activeSource.label} · свежий снимок</span>
          <div className={styles.sourcePrimaryMetric}>
            <strong>{activeSource.primaryMetric}</strong>
            <span>{activeSource.primaryMetricLabel}</span>
          </div>
          <dl className={styles.compactFacts}>
            {activeSource.secondaryMetrics.map((metric) => (
              <div key={metric.label}>
                <dt>{metric.label}</dt>
                <dd>{metric.value}</dd>
              </div>
            ))}
          </dl>
          <div className={styles.insightCard}>
            <small>Замечен сигнал</small>
            <strong>{activeSource.signal}</strong>
            <span>FounderOS свяжет его с фактами из других источников.</span>
          </div>
        </section>
      </div>
    </SceneLayout>
  );
}

function SignalScene({ hintsVisible }: { hintsVisible: boolean }) {
  return (
    <SceneLayout eyebrow="Связанный сигнал · уверенность 96%" title={DEMO_SIGNAL.title}>
      <div className={styles.signalSummary}>
        <div>
          <small>Возможный ущерб</small>
          <strong>{DEMO_SIGNAL.impact}</strong>
        </div>
        <div>
          <small>Владелец разбора</small>
          <strong>{DEMO_SIGNAL.owner}</strong>
        </div>
        <div>
          <small>Срок клиента</small>
          <strong>22 июля · неизменный</strong>
        </div>
      </div>
      <div className={styles.signalPipeline}>
        {DEMO_SIGNAL.events.map((event, index) => (
          <article className={styles.signalEvent} key={event.source}>
            <span className={styles.pipelineIndex}>0{index + 1}</span>
            <span className={styles.sourcePill}>{event.source}</span>
            <small>{event.time}</small>
            <h3>{event.title}</h3>
            <p>{event.detail}</p>
            {index < DEMO_SIGNAL.events.length - 1 ? (
              <span className={styles.pipelineArrow} aria-hidden="true">→</span>
            ) : null}
          </article>
        ))}
      </div>
      <div className={`${styles.causalConclusion} ${hintsVisible ? styles.hintTarget : ""}`}>
        <span>Не четыре уведомления</span>
        <strong>Один риск: запуск нельзя обещать без проверки безопасности и ответственного за откат.</strong>
      </div>
    </SceneLayout>
  );
}

function HeadquartersScene({
  actionSimulated,
  onNavigate
}: {
  actionSimulated: boolean;
  onNavigate: (sceneIndex: number) => void;
}) {
  const activeOwners = actionSimulated
    ? DEMO_TEAM.filter((person) => person.name === "Мила Орлова")
    : DEMO_TEAM.filter((person) => person.status === "В миссии");

  return (
    <SceneLayout
      eyebrow={actionSimulated ? "Штаб · после решения" : "Штаб · сегодня"}
      title={actionSimulated ? "Результат изменил следующий приоритет" : "Главное видно с первого взгляда"}
    >
      <div className={styles.hqGrid}>
        <section className={`${styles.missionHero} ${styles.heroPanelDark}`}>
          <div className={styles.missionHeroTop}>
            <span className={styles.criticalBadge}>{actionSimulated ? "Новый приоритет №1" : "Приоритет №1"}</span>
            <span>{actionSimulated ? "2 основания · 1 владелец" : "4 источника · 19 ссылок"}</span>
          </div>
          <h3>{actionSimulated ? "Назначить владельца повторной отправки уведомлений" : DEMO_SIGNAL.title}</h3>
          <p>
            {actionSimulated
              ? "Atlas SSO перешёл под контроль. Штаб пересчитал очередь и поднял следующий объяснимый риск."
              : "Срок заказчика совпал с техническим и операционным блокером. Решение нужно принять до 12:00."}
          </p>
          <div className={styles.ownerStack} aria-label="Владельцы миссии">
            {activeOwners.map((person) => (
              <span key={person.name} title={person.name}>{person.initials}</span>
            ))}
            <small>{actionSimulated ? "Мила Орлова" : "Тимур · Данияр · София"}</small>
          </div>
          <button className={styles.primaryCta} onClick={() => onNavigate(actionSimulated ? 9 : 4)} type="button">
            {actionSimulated ? "Открыть обновлённую очередь" : "Открыть карту связей"} <span aria-hidden="true">→</span>
          </button>
        </section>
        <section className={styles.worldPulseMini}>
          <div className={styles.worldPulseHeader}>
            <span className={styles.miniEyebrow}>Пульс компании</span>
            <span className={styles.liveStatus}><i aria-hidden="true" /> сейчас</span>
          </div>
          <div className={styles.orbitMini} aria-hidden="true">
            <span className={styles.orbitCompany}>N</span>
            <span className={styles.orbitTeam}>6</span>
            <span className={styles.orbitCustomer}>A</span>
            <span className={styles.orbitLead}>V</span>
            <span className={styles.orbitPartner}>K</span>
          </div>
          <dl className={styles.worldFacts}>
            <div><dt>Команда</dt><dd>6</dd></div>
            <div><dt>Компании</dt><dd>3</dd></div>
            <div><dt>Касания</dt><dd>37</dd></div>
          </dl>
        </section>
      </div>
      <div className={styles.hqQueue}>
        {actionSimulated ? (
          <article className={styles.hqQueueResolved}>
            <span>✓</span>
            <div><small>Результат зафиксирован</small><strong>Atlas SSO · на контроле</strong></div>
            <small>{DEMO_RECEIPT.receiptId}</small>
          </article>
        ) : null}
        {DEMO_BRIEFING.slice(actionSimulated ? 1 : 0).map((item, index) => (
          <article key={item.title}>
            <span>0{index + 1}</span>
            <div><small>{item.label}</small><strong>{item.title}</strong></div>
            <small>{item.evidence} основания</small>
          </article>
        ))}
      </div>
    </SceneLayout>
  );
}

function WorldScene({
  onNavigate,
  onSelectRelationship,
  selectedRelationship
}: {
  onNavigate: (sceneIndex: number) => void;
  onSelectRelationship: (name: string) => void;
  selectedRelationship: string;
}) {
  const selected =
    DEMO_RELATIONSHIPS.find((relationship) => relationship.name === selectedRelationship) ??
    DEMO_RELATIONSHIPS[0];

  return (
    <SceneLayout eyebrow="Мир компании · 37 касаний" title="Компания — это сеть живых отношений">
      <div className={styles.worldLayout}>
        <section className={styles.worldCanvas} aria-label="Карта отношений NovaFlow">
          <div className={styles.worldRing} aria-hidden="true" />
          <div className={`${styles.worldNode} ${styles.worldNodeCompany}`}>
            <span>N</span><strong>NovaFlow</strong><small>ваша компания</small>
          </div>
          {DEMO_RELATIONSHIPS.map((relationship, index) => (
            <button
              aria-pressed={selected.name === relationship.name}
              className={`${styles.worldNode} ${styles.worldNodeExternal} ${styles[`worldNodeExternal${index + 1}`]}`}
              key={relationship.name}
              onClick={() => onSelectRelationship(relationship.name)}
              type="button"
            >
              <span>{relationship.name.slice(0, 1)}</span>
              <strong>{relationship.name}</strong>
              <small>
                {relationship.touchpoints} {touchpointLabel(relationship.touchpoints)}
              </small>
            </button>
          ))}
          <div className={`${styles.worldNode} ${styles.worldNodeTeam}`}>
            <span>6</span><strong>Команда</strong><small>людей</small>
          </div>
        </section>
        <section className={styles.worldInspector} aria-live="polite">
          <span className={styles.miniEyebrow}>{selected.kind}</span>
          <h3>{selected.name}</h3>
          <p>{selected.risk}</p>
          <MetricStrip
            compact
            items={[
              [String(selected.contacts), "контакта"],
              [String(selected.touchpoints), touchpointLabel(selected.touchpoints)],
              [selected.name === "Atlas Retail" ? "2 ч" : "1 д", "последнее"]
            ]}
          />
          <div className={styles.relationshipOwners}>
            <small>Владелец отношения</small>
            <strong>{selected.name === "Atlas Retail" ? "Данияр Иманов" : "Арсен Ким"}</strong>
          </div>
          {selected.name === "Atlas Retail" ? (
            <button className={styles.secondaryCta} onClick={() => onNavigate(5)} type="button">
              Открыть профиль заказчика
            </button>
          ) : null}
        </section>
      </div>
    </SceneLayout>
  );
}

function CustomerScene({
  onProfileViewChange,
  profileView
}: {
  onProfileViewChange: (view: DemoProfileView) => void;
  profileView: DemoProfileView;
}) {
  const decisionMaker = DEMO_ATLAS_PROFILE.people[0];
  return (
    <SceneLayout eyebrow="Atlas Retail · стратегический заказчик" title="Контекст до разговора — в одном профиле">
      <div className={styles.profileScene}>
        <div className={styles.profileTabs} role="tablist" aria-label="Профиль Atlas Retail">
          <button aria-selected={profileView === "company"} onClick={() => onProfileViewChange("company")} role="tab" type="button">
            Компания
          </button>
          <button aria-selected={profileView === "person"} onClick={() => onProfileViewChange("person")} role="tab" type="button">
            Ключевое лицо
          </button>
        </div>
        <div className={styles.profileGrid}>
          <section className={styles.profileIdentity}>
          <div className={styles.profileAvatar}>{profileView === "company" ? "AR" : decisionMaker.initials}</div>
          <span className={styles.miniEyebrow}>{profileView === "company" ? DEMO_ATLAS_PROFILE.company.status : decisionMaker.decisionRole}</span>
          <h3>{profileView === "company" ? DEMO_ATLAS_PROFILE.company.name : decisionMaker.name}</h3>
          <p>{profileView === "company" ? "Retail · корпоративный контур" : decisionMaker.role}</p>
          <dl className={styles.profileFacts}>
            <div><dt>Касания</dt><dd>{profileView === "company" ? 21 : decisionMaker.touchpoints}</dd></div>
            <div><dt>Последнее</dt><dd>2 часа назад</dd></div>
            <div><dt>Владелец</dt><dd>Данияр</dd></div>
          </dl>
          <div className={styles.profilePeople}>
            {DEMO_ATLAS_PROFILE.people.map((person) => (
              <span key={person.name} title={`${person.name} · ${person.decisionRole}`}>{person.initials}</span>
            ))}
            <small>4 контакта в компании</small>
          </div>
          </section>
          <section className={styles.timelinePanel}>
          <div className={styles.sectionHeading}>
            <div><span className={styles.miniEyebrow}>История отношений</span><h3>Что уже произошло</h3></div>
            <span className={styles.sourcePill}>Gmail + Drive</span>
          </div>
          <ol className={styles.timelineList}>
            {DEMO_ATLAS_PROFILE.timeline.map((event) => (
              <li key={`${event.source}-${event.time}`}>
                <span className={styles.timelineDot} aria-hidden="true" />
                <div><small>{event.source} · {event.time}</small><strong>{event.text}</strong></div>
              </li>
            ))}
          </ol>
          <div className={styles.profilePromise}>
            <small>Зафиксированное обещание</small>
            <strong>Запуск 22 июля · итог проверки безопасности до 16 июля</strong>
          </div>
          </section>
        </div>
      </div>
    </SceneLayout>
  );
}

function TeamScene() {
  return (
    <SceneLayout eyebrow="Команда · 6 человек" title="У результата есть конкретные владельцы">
      <div className={styles.teamLayout}>
        <section className={styles.teamGrid} aria-label="Команда NovaFlow">
          {DEMO_TEAM.map((person) => (
            <article className={`${styles.personCard} ${person.status === "В миссии" ? styles.personCardActive : ""}`} key={person.name}>
              <span className={styles.personAvatar}>{person.initials}</span>
              <div><strong>{person.name}</strong><small>{person.role}</small></div>
              <p>{person.focus}</p>
              <span className={styles.personStatus}>{person.status}</span>
            </article>
          ))}
        </section>
        <aside className={`${styles.squadPanel} ${styles.heroPanelDark}`}>
          <span className={styles.miniEyebrow}>Команда миссии</span>
          <h3>Atlas SSO</h3>
          {DEMO_TEAM.filter((person) => person.status === "В миссии").map((person, index) => (
            <div className={styles.squadMember} key={person.name}>
              <span>{person.initials}</span>
              <div><strong>{person.name}</strong><small>{index === 0 ? "Решение" : index === 1 ? "Клиент" : "Исполнение"}</small></div>
            </div>
          ))}
          <p>FounderOS показывает ответственность, но не назначает людей автоматически.</p>
        </aside>
      </div>
    </SceneLayout>
  );
}

function KnowledgeScene() {
  return (
    <SceneLayout eyebrow="Знания · 19 ссылок на факты" title="Основания решения собраны в один пакет">
      <div className={styles.knowledgeLayout}>
        <section className={styles.documentList}>
          <div className={styles.sectionHeading}>
            <div><span className={styles.miniEyebrow}>Связано с Atlas SSO</span><h3>Рабочие документы</h3></div>
            <span className={styles.liveStatus}><i aria-hidden="true" /> актуально</span>
          </div>
          {DEMO_DOCUMENTS.map((document) => (
            <article key={document.name}>
              <span className={styles.documentIcon} aria-hidden="true">▤</span>
              <div><strong>{document.name}</strong><small>{document.owner} · {document.updated}</small></div>
              <span>{document.evidence} ссылок</span>
              <em>{document.status}</em>
            </article>
          ))}
        </section>
        <section className={styles.evidenceGraph}>
          <span className={styles.miniEyebrow}>Цепочка доказательств</span>
          <h3>Почему миссия существует</h3>
          <div className={styles.evidenceSources}>
            {DEMO_SOURCES.map((source) => (
              <div key={source.key} style={{ "--source-accent": source.accent } as React.CSSProperties}>
                <span className={styles.sourceDot} />
                <strong>{source.label}</strong>
                <small>{source.key === "drive" ? "4 документа" : "1 подтверждённый факт"}</small>
              </div>
            ))}
          </div>
          <div className={styles.evidenceOutcome}>
            <small>Проверяемый вывод</small>
            <strong>Запуск требует проверки безопасности и ответственного за откат.</strong>
          </div>
        </section>
      </div>
    </SceneLayout>
  );
}

function BriefingScene({ onNavigate }: { onNavigate: (sceneIndex: number) => void }) {
  return (
    <SceneLayout eyebrow="Сводка основателя · 10:30" title="Три решения вместо потока новостей">
      <div className={styles.briefingIntro}>
        <div><small>Что изменилось</small><strong>Atlas подтвердил срок, а проверка безопасности всё ещё заблокирована.</strong></div>
        <div><small>Главный риск</small><strong>Запуск может сдвинуться на 5–8 рабочих дней.</strong></div>
        <div><small>Фокус дня</small><strong>Закрыть Atlas SSO до 12:00.</strong></div>
      </div>
      <section className={styles.briefingList}>
        {DEMO_BRIEFING.map((item, index) => (
          <article className={index === 0 ? styles.briefingPrimary : ""} key={item.title}>
            <span className={styles.briefingNumber}>0{index + 1}</span>
            <div><small>{item.label}</small><h3>{item.title}</h3><p>{item.sources}</p></div>
            <span className={styles.evidenceCount}>{item.evidence} основания</span>
            {index === 0 ? (
              <button onClick={() => onNavigate(9)} type="button">Открыть миссию →</button>
            ) : (
              <span className={styles.queueTime}>{index === 1 ? "до 15:00" : "до 16:00"}</span>
            )}
          </article>
        ))}
      </section>
    </SceneLayout>
  );
}

function MissionsScene({
  actionSimulated,
  onNavigate
}: {
  actionSimulated: boolean;
  onNavigate: (sceneIndex: number) => void;
}) {
  const visibleMissions = actionSimulated ? DEMO_MISSIONS.slice(1) : DEMO_MISSIONS;

  return (
    <SceneLayout
      eyebrow="Миссии · загружено 12"
      title={actionSimulated ? "Очередь пересчитана по результату" : "Очередь показывает только решения человека"}
    >
      <MetricStrip
        items={[
          [String(actionSimulated ? DEMO_MISSION_SUMMARY.waitingAfter : DEMO_MISSION_SUMMARY.waiting), "ждут решения"],
          [String(DEMO_MISSION_SUMMARY.approved), "одобрены"],
          [String(DEMO_MISSION_SUMMARY.completed + (actionSimulated ? 1 : 0)), "с результатом"]
        ]}
      />
      <div className={styles.missionsLayout}>
        <section className={styles.missionQueueDemo}>
          <div className={styles.sectionHeading}>
            <div><span className={styles.miniEyebrow}>Очередь решений</span><h3>Сначала самое важное</h3></div>
            <span>{visibleMissions.length} миссии</span>
          </div>
          {visibleMissions.map((mission, index) => {
            const content = (
              <>
                <span className={styles.missionQueueNumber}>0{index + 1}</span>
                <div><small>{mission.urgency}</small><strong>{mission.title}</strong><span>{mission.owner}</span></div>
                <em>{mission.evidenceRefs} ссылок</em>
                {!actionSimulated && index === 0 ? <span aria-hidden="true">→</span> : <span className={styles.queueSnapshotMark}>•</span>}
              </>
            );

            return !actionSimulated && index === 0 ? (
              <button className={styles.missionQueueActive} key={mission.id} onClick={() => onNavigate(10)} type="button">
                {content}
              </button>
            ) : (
              <article className={index === 0 ? styles.missionQueueActive : ""} key={mission.id}>
                {content}
              </article>
            );
          })}
        </section>
        <aside className={styles.queueLogic}>
          <span className={styles.miniEyebrow}>Почему такой порядок</span>
          <h3>{actionSimulated ? "Результат учтён" : "Приоритет объясним"}</h3>
          {actionSimulated ? (
            <ol>
              <li><span>✓</span> Atlas SSO уже на контроле</li>
              <li><span>01</span> Повторная отправка уведомлений без владельца</li>
              <li><span>02</span> Два источника подтверждают пробел</li>
              <li><span>03</span> Назначение доступно сегодня</li>
            </ol>
          ) : (
            <ol>
              <li><span>01</span> Неизменный срок клиента</li>
              <li><span>02</span> Два независимых блокера</li>
              <li><span>03</span> Четыре источника подтверждают риск</li>
              <li><span>04</span> Решение доступно сегодня</li>
            </ol>
          )}
          <p>{actionSimulated ? "Квитанция убрала завершённую миссию из ожидания. Внешних действий не было." : "Система предлагает порядок. Решение всё равно принимает человек."}</p>
        </aside>
      </div>
    </SceneLayout>
  );
}

function DecisionScene({
  actionSimulated,
  confirmationChecked,
  decisionStep,
  onConfirmationChange,
  onDecisionStepChange,
  onNavigate,
  onSimulateAction
}: {
  actionSimulated: boolean;
  confirmationChecked: boolean;
  decisionStep: DemoDecisionStep;
  onConfirmationChange: (checked: boolean) => void;
  onDecisionStepChange: (step: DemoDecisionStep) => void;
  onNavigate: (sceneIndex: number) => void;
  onSimulateAction: () => void;
}) {
  return (
    <SceneLayout eyebrow="Комната решений · DEMO-MISSION-042" title={DEMO_SIGNAL.title}>
      <div className={styles.decisionLayout}>
        <section className={`${styles.decisionContext} ${styles.heroPanelDark}`}>
          <span className={styles.criticalBadge}>{actionSimulated ? "Решение зафиксировано" : "Решение нужно до 12:00"}</span>
          <h3>{actionSimulated ? "Atlas SSO · на контроле" : "Почему сейчас"}</h3>
          <p>{actionSimulated ? "Владельцы назначены, локальная квитанция сохранена, очередь пересчитана." : "Срок клиента не изменился, проверка безопасности задержана, изменение кода заблокировано, а ответственный за откат не назначен."}</p>
          <dl>
            <div><dt>{actionSimulated ? "Результат" : "Ущерб"}</dt><dd>{actionSimulated ? DEMO_RECEIPT.externalResult : "5–8 рабочих дней"}</dd></div>
            <div><dt>Владельцы</dt><dd>Тимур · Данияр · София</dd></div>
            <div><dt>Основания</dt><dd>4 источника · 19 ссылок</dd></div>
          </dl>
          <div className={styles.decisionEvidenceRow}>
            {DEMO_SOURCES.map((source) => <span key={source.key}>{source.label}</span>)}
          </div>
        </section>
        <section className={styles.decisionAction}>
          {actionSimulated ? (
            <>
              <span className={styles.miniEyebrow}>Шаг завершён · квитанция готова</span>
              <h3>Повторное выполнение не требуется</h3>
              <p>Эта симуляция уже завершена. Результат можно проверить, а новый штаб — открыть из квитанции.</p>
              <div className={styles.decisionChecks}>
                <span><i aria-hidden="true">✓</i> Решение сохранено локально</span>
                <span><i aria-hidden="true">✓</i> Очередь 3 → 2</span>
                <span><i aria-hidden="true">✓</i> Внешних записей нет</span>
              </div>
              <button className={styles.primaryCta} onClick={() => onNavigate(11)} type="button">
                Открыть квитанцию →
              </button>
            </>
          ) : decisionStep === "review" ? (
            <>
              <span className={styles.miniEyebrow}>Шаг 1 · решение внутри FounderOS</span>
              <h3>Снять блокеры и назначить владельцев</h3>
              <p>Решение сохранится локально. Никакого внешнего действия на этом шаге нет.</p>
              <div className={styles.decisionChecks}>
                <span><i aria-hidden="true">✓</i> Проверка безопасности — Тимур</span>
                <span><i aria-hidden="true">✓</i> Ответственный за откат — София</span>
                <span><i aria-hidden="true">✓</i> Клиентский статус — Данияр</span>
              </div>
              <button className={styles.primaryCta} onClick={() => onDecisionStepChange("preview")} type="button">
                Принять решение в демо →
              </button>
            </>
          ) : (
            <>
              <span className={styles.miniEyebrow}>Шаг 2 · точный предпросмотр</span>
              <h3>Что было бы отправлено</h3>
              <dl className={styles.previewFacts}>
                <div><dt>DEMO репозиторий</dt><dd>{DEMO_PREVIEW.repository}</dd></div>
                <div><dt>Заголовок</dt><dd>{DEMO_PREVIEW.title}</dd></div>
                <div><dt>Исполнитель</dt><dd>{DEMO_PREVIEW.assignee}</dd></div>
                <div><dt>Метки</dt><dd>{DEMO_PREVIEW.labels.join(" · ")}</dd></div>
              </dl>
              <label className={styles.demoConfirmation}>
                <input checked={confirmationChecked} onChange={(event) => onConfirmationChange(event.target.checked)} type="checkbox" />
                Я понимаю: это только симуляция, внешней записи не будет.
              </label>
              <div className={styles.decisionButtons}>
                <button className={styles.secondaryCta} onClick={() => onDecisionStepChange("review")} type="button">Назад</button>
                <button className={styles.primaryCta} disabled={!confirmationChecked} onClick={onSimulateAction} type="button">
                  Симулировать результат →
                </button>
              </div>
            </>
          )}
          <p className={styles.inlineTruth}>{DEMO_TRUTH_LABEL}</p>
        </section>
      </div>
    </SceneLayout>
  );
}

function ResultScene({
  actionSimulated,
  onNavigate
}: {
  actionSimulated: boolean;
  onNavigate: (sceneIndex: number) => void;
}) {
  return (
    <SceneLayout
      eyebrow={actionSimulated ? "Замкнутый цикл · результат" : "Замкнутый цикл · предпросмотр"}
      title={actionSimulated ? "Миссия завершилась проверяемой квитанцией" : "Так будет выглядеть результат после подтверждения"}
    >
      <div className={styles.resultLayout}>
        <section className={`${styles.receiptCard} ${styles.heroPanelDark}`}>
          <div className={styles.receiptStatus}>
            <span aria-hidden="true">{actionSimulated ? "✓" : "…"}</span>
            <div>
              <small>{actionSimulated ? "Симуляция завершена" : "Ожидаемый формат квитанции"}</small>
              <strong>{actionSimulated ? "Результат сохранён" : "Результат ещё не сохранён"}</strong>
            </div>
          </div>
          <dl>
            <div><dt>Квитанция</dt><dd>{actionSimulated ? DEMO_RECEIPT.receiptId : "после шага 11"}</dd></div>
            <div><dt>Результат</dt><dd>{actionSimulated ? DEMO_RECEIPT.externalResult : "ещё не присвоен"}</dd></div>
            <div><dt>Режим</dt><dd>{actionSimulated ? DEMO_RECEIPT.status : "предпросмотр"}</dd></div>
            <div><dt>Внешняя запись</dt><dd>нет · false</dd></div>
          </dl>
          <p>
            {actionSimulated
              ? DEMO_RECEIPT.summary
              : "Это только предпросмотр безопасного результата. Очередь и штаб пока не изменены."}
          </p>
        </section>
        <section className={styles.beforeAfter}>
          <span className={styles.miniEyebrow}>{actionSimulated ? "Что изменилось в картине компании" : "Что изменится после подтверждения"}</span>
          <div className={styles.comparisonGrid}>
            <div><small>До решения</small><strong>3</strong><span>ждут решения</span><em>Atlas SSO · под риском</em></div>
            <span className={styles.comparisonArrow} aria-hidden="true">→</span>
            <div>
              <small>{actionSimulated ? "После симуляции" : "Ожидается после симуляции"}</small>
              <strong>{actionSimulated ? "2" : "—"}</strong>
              <span>{actionSimulated ? "ждут решения" : "ещё не рассчитано"}</span>
              <em>{actionSimulated ? "Atlas SSO · на контроле" : "Требуется шаг 11"}</em>
            </div>
          </div>
          <div className={styles.closedLoop}>
            <span>Сигнал</span><i>→</i><span>Контекст</span><i>→</i><span>Решение</span><i>→</i><span>Квитанция</span><i>→</i><strong>Новый штаб</strong>
          </div>
          <button className={styles.primaryCta} onClick={() => onNavigate(actionSimulated ? 3 : 10)} type="button">
            {actionSimulated ? "Увидеть обновлённый штаб" : "Сначала пройти решение"} →
          </button>
        </section>
      </div>
    </SceneLayout>
  );
}

function SceneLayout({
  children,
  eyebrow,
  title
}: {
  children: React.ReactNode;
  eyebrow: string;
  title: string;
}) {
  return (
    <div className={styles.sceneLayout}>
      <header className={styles.sceneHeader}>
        <div><span>{eyebrow}</span><h2>{title}</h2></div>
        <span className={styles.sceneTimestamp}>Снимок · 10:30</span>
      </header>
      <div className={styles.sceneBody}>{children}</div>
    </div>
  );
}

function MetricStrip({
  compact = false,
  items
}: {
  compact?: boolean;
  items: readonly (readonly [string, string])[];
}) {
  return (
    <dl className={`${styles.metricStrip} ${compact ? styles.metricStripCompact : ""}`}>
      {items.map(([value, label]) => (
        <div key={label}><dd>{value}</dd><dt>{label}</dt></div>
      ))}
    </dl>
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
