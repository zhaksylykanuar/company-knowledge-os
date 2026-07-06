import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { DriveConnectorPanelView, extractDriveFilesFromJson } from "../app/drive/page";
import { buildWorkspaceDriveFilesPath, buildWorkspaceDriveImportPath } from "../lib/api";
import { M } from "../lib/messages";
import type { DriveFileListResponse } from "../lib/types";

const driveFiles: DriveFileListResponse = {
  workspace_id: "workspace-1",
  counts: {
    total: 2,
    shared: 1,
    not_shared: 1
  },
  boundary: {
    provider_calls: false,
    sync_started: false,
    external_writes: false,
    llm: false,
    reads_secrets: false
  },
  warnings: [],
  files: [
    {
      source_record_id: "source-1",
      file_id: "file-1",
      name: "Private beta launch checklist",
      mime_type: "application/vnd.google-apps.document",
      owners: ["founder@example.test"],
      drive_id: null,
      folder_path: null,
      shared: true,
      size_bytes: null,
      modified_at: "2026-07-06T10:00:00Z",
      source_url: "https://drive.google.com/file/d/file-1/view",
      evidence_refs: [
        {
          kind: "drive_file",
          source: "drive",
          ref: "file-1",
          url: "https://drive.google.com/file/d/file-1/view"
        }
      ]
    },
    {
      source_record_id: "source-2",
      file_id: "file-2",
      name: "Weekly metrics",
      mime_type: "application/vnd.google-apps.spreadsheet",
      owners: [],
      drive_id: null,
      folder_path: null,
      shared: false,
      size_bytes: null,
      modified_at: null,
      source_url: null,
      evidence_refs: []
    }
  ]
};

function renderPanel(
  props: Partial<Parameters<typeof DriveConnectorPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <DriveConnectorPanelView
      data={props.data === undefined ? driveFiles : props.data}
      error={props.error ?? null}
      importError={props.importError ?? null}
      importMessage={props.importMessage ?? null}
      importPending={props.importPending ?? false}
      importText={props.importText ?? ""}
      onImport={props.onImport}
      onImportTextChange={props.onImportTextChange}
      onRetry={props.onRetry}
      status={props.status ?? "ready"}
    />
  );
}

test("builds Drive connector API paths", () => {
  assert.equal(
    buildWorkspaceDriveFilesPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/drive/files"
  );
  assert.equal(
    buildWorkspaceDriveImportPath("workspace/with slash"),
    "/api/v1/workspaces/workspace%2Fwith%20slash/drive/files/import"
  );
});

test("extracts Drive files from array or object JSON", () => {
  assert.deepEqual(extractDriveFilesFromJson('[{"id":"file-1"}]'), [{ id: "file-1" }]);
  assert.deepEqual(extractDriveFilesFromJson('{"files":[{"id":"file-2"}]}'), [
    { id: "file-2" }
  ]);
  assert.throws(() => extractDriveFilesFromJson('{"items":[]}'), /JSON/);
});

test("renders local Drive files and import boundary without provider-write claims", () => {
  const html = renderPanel({
    importMessage: M.drive.importSuccess(2, 0),
    importText: '[{"id":"file-1"}]'
  });

  assert.ok(html.includes(M.drive.title));
  assert.ok(html.includes(M.drive.badgeLocalOnly));
  assert.ok(html.includes("Private beta launch checklist"));
  assert.ok(html.includes(M.drive.sharedBadge));
  assert.ok(html.includes(M.drive.importTitle));
  assert.ok(html.includes(M.drive.boundaryNote));
  assert.ok(html.includes(M.drive.importSuccess(2, 0)));
  assert.ok(html.includes('href="https://drive.google.com/file/d/file-1/view"'));
  assert.doesNotMatch(html, /provider call started/i);
  assert.doesNotMatch(html, /external write performed/i);
  assert.doesNotMatch(html, /LLM started/i);
  assert.doesNotMatch(html, /RAW_DOC_BODY/);
});

test("renders empty loading missing and error states", () => {
  const emptyHtml = renderPanel({
    data: { ...driveFiles, counts: { not_shared: 0, shared: 0, total: 0 }, files: [] }
  });
  assert.ok(emptyHtml.includes(M.drive.emptyTitle));
  assert.ok(renderPanel({ data: null, status: "loading" }).includes(M.drive.loading));
  assert.ok(
    renderPanel({ data: null, status: "missing" }).includes(M.drive.noWorkspaceDescription)
  );
  const errorHtml = renderPanel({
    data: null,
    error: "drive backend unavailable",
    onRetry: () => undefined,
    status: "error"
  });
  assert.ok(errorHtml.includes(M.drive.unavailableTitle));
  assert.match(errorHtml, /drive backend unavailable/);
  assert.ok(errorHtml.includes(M.common.retry));
});
