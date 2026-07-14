import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import GitHubPage from "../app/github/page";
import { M } from "../lib/messages";

test("GitHub page composes the command center and operational pulse", () => {
  const html = renderToStaticMarkup(<GitHubPage />);

  assert.ok(html.includes(M.githubPage.title));
  assert.ok(html.includes(M.githubPage.description));
  assert.ok(html.includes(M.githubProductConnect.title));
  assert.ok(html.includes(M.githubProductConnect.loading));
  assert.ok(html.includes(M.githubWork.title));
  assert.ok(html.includes(M.githubWork.loading));
  assert.match(html, /class="github-page"/);
  assert.match(html, /class="panel github-product-connect github-command-center"/);
  assert.match(html, /class="panel operational-work github-work-pulse"/);
  assert.doesNotMatch(html, /Поток бэкенда GitHub/);
  assert.doesNotMatch(html, /пока локальные заготовки MVP/);
});
