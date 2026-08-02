import type { ReactNode } from "react";

type MissionStripProps = {
  action: string;
  current: string;
  details?: ReactNode;
  outcome: string;
};

export function MissionStrip({
  action,
  current,
  details,
  outcome
}: MissionStripProps) {
  return (
    <aside className="mission-strip" aria-label="Что делать на этом экране">
      <div className="mission-strip-step">
        <span className="mission-strip-index" aria-hidden="true">01</span>
        <div>
          <small>Сейчас</small>
          <strong>{current}</strong>
        </div>
      </div>
      <div className="mission-strip-step">
        <span className="mission-strip-index" aria-hidden="true">02</span>
        <div>
          <small>Нажмите</small>
          <strong>{action}</strong>
        </div>
      </div>
      <div className="mission-strip-step mission-strip-step--outcome">
        <span className="mission-strip-index" aria-hidden="true">03</span>
        <div>
          <small>Результат</small>
          <strong>{outcome}</strong>
        </div>
      </div>
      {details ? (
        <details className="mission-strip-details">
          <summary>Как это работает безопасно</summary>
          <div>{details}</div>
        </details>
      ) : null}
    </aside>
  );
}

export function MiniHint({
  children,
  label = "Что это значит?"
}: {
  children: ReactNode;
  label?: string;
}) {
  return (
    <details className="mini-hint">
      <summary aria-label={label}>?</summary>
      <div>{children}</div>
    </details>
  );
}
