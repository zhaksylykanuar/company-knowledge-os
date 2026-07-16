import assert from "node:assert/strict";
import test from "node:test";

import { createRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  lockOverlayEnvironment,
  OverlayShell,
  resolveOverlayTabTarget
} from "../components/OverlayShell";

test("overlay shell renders labelled modal and drawer dialog contracts", () => {
  for (const mode of ["modal", "drawer"] as const) {
    const html = renderToStaticMarkup(
      <OverlayShell
        backgroundRef={createRef<HTMLElement>()}
        label="Основания решения"
        mode={mode}
        onClose={() => undefined}
      >
        <button type="button">Продолжить</button>
      </OverlayShell>
    );

    assert.match(html, /class="overlay-shell-backdrop"/);
    assert.match(html, new RegExp(`data-mode="${mode}"`));
    assert.match(
      html,
      new RegExp(`overlay-shell-dialog overlay-shell-dialog--${mode}`)
    );
    assert.match(html, /role="dialog"/);
    assert.match(html, /aria-modal="true"/);
    assert.match(html, /aria-labelledby="([^"]+)"/);
    assert.match(html, /<h2 id="([^"]+)">Основания решения<\/h2>/);
    assert.match(html, /aria-label="Закрыть"/);
    assert.match(html, /tabindex="-1"/);
    assert.match(html, />Продолжить<\/button>/);
  }
});

test("overlay environment locks and exactly restores background and body", () => {
  const attributes = new Map<string, string>([
    ["aria-hidden", "false"],
    ["inert", "previous"]
  ]);
  const background = {
    getAttribute: (name: string) => attributes.get(name) ?? null,
    removeAttribute: (name: string) => {
      attributes.delete(name);
    },
    setAttribute: (name: string, value: string) => {
      attributes.set(name, value);
    }
  };
  const body = { style: { overflow: "clip" } };

  const restore = lockOverlayEnvironment(background, body);
  assert.equal(body.style.overflow, "hidden");
  assert.equal(attributes.get("aria-hidden"), "true");
  assert.equal(attributes.get("inert"), "");

  restore();
  assert.equal(body.style.overflow, "clip");
  assert.equal(attributes.get("aria-hidden"), "false");
  assert.equal(attributes.get("inert"), "previous");
});

test("overlay environment removes attributes that were previously absent", () => {
  const attributes = new Map<string, string>();
  const background = {
    getAttribute: (name: string) => attributes.get(name) ?? null,
    removeAttribute: (name: string) => {
      attributes.delete(name);
    },
    setAttribute: (name: string, value: string) => {
      attributes.set(name, value);
    }
  };
  const body = { style: { overflow: "" } };

  const restore = lockOverlayEnvironment(background, body);
  restore();

  assert.equal(body.style.overflow, "");
  assert.equal(attributes.has("aria-hidden"), false);
  assert.equal(attributes.has("inert"), false);
});

test("overlay environment locks and restores every application background", () => {
  const first = new Map<string, string>();
  const second = new Map<string, string>([["aria-hidden", "false"]]);
  const target = (attributes: Map<string, string>) => ({
    getAttribute: (name: string) => attributes.get(name) ?? null,
    removeAttribute: (name: string) => {
      attributes.delete(name);
    },
    setAttribute: (name: string, value: string) => {
      attributes.set(name, value);
    }
  });
  const body = { style: { overflow: "visible" } };

  const restore = lockOverlayEnvironment(
    [target(first), target(second)],
    body
  );
  assert.equal(first.get("aria-hidden"), "true");
  assert.equal(first.get("inert"), "");
  assert.equal(second.get("aria-hidden"), "true");
  assert.equal(second.get("inert"), "");

  restore();
  assert.equal(body.style.overflow, "visible");
  assert.equal(first.has("aria-hidden"), false);
  assert.equal(first.has("inert"), false);
  assert.equal(second.get("aria-hidden"), "false");
  assert.equal(second.has("inert"), false);
});

test("Tab trap wraps at both boundaries and leaves middle focus untouched", () => {
  const first = { id: "first" };
  const middle = { id: "middle" };
  const last = { id: "last" };
  const focusable = [first, middle, last];

  assert.equal(resolveOverlayTabTarget(focusable, last, false), first);
  assert.equal(resolveOverlayTabTarget(focusable, first, true), last);
  assert.equal(resolveOverlayTabTarget(focusable, middle, false), undefined);
  assert.equal(resolveOverlayTabTarget(focusable, middle, true), undefined);
  assert.equal(resolveOverlayTabTarget(focusable, null, false), first);
  assert.equal(resolveOverlayTabTarget(focusable, null, true), last);
  assert.equal(resolveOverlayTabTarget([], null, false), null);
});
