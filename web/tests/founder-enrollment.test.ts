import assert from "node:assert/strict";
import test from "node:test";

import {
  enrollFounder,
  EnrollmentError,
  type FounderEnrollmentResponse
} from "../lib/auth";
import {
  companyNameToSlug,
  enrollmentTokenFromLocation,
  setupTokenFromLocation
} from "../lib/enrollment";

test("reads the invite only from a URL fragment so request logs never receive it", () => {
  assert.equal(
    enrollmentTokenFromLocation({
      hash: "#token=fragment-invite",
      search: ""
    }),
    "fragment-invite"
  );
  assert.equal(
    enrollmentTokenFromLocation({
      hash: "",
      search: "?token=query-token-must-not-be-used"
    }),
    null
  );
});

test("reads teammate setup bearer only from the fragment", () => {
  assert.equal(
    setupTokenFromLocation({ hash: "#token=setup-fragment", search: "" }),
    "setup-fragment"
  );
  assert.equal(
    setupTokenFromLocation({
      hash: "",
      search: "?token=legacy-query-must-not-be-used"
    }),
    null
  );
});

test("creates safe readable workspace slugs from Russian and Latin names", () => {
  assert.equal(companyNameToSlug("  ТОО Atlas Студия  "), "too-atlas-studiya");
  assert.equal(companyNameToSlug("Қазақ Өнім"), "qazaq-onim");
  assert.equal(companyNameToSlug("Café & Product / Lab"), "cafe-product-lab");
  assert.equal(companyNameToSlug("***"), "");
});

test("enrollment posts the invite once and uses the first-party session cookie", async () => {
  const originalFetch = globalThis.fetch;
  const expected: FounderEnrollmentResponse = {
    status: "ok",
    user: {
      id: "user-1",
      email: "founder@example.test",
      name: "Founder",
      status: "active"
    },
    workspace: {
      id: "workspace-1",
      name: "Atlas",
      slug: "atlas",
      role: "owner"
    }
  };
  let request: RequestInit | undefined;
  let requestUrl = "";
  globalThis.fetch = (async (input, init) => {
    requestUrl = String(input);
    request = init;
    return new Response(JSON.stringify(expected), {
      status: 201,
      headers: { "Content-Type": "application/json" }
    });
  }) as typeof fetch;

  try {
    const response = await enrollFounder({
      token: "one-time-invite",
      email: "founder@example.test",
      name: "Founder",
      password: "long-enough-password",
      workspaceName: "Atlas",
      workspaceSlug: "atlas"
    });
    assert.deepEqual(response, expected);
    assert.equal(requestUrl, "/api/v1/auth/enroll");
    assert.equal(request?.method, "POST");
    assert.equal(request?.credentials, "include");
    assert.deepEqual(JSON.parse(String(request?.body)), {
      token: "one-time-invite",
      email: "founder@example.test",
      name: "Founder",
      password: "long-enough-password",
      workspace_name: "Atlas",
      workspace_slug: "atlas"
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("enrollment exposes safe actionable errors without returning token details", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(null, { status: 400 })) as typeof fetch;

  try {
    await assert.rejects(
      enrollFounder({
        token: "secret-invite-value",
        email: "founder@example.test",
        name: "Founder",
        password: "long-enough-password",
        workspaceName: "Atlas",
        workspaceSlug: "atlas"
      }),
      (error: unknown) => {
        assert.ok(error instanceof EnrollmentError);
        assert.equal(error.status, 400);
        assert.match(error.message, /недействительна или устарела/i);
        assert.doesNotMatch(error.message, /secret-invite-value/);
        return true;
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("enrollment distinguishes a resolvable account or workspace conflict", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(null, { status: 409 })) as typeof fetch;

  try {
    await assert.rejects(
      enrollFounder({
        token: "one-time-invite",
        email: "founder@example.test",
        name: "Founder",
        password: "long-enough-password",
        workspaceName: "Atlas",
        workspaceSlug: "atlas"
      }),
      (error: unknown) => {
        assert.ok(error instanceof EnrollmentError);
        assert.equal(error.status, 409);
        assert.match(error.message, /уже используются/i);
        return true;
      }
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
