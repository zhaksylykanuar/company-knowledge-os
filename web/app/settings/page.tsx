"use client";

import { FormEvent, useEffect, useState } from "react";

import { PageHeader } from "../../components/PageHeader";
import {
  clearOperatorConfig,
  DEFAULT_OPERATOR_CONFIG,
  readOperatorConfig,
  resolveApiBaseUrl,
  writeOperatorConfig
} from "../../lib/config";
import { API_KEY_HEADER } from "../../lib/api";
import type { OperatorConfig } from "../../lib/types";

export default function SettingsPage() {
  const [config, setConfig] = useState<OperatorConfig>(DEFAULT_OPERATOR_CONFIG);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setConfig(readOperatorConfig());
  }, []);

  function updateField(field: keyof OperatorConfig, value: string): void {
    setSaved(false);
    setConfig((current) => ({ ...current, [field]: value }));
  }

  function save(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    writeOperatorConfig(config);
    setSaved(true);
  }

  function clear(): void {
    clearOperatorConfig();
    setConfig(DEFAULT_OPERATOR_CONFIG);
    setSaved(false);
  }

  return (
    <>
      <PageHeader
        eyebrow="Settings"
        title="Local operator settings"
        description="Browser-only configuration for the local MVP frontend shell."
      />
      <form className="form panel" onSubmit={save}>
        <div className="field">
          <label htmlFor="apiBaseUrl">API base URL</label>
          <input
            id="apiBaseUrl"
            onChange={(event) => updateField("apiBaseUrl", event.target.value)}
            placeholder="http://localhost:8000"
            type="url"
            value={config.apiBaseUrl}
          />
        </div>
        <div className="field">
          <label htmlFor="apiKey">Operator API key</label>
          <input
            autoComplete="off"
            id="apiKey"
            onChange={(event) => updateField("apiKey", event.target.value)}
            placeholder={API_KEY_HEADER}
            type="password"
            value={config.apiKey}
          />
        </div>
        <div className="field">
          <label htmlFor="ownerEmail">Owner email</label>
          <input
            id="ownerEmail"
            onChange={(event) => updateField("ownerEmail", event.target.value)}
            placeholder="founder@example.com"
            type="email"
            value={config.ownerEmail}
          />
        </div>
        <div className="field">
          <label htmlFor="workspaceId">Workspace ID</label>
          <input
            id="workspaceId"
            onChange={(event) => updateField("workspaceId", event.target.value)}
            placeholder="Workspace UUID"
            type="text"
            value={config.workspaceId}
          />
        </div>
        <div className="actions-row">
          <button className="button" type="submit">
            Save settings
          </button>
          <button className="button secondary" onClick={clear} type="button">
            Clear
          </button>
        </div>
      </form>
      <section className="panel">
        <ul className="meta-list">
          <li>Effective API base URL: {resolveApiBaseUrl(config)}</li>
          <li>API key header: {API_KEY_HEADER}</li>
          <li>API key saved: {config.apiKey ? "Yes" : "No"}</li>
          <li>Owner email saved: {config.ownerEmail ? "Yes" : "No"}</li>
          <li>Workspace ID saved: {config.workspaceId ? "Yes" : "No"}</li>
          <li>Saved in this session: {saved ? "Yes" : "No"}</li>
        </ul>
      </section>
    </>
  );
}
