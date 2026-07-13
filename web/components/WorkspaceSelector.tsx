"use client";

import type { AuthWorkspace } from "../lib/auth";
import styles from "./workspace-selector.module.css";

type WorkspaceSelectorProps = {
  workspaces: AuthWorkspace[];
  workspaceId: string;
  onSelect: (workspaceId: string) => void;
};

export function WorkspaceSelector({
  workspaces,
  workspaceId,
  onSelect
}: WorkspaceSelectorProps) {
  if (workspaces.length < 2) {
    return (
      <span className={styles.currentWorkspace}>
        {workspaces.find((workspace) => workspace.id === workspaceId)?.name ?? "Компания"}
      </span>
    );
  }

  return (
    <label className={styles.compactSelector}>
      <span>Компания</span>
      <select
        aria-label="Выбрать компанию"
        onChange={(event) => onSelect(event.target.value)}
        value={workspaceId}
      >
        {workspaces.map((workspace) => (
          <option key={workspace.id} value={workspace.id}>
            {workspace.name}
          </option>
        ))}
      </select>
    </label>
  );
}

type WorkspaceChoiceProps = {
  workspaces: AuthWorkspace[];
  onSelect: (workspaceId: string) => void;
  onLogout: () => void;
};

function workspaceRoleLabel(role: string): string {
  if (role === "owner") {
    return "Владелец";
  }
  if (role === "admin") {
    return "Администратор";
  }
  if (role === "viewer") {
    return "Только просмотр";
  }
  return "Участник";
}

export function WorkspaceChoice({
  workspaces,
  onLogout,
  onSelect
}: WorkspaceChoiceProps) {
  return (
    <main className={styles.choiceScreen}>
      <section className={styles.choiceCard} aria-labelledby="workspace-choice-title">
        <div className={styles.choiceMark} aria-hidden="true">
          F
        </div>
        <p className={styles.eyebrow}>Куда войти?</p>
        <h1 id="workspace-choice-title">Выберите компанию</h1>
        <p className={styles.choiceLead}>
          У вас несколько рабочих пространств. FounderOS покажет данные только выбранной
          компании.
        </p>
        <div className={styles.workspaceList}>
          {workspaces.map((workspace) => (
            <button
              className={styles.workspaceButton}
              key={workspace.id}
              onClick={() => onSelect(workspace.id)}
              type="button"
            >
              <span>
                <strong>{workspace.name}</strong>
                <small>{workspaceRoleLabel(workspace.role)}</small>
              </span>
              <span aria-hidden="true">→</span>
            </button>
          ))}
        </div>
        <p className={styles.choiceHint}>
          Выбор сохранится только в этом браузере. Его всегда можно изменить сверху.
        </p>
        <button className={styles.choiceSignOut} onClick={onLogout} type="button">
          Выйти из аккаунта
        </button>
      </section>
    </main>
  );
}
