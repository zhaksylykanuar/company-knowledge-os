import assert from "node:assert/strict";
import test from "node:test";

import CompanyBrainPage from "../app/company-brain/page";
import { CompanyBrainPageClient } from "../components/CompanyBrainPageClient";
import {
  BACKSTAGE_NAV,
  isNavigationItemActive,
  NAV_LINKS,
  PRIMARY_NAV
} from "../components/Sidebar";
import { M } from "../lib/messages";

test("Company zone opens the evidence-backed company memory route", () => {
  const link = NAV_LINKS.find((item) => item.href === "/company-brain");
  assert.ok(link, "expected a /company-brain nav link");
  assert.equal(link?.label, "Компания");
});

test("sidebar exposes the three AI-first zones and one settings entry", () => {
  assert.deepEqual(
    PRIMARY_NAV.map((item) => item.label),
    ["Сейчас", "Компания", "Спросить"]
  );
  assert.deepEqual(
    PRIMARY_NAV.map((item) => item.href),
    ["/dashboard", "/company-brain", "/ask"]
  );
  assert.deepEqual(
    BACKSTAGE_NAV.map((item) => [item.href, item.label]),
    [["/settings", M.nav.settings]]
  );
  assert.equal(PRIMARY_NAV.some((item) => item.href === "/github"), false);
  assert.equal(NAV_LINKS.some((item) => item.href === "/connectors"), false);
  assert.equal(NAV_LINKS.some((item) => item.href === "/actions"), false);
  assert.equal(NAV_LINKS.some((item) => item.href === "/audit"), false);
});

test("hidden company detail routes remain in Company while providers have no nav entry", () => {
  const settings = BACKSTAGE_NAV[0];
  const company = PRIMARY_NAV[1];
  assert.equal(isNavigationItemActive("/settings/integrations", settings), true);
  assert.equal(isNavigationItemActive("/github", settings), false);
  assert.equal(isNavigationItemActive("/actions", company), true);
  assert.equal(isNavigationItemActive("/documents", company), true);
});

test("company brain route renders the client world shell", async () => {
  const page = await CompanyBrainPage({});
  assert.equal(page.type, CompanyBrainPageClient);
  assert.equal(page.props.profileSelector, null);
  assert.equal(page.props.profileSelectorRequested, false);
});

test("company brain route preserves explicit profile intent for client validation", async () => {
  const selected = await CompanyBrainPage({
    searchParams: Promise.resolve({ profile: "v1:member:member-1" })
  });
  const invalid = await CompanyBrainPage({
    searchParams: Promise.resolve({ profile: "v1:member:member-1\u0000" })
  });

  assert.equal(selected.props.profileSelector, "v1:member:member-1");
  assert.equal(selected.props.profileSelectorRequested, true);
  assert.equal(invalid.props.profileSelector, null);
  assert.equal(invalid.props.profileSelectorRequested, true);
});
