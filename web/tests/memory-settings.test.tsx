import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  memoryDate,
  parseMemoryTags
} from "../app/settings/memory/page";
import {
  buildWorkspaceDocumentMemoryPath,
  correctDocumentMemory,
  fetchDocumentMemoryPreview,
  forgetDocumentMemory
} from "../lib/api";

test("uses exact preview-bound memory correction and forgetting contracts", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ body: unknown; method: string; path: string }> = [];
  globalThis.fetch = (async (input, init) => {
    const path = new URL(String(input)).pathname;
    requests.push({
      body: init?.body ? JSON.parse(String(init.body)) : null,
      method: init?.method ?? "GET",
      path
    });
    assert.equal(init?.credentials, "include");
    const headers = new Headers(init?.headers);
    assert.equal(headers.has("X-FounderOS-API-Key"), false);
    if (path.endsWith("/memory")) {
      return Response.json({
        correction: {
          active_document_replaced: true,
          prior_versions_deleted: 2,
          versions_after: 1
        },
        document_id: "doc/1",
        forgetting: {
          active_document_deleted: true,
          backup_retention_may_apply: true,
          provider_source_deleted: false,
          versions_deleted: 2
        },
        status: "draft",
        title: "Memory",
        updated_at: "2026-07-29T10:00:00Z",
        version_count: 2,
        workspace_id: "workspace/1"
      });
    }
    if (path.endsWith("/correct")) {
      return Response.json({
        active_database_replaced: true,
        backup_retention_may_apply: true,
        document: {
          body_markdown: "correct",
          body_text: "correct",
          created_at: "2026-07-29T09:00:00Z",
          created_by_user_id: "user-1",
          excerpt: "correct",
          id: "doc/1",
          status: "published",
          tags: [],
          title: "Correct",
          updated_at: "2026-07-29T10:01:00Z",
          updated_by_user_id: "user-1",
          workspace_id: "workspace/1"
        },
        external_writes: false,
        llm: false,
        prior_versions_deleted: 2,
        provider_calls: false,
        versions_after: 1
      });
    }
    return Response.json({
      active_document_deleted: true,
      backup_retention_may_apply: true,
      document_id: "doc/1",
      provider_source_deleted: false,
      versions_deleted: 1,
      workspace_id: "workspace/1"
    });
  }) as typeof fetch;

  try {
    assert.equal(
      buildWorkspaceDocumentMemoryPath("workspace/1", "doc/1"),
      "/api/v1/workspaces/workspace%2F1/documents/doc%2F1/memory"
    );
    await fetchDocumentMemoryPreview("workspace/1", "doc/1");
    await correctDocumentMemory("workspace/1", "doc/1", {
      body_markdown: "correct",
      confirmation: "purge_document_history",
      expected_updated_at: "2026-07-29T10:00:00Z",
      expected_version_count: 2,
      status: "published",
      tags: [],
      title: "Correct"
    });
    await forgetDocumentMemory("workspace/1", "doc/1", {
      confirmation: "forget_document",
      expected_updated_at: "2026-07-29T10:01:00Z",
      expected_version_count: 1
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(
    requests.map(({ method, path }) => [method, path]),
    [
      ["GET", "/api/v1/workspaces/workspace%2F1/documents/doc%2F1/memory"],
      [
        "POST",
        "/api/v1/workspaces/workspace%2F1/documents/doc%2F1/memory/correct"
      ],
      [
        "POST",
        "/api/v1/workspaces/workspace%2F1/documents/doc%2F1/memory/forget"
      ]
    ]
  );
  assert.deepEqual(requests[1]?.body, {
    body_markdown: "correct",
    confirmation: "purge_document_history",
    expected_updated_at: "2026-07-29T10:00:00Z",
    expected_version_count: 2,
    status: "published",
    tags: [],
    title: "Correct"
  });
});

test("normalizes memory tags and exposes honest deletion boundaries", () => {
  assert.deepEqual(parseMemoryTags(" customer, risk,customer,  "), [
    "customer",
    "risk"
  ]);
  assert.equal(memoryDate("not-a-date"), "время неизвестно");

  const page = readFileSync(
    resolve(process.cwd(), "app/settings/memory/page.tsx"),
    "utf8"
  );
  const settings = readFileSync(
    resolve(process.cwd(), "app/settings/page.tsx"),
    "utf8"
  );
  assert.ok(page.includes("Подтвердить исправление"));
  assert.ok(page.includes("Подтвердить удаление"));
  assert.ok(page.includes("резервные копии"));
  assert.ok(page.includes("здесь не удаляются"));
  assert.ok(page.includes("evidence-safe"));
  assert.equal(page.includes('method: "DELETE"'), false);
  assert.ok(settings.includes('href="/settings/memory"'));
});
