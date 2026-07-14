import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { ProfileMenu } from "../components/AuthGate";

test("profile menu keeps the active account email visible when a name exists", () => {
  const html = renderToStaticMarkup(
    <ProfileMenu
      onLogout={async () => undefined}
      user={{
        email: "founder@example.test",
        id: "user-1",
        name: "Основатель",
        status: "active"
      }}
    />
  );

  assert.ok(html.includes("Основатель"));
  assert.ok(html.includes("founder@example.test"));
  assert.ok(html.includes("Открыть меню аккаунта"));
  assert.match(html, /href="\/settings"/);
});
