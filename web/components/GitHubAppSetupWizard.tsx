"use client";

import type { FormEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

import {
  ApiRequestError,
  beginGitHubAppInstallSetup,
  beginGitHubAppManifestSetup,
  fetchGitHubAppSetupStatus,
  refreshGitHubAppSetupRepositories,
  restartGitHubAppSetup,
  selectGitHubAppRepositories
} from "../lib/api";
import { M } from "../lib/messages";
import { safeGitHubLaunchHref } from "../lib/safeHref";
import type {
  GitHubAppSetupPhase,
  GitHubAppSetupRepositoryRead,
  GitHubAppSetupStatus
} from "../lib/types";

const REPOSITORY_PREVIEW_LIMIT = 8;
const REPOSITORY_SELECTION_LIMIT = 100;

type SetupLoadState = "loading" | "ready" | "error";
type SetupAction =
  | "idle"
  | "manifest"
  | "install"
  | "refresh"
  | "repositories"
  | "restart";
type GitHubAppOwnerType = "user" | "organization";

export type GitHubManifestFormSpec = {
  action: string;
  method: "POST";
  fields: [{ name: "manifest"; value: string }];
};

type GitHubAppSetupWizardProps = {
  canAdminister: boolean;
  onSetupChange?: () => void;
  workspaceId: string;
};

type GitHubAppSetupWizardViewProps = {
  action: SetupAction;
  actionError: string | null;
  canAdminister: boolean;
  loadState: SetupLoadState;
  onInstall: () => void;
  onOrganizationLoginChange: (value: string) => void;
  onOwnerTypeChange: (value: GitHubAppOwnerType) => void;
  onRefreshRepositories: () => void;
  onRepositoryToggle: (repository: string) => void;
  onRestart: () => void;
  onRetry: () => void;
  onSaveRepositories: () => void;
  onStart: () => void;
  organizationLogin: string;
  ownerType: GitHubAppOwnerType;
  selectedRepositories: Set<string>;
  status: GitHubAppSetupStatus | null;
};

export function buildGitHubManifestFormSpec(
  actionUrl: string,
  manifest: string
): GitHubManifestFormSpec | null {
  const action = safeGitHubLaunchHref(actionUrl);
  if (action === null || manifest.trim() === "") {
    return null;
  }
  return {
    action,
    fields: [{ name: "manifest", value: manifest }],
    method: "POST"
  };
}

function submitGitHubManifestForm(actionUrl: string, manifest: string): boolean {
  const spec = buildGitHubManifestFormSpec(actionUrl, manifest);
  if (spec === null) {
    return false;
  }

  const form = document.createElement("form");
  form.action = spec.action;
  form.method = spec.method;
  form.hidden = true;
  const input = document.createElement("input");
  input.name = spec.fields[0].name;
  input.type = "hidden";
  input.value = spec.fields[0].value;
  form.append(input);
  document.body.append(form);
  form.submit();
  return true;
}

export function GitHubAppSetupWizard({
  canAdminister,
  onSetupChange,
  workspaceId
}: GitHubAppSetupWizardProps) {
  const [action, setAction] = useState<SetupAction>("idle");
  const [actionError, setActionError] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<SetupLoadState>("loading");
  const [organizationLogin, setOrganizationLogin] = useState("");
  const [ownerType, setOwnerType] = useState<GitHubAppOwnerType>("user");
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedRepositories, setSelectedRepositories] = useState<Set<string>>(
    new Set()
  );
  const [status, setStatus] = useState<GitHubAppSetupStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadState("loading");
    setActionError(null);
    fetchGitHubAppSetupStatus(workspaceId)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setStatus(payload);
        setSelectedRepositories(initialRepositorySelection(payload));
        setLoadState("ready");
      })
      .catch(() => {
        if (!cancelled) {
          setStatus(null);
          setLoadState("error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey, workspaceId]);

  useEffect(() => {
    const refreshAfterBrowserBack = (event: PageTransitionEvent) => {
      if (event.persisted) {
        setReloadKey((current) => current + 1);
      }
    };
    window.addEventListener("pageshow", refreshAfterBrowserBack);
    return () => window.removeEventListener("pageshow", refreshAfterBrowserBack);
  }, []);

  const canManage = Boolean(canAdminister && status?.can_manage);

  async function startManifestSetup() {
    const organization = organizationLogin.trim();
    if (!canManage || action !== "idle") {
      return;
    }
    if (ownerType === "organization" && organization === "") {
      setActionError(M.githubAppSetup.organizationRequired);
      return;
    }

    setAction("manifest");
    setActionError(null);
    try {
      const payload = await beginGitHubAppManifestSetup(workspaceId, {
        app_origin: window.location.origin,
        owner_type: ownerType,
        ...(ownerType === "organization"
          ? { organization_login: organization }
          : {})
      });
      if (!submitGitHubManifestForm(payload.action_url, payload.manifest)) {
        setActionError(M.githubAppSetup.launchBlocked);
        setAction("idle");
      }
    } catch (caught: unknown) {
      setActionError(setupActionError(caught));
      setAction("idle");
    }
  }

  async function startInstallation() {
    if (!canManage || action !== "idle") {
      return;
    }
    setAction("install");
    setActionError(null);
    try {
      const payload = await beginGitHubAppInstallSetup(workspaceId);
      const redirectUrl = safeGitHubLaunchHref(payload.redirect_url);
      if (redirectUrl === null) {
        setActionError(M.githubAppSetup.launchBlocked);
        setAction("idle");
        return;
      }
      window.location.assign(redirectUrl);
    } catch (caught: unknown) {
      setActionError(setupActionError(caught));
      setAction("idle");
    }
  }

  async function saveRepositories() {
    if (!canManage || action !== "idle" || !status) {
      return;
    }
    const repositories = status.repositories
      .map((repository) => repository.full_name)
      .filter((repository) => selectedRepositories.has(repository));
    if (repositories.length === 0) {
      setActionError(M.githubAppSetup.repositorySelectionRequired);
      return;
    }
    if (repositories.length > REPOSITORY_SELECTION_LIMIT) {
      setActionError(M.githubAppSetup.repositorySelectionLimit);
      return;
    }

    setAction("repositories");
    setActionError(null);
    try {
      await selectGitHubAppRepositories(workspaceId, {
        repositories
      });
      setReloadKey((current) => current + 1);
      setAction("idle");
      onSetupChange?.();
    } catch (caught: unknown) {
      setActionError(setupActionError(caught));
      setAction("idle");
    }
  }

  async function refreshRepositories() {
    if (!canManage || action !== "idle") {
      return;
    }
    setAction("refresh");
    setActionError(null);
    try {
      const payload = await refreshGitHubAppSetupRepositories(workspaceId);
      setStatus(payload);
      setSelectedRepositories(initialRepositorySelection(payload));
      setAction("idle");
      onSetupChange?.();
    } catch (caught: unknown) {
      setActionError(setupActionError(caught));
      setAction("idle");
    }
  }

  async function restartSetup() {
    if (!canManage || action !== "idle") {
      return;
    }
    setAction("restart");
    setActionError(null);
    try {
      await restartGitHubAppSetup(workspaceId);
      setReloadKey((current) => current + 1);
      setAction("idle");
      onSetupChange?.();
    } catch (caught: unknown) {
      setActionError(setupActionError(caught));
      setAction("idle");
    }
  }

  function toggleRepository(repository: string) {
    if (
      !selectedRepositories.has(repository) &&
      selectedRepositories.size >= REPOSITORY_SELECTION_LIMIT
    ) {
      setActionError(M.githubAppSetup.repositorySelectionLimit);
      return;
    }
    setSelectedRepositories((current) => {
      const next = new Set(current);
      if (next.has(repository)) {
        next.delete(repository);
      } else {
        next.add(repository);
      }
      return next;
    });
    setActionError(null);
  }

  return (
    <GitHubAppSetupWizardView
      action={action}
      actionError={actionError}
      canAdminister={canAdminister}
      loadState={loadState}
      onInstall={() => void startInstallation()}
      onOrganizationLoginChange={setOrganizationLogin}
      onOwnerTypeChange={setOwnerType}
      onRefreshRepositories={() => void refreshRepositories()}
      onRepositoryToggle={toggleRepository}
      onRestart={() => void restartSetup()}
      onRetry={() => setReloadKey((current) => current + 1)}
      onSaveRepositories={() => void saveRepositories()}
      onStart={() => void startManifestSetup()}
      organizationLogin={organizationLogin}
      ownerType={ownerType}
      selectedRepositories={selectedRepositories}
      status={status}
    />
  );
}

export function GitHubAppSetupWizardView({
  action,
  actionError,
  canAdminister,
  loadState,
  onInstall,
  onOrganizationLoginChange,
  onOwnerTypeChange,
  onRefreshRepositories,
  onRepositoryToggle,
  onRestart,
  onRetry,
  onSaveRepositories,
  onStart,
  organizationLogin,
  ownerType,
  selectedRepositories,
  status
}: GitHubAppSetupWizardViewProps) {
  const busy = action !== "idle" || loadState === "loading";
  const canManage = Boolean(canAdminister && status?.can_manage);
  const phase = status?.phase ?? null;
  const phaseAnnouncement =
    status && !canManage && status.phase !== "connected"
      ? M.githubAppSetup.adminOnly
      : status
        ? setupPhaseAnnouncement(status.phase)
        : "";
  const phaseFocusRef = useRef<HTMLDivElement>(null);
  const previousPhaseRef = useRef<GitHubAppSetupPhase | null>(null);

  useEffect(() => {
    if (loadState !== "ready" || phase === null) {
      return;
    }
    if (previousPhaseRef.current !== null && previousPhaseRef.current !== phase) {
      phaseFocusRef.current?.focus();
    }
    previousPhaseRef.current = phase;
  }, [loadState, phase]);

  return (
    <section
      aria-busy={busy}
      aria-labelledby="github-app-setup-title"
      className={`github-app-setup${
        status?.phase === "connected" ? " github-app-setup--connected" : ""
      }`}
      id="github-setup"
    >
      <div className="github-app-setup__header">
        <div>
          <span className="eyebrow">{M.githubAppSetup.eyebrow}</span>
          <h3 id="github-app-setup-title">{M.githubAppSetup.title}</h3>
        </div>
        <span className="badge">{M.githubAppSetup.badge}</span>
      </div>
      <p className="github-app-setup__intro">{M.githubAppSetup.description}</p>

      {loadState === "loading" ? (
        <p className="github-app-setup__state" role="status">
          {M.githubAppSetup.loading}
        </p>
      ) : null}

      {loadState === "error" ? (
        <div className="github-app-setup__state github-app-setup__state--error">
          <div role="alert">
            <strong>{M.githubAppSetup.loadErrorTitle}</strong>
            <p>{M.githubAppSetup.loadErrorDescription}</p>
          </div>
          <button className="button secondary" onClick={onRetry} type="button">
            {M.githubAppSetup.retry}
          </button>
        </div>
      ) : null}

      {loadState === "ready" && status ? (
        <>
          <GitHubSetupProgress phase={status.phase} />
          <p
            aria-live="polite"
            className="github-app-setup__phase-announcement"
            role="status"
          >
            {phaseAnnouncement}
          </p>
          <div
            aria-label={phaseAnnouncement}
            className="github-app-setup__phase-focus"
            ref={phaseFocusRef}
            tabIndex={-1}
          >
            <GitHubSetupPhaseContent
              action={action}
              canManage={canManage}
              onInstall={onInstall}
              onOrganizationLoginChange={onOrganizationLoginChange}
              onOwnerTypeChange={onOwnerTypeChange}
              onRefreshRepositories={onRefreshRepositories}
              onRepositoryToggle={onRepositoryToggle}
              onRestart={onRestart}
              onSaveRepositories={onSaveRepositories}
              onStart={onStart}
              organizationLogin={organizationLogin}
              ownerType={ownerType}
              selectedRepositories={selectedRepositories}
              status={status}
            />
          </div>
          {actionError ? (
            <p className="github-app-setup__error" role="alert">
              {actionError}
            </p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function GitHubSetupProgress({ phase }: { phase: GitHubAppSetupPhase }) {
  const currentStep = setupCurrentStep(phase);
  const steps = [
    [M.githubAppSetup.stepCreate, M.githubAppSetup.stepCreateHint],
    [M.githubAppSetup.stepInstall, M.githubAppSetup.stepInstallHint],
    [M.githubAppSetup.stepRepositories, M.githubAppSetup.stepRepositoriesHint],
    [M.githubAppSetup.stepReady, M.githubAppSetup.stepReadyHint]
  ] as const;

  return (
    <ol aria-label={M.githubAppSetup.flowLabel} className="github-app-setup__steps">
      {steps.map(([title, hint], index) => {
        const complete = phase === "connected" || index < currentStep;
        const current = index === currentStep;
        return (
          <li
            aria-current={current ? "step" : undefined}
            className={`github-app-setup__step${
              complete ? " github-app-setup__step--complete" : ""
            }${current ? " github-app-setup__step--current" : ""}`}
            key={title}
          >
            <span className="github-app-setup__step-index" aria-hidden="true">
              {complete ? "✓" : index + 1}
            </span>
            <span>
              <strong>{title}</strong>
              <small>{hint}</small>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function GitHubSetupPhaseContent({
  action,
  canManage,
  onInstall,
  onOrganizationLoginChange,
  onOwnerTypeChange,
  onRefreshRepositories,
  onRepositoryToggle,
  onRestart,
  onSaveRepositories,
  onStart,
  organizationLogin,
  ownerType,
  selectedRepositories,
  status
}: {
  action: SetupAction;
  canManage: boolean;
  onInstall: () => void;
  onOrganizationLoginChange: (value: string) => void;
  onOwnerTypeChange: (value: GitHubAppOwnerType) => void;
  onRefreshRepositories: () => void;
  onRepositoryToggle: (repository: string) => void;
  onRestart: () => void;
  onSaveRepositories: () => void;
  onStart: () => void;
  organizationLogin: string;
  ownerType: GitHubAppOwnerType;
  selectedRepositories: Set<string>;
  status: GitHubAppSetupStatus;
}) {
  if (!canManage && status.phase !== "connected") {
    return <p className="github-app-setup__admin-note">{M.githubAppSetup.adminOnly}</p>;
  }

  if (status.phase === "not_started") {
    return (
      <form
        className="github-app-setup__action-card"
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          onStart();
        }}
      >
        <fieldset disabled={action !== "idle"}>
          <legend>{M.githubAppSetup.ownerLegend}</legend>
          <div className="github-app-setup__owner-options">
            <label>
              <input
                checked={ownerType === "user"}
                name="github-app-owner"
                onChange={() => onOwnerTypeChange("user")}
                type="radio"
              />
              <span>
                <strong>{M.githubAppSetup.ownerUser}</strong>
                <small>{M.githubAppSetup.ownerUserHint}</small>
              </span>
            </label>
            <label>
              <input
                checked={ownerType === "organization"}
                name="github-app-owner"
                onChange={() => onOwnerTypeChange("organization")}
                type="radio"
              />
              <span>
                <strong>{M.githubAppSetup.ownerOrganization}</strong>
                <small>{M.githubAppSetup.ownerOrganizationHint}</small>
              </span>
            </label>
          </div>
          {ownerType === "organization" ? (
            <label className="github-app-setup__organization">
              <span>{M.githubAppSetup.organizationLabel}</span>
              <input
                autoComplete="off"
                maxLength={39}
                onChange={(event) => onOrganizationLoginChange(event.target.value)}
                pattern="[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
                placeholder={M.githubAppSetup.organizationPlaceholder}
                required
                value={organizationLogin}
              />
            </label>
          ) : null}
        </fieldset>
        <div className="github-app-setup__primary-action">
          <button className="button" disabled={action !== "idle"} type="submit">
            {action === "manifest"
              ? M.githubAppSetup.startPending
              : M.githubAppSetup.start}
          </button>
          <span>{M.githubAppSetup.startHint}</span>
        </div>
      </form>
    );
  }

  if (status.phase === "manifest_pending") {
    return (
      <SetupStateCard
        description={M.githubAppSetup.registrationPendingDescription}
        title={M.githubAppSetup.registrationPendingTitle}
      >
        {status.can_restart ? (
          <RestartButton action={action} onRestart={onRestart} />
        ) : null}
      </SetupStateCard>
    );
  }

  if (status.phase === "manifest_exchanging") {
    return (
      <SetupStateCard
        description={M.githubAppSetup.exchangePendingDescription}
        pending
        title={M.githubAppSetup.exchangePendingTitle}
      />
    );
  }

  if (status.phase === "installation_pending") {
    return (
      <SetupStateCard
        description={M.githubAppSetup.installDescription}
        title={M.githubAppSetup.installTitle}
      >
        <button
          className="button"
          disabled={action !== "idle"}
          onClick={onInstall}
          type="button"
        >
          {action === "install"
            ? M.githubAppSetup.installPending
            : M.githubAppSetup.install}
        </button>
      </SetupStateCard>
    );
  }

  if (status.phase === "oauth_pending" || status.phase === "oauth_exchanging") {
    return (
      <SetupStateCard
        description={M.githubAppSetup.verifyDescription}
        pending
        title={M.githubAppSetup.verifyTitle}
      />
    );
  }

  if (status.phase === "repository_selection") {
    const settingsHref = safeGitHubLaunchHref(status.installation_settings_url);
    if (status.repositories.length === 0) {
      return (
        <SetupStateCard
          description={M.githubAppSetup.repositoriesEmptyDescription}
          title={M.githubAppSetup.repositoriesEmptyTitle}
        >
          <div className="actions-row">
            {settingsHref ? (
              <a
                className="button secondary"
                href={settingsHref}
                rel="noreferrer"
                target="_blank"
              >
                {M.githubAppSetup.openRepositoryAccess}
              </a>
            ) : null}
            <button
              className="button"
              disabled={action !== "idle"}
              onClick={onRefreshRepositories}
              type="button"
            >
              {action === "refresh"
                ? M.githubAppSetup.refreshingRepositories
                : M.githubAppSetup.refreshRepositories}
            </button>
          </div>
        </SetupStateCard>
      );
    }
    return (
      <section className="github-app-setup__repository-step">
        <div>
          <h4>{M.githubAppSetup.repositoriesTitle}</h4>
          <p>{M.githubAppSetup.repositoriesDescription}</p>
        </div>
        <RepositorySelection
          disabled={action !== "idle"}
          onToggle={onRepositoryToggle}
          repositories={status.repositories}
          selected={selectedRepositories}
        />
        <button
          className="button"
          disabled={action !== "idle" || selectedRepositories.size === 0}
          onClick={onSaveRepositories}
          type="button"
        >
          {action === "repositories"
            ? M.githubAppSetup.savingRepositories
            : `${M.githubAppSetup.saveRepositories} · ${selectedRepositories.size}`}
        </button>
      </section>
    );
  }

  if (status.phase === "connected") {
    const settingsHref = safeGitHubLaunchHref(status.installation_settings_url);
    return (
      <section className="github-app-setup__connected">
        <div className="github-app-setup__connected-copy">
          <span className="github-app-setup__success-mark" aria-hidden="true">✓</span>
          <div>
            <h4>{M.githubAppSetup.connectedTitle}</h4>
            <p>{M.githubAppSetup.connectedDescription}</p>
          </div>
        </div>
        <dl>
          <div>
            <dt>{M.githubAppSetup.connectedAccount}</dt>
            <dd>{status.installation_account ?? "—"}</dd>
          </div>
          <div>
            <dt>{M.githubAppSetup.connectedApp}</dt>
            <dd>{status.app_name ?? status.app_slug ?? "—"}</dd>
          </div>
          <div>
            <dt>{M.githubAppSetup.connectedRepositories}</dt>
            <dd>{status.selected_repositories.length}</dd>
          </div>
        </dl>
        {canManage ? (
          <div className="github-app-setup__connected-manage">
            <p>{M.githubAppSetup.connectedManageHint}</p>
            <div className="actions-row">
              {settingsHref ? (
                <a
                  className="button secondary"
                  href={settingsHref}
                  rel="noreferrer"
                  target="_blank"
                >
                  {M.githubAppSetup.openRepositoryAccess}
                </a>
              ) : null}
              <button
                className="button secondary"
                disabled={action !== "idle"}
                onClick={onRefreshRepositories}
                type="button"
              >
                {action === "refresh"
                  ? M.githubAppSetup.refreshingRepositories
                  : M.githubAppSetup.refreshRepositorySelection}
              </button>
            </div>
          </div>
        ) : null}
      </section>
    );
  }

  const cancelled = status.phase === "cancelled";
  return (
    <SetupStateCard
      description={
        cancelled
          ? M.githubAppSetup.cancelledDescription
          : setupStatusError(status.error_code)
      }
      tone="error"
      title={
        cancelled ? M.githubAppSetup.cancelledTitle : M.githubAppSetup.failedTitle
      }
    >
      {status.can_restart ? (
        <RestartButton action={action} onRestart={onRestart} />
      ) : null}
    </SetupStateCard>
  );
}

function RepositorySelection({
  disabled,
  onToggle,
  repositories,
  selected
}: {
  disabled: boolean;
  onToggle: (repository: string) => void;
  repositories: GitHubAppSetupRepositoryRead[];
  selected: Set<string>;
}) {
  const preview = repositories.slice(0, REPOSITORY_PREVIEW_LIMIT);
  const remaining = repositories.slice(REPOSITORY_PREVIEW_LIMIT);
  const renderRepository = (repository: GitHubAppSetupRepositoryRead) => (
    <label className="github-app-setup__repository" key={repository.id}>
      <input
        checked={selected.has(repository.full_name)}
        disabled={disabled}
        onChange={() => onToggle(repository.full_name)}
        type="checkbox"
      />
      <span>
        <strong>{repository.full_name}</strong>
        <small>
          {repository.archived
            ? "Архивный"
            : repository.private
              ? "Приватный"
              : "Публичный"}
        </small>
      </span>
    </label>
  );

  return (
    <div className="github-app-setup__repository-list">
      <div className="github-app-setup__repository-grid">
        {preview.map(renderRepository)}
      </div>
      {remaining.length > 0 ? (
        <details>
          <summary>Показать ещё: {remaining.length}</summary>
          <div className="github-app-setup__repository-grid">
            {remaining.map(renderRepository)}
          </div>
        </details>
      ) : null}
    </div>
  );
}

function SetupStateCard({
  children,
  description,
  pending = false,
  title,
  tone = "default"
}: {
  children?: ReactNode;
  description: string;
  pending?: boolean;
  title: string;
  tone?: "default" | "error";
}) {
  return (
    <div
      className={`github-app-setup__state-card${
        tone === "error" ? " github-app-setup__state-card--error" : ""
      }`}
      role={pending ? "status" : undefined}
    >
      <div>
        <h4>{title}</h4>
        <p>{description}</p>
      </div>
      {pending ? <span className="github-app-setup__pulse" aria-hidden="true" /> : null}
      {children}
    </div>
  );
}

function RestartButton({
  action,
  onRestart
}: {
  action: SetupAction;
  onRestart: () => void;
}) {
  return (
    <button
      className="button secondary"
      disabled={action !== "idle"}
      onClick={onRestart}
      type="button"
    >
      {action === "restart" ? M.githubAppSetup.restarting : M.githubAppSetup.restart}
    </button>
  );
}

function setupCurrentStep(phase: GitHubAppSetupPhase): number {
  if (phase === "installation_pending" || phase === "oauth_pending" || phase === "oauth_exchanging") {
    return 1;
  }
  if (phase === "repository_selection") {
    return 2;
  }
  if (phase === "connected") {
    return 3;
  }
  if (phase === "failed" || phase === "cancelled") {
    return -1;
  }
  return 0;
}

function setupPhaseAnnouncement(phase: GitHubAppSetupPhase): string {
  if (phase === "manifest_pending") {
    return M.githubAppSetup.registrationPendingTitle;
  }
  if (phase === "manifest_exchanging") {
    return M.githubAppSetup.exchangePendingTitle;
  }
  if (phase === "installation_pending") {
    return M.githubAppSetup.installTitle;
  }
  if (phase === "oauth_pending" || phase === "oauth_exchanging") {
    return M.githubAppSetup.verifyTitle;
  }
  if (phase === "repository_selection") {
    return M.githubAppSetup.repositoriesTitle;
  }
  if (phase === "connected") {
    return M.githubAppSetup.connectedTitle;
  }
  if (phase === "cancelled") {
    return M.githubAppSetup.cancelledTitle;
  }
  if (phase === "failed") {
    return M.githubAppSetup.failedTitle;
  }
  return M.githubAppSetup.start;
}

function setupStatusError(errorCode: string | null): string {
  const code = errorCode?.toLowerCase() ?? "";
  if (code.includes("expired")) {
    return M.githubAppSetup.errorExpired;
  }
  if (code.includes("replay") || code.includes("consumed")) {
    return M.githubAppSetup.errorReplay;
  }
  if (code.includes("denied") || code.includes("cancel")) {
    return M.githubAppSetup.errorDenied;
  }
  if (code.includes("installation") || code.includes("not_visible")) {
    return M.githubAppSetup.errorInstallationMissing;
  }
  if (code.includes("github") || code.includes("provider")) {
    return M.githubAppSetup.errorProvider;
  }
  return M.githubAppSetup.failedDescription;
}

function setupActionError(caught: unknown): string {
  if (caught instanceof ApiRequestError) {
    if (caught.status === 403) {
      return M.githubAppSetup.adminOnly;
    }
    if (caught.status === 409 || caught.status === 410) {
      return M.githubAppSetup.errorExpired;
    }
    if (caught.status >= 500) {
      return M.githubAppSetup.errorProvider;
    }
  }
  return M.githubAppSetup.errorGeneric;
}

function initialRepositorySelection(
  status: GitHubAppSetupStatus
): Set<string> {
  if (status.selected_repositories.length > 0) {
    return new Set(status.selected_repositories);
  }
  if (status.phase !== "repository_selection") {
    return new Set();
  }
  return new Set(
    status.repositories
      .slice(0, REPOSITORY_SELECTION_LIMIT)
      .map((repository) => repository.full_name)
  );
}
