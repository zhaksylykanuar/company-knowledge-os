import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import GitHubPage from "../app/github/page";
import { M } from "../lib/messages";

test("GitHub page starts with one connection surface and reveals work only when ready", () => {
  const html = renderToStaticMarkup(<GitHubPage />);

  assert.ok(html.includes(M.githubPage.title));
  assert.ok(html.includes(M.githubPage.description));
  assert.ok(html.includes(M.githubProductConnect.loading));
  assert.match(html, /class="github-page"/);
  assert.match(html, /class="github-page__content"/);
  assert.match(html, /class="panel github-source github-source--state"/);
  assert.doesNotMatch(html, new RegExp(M.githubWork.title));
  assert.doesNotMatch(html, /github-command-center/);
  assert.doesNotMatch(html, /github-work-pulse/);
});
