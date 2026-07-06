import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { DocumentsPanelView, parseTags } from "../app/documents/page";
import {
  buildWorkspaceDocumentPath,
  buildWorkspaceDocumentVersionsPath,
  buildWorkspaceDocumentsCollectionPath,
  buildWorkspaceDocumentsPath,
  createDocument,
  deleteDocument,
  fetchDocumentVersions
} from "../lib/api";
import { M } from "../lib/messages";
import type { DocumentDetail, DocumentListResponse, DocumentVersion } from "../lib/types";

const documentList: DocumentListResponse = {
  workspace_id: "workspace-1",
  count: 2,
  boundary: {
    provider_calls: false,
    external_writes: false,
    llm: false,
    reads_secrets: false
  },
  documents: [
    {
      id: "doc-1",
      workspace_id: "workspace-1",
      title: "Launch Plan",
      status: "published",
      tags: ["launch"],
      excerpt: "Ship beta to first users.",
      created_by_user_id: "user-1",
      updated_by_user_id: "user-1",
      created_at: "2026-07-06T10:00:00Z",
      updated_at: "2026-07-06T10:00:00Z"
    },
    {
      id: "doc-2",
      workspace_id: "workspace-1",
      title: "Runway Notes",
      status: "draft",
      tags: [],
      excerpt: "Cash runway is eighteen months.",
      created_by_user_id: "user-1",
      updated_by_user_id: null,
      created_at: "2026-07-05T10:00:00Z",
      updated_at: "2026-07-05T10:00:00Z"
    }
  ]
};

const documentDetail: DocumentDetail = {
  ...documentList.documents[0]!,
  body_markdown: "# Launch\n\nShip beta.",
  body_text: "Launch\n\nShip beta."
};

const documentVersions: DocumentVersion[] = [
  {
    id: "version-2",
    workspace_id: "workspace-1",
    document_id: "doc-1",
    version_number: 2,
    title: "Launch Plan v2",
    body_markdown: "# Launch v2",
    body_text: "Launch v2",
    status: "published",
    tags: ["launch"],
    created_by_user_id: "user-1",
    created_at: "2026-07-06T11:00:00Z",
    excerpt: "Launch v2"
  },
  {
    id: "version-1",
    workspace_id: "workspace-1",
    document_id: "doc-1",
    version_number: 1,
    title: "Launch Plan",
    body_markdown: "# Launch",
    body_text: "Launch",
    status: "draft",
    tags: ["launch"],
    created_by_user_id: "user-1",
    created_at: "2026-07-06T10:00:00Z",
    excerpt: "Launch"
  }
];

function renderPanel(
  props: Partial<Parameters<typeof DocumentsPanelView>[0]> = {}
): string {
  return renderToStaticMarkup(
    <DocumentsPanelView
      createBody={props.createBody ?? ""}
      createError={props.createError ?? null}
      createMessage={props.createMessage ?? null}
      createPending={props.createPending ?? false}
      createStatusValue={props.createStatusValue ?? "draft"}
      createTags={props.createTags ?? ""}
      createTitle={props.createTitle ?? ""}
      data={"data" in props ? props.data ?? null : documentList}
      error={props.error ?? null}
      onCloseDetail={props.onCloseDetail}
      onCreate={props.onCreate}
      onOpenDocument={props.onOpenDocument}
      onRetry={props.onRetry}
      search={props.search ?? ""}
      selected={props.selected ?? null}
      selectedVersions={props.selectedVersions ?? []}
      status={props.status ?? "ready"}
    />
  );
}

test("builds document API paths", () => {
  assert.equal(
    buildWorkspaceDocumentsCollectionPath("workspace-1"),
    "/api/v1/workspaces/workspace-1/documents"
  );
  assert.equal(
    buildWorkspaceDocumentPath("workspace-1", "doc-1"),
    "/api/v1/workspaces/workspace-1/documents/doc-1"
  );
  assert.equal(
    buildWorkspaceDocumentVersionsPath("workspace-1", "doc-1"),
    "/api/v1/workspaces/workspace-1/documents/doc-1/versions"
  );
  assert.equal(
    buildWorkspaceDocumentsPath("workspace-1", { search: "runway", limit: 10 }),
    "/api/v1/workspaces/workspace-1/documents?limit=10&search=runway"
  );
});

