import assert from "node:assert/strict";
import test from "node:test";

import nextConfig, { buildBrowserSecurityHeaders } from "../next.config.mjs";

test("applies browser security headers and proxies every health probe", async () => {
  const productionHeaders = buildBrowserSecurityHeaders(true);
  const byName = new Map(
    productionHeaders.map(({ key, value }) => [key.toLowerCase(), value])
  );

  assert.match(byName.get("content-security-policy"), /frame-ancestors 'none'/);
  assert.equal(byName.get("x-content-type-options"), "nosniff");
  assert.equal(byName.get("x-frame-options"), "DENY");
  assert.equal(
    byName.get("strict-transport-security"),
    "max-age=31536000; includeSubDomains"
  );

  const headerRules = await nextConfig.headers();
  assert.equal(headerRules[0].source, "/:path*");

  const rewrites = await nextConfig.rewrites();
  assert.ok(
    rewrites.some(({ source }) => source === "/health/:path*"),
    "readiness and operator metrics must use the same-origin proxy"
  );
});
