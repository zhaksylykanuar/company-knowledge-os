import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { SourceLink } from "../components/SourceLink";
import { safeHref } from "../lib/safeHref";
import type { BriefingEvidenceRef } from "../lib/types";

test("safeHref allows http and https URLs", () => {
  assert.equal(
    safeHref("https://github.com/qtwin-io/founderos-api/issues/42"),
    "https://github.com/qtwin-io/founderos-api/issues/42"
  );
  assert.equal(safeHref("http://localhost:8000/health"), "http://localhost:8000/health");
});

test("safeHref rejects dangerous and malformed URLs", () => {
  for (const dangerous of [
    "javascript:alert(1)",
    "  javascript:alert(document.cookie)  ",
    "JavaScript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox(1)",
    "",
    "   ",
    "not a url",
    "//evil.example.com",
    null,
    undefined
  ]) {
    assert.equal(safeHref(dangerous), null, `expected null for ${String(dangerous)}`);
  }
});

test("SourceLink renders an anchor for safe URLs", () => {
  const html = renderToStaticMarkup(
    <SourceLink url="https://github.com/qtwin-io/founderos-api">Open source</SourceLink>
  );

  assert.match(html, /href="https:\/\/github.com\/qtwin-io\/founderos-api"/);
  assert.match(html, /class="source-link"/);
  assert.match(html, /Open source/);
});

test("SourceLink never renders a javascript: href", () => {
  const html = renderToStaticMarkup(
    <SourceLink url="javascript:alert(document.cookie)">Open source</SourceLink>
  );

  assert.doesNotMatch(html, /href=/);
  assert.doesNotMatch(html, /javascript:/);
  assert.match(html, /source-link--unavailable/);
  // The label is still shown, just not as a clickable link.
  assert.match(html, /Open source/);
});

test("EvidenceDrawer does not render an executable href for an untrusted url", () => {
  const evidence: BriefingEvidenceRef = {
    kind: "github_issue",
    source: "canonical_source_record",
    ref: "qtwin-io/founderos-api#issue/42",
    url: "javascript:alert(document.cookie)"
  };

  const html = renderToStaticMarkup(<EvidenceDrawer evidence={evidence} />);

  assert.doesNotMatch(html, /href="javascript:/);
  assert.doesNotMatch(html, /javascript:alert/);
});

test("EvidenceDrawer renders a safe href for an http(s) url", () => {
  const evidence: BriefingEvidenceRef = {
    kind: "github_issue",
    source: "canonical_source_record",
    ref: "qtwin-io/founderos-api#issue/42",
    url: "https://github.com/qtwin-io/founderos-api/issues/42"
  };

  const html = renderToStaticMarkup(<EvidenceDrawer evidence={evidence} />);

  assert.match(html, /href="https:\/\/github.com\/qtwin-io\/founderos-api\/issues\/42"/);
});
