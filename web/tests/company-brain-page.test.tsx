import assert from "node:assert/strict";
import test from "node:test";

import CompanyBrainPage from "../app/company-brain/page";
import { CompanyBrainPageClient } from "../components/CompanyBrainPageClient";
import {
  BACKSTAGE_NAV,
  COMPANY_NAV,
  getContextNavigation,
  isNavigationItemActive,
  NAV_LINKS,
  PRIMARY_NAV,
  SOURCE_NAV,
  TODAY_NAV
} from "../components/Sidebar";
import { M } from "../lib/messages";

test("World zone opens the evidence-backed Company Brain route", () => {
  const link = NAV_LINKS.find((item) => item.href === "/company-brain");
  assert.ok(link, "expected a /company-brain nav link");
  assert.equal(link?.label, "Мир");
});

test("sidebar exposes three everyday zones and keeps system controls backstage", () => {
  assert.deepEqual(
    PRIMARY_NAV.map((item) => item.label),
    ["Штаб", "Мир", "Миссии"]
  );
  assert.deepEqual(
    PRIMARY_NAV.map((item) => item.href),
    ["/dashboard", "/company-brain", "/actions"]
  );
  assert.deepEqual(
    BACKSTAGE_NAV.map((item) => [item.href, item.label]),
    [
      ["/connectors", "Радары"],
      ["/settings", M.nav.settings]
    ]
  );
  assert.deepEqual(
    SOURCE_NAV.map((item) => item.label),
    [M.nav.sourceOverview, M.nav.github, M.nav.jira, M.nav.gmail, M.nav.drive]
  );
  assert.equal(PRIMARY_NAV.some((item) => item.href === "/github"), false);
  assert.equal(NAV_LINKS.some((item) => item.href === "/audit"), false);
});

test("provider routes activate Radars and compatibility routes activate their world", () => {
  const sources = BACKSTAGE_NAV.find((item) => item.href === "/connectors");
  const today = PRIMARY_NAV.find((item) => item.href === "/dashboard");
  const world = PRIMARY_NAV.find((item) => item.href === "/company-brain");
  assert.ok(sources);
  assert.ok(today);
  assert.ok(world);
  assert.equal(isNavigationItemActive("/gmail", sources), true);
  assert.equal(isNavigationItemActive("/briefings/briefing-1", today), true);
  assert.equal(isNavigationItemActive("/documents/document-1", world), true);
});

test("only source and provider routes expose contextual navigation", () => {
  assert.deepEqual(
    TODAY_NAV.map((item) => item.href),
    ["/dashboard", "/briefings"]
  );
  assert.deepEqual(
    COMPANY_NAV.map((item) => item.href),
    ["/company-brain", "/documents"]
  );
  assert.equal(getContextNavigation("/dashboard"), null);
  assert.equal(getContextNavigation("/briefings"), null);
  assert.equal(getContextNavigation("/company-brain"), null);
  assert.equal(getContextNavigation("/documents"), null);
  assert.equal(getContextNavigation("/connectors")?.links, SOURCE_NAV);
  assert.equal(getContextNavigation("/gmail")?.links, SOURCE_NAV);
  assert.ok(NAV_LINKS.some((item) => item.href === "/briefings"));
  assert.ok(NAV_LINKS.some((item) => item.href === "/documents"));
});

test("company brain route renders the client world shell", async () => {
  const page = await CompanyBrainPage({});
  assert.equal(page.type, CompanyBrainPageClient);
  assert.equal(page.props.profileSelector, null);
});

test("company brain route forwards only a normalized opaque profile selector", async () => {
  const selected = await CompanyBrainPage({
    searchParams: Promise.resolve({ profile: "v1:member:member-1" })
  });
  const invalid = await CompanyBrainPage({
    searchParams: Promise.resolve({ profile: "v1:member:member-1\u0000" })
  });

  assert.equal(selected.props.profileSelector, "v1:member:member-1");
  assert.equal(invalid.props.profileSelector, null);
});