test("parseTags dedupes and trims comma-separated tags", () => {
  assert.deepEqual(parseTags("launch, launch,  beta "), ["launch", "beta"]);
  assert.deepEqual(parseTags("   "), []);
});

test("creates a document through the POST client without external writes", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-1/documents"
    );
    assert.equal(init?.method, "POST");
    assert.equal(
      init?.body,
      JSON.stringify({
        title: "Launch Plan",
        body_markdown: "# Launch",
        tags: ["launch"],
        status: "published"
      })
    );
    return new Response(
      JSON.stringify({
        document: documentDetail,
        boundary: documentList.boundary
      }),
      { headers: { "Content-Type": "application/json" }, status: 201 }
    );
  }) as typeof fetch;
  try {
    const payload = await createDocument("workspace-1", {
      title: "Launch Plan",
      body_markdown: "# Launch",
      tags: ["launch"],
      status: "published"
    });
    assert.equal(payload.boundary.external_writes, false);
    assert.equal(payload.document.title, "Launch Plan");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fetches document version history through the GET client", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input, init) => {
    assert.equal(
      String(input),
      "http://localhost/api/v1/workspaces/workspace-1/documents/doc-1/versions"
    );
    assert.equal(init?.method, undefined);
    return new Response(
      JSON.stringify({
        boundary: documentList.boundary,
        count: 2,
        document_id: "doc-1",
        versions: documentVersions,
        workspace_id: "workspace-1"
      }),
      { headers: { "Content-Type": "application/json" }, status: 200 }
    );
  }) as typeof fetch;
  try {
    const payload = await fetchDocumentVersions("workspace-1", "doc-1");
    assert.equal(payload.count, 2);
    assert.equal(payload.versions[0]?.version_number, 2);
    assert.equal(payload.boundary.llm, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("deletes a document through the DELETE client (204)", async () => {
  const originalFetch = globalThis.fetch;
  let calledMethod: string | undefined;
  globalThis.fetch = (async (_input, init) => {
    calledMethod = init?.method;
    return new Response(null, { status: 204 });
  }) as typeof fetch;
  try {
    await deleteDocument("workspace-1", "doc-1");
    assert.equal(calledMethod, "DELETE");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("renders document list, summary counts, and create form", () => {
  const html = renderPanel();
  assert.ok(html.includes(M.documents.title));
  assert.ok(html.includes("Launch Plan"));
  assert.ok(html.includes("Runway Notes"));
  assert.ok(html.includes(M.documents.createTitle));
  assert.ok(html.includes(M.documents.boundaryNote));
  assert.doesNotMatch(html, /provider call started/i);
});

test("renders empty state when there are no documents", () => {
  const html = renderPanel({
    data: { ...documentList, count: 0, documents: [] }
  });
  assert.ok(html.includes(M.documents.emptyTitle));
  assert.ok(html.includes(M.documents.emptyDescription));
});

test("renders selected document detail with version snapshot body", () => {
  const html = renderPanel({
    selected: documentDetail,
    selectedVersions: documentVersions,
    onCloseDetail: () => undefined
  });
  assert.ok(html.includes(M.documents.detailBodyLabel));
  assert.match(html, /# Launch/);
  assert.ok(html.includes(M.documents.detailBackToList));
  assert.ok(html.includes(M.documents.versionHistoryTitle));
  assert.ok(html.includes(M.documents.versionLabel(2)));
  assert.ok(html.includes(M.documents.viewVersion));
  assert.ok(html.includes(M.documents.selectedVersionBadge));
  assert.ok(html.includes(M.documents.versionSnapshotTitle));
  assert.ok(html.includes(M.documents.versionSnapshotBodyLabel));
  assert.ok(html.includes(M.documents.versionSnapshotBoundary));
  assert.ok(html.includes("Launch Plan v2"));
  assert.ok(html.includes("# Launch v2"));
  assert.doesNotMatch(html, /provider call started/i);
});

test("renders missing and error states safely", () => {
  const missing = renderPanel({ data: null, status: "missing" });
  assert.ok(missing.includes(M.documents.noWorkspaceDescription));
  const errored = renderPanel({
    data: null,
    status: "error",
    error: "backend down",
    onRetry: () => undefined
  });
  assert.ok(errored.includes(M.documents.unavailableTitle));
  assert.match(errored, /backend down/);
  assert.ok(errored.includes(M.common.retry));
});
