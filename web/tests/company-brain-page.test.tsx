import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import CompanyBrainPage from "../app/company-brain/page";
import {
  COMPANY_NAV,
  getContextNavigation,
  isNavigationItemActive,
  NAV_LINKS,
  PRIMARY_NAV,
  SOURCE_NAV,
  TODAY_NAV
} from "../components/Sidebar";
import { M } from "../lib/messages";

test("Company zone opens the evidence-backed Company Brain route", () => {
  const link = NAV_LINKS.find((item) => item.href === "/company-brain");
  assert.ok(link, "expected a /company-brain nav link");
  assert.equal(link?.label, M.nav.company);
});

test("sidebar exposes five human zones and keeps providers secondary", () => {
  assert.deepEqual(
    PRIMARY_NAV.map((item) => item.label),
    [M.nav.today, M.nav.company, M.nav.decisions, M.nav.sources, M.nav.settings]
  );
  assert.deepEqual(
    SOURCE_NAV.map((item) => item.label),
    [M.nav.sourceOverview, M.nav.github, M.nav.jira, M.nav.gmail, M.nav.drive]
  );
  assert.equal(PRIMARY_NAV.some((item) => item.href === "/github"), false);
  assert.equal(NAV_LINKS.some((item) => item.href === "/audit"), false);
});

test("provider routes activate the Sources zone and briefings activate Today", () => {
  const sources = PRIMARY_NAV.find((item) => item.href === "/connectors");
  const today = PRIMARY_NAV.find((item) => item.href === "/dashboard");
  assert.ok(sources);
  assert.ok(today);
  assert.equal(isNavigationItemActive("/gmail", sources), true);
  assert.equal(isNavigationItemActive("/briefings/briefing-1", today), true);
});

test("every secondary product route is reachable through contextual navigation", () => {
  assert.deepEqual(
    TODAY_NAV.map((item) => item.href),
    ["/dashboard", "/briefings"]
  );
  assert.deepEqual(
    COMPANY_NAV.map((item) => item.href),
    ["/company-brain", "/documents"]
  );
  assert.equal(getContextNavigation("/briefings")?.links, TODAY_NAV);
  assert.equal(getContextNavigation("/documents")?.links, COMPANY_NAV);
  assert.equal(getContextNavigation("/gmail")?.links, SOURCE_NAV);
  assert.ok(NAV_LINKS.some((item) => item.href === "/briefings"));
  assert.ok(NAV_LINKS.some((item) => item.href === "/documents"));
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
