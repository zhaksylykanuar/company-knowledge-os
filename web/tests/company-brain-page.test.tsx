import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import CompanyBrainPage from "../app/company-brain/page";
import { NAV_GROUPS, NAV_LINKS } from "../components/Sidebar";
import { M } from "../lib/messages";

test("sidebar exposes a dedicated Company Brain nav link", () => {
  const link = NAV_LINKS.find((item) => item.href === "/company-brain");
  assert.ok(link, "expected a /company-brain nav link");
  assert.equal(link?.label, M.nav.companyBrain);
});

test("sidebar groups the company operating loop and omits the retired legacy audit", () => {
  assert.deepEqual(
    NAV_GROUPS.map((group) => group.label),
    [
      M.nav.groups.command,
      M.nav.groups.management,
      M.nav.groups.sources,
      M.nav.groups.system
    ]
  );
  assert.equal(NAV_LINKS.some((item) => item.href === "/audit"), false);
});

test("company brain page renders header without a session provider", () => {
  const html = renderToStaticMarkup(<CompanyBrainPage />);
  assert.ok(html.includes(M.companyBrainPage.title));
  assert.ok(html.includes(M.common.refreshStatus));
  assert.ok(html.includes(M.companyWorld.loading));
  // The composed panels mount in their initial loading state under static
  // render (effects do not run), proving the page wires both panels without
  // crashing when no session context is present.
  assert.ok(html.includes(M.companyBrain.loading));
  assert.ok(html.includes(M.companyBrainEntities.loading));
});
